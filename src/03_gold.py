"""
Entrena modelos de churn y genera la capa Gold del producto de datos.

Este módulo:
1. Lee la capa Silver desde S3.
2. Entrena modelos de clasificación para predecir churn.
3. Selecciona el mejor modelo por ROC AUC.
4. Genera predicciones, niveles de riesgo y métricas.
5. Guarda outputs en S3 para consumo de Streamlit.

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
    """Read a Parquet file from S3 and return it as a pandas DataFrame."""
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


def put_bytes_to_s3(data: bytes, bucket: str, key: str) -> None:
    """Upload bytes to an S3 object."""
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=data)


def write_df_csv_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    """Write a DataFrame as CSV to S3."""
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    put_bytes_to_s3(buffer.getvalue().encode("utf-8"), bucket, key)


def write_df_parquet_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    """Write a DataFrame as Parquet to S3."""
    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    put_bytes_to_s3(buffer.getvalue(), bucket, key)


def build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    """Create preprocessing pipeline for numeric and categorical variables."""
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
    """Train candidate models and select the best one by ROC AUC."""
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
    """Generate churn probabilities, binary predictions and risk levels."""
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
    """Serialize trained model and upload it to S3."""
    buffer = BytesIO()
    joblib.dump(model, buffer)
    buffer.seek(0)
    put_bytes_to_s3(buffer.getvalue(), bucket, artifact_key)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--silver-key", default="silver/customers_clean.parquet")
    parser.add_argument("--gold-prefix", default="gold")
    parser.add_argument(
        "--artifact-key",
        default="gold/artifacts/churn_model.joblib",
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
