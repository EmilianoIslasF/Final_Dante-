"""
Aplicación Streamlit para consumir el producto de datos de churn.

La app lee los outputs de la capa Gold desde Amazon S3 y permite al usuario:
- ver un resumen ejecutivo del riesgo de churn,
- filtrar clientes por nivel de riesgo, contrato y probabilidad,
- consultar un ranking de clientes con mayor riesgo,
- revisar el perfil individual de un cliente,
- visualizar métricas del modelo.

Inputs:
- Archivo Parquet con predicciones en S3 Gold.
- Archivo CSV con métricas del modelo en S3 Gold.
- Variables de entorno opcionales:
  CHURN_BUCKET, CHURN_PREDICTIONS_KEY y CHURN_METRICS_KEY.

Outputs:
- Dashboard web en Streamlit.
- Ranking filtrado descargable en CSV.
"""

from __future__ import annotations

import os
from io import BytesIO

import boto3
import pandas as pd
import plotly.express as px
import streamlit as st


BUCKET = os.getenv("CHURN_BUCKET", "churn-data-product-780191826160-2026")

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
    layout="wide",
)


@st.cache_data(show_spinner=True)
def read_parquet_from_s3(bucket: str, key: str) -> pd.DataFrame:
    """
    Lee un archivo Parquet desde Amazon S3.

    Inputs:
    - bucket: nombre del bucket S3.
    - key: ruta del archivo Parquet dentro del bucket.

    Output:
    - DataFrame con las predicciones de churn.
    """
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


@st.cache_data(show_spinner=True)
def read_csv_from_s3(bucket: str, key: str) -> pd.DataFrame:
    """
    Lee un archivo CSV desde Amazon S3.

    Inputs:
    - bucket: nombre del bucket S3.
    - key: ruta del archivo CSV dentro del bucket.

    Output:
    - DataFrame con las métricas del modelo.
    """
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(obj["Body"])


def format_percent(x: float) -> str:
    """
    Convierte un número entre 0 y 1 a formato porcentaje.

    Input:
    - x: valor numérico.

    Output:
    - String formateado como porcentaje.
    """
    return f"{100 * x:.1f}%"


def get_top_risk_factors(row: pd.Series) -> list[str]:
    """
    Genera factores de riesgo simples para un cliente.

    Input:
    - row: fila con información de un cliente.

    Output:
    - Lista de factores de riesgo interpretables.
    """
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


def apply_filters(
    df: pd.DataFrame,
    selected_risk: str,
    selected_contract: str,
    min_prob: float,
    max_prob: float,
) -> pd.DataFrame:
    """
    Aplica filtros seleccionados por el usuario.

    Inputs:
    - df: DataFrame de predicciones Gold.
    - selected_risk: nivel de riesgo seleccionado.
    - selected_contract: tipo de contrato seleccionado.
    - min_prob: probabilidad mínima de churn.
    - max_prob: probabilidad máxima de churn.

    Output:
    - DataFrame filtrado.
    """
    filtered = df.copy()

    if selected_risk != "Todos":
        filtered = filtered[filtered["risk_level"] == selected_risk]

    if selected_contract != "Todos":
        filtered = filtered[filtered["contract"] == selected_contract]

    filtered = filtered[
        (filtered["prob_churn"] >= min_prob)
        & (filtered["prob_churn"] <= max_prob)
    ]

    return filtered


def render_kpis(df: pd.DataFrame) -> None:
    """
    Muestra indicadores principales del dashboard.

    Input:
    - df: DataFrame completo de predicciones Gold.

    Output:
    - Métricas visuales en Streamlit.
    """
    total_clients = len(df)
    high_risk_clients = int((df["risk_level"] == "Alto").sum())
    avg_churn_prob = df["prob_churn"].mean()
    best_model = df["model_name"].iloc[0] if "model_name" in df.columns else "N/A"

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Clientes totales", f"{total_clients:,}")
    col2.metric("Clientes alto riesgo", f"{high_risk_clients:,}")
    col3.metric("Prob. promedio churn", format_percent(avg_churn_prob))
    col4.metric("Modelo usado", best_model)


