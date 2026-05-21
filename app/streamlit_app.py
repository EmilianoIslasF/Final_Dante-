import os
from io import BytesIO

import boto3
import pandas as pd
import streamlit as st
import plotly.express as px


BUCKET = os.getenv("CHURN_BUCKET", "itam-churn-317521775-2026")
PREDICTIONS_KEY = os.getenv(
    "CHURN_PREDICTIONS_KEY",
    "gold/predictions/churn_predictions.parquet",
)
METRICS_KEY = os.getenv(
    "CHURN_METRICS_KEY",
    "gold/metrics/model_metrics.csv",
)


st.set_page_config(
    page_title="Customer Churn Risk Dashboard",
    page_icon="📉",
    layout="wide",
)


@st.cache_data(show_spinner=True)
def read_parquet_from_s3(bucket: str, key: str) -> pd.DataFrame:
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


@st.cache_data(show_spinner=True)
def read_csv_from_s3(bucket: str, key: str) -> pd.DataFrame:
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(obj["Body"])


def format_percent(x: float) -> str:
    return f"{100 * x:.1f}%"


def get_top_risk_factors(row: pd.Series) -> list[str]:
    factors = []

    if str(row.get("contract", "")).lower() == "month-to-month":
        factors.append("Contrato mes a mes")

    if row.get("tenure", 999) <= 12:
        factors.append("Poca antigüedad")

    if row.get("monthlycharges", 0) >= 70:
        factors.append("Cargo mensual alto")

    if str(row.get("internetservice", "")).lower() == "fiber optic":
        factors.append("Servicio de fibra óptica")

    if str(row.get("paymentmethod", "")).lower() == "electronic check":
        factors.append("Pago con electronic check")

    if not factors:
        factors.append("Sin factores de riesgo simples destacados")

    return factors


