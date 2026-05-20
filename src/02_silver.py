"""
Limpia el dataset crudo de churn y guarda la capa silver en S3 como Parquet.

Ejemplo:
python src/02_silver.py \
  --bucket churn-project-itam \
  --bronze-key bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv \
  --silver-key silver/customers_clean.parquet
"""

from __future__ import annotations

import argparse
from io import BytesIO

import boto3
import pandas as pd


def read_csv_from_s3(bucket: str, key: str) -> pd.DataFrame:
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(obj["Body"])


def write_parquet_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    s3 = boto3.client("s3")
    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())


def clean_telco_churn(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = (
        df.columns
        .str.strip()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.lower()
    )

    if "customerid" in df.columns:
        df = df.rename(columns={"customerid": "customer_id"})

    df["totalcharges"] = pd.to_numeric(df["totalcharges"], errors="coerce")

    df["totalcharges"] = df["totalcharges"].fillna(0)

    yes_no_cols = [
        "partner",
        "dependents",
        "phoneservice",
        "paperlessbilling",
        "churn",
    ]

    for col in yes_no_cols:
        if col in df.columns:
            df[col] = df[col].map({"Yes": 1, "No": 0}).astype("int64")

    if "gender" in df.columns:
        df["gender"] = df["gender"].str.lower()

    categorical_cols = df.select_dtypes(include=["object"]).columns.tolist()
    for col in categorical_cols:
        if col != "customer_id":
            df[col] = df[col].astype(str).str.strip()

    df = df.drop_duplicates(subset=["customer_id"])

    expected_cols = [
        "customer_id",
        "gender",
        "seniorcitizen",
        "partner",
        "dependents",
        "tenure",
        "phoneservice",
        "multiplelines",
        "internetservice",
        "onlinesecurity",
        "onlinebackup",
        "deviceprotection",
        "techsupport",
        "streamingtv",
        "streamingmovies",
        "contract",
        "paperlessbilling",
        "paymentmethod",
        "monthlycharges",
        "totalcharges",
        "churn",
    ]

    existing_cols = [col for col in expected_cols if col in df.columns]
    df = df[existing_cols]

    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument(
        "--bronze-key",
        default="bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv",
    )
    parser.add_argument(
        "--silver-key",
        default="silver/customers_clean.parquet",
    )

    args = parser.parse_args()

    print(f"Leyendo bronze: s3://{args.bucket}/{args.bronze_key}")
    raw = read_csv_from_s3(args.bucket, args.bronze_key)

    print("Limpiando datos...")
    clean = clean_telco_churn(raw)

    print(f"Filas silver: {len(clean)}")
    print(f"Columnas silver: {len(clean.columns)}")

    print(f"Guardando silver: s3://{args.bucket}/{args.silver_key}")
    write_parquet_to_s3(clean, args.bucket, args.silver_key)

    print("Silver terminado.")


if __name__ == "__main__":
    main()