def render_summary_tab(df: pd.DataFrame) -> None:
    """
    Muestra gráficas agregadas de riesgo.

    Input:
    - df: DataFrame completo de predicciones Gold.

    Output:
    - Gráficas y lectura rápida en Streamlit.
    """
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
        "Los clientes con contrato mes a mes concentran el mayor riesgo promedio "
        "de abandono. Esto permite al equipo de retención priorizar campañas o "
        "beneficios antes de que el cliente cancele."
    )


def render_ranking_tab(filtered: pd.DataFrame) -> None:
    """
    Muestra el ranking de clientes filtrados por riesgo.

    Input:
    - filtered: DataFrame filtrado según la selección del usuario.

    Output:
    - Tabla interactiva y botón de descarga CSV.
    """
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
    show_cols = [col for col in show_cols if col in filtered.columns]

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


def render_customer_tab(filtered: pd.DataFrame) -> None:
    """
    Permite consultar el perfil individual de un cliente.

    Input:
    - filtered: DataFrame filtrado según la selección del usuario.

    Output:
    - Métricas, perfil y factores de riesgo del cliente seleccionado.
    """
    st.subheader("Consulta individual de cliente")

    customer_ids = filtered["customer_id"].astype(str).tolist()

    if not customer_ids:
        st.warning("No hay clientes con los filtros seleccionados.")
        return

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
    profile_cols = [col for col in profile_cols if col in row.index]

    profile_df = pd.DataFrame(
        {
            "variable": profile_cols,
            "valor": [row[col] for col in profile_cols],
        }
    )
    st.dataframe(profile_df, use_container_width=True, hide_index=True)

    st.write("### Factores de riesgo simples")
    for factor in get_top_risk_factors(row):
        st.write(f"- {factor}")


def render_metrics_tab(metrics: pd.DataFrame) -> None:
    """
    Muestra métricas de evaluación del modelo.

    Input:
    - metrics: DataFrame con métricas de entrenamiento.

    Output:
    - Tabla de métricas y explicación del mejor modelo.
    """
    st.subheader("Métricas de entrenamiento")

    st.dataframe(metrics, use_container_width=True, hide_index=True)

    if "roc_auc" in metrics.columns:
        best = metrics.sort_values("roc_auc", ascending=False).iloc[0]
        st.info(
            f"El modelo seleccionado fue **{best['model_name']}**, "
            f"con ROC AUC de **{best['roc_auc']:.3f}**."
        )

    st.write(
        "Estas métricas se calculan con una partición de prueba y sirven para "
        "comparar qué tan bien el modelo separa clientes que abandonan y "
        "clientes que permanecen."
    )


def main() -> None:
    """
    Orquesta la aplicación:
    1. Lee predicciones y métricas desde S3 Gold.
    2. Crea filtros interactivos.
    3. Renderiza KPIs, gráficas, ranking, consulta individual y métricas.
    """
    st.title("Customer Churn Risk Dashboard")
    st.caption(
        "Producto de datos para priorizar clientes con mayor probabilidad de abandono."
    )

    try:
        df = read_parquet_from_s3(BUCKET, PREDICTIONS_KEY)
        metrics = read_csv_from_s3(BUCKET, METRICS_KEY)
    except Exception as error:
        st.error("No pude leer los datos desde S3.")
        st.write(
            "Revisa que las credenciales de AWS estén configuradas y que "
            "el bucket/key existan."
        )
        st.exception(error)
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

    filtered = apply_filters(
        df=df,
        selected_risk=selected_risk,
        selected_contract=selected_contract,
        min_prob=min_prob,
        max_prob=max_prob,
    )

    render_kpis(df)
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
        render_summary_tab(df)

    with tab2:
        render_ranking_tab(filtered)

    with tab3:
        render_customer_tab(filtered)

    with tab4:
        render_metrics_tab(metrics)


if __name__ == "__main__":
    main()
