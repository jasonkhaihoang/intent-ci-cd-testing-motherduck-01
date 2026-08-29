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
        region
    from source
)

select * from renamed
