"""
Registra tablas externas de Athena/Glue para consultar las capas Silver y Gold.

Este script no mueve datos. Solo crea metadata en Glue Data Catalog para que
Athena pueda consultar archivos Parquet/CSV almacenados en S3.

Ejemplo:
uv run python src/04_register_athena_tables.py \
  --bucket churn-data-product-780191826160-2026 \
  --region us-east-1
"""

from __future__ import annotations

import argparse
import time

import boto3


def run_athena_query(
    query: str,
    database: str,
    output_location: str,
    region: str,
) -> None:
    """Ejecuta una consulta DDL en Athena y espera a que termine."""
    athena = boto3.client("athena", region_name=region)

    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output_location},
    )

    query_execution_id = response["QueryExecutionId"]

    while True:
        result = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = result["QueryExecution"]["Status"]["State"]

        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break

        time.sleep(2)

    if state != "SUCCEEDED":
        reason = result["QueryExecution"]["Status"].get("StateChangeReason", "")
        raise RuntimeError(f"Athena query failed: {state}. Reason: {reason}")

    print(f"Query succeeded: {query_execution_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--silver-db", default="churn_silver")
    parser.add_argument("--gold-db", default="churn_gold")
    parser.add_argument("--athena-results-prefix", default="athena-results")

    args = parser.parse_args()

    output_location = f"s3://{args.bucket}/{args.athena_results_prefix}/"

    queries = [
        (
            args.silver_db,
            f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {args.silver_db}.customers_clean (
              customer_id string,
              gender string,
              seniorcitizen int,
              partner int,
              dependents int,
              tenure int,
              phoneservice int,
              multiplelines string,
              internetservice string,
              onlinesecurity string,
              onlinebackup string,
              deviceprotection string,
              techsupport string,
              streamingtv string,
              streamingmovies string,
              contract string,
              paperlessbilling int,
              paymentmethod string,
              monthlycharges double,
              totalcharges double,
              churn int
            )
            STORED AS PARQUET
            LOCATION 's3://{args.bucket}/silver/';
            """,
        ),
        (
            args.gold_db,
            f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {args.gold_db}.churn_predictions (
              customer_id string,
              prob_churn double,
              prediction int,
              risk_level string,
              model_name string,
              contract string,
              tenure int,
              monthlycharges double,
              totalcharges double,
              internetservice string,
              paymentmethod string,
              seniorcitizen int,
              churn int
            )
            STORED AS PARQUET
            LOCATION 's3://{args.bucket}/gold/predictions/';
            """,
        ),
        (
            args.gold_db,
            f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {args.gold_db}.model_metrics (
              model_name string,
              accuracy double,
              precision double,
              recall double,
              f1 double,
              roc_auc double
            )
            ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
            WITH SERDEPROPERTIES (
              'separatorChar' = ',',
              'quoteChar' = '"'
            )
            LOCATION 's3://{args.bucket}/gold/metrics/'
            TBLPROPERTIES (
              'skip.header.line.count'='1'
            );
            """,
        ),
    ]

    for database, query in queries:
        print(f"Registering table in database: {database}")
        run_athena_query(
            query=query,
            database=database,
            output_location=output_location,
            region=args.region,
        )

    print("Athena/Glue tables registered successfully.")


if __name__ == "__main__":
    main()
