-- Downstream-chain fixture (VD-6962): one row per region.
select
    region,
    sum(revenue) as revenue
from {{ ref('fct_sales_daily') }}
group by region
