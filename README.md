# Customer Churn Data Product

Producto de datos desplegado en AWS para ayudar a un equipo de retención o Customer Success a identificar clientes con mayor probabilidad de abandonar el servicio. La solución utiliza datos del dataset **Telco Customer Churn** de Kaggle, genera predicciones de churn mediante modelos de clasificación y expone los resultados en una aplicación web desarrollada en Streamlit.

El objetivo del producto es que el usuario final pueda priorizar clientes con mayor riesgo, consultar su probabilidad estimada de churn, revisar factores de riesgo simples y tomar mejores decisiones comerciales.

---

## Aplicación desplegada

La aplicación está desplegada en AWS ECS Fargate y expuesta mediante un Application Load Balancer.

```text
http://churn-streamlit-alb-1369386964.us-east-1.elb.amazonaws.com/
```

---

## Usuario final

El usuario final es un equipo de retención, Customer Success o CRM de una empresa de telecomunicaciones. Este equipo necesita identificar qué clientes tienen mayor probabilidad de cancelar el servicio para priorizar acciones de retención.

---

## Problema que resuelve

En lugar de contactar clientes al azar o depender únicamente de reglas manuales, el producto permite ordenar clientes según su probabilidad estimada de churn. Esto ayuda a enfocar recursos comerciales en los clientes con mayor riesgo y mayor urgencia de atención.

---

## Fuente de datos

El dataset utilizado es **Telco Customer Churn** de Kaggle:

```text
https://www.kaggle.com/datasets/blastchar/telco-customer-churn/data
```

La base contiene aproximadamente 7,043 clientes y 21 columnas. Cada fila representa un cliente e incluye variables como:

- tipo de contrato
- antigüedad del cliente
- cargos mensuales
- cargos totales
- servicios contratados
- método de pago
- variable objetivo `Churn`

La variable objetivo indica si el cliente abandonó o no el servicio.

---

## Arquitectura general

La solución sigue una arquitectura tipo **data lake medallion** con capas Bronze, Silver y Gold en Amazon S3.

<img width="1901" height="1201" alt="churn_architecture" src="https://github.com/user-attachments/assets/12e82862-f322-4e0c-bc9c-021723f1836f" />

---

## Servicios de AWS utilizados

- **Amazon S3:** almacenamiento de las capas Bronze, Silver y Gold.
- **AWS Glue Data Catalog:** catálogo de metadatos para consultar los datos desde Athena.
- **Amazon Athena:** motor SQL serverless para consultar las tablas externas.
- **Amazon SageMaker Studio:** ambiente de desarrollo y ejecución del pipeline.
- **Amazon ECR:** repositorio de la imagen Docker de la aplicación.
- **Amazon ECS Fargate:** servicio serverless para ejecutar el contenedor de Streamlit.
- **Application Load Balancer:** exposición pública de la aplicación.
- **IAM Roles:** permisos seguros para que ECS pueda leer outputs desde S3.
- **CloudFormation:** definición de infraestructura como código.

---

## Decisión de arquitectura: sin RDS

Esta versión no utiliza RDS ni SQLAlchemy. La solución está diseñada como un producto analítico basado en data lake:

- S3 almacena los datos crudos, limpios y enriquecidos.
- Glue cataloga las tablas externas.
- Athena permite consultar los datos con SQL.
- Streamlit consume directamente los outputs Gold desde S3 usando `boto3` y `pandas`.

RDS sería una extensión futura si se quisiera guardar información transaccional, como comentarios del usuario, clientes contactados, historial de acciones comerciales o feedback operativo.

---

## Estructura del repositorio

```text
.
├── .dockerignore
├── .gitignore
├── .python-version
├── README.md
├── app
│   └── streamlit_app.py
├── docker
│   └── Dockerfile
├── docs
│   ├── Definición del Producto.pdf
│   ├── FAQ del Producto.pdf
│   └── churn_architecture.png
├── infra
│   ├── data_lake_foundation.yaml
│   └── ecs_streamlit_service.yaml
├── pyproject.toml
├── scripts
│   └── run_pipeline.sh
├── src
│   ├── 01_bronze_kaggle_to_s3.py
│   ├── 02_silver.py
│   ├── 03_gold.py
│   └── 04_register_athena_tables.py
└── uv.lock

```

---

## Componentes principales

