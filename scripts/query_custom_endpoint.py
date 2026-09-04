from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from openai import OpenAI

from trace_to_tune.dataset import SYSTEM_PROMPT, generate_trace_rows
from trace_to_tune.evaluate import parse_skill


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fe-vm-lakebase-praneeth")
    parser.add_argument("--endpoint", default="trace-to-tune-skill-router")
    parser.add_argument("--output", default="outputs/runtime/custom-endpoint-results.json")
    args = parser.parse_args()

    workspace = WorkspaceClient(profile=args.profile)
    token = workspace.config.authenticate()["Authorization"].removeprefix("Bearer ")
    client = OpenAI(
        api_key=token,
        base_url=f"{workspace.config.host}/serving-endpoints",
    )
    evaluation_rows = [row for row in generate_trace_rows() if row["split"] == "eval"]
    results = []
    for row in evaluation_rows:
        prompt = str(row["prompt"])
        response = client.chat.completions.create(
            model=args.endpoint,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=96,
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        predicted = parse_skill(content)
        results.append(
            {
                "prompt": prompt,
                "expected_skill": row["skill_name"],
                "predicted_skill": predicted,
                "correct": predicted == row["skill_name"],
                "response": content,
                "model": response.model,
            }
        )

    correct = sum(result["correct"] for result in results)
    output = {
        "endpoint": args.endpoint,
        "accuracy": correct / len(results),
        "correct": correct,
        "total": len(results),
        "results": results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
