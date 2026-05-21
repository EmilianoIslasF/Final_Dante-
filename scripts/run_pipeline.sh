#!/usr/bin/env bash
set -euo pipefail

BUCKET="${CHURN_BUCKET:-itam-churn-317521775-2026}"
REGION="${AWS_REGION:-us-east-1}"

echo "Using bucket: s3://${BUCKET}"
echo "Using region: ${REGION}"

echo "Step 1/3 - Bronze: Kaggle to S3"
uv run python src/01_bronze_kaggle_to_s3.py \
  --bucket "${BUCKET}" \
  --region "${REGION}" \
  --bronze-key "bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv"

echo "Step 2/3 - Silver: clean raw data"
uv run python src/02_silver.py \
  --bucket "${BUCKET}" \
  --bronze-key "bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv" \
  --silver-key "silver/customers_clean.parquet"

echo "Step 3/3 - Gold: train model and score customers"
uv run python src/03_gold.py \
  --bucket "${BUCKET}" \
  --silver-key "silver/customers_clean.parquet" \
  --gold-prefix "gold" \
  --artifact-key "gold/artifacts/churn_model.joblib"

echo "Pipeline finished successfully."
