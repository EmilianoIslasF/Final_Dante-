# Final_Dante-
Proyecto final: churn-data-product


Una app para que un área de retención vea qué clientes tienen más riesgo de abandonar el servicio. El usuario final puede consultar clientes, ver su probabilidad de churn, entender los factores de riesgo y priorizar a quién contactar primero.




los datos son de kaggle: 
https://www.kaggle.com/datasets/blastchar/telco-customer-churn/data

Está chiquito: aprox. 7043 clientes y 21 columnas.
La variable objetivo ya viene lista: Churn.
Sirve perfecto para clasificación: cliente se va / cliente no se va.
Tiene variables fáciles de explicar: contrato, antigüedad, cargos mensuales, método de pago, servicios contratados, etc.



El enlace para ejecución local 


http://192.168.0.17:8501



---

## Arquitectura general

El proyecto sigue una arquitectura tipo medallion en AWS:

```text
Kaggle Dataset
   ↓
S3 Bronze
   ↓
ETL / Preprocesamiento
   ↓
S3 Silver
   ↓
Entrenamiento y scoring del modelo
   ↓
S3 Gold
   ↓
Glue Data Catalog
   ↓
Athena
   ↓
Streamlit App
   ↓
Docker + ECR + ECS Fargate
   ↓
URL pública



Las capas principales son:

Bronze: contiene el archivo crudo descargado de Kaggle.
Silver: contiene los datos limpios y transformados.
Gold: contiene las predicciones de churn, niveles de riesgo y métricas del modelo.
´´´
Fuente de datos

El dataset utilizado es Telco Customer Churn de Kaggle.

Cada fila representa un cliente e incluye variables como:

tipo de contrato
antigüedad del cliente
cargos mensuales
cargos totales
servicios contratados
método de pago
variable objetivo Churn
