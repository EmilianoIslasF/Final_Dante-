
CREATE DATABASE IF NOT EXISTS churn_db;

-- Tabla silver
CREATE EXTERNAL TABLE IF NOT EXISTS churn_db.customers_silver (
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
LOCATION 's3://itam-churn-317521775-2026/silver/';

-- Tabla gold de predicciones
CREATE EXTERNAL TABLE IF NOT EXISTS churn_db.churn_predictions_gold (
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
LOCATION 's3://itam-churn-317521775-2026/gold/';

-- Tabla gold de métricas
CREATE EXTERNAL TABLE IF NOT EXISTS churn_db.model_metrics_gold (
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
LOCATION 's3://itam-churn-317521775-2026/gold/'
TBLPROPERTIES ('skip.header.line.count'='1');
