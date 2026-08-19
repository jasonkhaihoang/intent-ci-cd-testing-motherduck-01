with source as (
    select * from {{ source('raw', 'customers') }}
),

renamed as (
    select
        id as customer_id,
        name as customer_name,
        cast(signup_date as date) as signup_date,
        country
    from source
)

select * from renamed
