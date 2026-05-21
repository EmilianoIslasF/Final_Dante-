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
```
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

Estructura del Repositorio 
```text

churn_data_product_starter/
│
├── app/
│   └── streamlit_app.py
│
├── data/
│   ├── sample/
│   │   └── WA_Fn-UseC_-Telco-Customer-Churn.csv
│
├── src/
│   ├── 01_bronze_kaggle_to_s3.py
│   ├── 02_silver.py
│   └── 03_gold.py
│
├── sql/
│   └── create_athena_tables.sql
│
├── Dockerfile
├── requirements.txt
└── README.md


```


Componentes principales:
src/00_upload_local_to_bronze.py

Carga el archivo CSV crudo a Amazon S3 en la capa bronze.




src/02_silver.py

Limpia y transforma los datos crudos.

Este script realiza tareas como:

limpieza de nombres de columnas
conversión de TotalCharges a numérico
codificación de Churn como 0/1
eliminación de duplicados
generación de archivo Parquet




src/03_gold.py

Entrena modelos de clasificación para predecir churn.

Modelos utilizados:

Logistic Regression
Random Forest

Métricas generadas:

Accuracy
Precision
Recall
F1
ROC AUC




sql/create_athena_tables.sql

Contiene las sentencias SQL para crear las tablas externas en Athena usando los datos almacenados en S3.



app/streamlit_app.py

Aplicación web para consumir los resultados del producto de datos.

La app permite:

visualizar resumen ejecutivo
filtrar clientes por nivel de riesgo
consultar clientes con mayor probabilidad de churn
revisar información individual de clientes
visualizar métricas del modelo



Despliegue

La aplicación se empaqueta en una imagen Docker. Después, la imagen se publica en Amazon ECR y se ejecuta en ECS Fargate. El servicio se expone mediante un Application Load Balancer para que el usuario final pueda acceder a una URL pública.





Resultado del modelo

El modelo seleccionado fue Logistic Regression, ya que obtuvo el mejor desempeño según ROC AUC.

Métricas principales:
```text
Accuracy: 0.750
Precision: 0.519
Recall: 0.797
F1: 0.628
ROC AUC: 0.846


Bajo: probabilidad menor a 0.40
Medio: probabilidad entre 0.40 y 0.70
Alto: probabilidad mayor o igual a 0.70

```

El dashboard ayuda al equipo de retención a identificar clientes con mayor probabilidad de abandono y priorizar acciones comerciales. En lugar de contactar clientes al azar, el usuario puede enfocarse en aquellos con mayor riesgo estimado por el modelo.



<img width="1582" height="1121" alt="Final_drawww drawio" src="https://github.com/user-attachments/assets/579783c4-3ec7-479c-8374-2ec865c018ac" />
