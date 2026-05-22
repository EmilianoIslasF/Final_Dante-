"""
Entrena modelos de churn y genera la capa Gold del producto de datos.

Inputs:
- Archivo Parquet limpio en S3 Silver.
- Nombre del bucket S3.
- Ruta destino para predicciones, métricas y modelo entrenado.

Outputs:
- Predicciones por cliente en S3 Gold:
  s3://<bucket>/gold/predictions/churn_predictions.parquet
- Métricas de modelos en S3 Gold:
  s3://<bucket>/gold/metrics/model_metrics.csv
- Modelo entrenado serializado:
  s3://<bucket>/gold/artifacts/churn_model.joblib

Ejemplo:
uv run python src/03_gold.py \
  --bucket churn-data-product-780191826160-2026 \
  --silver-key silver/customers_clean.parquet \
  --gold-prefix gold \
  --artifact-key gold/artifacts/churn_model.joblib
"""

from __future__ import annotations

import argparse
from io import BytesIO, StringIO

import boto3
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


TARGET = "churn"
ID_COL = "customer_id"


def read_parquet_from_s3(bucket: str, key: str) -> pd.DataFrame:
    """
    Lee un archivo Parquet desde Amazon S3.

    Inputs:
    - bucket: nombre del bucket S3.
    - key: ruta del archivo Parquet dentro del bucket.

    Output:
    - DataFrame con los datos Silver.
    """
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


def put_bytes_to_s3(data: bytes, bucket: str, key: str) -> None:
    """
    Sube contenido en bytes a Amazon S3.

    Inputs:
    - data: contenido serializado en bytes.
    - bucket: nombre del bucket S3.
    - key: ruta destino dentro del bucket.

    Output:
    - Objeto escrito en S3.
    """
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=data)


def write_df_csv_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    """
    Guarda un DataFrame como CSV en Amazon S3.

    Inputs:
    - df: DataFrame a guardar.
    - bucket: nombre del bucket S3.
    - key: ruta destino del CSV dentro del bucket.

    Output:
    - Archivo CSV escrito en S3.
    """
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    put_bytes_to_s3(buffer.getvalue().encode("utf-8"), bucket, key)


def write_df_parquet_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    """
    Guarda un DataFrame como Parquet en Amazon S3.

    Inputs:
    - df: DataFrame a guardar.
    - bucket: nombre del bucket S3.
    - key: ruta destino del Parquet dentro del bucket.

    Output:
    - Archivo Parquet escrito en S3.
    """
    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    put_bytes_to_s3(buffer.getvalue(), bucket, key)


def build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    """
    Construye el preprocesador para variables numéricas y categóricas.

    Input:
    - X: DataFrame de variables predictoras.

    Output:
    - ColumnTransformer con escalamiento para variables numéricas y
      one-hot encoding para variables categóricas.
    """
    numeric_features = X.select_dtypes(
        include=["int64", "float64", "int32", "float32"]
    ).columns.tolist()

    categorical_features = X.select_dtypes(
        include=["object", "category", "bool"]
    ).columns.tolist()

    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
        ]
    )


def train_models(df: pd.DataFrame):
    """
    Entrena modelos candidatos y selecciona el mejor según ROC AUC.

    Input:
    - df: DataFrame Silver con variables predictoras, customer_id y churn.

    Outputs:
    - Nombre del mejor modelo.
    - Pipeline entrenado del mejor modelo.
    - DataFrame con métricas de todos los modelos.
    """
    X = df.drop(columns=[TARGET, ID_COL])
    y = df[TARGET].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    models = {
        "logistic_regression": LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            random_state=42,
            class_weight="balanced",
            min_samples_leaf=5,
        ),
    }

    results = []
    trained_models = {}

    for model_name, estimator in models.items():
        print(f"Entrenando modelo: {model_name}")

        pipeline = Pipeline(
            steps=[
                ("preprocess", build_preprocessor(X_train)),
                ("model", estimator),
            ]
        )

        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        y_prob = pipeline.predict_proba(X_test)[:, 1]

        results.append(
            {
                "model_name": model_name,
                "accuracy": accuracy_score(y_test, y_pred),
                "precision": precision_score(y_test, y_pred, zero_division=0),
                "recall": recall_score(y_test, y_pred, zero_division=0),
                "f1": f1_score(y_test, y_pred, zero_division=0),
                "roc_auc": roc_auc_score(y_test, y_prob),
            }
        )

        trained_models[model_name] = pipeline

    metrics_df = pd.DataFrame(results).sort_values("roc_auc", ascending=False)
    best_model_name = metrics_df.iloc[0]["model_name"]
    best_model = trained_models[best_model_name]

    print("\nMétricas de modelos:")
    print(metrics_df)
    print(f"\nMejor modelo: {best_model_name}")

    return best_model_name, best_model, metrics_df


