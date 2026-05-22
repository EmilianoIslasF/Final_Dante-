"""
Descarga el dataset Telco Customer Churn desde Kaggle y carga el CSV crudo
a la capa Bronze en Amazon S3.

Inputs:
- Credenciales de Kaggle configuradas como variables de entorno o en ~/.kaggle/kaggle.json.
- Credenciales de AWS configuradas en el ambiente.
- Nombre del bucket S3.
- Región de AWS.
- Ruta destino dentro del bucket.

Outputs:
- Archivo CSV crudo en S3 Bronze:
  s3://<bucket>/bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv

Ejemplo:
uv run python src/01_bronze_kaggle_to_s3.py \
  --bucket churn-data-product-780191826160-2026 \
  --region us-east-1
"""

from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


DATASET = "blastchar/telco-customer-churn"
CSV_NAME = "WA_Fn-UseC_-Telco-Customer-Churn.csv"


def create_bucket_if_needed(bucket: str, region: str) -> None:
    """
    Crea el bucket de S3 si no existe.

    Inputs:
    - bucket: nombre del bucket de S3.
    - region: región de AWS.

    Output:
    - Bucket creado en S3, si no existía previamente.
    """
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
    """
    Descarga y descomprime el dataset desde Kaggle.

    Input:
    - output_dir: carpeta local temporal donde se descargará el dataset.

    Output:
    - Ruta local del CSV descargado.
    """
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
    """
    Sube un archivo local a Amazon S3.

    Inputs:
    - local_file: ruta local del archivo a subir.
    - bucket: nombre del bucket S3.
    - key: ruta destino dentro del bucket.
    - region: región de AWS.

    Output:
    - Archivo cargado en S3.
    """
    s3 = boto3.client("s3", region_name=region)

    print(f"Subiendo {local_file}")
    print(f"a s3://{bucket}/{key}")

    s3.upload_file(str(local_file), bucket, key)

    print("Carga a Bronze terminada.")


def main() -> None:
    """
    Orquesta el proceso Bronze:
    1. Opcionalmente crea el bucket.
    2. Descarga el dataset desde Kaggle.
    3. Sube el CSV crudo a S3 Bronze.
    """
    parser = argparse.ArgumentParser(
        description="Descarga el dataset de Kaggle y lo sube a S3 Bronze."
    )

    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3.")
    parser.add_argument("--region", default="us-east-1", help="Región de AWS.")

    parser.add_argument(
        "--bronze-key",
        default=f"bronze/{CSV_NAME}",
        help="Ruta destino del CSV dentro del bucket.",
    )

    parser.add_argument(
        "--create-bucket",
        action="store_true",
        help="Crea el bucket si no existe.",
    )

    parser.add_argument(
        "--workdir",
        default="data/raw",
        help="Carpeta local temporal para descargar el dataset.",
    )

    args = parser.parse_args()

    if args.create_bucket:
        create_bucket_if_needed(args.bucket, args.region)

    workdir = Path(args.workdir)
    csv_path = download_from_kaggle(workdir)

    upload_to_s3(
        local_file=csv_path,
        bucket=args.bucket,
        key=args.bronze_key,
        region=args.region,
    )


if __name__ == "__main__":
    main()
