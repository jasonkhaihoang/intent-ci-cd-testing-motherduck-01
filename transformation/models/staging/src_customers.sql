{{ config(materialized='table') }}

SELECT
    1 AS id,
    'Alice Johnson' AS name,
    '2024-01-15' AS signup_date,
    'united states' AS country
UNION ALL
SELECT
    2,
    'Bob Smith',
    '2024-02-20',
    'canada'
UNION ALL
SELECT
    3,
    'Carol Lee',
    '2024-03-10',
    'united kingdom'
UNION ALL
SELECT
    4,
    'David Kim',
    '2023-11-05',
    'south korea'
UNION ALL
SELECT
    5,
    'Eva Martinez',
    '2024-04-22',
    'spain'
UNION ALL
SELECT
    6,
    'Frank Chen',
    '2023-12-01',
    'china'
UNION ALL
SELECT
    7,
    'Grace Patel',
    '2024-05-30',
    'india'
UNION ALL
SELECT
    8,
    'Henry Brown',
    '2024-06-14',
    'australia'
