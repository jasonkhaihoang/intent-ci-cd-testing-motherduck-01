-- Downstream-chain fixture (VD-6962): sales with a positive quantity.
select *
from {{ ref('stg_raw__sales') }}
where quantity > 0
