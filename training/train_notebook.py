# Databricks notebook source
# ruff: noqa: F821
# MAGIC %pip install "accelerate>=1.10.0" "datasets>=4.0.0" "databricks-sdk>=0.125.0" "hf_transfer==0.1.9" "mlflow==3.12.0" "openai==2.17.0" "opencv-python-headless==4.12.*" "peft>=0.18.0" "transformers==4.57.6" "trl>=0.20.0" "vllm==0.11.2" "flashinfer-cubin==0.5.2"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import runpy
import sys

dbutils.widgets.text("training_script", "")
dbutils.widgets.text("catalog", "serverless_lakebase_praneeth_catalog")
dbutils.widgets.text("schema", "trace_to_tune")
dbutils.widgets.text(
    "registered_model",
    "serverless_lakebase_praneeth_catalog.trace_to_tune.skill_router",
)
dbutils.widgets.text("max_steps", "40")

training_script = dbutils.widgets.get("training_script")
if not training_script:
    raise ValueError("training_script job parameter is required")

sys.argv = [
    training_script,
    "--catalog",
    dbutils.widgets.get("catalog"),
    "--schema",
    dbutils.widgets.get("schema"),
    "--registered-model",
    dbutils.widgets.get("registered_model"),
    "--max-steps",
    dbutils.widgets.get("max_steps"),
]
runpy.run_path(training_script, run_name="__main__")
