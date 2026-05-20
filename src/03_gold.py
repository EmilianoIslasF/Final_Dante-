"""
Entrena modelos de churn y genera la capa gold con predicciones y métricas.

Ejemplo:
python src/03_gold.py \
  --bucket churn-project-itam \
  --silver-key silver/customers_clean.parquet \
  --gold-prefix gold \
  --artifact-key artifacts/churn_model.joblib
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path


import boto3
import joblib
import numpy as np
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
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


def put_bytes_to_s3(data: bytes, bucket: str, key: str) -> None:
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=data)


def write_df_csv_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    buffer = BytesIO()
    df.to_csv(buffer, index=False)
    put_bytes_to_s3(buffer.getvalue(), bucket, key)


def write_df_parquet_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    put_bytes_to_s3(buffer.getvalue(), bucket, key)


def build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    numeric_features = X.select_dtypes(include=["int64", "float64", "int32", "float32"]).columns.tolist()
    categorical_features = X.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
        ]
    )


def train_models(df: pd.DataFrame):
    X = df.drop(columns=[TARGET, ID_COL])
    y = df[TARGET].astype(int)

    X_train, X_test, y_train, y_test, ids_train, ids_test = train_test_split(
        X,
        y,
        df[ID_COL],
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    preprocessor = build_preprocessor(X_train)

    models = {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            random_state=42,
            class_weight="balanced",
            min_samples_leaf=5,
        ),
    }

    results = []
    trained = {}

    for name, estimator in models.items():
        pipe = Pipeline(
            steps=[
                ("preprocess", preprocessor),
                ("model", estimator),
            ]
        )

        print(f"Entrenando modelo: {name}")
        pipe.fit(X_train, y_train)

        y_pred = pipe.predict(X_test)
        y_prob = pipe.predict_proba(X_test)[:, 1]

        metrics = {
            "model_name": name,
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),
            "recall": recall_score(y_test, y_pred, zero_division=0),
            "f1": f1_score(y_test, y_pred, zero_division=0),
            "roc_auc": roc_auc_score(y_test, y_prob),
        }

        results.append(metrics)
        trained[name] = pipe

    metrics_df = pd.DataFrame(results).sort_values("roc_auc", ascending=False)
    best_model_name = metrics_df.iloc[0]["model_name"]
    best_model = trained[best_model_name]

    print("Métricas:")
    print(metrics_df)
    print(f"Mejor modelo: {best_model_name}")

    return best_model_name, best_model, metrics_df


def make_predictions(df: pd.DataFrame, model, model_name: str) -> pd.DataFrame:
    X = df.drop(columns=[TARGET, ID_COL])
    prob = model.predict_proba(X)[:, 1]
    pred = (prob >= 0.5).astype(int)

    gold = pd.DataFrame(
        {
            "customer_id": df[ID_COL],
            "prob_churn": prob,
            "prediction": pred,
            "risk_level": pd.cut(
                prob,
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
            gold[col] = df[col]

    gold = gold.sort_values("prob_churn", ascending=False)
    return gold


def save_model_to_s3(model, bucket: str, artifact_key: str) -> None:
    buffer = BytesIO()
    joblib.dump(model, buffer)
    buffer.seek(0)

    put_bytes_to_s3(buffer.getvalue(), bucket, artifact_key)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--silver-key", default="silver/customers_clean.parquet")
    parser.add_argument("--gold-prefix", default="gold")
    parser.add_argument("--artifact-key", default="artifacts/churn_model.joblib")

    args = parser.parse_args()

    print(f"Leyendo silver: s3://{args.bucket}/{args.silver_key}")
    df = read_parquet_from_s3(args.bucket, args.silver_key)

    best_model_name, best_model, metrics_df = train_models(df)

    gold_df = make_predictions(df, best_model, best_model_name)

    predictions_key = f"{args.gold_prefix}/churn_predictions.parquet"
    metrics_key = f"{args.gold_prefix}/model_metrics.csv"

    print(f"Guardando predicciones gold: s3://{args.bucket}/{predictions_key}")
    write_df_parquet_to_s3(gold_df, args.bucket, predictions_key)

    print(f"Guardando métricas gold: s3://{args.bucket}/{metrics_key}")
    write_df_csv_to_s3(metrics_df, args.bucket, metrics_key)

    print(f"Guardando modelo: s3://{args.bucket}/{args.artifact_key}")
    save_model_to_s3(best_model, args.bucket, args.artifact_key)

    print("Gold terminado.")


if __name__ == "__main__":
    main()