def main():
    st.title("📉 Customer Churn Risk Dashboard")
    st.caption(
        "Producto de datos para priorizar clientes con mayor probabilidad de abandono."
    )

    try:
        df = read_parquet_from_s3(BUCKET, PREDICTIONS_KEY)
        metrics = read_csv_from_s3(BUCKET, METRICS_KEY)
    except Exception as e:
        st.error("No pude leer los datos desde S3.")
        st.write("Revisa que tus credenciales de AWS estén configuradas y que el bucket/key existan.")
        st.exception(e)
        return

    st.sidebar.header("Filtros")

    risk_options = ["Todos"] + sorted(df["risk_level"].dropna().unique().tolist())
    selected_risk = st.sidebar.selectbox("Nivel de riesgo", risk_options)

    contract_options = ["Todos"] + sorted(df["contract"].dropna().unique().tolist())
    selected_contract = st.sidebar.selectbox("Tipo de contrato", contract_options)

    min_prob, max_prob = st.sidebar.slider(
        "Rango de probabilidad de churn",
        min_value=0.0,
        max_value=1.0,
        value=(0.0, 1.0),
        step=0.01,
    )

    filtered = df.copy()

    if selected_risk != "Todos":
        filtered = filtered[filtered["risk_level"] == selected_risk]

    if selected_contract != "Todos":
        filtered = filtered[filtered["contract"] == selected_contract]

    filtered = filtered[
        (filtered["prob_churn"] >= min_prob)
        & (filtered["prob_churn"] <= max_prob)
    ]

    total_clients = len(df)
    high_risk_clients = int((df["risk_level"] == "Alto").sum())
    avg_churn_prob = df["prob_churn"].mean()
    best_model = df["model_name"].iloc[0] if "model_name" in df.columns else "N/A"

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Clientes totales", f"{total_clients:,}")
    col2.metric("Clientes alto riesgo", f"{high_risk_clients:,}")
    col3.metric("Prob. promedio churn", format_percent(avg_churn_prob))
    col4.metric("Modelo usado", best_model)

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "Resumen",
            "Ranking de clientes",
            "Consulta individual",
            "Métricas del modelo",
        ]
    )

    with tab1:
        st.subheader("Resumen de riesgo")

        c1, c2 = st.columns(2)

        risk_summary = (
            df.groupby("risk_level", as_index=False)
            .agg(clientes=("customer_id", "count"), prob_promedio=("prob_churn", "mean"))
            .sort_values("prob_promedio", ascending=False)
        )

        fig_risk = px.bar(
            risk_summary,
            x="risk_level",
            y="clientes",
            text="clientes",
            title="Clientes por nivel de riesgo",
            labels={"risk_level": "Nivel de riesgo", "clientes": "Clientes"},
        )
        c1.plotly_chart(fig_risk, use_container_width=True)

        contract_summary = (
            df.groupby("contract", as_index=False)
            .agg(clientes=("customer_id", "count"), riesgo_promedio=("prob_churn", "mean"))
            .sort_values("riesgo_promedio", ascending=False)
        )

        fig_contract = px.bar(
            contract_summary,
            x="contract",
            y="riesgo_promedio",
            text=contract_summary["riesgo_promedio"].map(lambda x: f"{x:.3f}"),
            title="Riesgo promedio por tipo de contrato",
            labels={"contract": "Contrato", "riesgo_promedio": "Riesgo promedio"},
        )
        c2.plotly_chart(fig_contract, use_container_width=True)

        st.subheader("Lectura rápida")
        st.write(
            "Los clientes con contrato mes a mes concentran el mayor riesgo promedio de abandono. "
            "Esto permite al equipo de retención priorizar campañas o beneficios antes de que el cliente cancele."
        )

    with tab2:
        st.subheader("Ranking de clientes con mayor riesgo")

        show_cols = [
            "customer_id",
            "prob_churn",
            "risk_level",
            "contract",
            "tenure",
            "monthlycharges",
            "internetservice",
            "paymentmethod",
            "churn",
        ]
        show_cols = [c for c in show_cols if c in filtered.columns]

        ranking = filtered.sort_values("prob_churn", ascending=False)[show_cols].copy()

        if "prob_churn" in ranking.columns:
            ranking["prob_churn"] = ranking["prob_churn"].map(lambda x: round(x, 4))

        st.dataframe(ranking, use_container_width=True, hide_index=True)

        csv = ranking.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar ranking filtrado",
            data=csv,
            file_name="ranking_clientes_churn.csv",
            mime="text/csv",
        )

    with tab3:
        st.subheader("Consulta individual de cliente")

        customer_ids = filtered["customer_id"].astype(str).tolist()

        if not customer_ids:
            st.warning("No hay clientes con los filtros seleccionados.")
        else:
            selected_customer = st.selectbox("Selecciona un cliente", customer_ids)
            row = filtered[filtered["customer_id"].astype(str) == selected_customer].iloc[0]

            c1, c2, c3 = st.columns(3)

            c1.metric("Probabilidad de churn", format_percent(row["prob_churn"]))
            c2.metric("Nivel de riesgo", row["risk_level"])
            c3.metric("Contrato", row.get("contract", "N/A"))

            st.write("### Perfil del cliente")

            profile_cols = [
                "customer_id",
                "tenure",
                "monthlycharges",
                "totalcharges",
                "internetservice",
                "paymentmethod",
                "churn",
            ]
            profile_cols = [c for c in profile_cols if c in row.index]

            profile_df = pd.DataFrame(
                {
                    "variable": profile_cols,
                    "valor": [row[c] for c in profile_cols],
                }
            )
            st.dataframe(profile_df, use_container_width=True, hide_index=True)

            st.write("### Factores de riesgo simples")
            for factor in get_top_risk_factors(row):
                st.write(f"- {factor}")

    with tab4:
        st.subheader("Métricas de entrenamiento")

        st.dataframe(metrics, use_container_width=True, hide_index=True)

        if "roc_auc" in metrics.columns:
            best = metrics.sort_values("roc_auc", ascending=False).iloc[0]
            st.info(
                f"El modelo seleccionado fue **{best['model_name']}**, "
                f"con ROC AUC de **{best['roc_auc']:.3f}**."
            )

        st.write(
            "Estas métricas se calculan con una partición de prueba y sirven para comparar "
            "qué tan bien el modelo separa clientes que abandonan y clientes que permanecen."
        )


if __name__ == "__main__":
    main()