def make_predictions(df: pd.DataFrame, model, model_name: str) -> pd.DataFrame:
    """
    Genera predicciones, probabilidades de churn y niveles de riesgo.

    Inputs:
    - df: DataFrame Silver.
    - model: pipeline entrenado.
    - model_name: nombre del modelo seleccionado.

    Output:
    - DataFrame Gold con predicción, probabilidad de churn, nivel de riesgo
      y variables de contexto del cliente.
    """
    X = df.drop(columns=[TARGET, ID_COL])

    prob_churn = model.predict_proba(X)[:, 1]
    prediction = (prob_churn >= 0.5).astype(int)

    gold_df = pd.DataFrame(
        {
            "customer_id": df[ID_COL],
            "prob_churn": prob_churn,
            "prediction": prediction,
            "risk_level": pd.cut(
                prob_churn,
                bins=[-0.01, 0.40, 0.70, 1.01],
                labels=["Bajo", "Medio", "Alto"],
            ).astype(str),
            "model_name": model_name,
        }
    )

    context_cols = [
        "contract",
        "tenure",
        "monthlycharges",
        "totalcharges",
        "internetservice",
        "paymentmethod",
        "seniorcitizen",
        "churn",
    ]

    for col in context_cols:
        if col in df.columns:
            gold_df[col] = df[col]

    return gold_df.sort_values("prob_churn", ascending=False)


def save_model_to_s3(model, bucket: str, artifact_key: str) -> None:
    """
    Serializa el modelo entrenado y lo guarda en Amazon S3.

    Inputs:
    - model: pipeline entrenado.
    - bucket: nombre del bucket S3.
    - artifact_key: ruta destino del modelo dentro del bucket.

    Output:
    - Archivo joblib del modelo en S3.
    """
    buffer = BytesIO()
    joblib.dump(model, buffer)
    buffer.seek(0)
    put_bytes_to_s3(buffer.getvalue(), bucket, artifact_key)


def main() -> None:
    """
    Orquesta el proceso Gold:
    1. Lee los datos Silver desde S3.
    2. Entrena y compara modelos.
    3. Genera predicciones y niveles de riesgo.
    4. Guarda predicciones, métricas y modelo en S3 Gold.
    """
    parser = argparse.ArgumentParser(
        description="Entrena modelos de churn y genera la capa Gold en S3."
    )

    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3.")

    parser.add_argument(
        "--silver-key",
        default="silver/customers_clean.parquet",
        help="Ruta del archivo Parquet en S3 Silver.",
    )

    parser.add_argument(
        "--gold-prefix",
        default="gold",
        help="Prefijo base para guardar outputs Gold.",
    )

    parser.add_argument(
        "--artifact-key",
        default="gold/artifacts/churn_model.joblib",
        help="Ruta destino del modelo entrenado.",
    )

    args = parser.parse_args()

    print(f"Leyendo Silver: s3://{args.bucket}/{args.silver_key}")
    silver_df = read_parquet_from_s3(args.bucket, args.silver_key)

    best_model_name, best_model, metrics_df = train_models(silver_df)
    gold_df = make_predictions(silver_df, best_model, best_model_name)

    predictions_key = f"{args.gold_prefix}/predictions/churn_predictions.parquet"
    metrics_key = f"{args.gold_prefix}/metrics/model_metrics.csv"

    print(f"Guardando predicciones Gold: s3://{args.bucket}/{predictions_key}")
    write_df_parquet_to_s3(gold_df, args.bucket, predictions_key)

    print(f"Guardando métricas Gold: s3://{args.bucket}/{metrics_key}")
    write_df_csv_to_s3(metrics_df, args.bucket, metrics_key)

    print(f"Guardando modelo entrenado: s3://{args.bucket}/{args.artifact_key}")
    save_model_to_s3(best_model, args.bucket, args.artifact_key)

    print("Gold terminado correctamente.")


if __name__ == "__main__":
    main()
