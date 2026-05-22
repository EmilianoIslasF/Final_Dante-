"""
Registra tablas externas de Athena/Glue para consultar las capas Silver y Gold.

Este script no mueve datos. Solo crea metadata en Glue Data Catalog para que
Athena pueda consultar archivos Parquet/CSV almacenados en Amazon S3.

Inputs:
- Bucket S3 donde viven las capas Silver y Gold.
- Región de AWS.
- Nombres de las bases de datos Glue/Athena.
- Prefijo de S3 para guardar resultados temporales de Athena.

Outputs:
- Base de datos churn_silver en Glue/Athena, si no existe.
- Base de datos churn_gold en Glue/Athena, si no existe.
- Tabla externa churn_silver.customers_clean.
- Tabla externa churn_gold.churn_predictions.
- Tabla externa churn_gold.model_metrics.

Ejemplo:
uv run python src/04_register_athena_tables.py \
  --bucket churn-data-product-780191826160-2026 \
  --region us-east-1
"""

from __future__ import annotations

import argparse
import time

import boto3
from botocore.exceptions import ClientError


def ensure_glue_database(database: str, region: str) -> None:
    """
    Crea una base de datos en Glue Data Catalog si no existe.

    Inputs:
    - database: nombre de la base de datos Glue/Athena.
    - region: región de AWS.

    Output:
    - Base de datos disponible en Glue Data Catalog.
    """
    glue = boto3.client("glue", region_name=region)

    try:
        glue.get_database(Name=database)
        print(f"Database ya existe: {database}")
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")

        if error_code != "EntityNotFoundException":
            raise

        print(f"Creando database: {database}")
        glue.create_database(
            DatabaseInput={
                "Name": database,
                "Description": "Database for churn data product tables.",
            }
        )


def run_athena_query(
    query: str,
    database: str,
    output_location: str,
    region: str,
) -> None:
    """
    Ejecuta una consulta DDL en Athena y espera a que termine.

    Inputs:
    - query: sentencia SQL a ejecutar.
    - database: base de datos donde se ejecuta la consulta.
    - output_location: ruta S3 donde Athena guarda resultados temporales.
    - region: región de AWS.

    Output:
    - Consulta ejecutada correctamente en Athena.
    """
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


def build_table_queries(bucket: str, silver_db: str, gold_db: str) -> list[tuple[str, str]]:
    """
    Construye las sentencias SQL para registrar tablas externas.

    Inputs:
    - bucket: bucket S3 donde viven las capas Silver y Gold.
    - silver_db: nombre de la base de datos Silver.
    - gold_db: nombre de la base de datos Gold.

    Output:
    - Lista de tuplas con database y query SQL.
    """
    return [
        (
            silver_db,
            f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {silver_db}.customers_clean (
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
            LOCATION 's3://{bucket}/silver/';
            """,
        ),
        (
            gold_db,
            f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {gold_db}.churn_predictions (
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
            LOCATION 's3://{bucket}/gold/predictions/';
            """,
        ),
        (
            gold_db,
            f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {gold_db}.model_metrics (
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
            LOCATION 's3://{bucket}/gold/metrics/'
            TBLPROPERTIES (
              'skip.header.line.count'='1'
            );
            """,
        ),
    ]


def main() -> None:
    """
    Orquesta el registro de tablas:
    1. Asegura que existan las bases Glue/Athena.
    2. Construye el DDL para Silver y Gold.
    3. Ejecuta las consultas en Athena.
    """
    parser = argparse.ArgumentParser(
        description="Registra tablas externas de Silver y Gold en Athena/Glue."
    )

    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3.")
    parser.add_argument("--region", default="us-east-1", help="Región de AWS.")

    parser.add_argument(
        "--silver-db",
        default="churn_silver",
        help="Nombre de la base de datos Silver.",
    )

    parser.add_argument(
        "--gold-db",
        default="churn_gold",
        help="Nombre de la base de datos Gold.",
    )

    parser.add_argument(
        "--athena-results-prefix",
        default="athena-results",
        help="Prefijo S3 donde Athena guarda resultados temporales.",
    )

    args = parser.parse_args()

    output_location = f"s3://{args.bucket}/{args.athena_results_prefix}/"

    ensure_glue_database(args.silver_db, args.region)
    ensure_glue_database(args.gold_db, args.region)

    queries = build_table_queries(
        bucket=args.bucket,
        silver_db=args.silver_db,
        gold_db=args.gold_db,
    )

    for database, query in queries:
        print(f"Registrando tabla en database: {database}")
        run_athena_query(
            query=query,
            database=database,
            output_location=output_location,
            region=args.region,
        )

    print("Tablas Athena/Glue registradas correctamente.")


if __name__ == "__main__":
    main()
