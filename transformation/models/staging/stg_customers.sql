{{ config(materialized='view') }}

-- Model: stg_customers
-- Grain: one row per customer, keyed by id
-- Source: raw_customers (dbt seed)

SELECT
  id,
  name,
  CAST(signup_date AS DATE) AS signup_date,
  UPPER(country) AS country
FROM {{ ref('raw_customers') }}
