from collections import OrderedDict

AramexSettings = OrderedDict([
    ("Groups", ('group_id', 'return_group_id')),
    ("Base", ('carrier_email', 'instruction_email', 'return_active', 'send_email', 'shipping_pdf', 'invoice_pdf', 'waybill_pdf', 'track_url')),
    ("Return API", ('return_username', 'return_password')),
    ("Service Points API", ('sp_username', 'sp_password', 'sp_account_number', 'sp_pin', 'sp_account_entity', 'sp_country_code')),
    ("Home Delivery Shipping XML", ('account_address', 'account_city', 'account_name', 'account_number',
                                    'account_post_code', 'entity_id', 'entity_pin', 'eori_number',)),
    ("Click And Collect Shipping XML", ('cc_account_number', 'cc_account_post_code', 'cc_entity_id', 'cc_entity_pin')),
    ("Shipping PDF", ('goods_description', 'goods_origin', 'location', 'product_group', 'product_type', 'telephone'))
])

AramexSASettings = OrderedDict([
    ("Groups", ('group_id', 'return_group_id')),
    ("Base", ('carrier_email', 'instruction_email', 'return_active', 'send_email', 'shipping_pdf', 'invoice_pdf', 'waybill_pdf', 'track_url')),
    ("Return API", ('return_username', 'return_password')),
    ("Home Delivery Shipping XML", ('account_address', 'account_city', 'account_name', 'account_number',
                                    'account_post_code', 'entity_id', 'entity_pin', 'eori_number',)),
    ("Shipping PDF", ('goods_description', 'goods_origin', 'location', 'product_group', 'product_type', 'telephone'))
])

NaqelSettings = OrderedDict([
    ("Groups", ('group_id',)),
    ("Base", ('carrier_email', 'instruction_email', 'send_email', 'shipping_pdf', 'invoice_pdf', 'waybill_pdf', 'track_url')),
    ("API Information", ('client_id', 'password', 'name', 'email', 'phone_number', 'first_address', 'country_code', 'city_code')),
    ("PDF Information", ('location', 'product_type', 'goods_description', 'goods_origin', 'account_number', 'account_address',
                         'account_name', 'account_post_code', 'telephone', 'eori_number'))
])

PostaPlusSettings = OrderedDict([
    ("Groups", ('group_id',)),
    ("Base", ('carrier_email', 'instruction_email', 'send_email', 'shipping_pdf', 'invoice_pdf', 'waybill_pdf', 'track_url')),
    ("API Information", ('shipper_account', 'username', 'password')),
    ("Account Information", ('account_email', 'account_name', 'account_country', 'account_city', 'account_post_code', 'account_address', 'telephone')),
    ("Shipping PDF", ('location', 'product_type', 'product_group', 'goods_origin', 'goods_description', 'eori_number'))
])

SMSASettings = OrderedDict([
    ("Base", ('carrier_email', 'instruction_email', 'send_email', 'shipping_pdf', 'invoice_pdf', 'waybill_pdf', 'track_url')),
    (" Home Delivery API Information", ('name', 'passkey', 'contact_name', 'first_address', 'city', 'phone_number', 'country_code')),
    ('Click And Collect API Information', ('cc_name', 'cc_passkey'))
])

DHLSettings = OrderedDict([
    ("Base", ('carrier_email', 'instruction_email', 'send_email', 'shipping_pdf', 'invoice_pdf', 'waybill_pdf', 'track_url')),
    ("API", ("pp_account", "cod_account")),
    ("Shipping PDF", ("company", "address1", "address2", "address3", "city", "postcode", "country", "email", "phone"))
])

RetailerAddress = OrderedDict([
    ("Address Info", ('street', 'postcode', 'city', 'country_code', 'contact', 'name', 'email', 'phone')),
])
