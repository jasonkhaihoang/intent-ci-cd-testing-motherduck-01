with source as (
    select * from {{ source('raw', 'sales') }}
),

renamed as (
    select
        sale_id,
        customer_id,
        product,
        quantity,
        unit_price,
        region,
        cast(sale_date as date) as sale_date,
        quantity * unit_price as total_amount
    from source
)

select * from renamed
