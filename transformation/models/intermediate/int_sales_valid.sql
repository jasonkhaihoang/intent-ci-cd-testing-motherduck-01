-- Downstream-chain fixture (VD-6962): sales with a positive quantity.
select
    sale_id,
    customer_id,
    product,
    quantity,
    unit_price,
    sale_date,
    region
from {{ ref('stg_raw__sales') }}
where quantity > 0
