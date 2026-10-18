-- Downstream-chain fixture (VD-6962): one row per sale date and region.
select
    sale_date,
    region,
    sum(quantity * unit_price) as revenue
from {{ ref('int_sales_valid') }}
group by sale_date, region
