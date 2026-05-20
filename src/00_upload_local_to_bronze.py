import argparse
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def create_bucket_if_needed(bucket: str, region: str) -> None:
    s3 = boto3.client("s3", region_name=region)

    try:
        s3.head_bucket(Bucket=bucket)
        print(f"Bucket ya existe o ya tienes acceso: s3://{bucket}")
        return
    except ClientError:
        print(f"Creando bucket: s3://{bucket}")

    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket)
    else:
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--local-file",
        default="data/raw/WA_Fn-UseC_-Telco-Customer-Churn.csv",
    )
    parser.add_argument(
        "--bronze-key",
        default="bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv",
    )
    parser.add_argument("--create-bucket", action="store_true")

    args = parser.parse_args()

    local_file = Path(args.local_file)

    if not local_file.exists():
        raise FileNotFoundError(f"No existe el archivo: {local_file}")

    if args.create_bucket:
        create_bucket_if_needed(args.bucket, args.region)

    s3 = boto3.client("s3", region_name=args.region)

    print(f"Subiendo {local_file}")
    print(f"a s3://{args.bucket}/{args.bronze_key}")

    s3.upload_file(str(local_file), args.bucket, args.bronze_key)

    print("Listo. Bronze quedó cargado en S3.")


if __name__ == "__main__":
    main()