### `src/01_bronze_kaggle_to_s3.py`

Descarga el dataset desde Kaggle y carga el archivo CSV crudo a Amazon S3 en la capa Bronze.

Output principal:

```text
s3://churn-data-product-780191826160-2026/bronze/WA_Fn-UseC_-Telco-Customer-Churn.csv
```

---

### `src/02_silver.py`

Limpia y transforma los datos crudos.

Tareas principales:

- normaliza nombres de columnas
- convierte `TotalCharges` a numérico
- codifica `Churn` como 0/1
- codifica variables Yes/No seleccionadas
- elimina duplicados
- genera un archivo Parquet limpio

Output principal:

```text
s3://churn-data-product-780191826160-2026/silver/customers_clean.parquet
```

---

### `src/03_gold.py`

Entrena modelos de clasificación y genera la capa Gold.

Modelos utilizados:

- Logistic Regression
- Random Forest

Métricas calculadas:

- Accuracy
- Precision
- Recall
- F1
- ROC AUC

Outputs principales:

```text
s3://churn-data-product-780191826160-2026/gold/predictions/churn_predictions.parquet
s3://churn-data-product-780191826160-2026/gold/metrics/model_metrics.csv
s3://churn-data-product-780191826160-2026/gold/artifacts/churn_model.joblib
```

La capa Gold incluye:

- `customer_id`
- `prob_churn`
- `prediction`
- `risk_level`
- `model_name`
- variables de contexto del cliente

Los niveles de riesgo se definen así:

```text
Bajo: probabilidad menor a 0.40
Medio: probabilidad entre 0.40 y 0.70
Alto: probabilidad mayor o igual a 0.70
```

---

### `src/04_register_athena_tables.py`

Registra tablas externas en AWS Glue Data Catalog para que Amazon Athena pueda consultar los archivos almacenados en S3.

Tablas registradas:

```text
churn_silver.customers_clean
churn_gold.churn_predictions
churn_gold.model_metrics
```

---

### `app/streamlit_app.py`

Aplicación web desarrollada en Streamlit para consumir los outputs Gold del producto de datos.

Funcionalidades principales:

- resumen ejecutivo
- filtros por nivel de riesgo
- filtros por tipo de contrato
- ranking de clientes con mayor probabilidad de churn
- consulta individual de cliente
- visualización de métricas del modelo
- descarga de ranking filtrado

La app lee directamente desde S3:

```text
gold/predictions/churn_predictions.parquet
gold/metrics/model_metrics.csv
```

---

## Bucket principal

```text
s3://churn-data-product-780191826160-2026/
```

Estructura:

```text
bronze/
silver/
gold/
  predictions/
  metrics/
  artifacts/
athena-results/
```
---

## Bases y tablas en Glue/Athena

### Database Silver

```text
churn_silver
```

Tabla:

```text
customers_clean
```

### Database Gold

```text
churn_gold
```

Tablas:

```text
churn_predictions
model_metrics
```
---

## Configuración del ambiente con uv

El proyecto utiliza `uv` para manejar dependencias.

Instalar dependencias:

```bash
uv sync
```

Agregar dependencias nuevas:

```bash
uv add nombre-paquete
```

Ejecutar Python dentro del ambiente:

```bash
uv run python --version
```

---

## Variables de entorno

Variables principales:

```bash
export CHURN_BUCKET=churn-data-product-780191826160-2026
export AWS_REGION=us-east-1
```

La app también puede usar:

```bash
export CHURN_PREDICTIONS_KEY=gold/predictions/churn_predictions.parquet
export CHURN_METRICS_KEY=gold/metrics/model_metrics.csv
```
---

## Ejecución del pipeline completo

El pipeline completo se ejecuta con:

```bash
export CHURN_BUCKET=churn-data-product-780191826160-2026
export AWS_REGION=us-east-1

./scripts/run_pipeline.sh
```

Este script ejecuta:

```text
1. Bronze: descarga/carga Kaggle → S3
2. Silver: limpieza y transformación → Parquet
3. Gold: entrenamiento, predicciones y métricas
4. Registro de tablas externas en Glue/Athena
```
---


## Docker

Construcción local de la imagen:

```bash
docker build --network sagemaker \
  -f docker/Dockerfile \
  -t churn-streamlit-app:latest .
```

