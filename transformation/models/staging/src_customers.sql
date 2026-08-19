{{ config(materialized='table') }}

SELECT
    1 AS id,
    'Alice Johnson' AS "name",
    '2024-01-15' AS signup_date,
    'united states' AS country
UNION ALL
SELECT
    2 AS id,
    'Bob Smith' AS "name",
    '2024-02-20' AS signup_date,
    'canada' AS country
UNION ALL
SELECT
    3 AS id,
    'Carol Lee' AS "name",
    '2024-03-10' AS signup_date,
    'united kingdom' AS country
UNION ALL
SELECT
    4 AS id,
    'David Kim' AS "name",
    '2023-11-05' AS signup_date,
    'south korea' AS country
UNION ALL
SELECT
    5 AS id,
    'Eva Martinez' AS "name",
    '2024-04-22' AS signup_date,
    'spain' AS country
UNION ALL
SELECT
    6 AS id,
    'Frank Chen' AS "name",
    '2023-12-01' AS signup_date,
    'china' AS country
UNION ALL
SELECT
    7 AS id,
    'Grace Patel' AS "name",
    '2024-05-30' AS signup_date,
    'india' AS country
UNION ALL
SELECT
    8 AS id,
    'Henry Brown' AS "name",
    '2024-06-14' AS signup_date,
    'australia' AS country
