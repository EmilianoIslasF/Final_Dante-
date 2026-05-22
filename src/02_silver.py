"""
Limpia el dataset crudo de churn y guarda la capa Silver en Amazon S3 como Parquet.

Inputs:
- Archivo CSV crudo en S3 Bronze.
- Nombre del bucket S3.
- Ruta del archivo Bronze.
- Ruta destino para el archivo Silver.

Outputs:
- Archivo Parquet limpio en S3 Silver:
  s3://<bucket>/silver/customers_clean.parquet

Ejemplo:
uv run python src/02_silver.py \
  --bucket churn-data-product-780191826160-2026 \
  --bronze-key bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv \
  --silver-key silver/customers_clean.parquet
"""

from __future__ import annotations

import argparse
from io import BytesIO

import boto3
import pandas as pd


def read_csv_from_s3(bucket: str, key: str) -> pd.DataFrame:
    """
    Lee un archivo CSV desde Amazon S3.

    Inputs:
    - bucket: nombre del bucket S3.
    - key: ruta del archivo CSV dentro del bucket.

    Output:
    - DataFrame con los datos crudos.
    """
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(obj["Body"])


def write_parquet_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    """
    Guarda un DataFrame como archivo Parquet en Amazon S3.

    Inputs:
    - df: DataFrame a guardar.
    - bucket: nombre del bucket S3.
    - key: ruta destino del archivo Parquet dentro del bucket.

    Output:
    - Archivo Parquet escrito en S3.
    """
    s3 = boto3.client("s3")

    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)

    s3.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())


def clean_telco_churn(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia y transforma el dataset Telco Customer Churn.

    Input:
    - df: DataFrame crudo leído desde Bronze.

    Output:
    - DataFrame limpio con nombres de columnas normalizados,
      variables convertidas y registros duplicados eliminados.
    """
    df = df.copy()

    # Normaliza nombres de columnas para facilitar el procesamiento.
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
    """
    Orquesta el proceso Silver:
    1. Lee el CSV crudo desde S3 Bronze.
    2. Limpia y transforma los datos.
    3. Guarda el resultado como Parquet en S3 Silver.
    """
    parser = argparse.ArgumentParser(
        description="Limpia el dataset Bronze y genera la capa Silver en S3."
    )

    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3.")

    parser.add_argument(
        "--bronze-key",
        default="bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv",
        help="Ruta del archivo CSV crudo en S3 Bronze.",
    )

    parser.add_argument(
        "--silver-key",
        default="silver/customers_clean.parquet",
        help="Ruta destino del archivo Parquet en S3 Silver.",
    )

    args = parser.parse_args()

    print(f"Leyendo Bronze: s3://{args.bucket}/{args.bronze_key}")
    raw_df = read_csv_from_s3(args.bucket, args.bronze_key)

    print("Limpiando datos...")
    clean_df = clean_telco_churn(raw_df)

    print(f"Filas Silver: {len(clean_df)}")
    print(f"Columnas Silver: {len(clean_df.columns)}")

    print(f"Guardando Silver: s3://{args.bucket}/{args.silver_key}")
    write_parquet_to_s3(clean_df, args.bucket, args.silver_key)

    print("Silver terminado correctamente.")


if __name__ == "__main__":
    main()