Login a ECR:

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=780191826160
export ECR_REPO=churn-streamlit-app
export IMAGE_TAG=latest
export IMAGE_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG

aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

Push a ECR:

```bash
docker tag $ECR_REPO:$IMAGE_TAG $IMAGE_URI
docker push $IMAGE_URI
```

Imagen publicada:

```text
780191826160.dkr.ecr.us-east-1.amazonaws.com/churn-streamlit-app:latest
```
---

## Infraestructura

La infraestructura se define mediante CloudFormation.

### Data lake foundation

```text
infra/data_lake_foundation.yaml
```

Crea o configura:

- bucket S3 del producto
- bases de datos Glue
- repositorio ECR

### ECS Streamlit Service

```text
infra/ecs_streamlit_service.yaml
```

Crea:

- ECS Cluster
- ECS Fargate Service
- Task Definition
- IAM Task Role
- IAM Execution Role
- Application Load Balancer
- Target Group
- Security Groups
- CloudWatch Logs

---

## Despliegue

El despliegue final sigue este flujo:

```text
Docker Image
→ Amazon ECR
→ ECS Fargate
→ Application Load Balancer
→ Public URL
```

La aplicación desplegada consume los datos Gold desde S3 usando permisos del IAM Task Role asignado al servicio de ECS.

---

## Costos esperados

La solución fue diseñada para mantenerse dentro de un presupuesto bajo y usar servicios serverless o de bajo costo cuando es posible.

Principales componentes de costo:

- almacenamiento S3
- consultas Athena
- ejecución de ECS Fargate
- Application Load Balancer
- almacenamiento de imagen en ECR
- logs en CloudWatch

Para una prueba de concepto con pocos datos y uso limitado, el costo esperado es bajo. Para producción, el costo dependería principalmente del tiempo activo de ECS Fargate, el uso del Load Balancer y la frecuencia de consultas en Athena.

---

## Limitaciones

- El dataset es pequeño y público, por lo que la solución funciona como prueba de concepto.
- El modelo se entrena batch, no en tiempo real.
- La app consume outputs ya generados, no calcula predicciones bajo demanda.
- No se guarda feedback del usuario.
- No se usa RDS porque no hay almacenamiento transaccional en esta versión.
- No se usa SQLAlchemy porque Streamlit lee directamente desde S3.

---

## Posibles mejoras futuras

- Agregar feedback operativo del equipo de retención.
- Guardar clientes contactados y acciones comerciales en RDS o DynamoDB.
- Automatizar el pipeline con EventBridge o Step Functions.
- Agregar monitoreo de drift del modelo.
- Agregar autenticación para usuarios finales.
- Agregar explicación de variables mediante SHAP.
- Agregar retraining programado.
- Crear endpoint de inferencia para scoring bajo demanda.

---

## Declaración sobre uso de AI

Durante el desarrollo del proyecto se utilizó inteligencia artificial generativa como apoyo para estructurar documentación, depurar errores, organizar comandos, mejorar la arquitectura, redactar entregables y generar versiones iniciales de algunos scripts de Python.

En particular, se utilizó AI para apoyar la construcción y mejora de los scripts de ingesta, transformación, entrenamiento, registro de tablas en Athena/Glue y aplicación en Streamlit. También se utilizó como apoyo para agregar comentarios y docstrings que explican los módulos, funciones, inputs y outputs del código.

El uso de AI fue de asistencia y no sustituyó la implementación ni la validación del proyecto. El equipo revisó, adaptó y ejecutó el código generado, validando que cada componente funcionara correctamente. La ejecución del pipeline, validación de outputs, configuración de AWS, despliegue de la aplicación y revisión final fueron realizadas por el equipo.

También se verificó manualmente que los datos se generaran correctamente en S3, que las tablas estuvieran disponibles en Glue/Athena, que la imagen Docker se publicara en ECR y que la aplicación funcionara desde ECS Fargate mediante una URL pública.

Las decisiones principales del producto, como el usuario final, el problema de negocio, la arquitectura tipo data lake, la selección de outputs Gold y la forma de consumo mediante Streamlit, fueron revisadas y ajustadas por el equipo. La AI se utilizó como herramienta de apoyo técnico y de documentación, manteniendo la responsabilidad final del desarrollo, pruebas y entrega en el equipo.


---

## Equipo

Proyecto final de arquitectura de productos de datos.

