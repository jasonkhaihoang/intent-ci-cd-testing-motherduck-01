{{ config(materialized='view') }}

-- Model: stg_customers
-- Grain: one row per customer, keyed by id
-- Source: src_customers (project-owned source model)

SELECT
    id,
    name,
    CAST(signup_date AS DATE) AS signup_date,
    UPPER(country) AS country
FROM {{ ref('src_customers') }}
