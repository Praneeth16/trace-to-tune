# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "accelerate>=1.10.0",
#   "datasets>=4.0.0",
#   "databricks-sdk>=0.125.0",
#   "hf_transfer==0.1.9",
#   "mlflow==3.12.0",
#   "openai==2.17.0",
#   "opencv-python-headless==4.12.*",
#   "peft>=0.18.0",
#   "torch>=2.7.0",
#   "transformers==4.57.6",
#   "trl>=0.20.0",
#   "vllm==0.11.2",
#   "flashinfer-cubin==0.5.2",
# ]
# ///
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

# AI Runtime may enable the optional transfer backend without installing its package.
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

import mlflow
import torch
from databricks.sdk import WorkspaceClient
from datasets import Dataset
from mlflow.pyfunc.model import ChatCompletionResponse, ChatModel
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

SYSTEM_PROMPT = (
    "Choose exactly one governed skill for the support request. "
    "Return JSON only with keys skill and reason. Never repeat personal data."
)


class LLMModel(ChatModel):
    def predict(self, context, messages, params):
        return ChatCompletionResponse.from_dict({"choices": []})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--registered-model", required=True)
    parser.add_argument("--model-id", default="HuggingFaceTB/SmolLM2-360M-Instruct")
    parser.add_argument("--max-steps", type=int, required=True)
    return parser.parse_args()


def training_rows(
    workspace: WorkspaceClient, catalog: str, schema: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    warehouse = next(
        warehouse
        for warehouse in workspace.warehouses.list()
        if warehouse.enable_serverless_compute
    )
    response = workspace.statement_execution.execute_statement(
        warehouse_id=warehouse.id,
        statement=f"""
          SELECT prompt, completion, skill_name, split
          FROM {catalog}.{schema}.curated_traces
          WHERE approved = true AND policy_decision = 'ALLOW'
          ORDER BY trace_id
        """,
        wait_timeout="50s",
    )
    if response.status and response.status.error:
        raise RuntimeError(response.status.error.message)
    data = response.result.data_array if response.result and response.result.data_array else []
    rows = [
        {"prompt": row[0], "completion": row[1], "skill": row[2], "split": row[3]} for row in data
    ]
    train_rows = [
        {key: value for key, value in row.items() if key != "split"}
        for row in rows
        if row["split"] == "train"
    ]
    eval_rows = [
        {key: value for key, value in row.items() if key != "split"}
        for row in rows
        if row["split"] == "eval"
    ]
    if not train_rows or not eval_rows:
        raise RuntimeError("Curated trace table must contain approved train and eval rows")
    return train_rows, eval_rows


def render(row: dict[str, str]) -> dict[str, object]:
    return {
        "prompt": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": row["prompt"]},
        ],
        "completion": [{"role": "assistant", "content": row["completion"]}],
        "skill": row["skill"],
    }


def predict_text(model, tokenizer, prompt: str) -> str:
    model.eval()
    model.config.use_cache = True
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    inputs = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt"
    ).to(model.device)
    with torch.no_grad():
        output = model.generate(inputs, max_new_tokens=64, do_sample=False)
    return tokenizer.decode(output[0][inputs.shape[-1] :], skip_special_tokens=True)


def predict_skill(text: str, allowed_skills: set[str]) -> str:
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if not match:
        return "unparseable"
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return "unparseable"
    skill = value.get("skill")
    return skill if isinstance(skill, str) and skill in allowed_skills else "unparseable"


def evaluate(model, tokenizer, rows: list[dict[str, str]]) -> tuple[float, list[dict[str, object]]]:
    predictions = []
    allowed_skills = {row["skill"] for row in rows}
    for row in rows:
        response = predict_text(model, tokenizer, row["prompt"])
        prediction = predict_skill(response, allowed_skills)
        predictions.append(
            {
                "prompt": row["prompt"],
                "expected_skill": row["skill"],
                "predicted_skill": prediction,
                "response": response,
                "correct": prediction == row["skill"],
            }
        )
    correct = sum(bool(prediction["correct"]) for prediction in predictions)
    return correct / len(rows), predictions


def main() -> None:
    args = parse_args()
    workspace = WorkspaceClient()
    train_rows, eval_rows = training_rows(workspace, args.catalog, args.schema)
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(args.model_id, torch_dtype=dtype)
    if torch.cuda.is_available():
        model = model.cuda()
    baseline_accuracy, baseline_predictions = evaluate(model, tokenizer, eval_rows)

    dataset = Dataset.from_list([render(row) for row in train_rows])
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
            task_type="CAUSAL_LM",
        ),
        args=SFTConfig(
            output_dir="/tmp/trace-to-tune-checkpoints",
            max_length=512,
            max_steps=args.max_steps,
            per_device_train_batch_size=4,
            gradient_accumulation_steps=2,
            learning_rate=5e-4,
            logging_steps=10,
            save_strategy="no",
            report_to="mlflow",
            bf16=torch.cuda.is_available(),
            completion_only_loss=True,
        ),
    )

    mlflow.set_registry_uri("databricks-uc")
    with mlflow.start_run(run_name="trace-to-tune-smollm2-lora") as run:
        trainer.train()
        merged_model = trainer.model.merge_and_unload()
        tuned_accuracy, tuned_predictions = evaluate(merged_model, tokenizer, eval_rows)
        mlflow.log_metrics(
            {
                "baseline_skill_accuracy": baseline_accuracy,
                "tuned_skill_accuracy": tuned_accuracy,
                "accuracy_delta": tuned_accuracy - baseline_accuracy,
                "train_examples": len(train_rows),
                "eval_examples": len(eval_rows),
            }
        )
        mlflow.log_dict(
            {"baseline": baseline_predictions, "tuned": tuned_predictions},
            "evaluation/predictions.json",
        )

        work_dir = Path(tempfile.mkdtemp(prefix="trace-to-tune-"))
        merged_dir = work_dir / "skill-router"
        merged_model.save_pretrained(merged_dir, safe_serialization=True)
        tokenizer.save_pretrained(merged_dir)

        metadata = {
            "task": "llm/v1/chat",
            "entrypoint": (
                "python -u -m vllm.entrypoints.openai.api_server "
                "--model skill-router --served-model-name trace-to-tune "
                "--host 0.0.0.0 --port 8080 --dtype float16 "
                "--max-model-len 2048 --gpu-memory-utilization 0.70"
            ),
        }
        model_info = mlflow.pyfunc.log_model(
            name="skill-router",
            python_model=LLMModel(),
            artifacts={"model_dir": str(merged_dir)},
            metadata=metadata,
            extra_pip_requirements=["mlflow==3.12.0"],
        )
        model_version = mlflow.register_model(
            model_info.model_uri,
            args.registered_model,
            env_pack="databricks_model_serving",
        )
        result = {
            "run_id": run.info.run_id,
            "registered_model": args.registered_model,
            "model_version": model_version.version,
            "baseline_skill_accuracy": baseline_accuracy,
            "tuned_skill_accuracy": tuned_accuracy,
            "accuracy_delta": tuned_accuracy - baseline_accuracy,
        }
        result_path = Path(f"/Volumes/{args.catalog}/{args.schema}/artifacts/latest_result.json")
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        print("TRACE_TO_TUNE_RESULT=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
