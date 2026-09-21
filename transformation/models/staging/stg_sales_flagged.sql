-- One row per sale: 1:1 with raw.sales, no join, no aggregation, no filter.
-- The flag marks rows; it never drops them, so the population stays equal to the source's.
with source as (
    select * from {{ source('raw', 'sales') }}
),

renamed as (
    select
        id as sale_id,
        customer_id,
        product,
        quantity,
        unit_price,
        cast(sale_date as date) as sale_date,
        region,
        -- Derived, never sourced: raw.sales holds no sale-total column under any name.
        quantity * unit_price as sale_total
    from source
),

flagged as (
    select
        *,
        -- Strictly over 500, and false rather than null when sale_total is null:
        -- a bare `sale_total > 500` would propagate NULL and break the never-null contract.
        case
            when sale_total > 500 then true
            else false
        end as is_over_500
    from renamed
)

select * from flagged
