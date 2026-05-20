"""
Descarga el dataset Telco Customer Churn de Kaggle y sube el CSV crudo a S3 bronze.

Requisitos:
- Tener credenciales de AWS configuradas.
- Tener credenciales de Kaggle configuradas con variables:
  KAGGLE_USERNAME y KAGGLE_KEY
  o con el archivo ~/.kaggle/kaggle.json

Ejemplo:
python src/01_bronze_kaggle_to_s3.py \
  --bucket churn-project-itam \
  --region us-east-1 \
  --create-bucket
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


DATASET = "blastchar/telco-customer-churn"
CSV_NAME = "WA_Fn-UseC_-Telco-Customer-Churn.csv"


def create_bucket_if_needed(bucket: str, region: str) -> None:
    s3 = boto3.client("s3", region_name=region)

    try:
        s3.head_bucket(Bucket=bucket)
        print(f"Bucket ya existe o ya tienes acceso: s3://{bucket}")
        return
    except ClientError:
        print(f"Bucket no encontrado. Creando: s3://{bucket}")

    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket)
    else:
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )

    print(f"Bucket creado: s3://{bucket}")


def download_from_kaggle(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "kaggle",
        "datasets",
        "download",
        "-d",
        DATASET,
        "-p",
        str(output_dir),
        "--force",
    ]

    print("Descargando dataset desde Kaggle...")
    subprocess.run(cmd, check=True)

    zip_files = list(output_dir.glob("*.zip"))
    if not zip_files:
        raise FileNotFoundError("No se encontró el ZIP descargado desde Kaggle.")

    zip_path = zip_files[0]
    print(f"Extrayendo: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir)

    csv_path = output_dir / CSV_NAME
    if not csv_path.exists():
        candidates = list(output_dir.glob("*.csv"))
        if not candidates:
            raise FileNotFoundError("No se encontró ningún CSV en el dataset.")
        csv_path = candidates[0]

    print(f"CSV encontrado: {csv_path}")
    return csv_path


def upload_to_s3(local_file: Path, bucket: str, key: str, region: str) -> None:
    s3 = boto3.client("s3", region_name=region)
    print(f"Subiendo a s3://{bucket}/{key}")
    s3.upload_file(str(local_file), bucket, key)
    print("Carga a bronze terminada.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3.")
    parser.add_argument("--region", default="us-east-1", help="Región AWS.")
    parser.add_argument(
        "--bronze-key",
        default=f"bronze/{CSV_NAME}",
        help="Ruta destino dentro del bucket.",
    )
    parser.add_argument(
        "--create-bucket",
        action="store_true",
        help="Crea el bucket si no existe.",
    )
    parser.add_argument(
        "--workdir",
        default="data/raw",
        help="Carpeta local temporal para descargar el CSV.",
    )

    args = parser.parse_args()

    if args.create_bucket:
        create_bucket_if_needed(args.bucket, args.region)

    workdir = Path(args.workdir)
    csv_path = download_from_kaggle(workdir)
    upload_to_s3(csv_path, args.bucket, args.bronze_key, args.region)


if __name__ == "__main__":
    main()
