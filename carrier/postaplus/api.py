# -*- coding:utf-8 -*-
from collections import namedtuple
from datetime import datetime
import logging
import pycountry
import re
import os

from pyramid.settings import asbool
from requests import Session
from unidecode import unidecode
from zeep import Client, Transport
from lxml import etree

from pimly.utils import cached_property
from pimly.utils.helpers import normalize_arabic_phone
from pimly.utils.vat import VATOrder
from pimly.models import DBSession, enum
from pimly.models.carrier.models import Carrier
from ..abc.exc import SendingOrderDelayed, SendingOrderCancelled

from .city_codes import get_country_code, get_city_code


PostaPlusTrackInfo = namedtuple('PostaPlusTrackInfo', [
    'event_code',
    'event_date',
    'description',
])


class PostaPlusAPI:
    production_url = 'https://example.url.com?wsdl'
    staging_url = 'https://live-example.url.com?singleWsdl'
    log = logging.getLogger('carriers_orders')
    exception_log = logging.getLogger('carriers_orders_exceptions')

    def __init__(self, shipment, settings):
        production_mode = asbool(settings.get('pimly.order_api.production_mode', False))
        self.url = self.production_url if production_mode else self.staging_url
        self.shipment = shipment
        self.order = shipment.order
        self.vat_order = VATOrder(self.shipment)
        self.carrier = self._carrier_qs.one()
        self.carrier_settings = self.carrier.get_settings(self.order.channel.code)

        if production_mode:
            self.verify = os.path.join(settings['webassets.base_dir'], enum.CarrierName.postaplus.name, 'api-certificate.crt')
        else:
            self.verify = False

    def send_order(self):
        shipping_info = self._shipping_info()
        self._validate(shipping_info)
        try:
            response = self.client.service.Special_Shipment_Package(SHIPINFO=shipping_info)
        except Exception as e:
            self.exception_log.exception(f"PostaPlus: Error during send shipping order info. Order: {self.order.code}")
            request = self.client.create_message(self.client.service, "Special_Shipment_Package", SHIPINFO=shipping_info)
            self.exception_log.error(f"PostaPlus Request: {etree.tostring(request, pretty_print=True)}")
            raise SendingOrderDelayed(f"PostaPlus API not available: {e}")

        if response != self.shipment.tracking_number:
            raise SendingOrderDelayed(f"Invalid PostaPlus response: {response}, Carrier Order UID: {self.shipment.tracking_number}")

    def get_shipping_tracking_info(self):
        response = self.client.service.Shipment_Tracking(
            UserName=self.carrier_settings.username,
            Password=self.carrier_settings.password,
            ShipperAccount=self.carrier_settings.shipper_account,
            AirwaybillNumber=self.shipment.tracking_number,
            Reference1='',
            Reference2=''
        )

        last_order_tracking = response[0]

        if last_order_tracking.ErrorMsg is not None:
            self.exception_log.error(f"PostapPlus. Response for order {self.order.code} has error message: {last_order_tracking.ErrorMsg}")
            request = self.client.create_message(
                self.client.service,
                "Shipment_Tracking",
                UserName=self.carrier_settings.username,
                Password=self.carrier_settings.password,
                ShipperAccount=self.carrier_settings.shipper_account,
                AirwaybillNumber=self.shipment.tracking_number,
                Reference1='',
                Reference2=''
            )
            self.exception_log.error(f"Request: {etree.tostring(request, pretty_print=True)}")
            raise SendingOrderCancelled(f"Shipment Tracking Failed. Response ({last_order_tracking.ErrorMsg})")

        tracking_info = []
        for track in response:
            try:
                tracking_info.append(PostaPlusTrackInfo(
                    event_code=track.Event,
                    event_date=datetime.strptime(track.DateTime, '%d/%m/%Y %H:%M:%S'),
                    description=track.Note
                ))
            except ValueError as e:
                self.exception_log.exception("PostapPlus: Error during parse Response. [Event Date format]")

        return tracking_info

    @cached_property
    def client(self):
        session = Session()
        session.verify = self.verify
        return Client(self.url, transport=Transport(timeout=180, operation_timeout=60, session=session))

    def _validate(self, shipping_info):
        mobile = shipping_info['Consignee']['ToMobile']
        phone = shipping_info['Consignee']['ToTelPhone']
        postcode = shipping_info['Consignee']['ToPinCode']
        name = shipping_info['Consignee']['ToName']
        base_msg = "The shipment won't be sent to PostaPlus till the following issues are fixed: {} Please refer to the supervisor."
        if not (4 <= len(mobile) <= 15 and mobile.isdigit()):
            raise SendingOrderCancelled(base_msg.format("Phone number length must be in range of 4..15 symbols."))

        if not (4 <= len(phone) <= 15 and phone.isdigit()):
            raise SendingOrderCancelled(base_msg.format("Alternative phone number length must be in range of 4..15 symbols."))

        if not (len(postcode) < 15 and (postcode == 'NA' or re.match(r'^[0-9,\s,-]+$', postcode))):
            raise SendingOrderCancelled(base_msg.format("Postal Code can include up to 15 characters from the following range: 0-9,whitespace,-."))

        if len(name) >= 50:
            raise SendingOrderCancelled(base_msg.format("Name length must be less than 50 characters."))

    def _shipping_info(self):
        return {
            'CashOnDelivery': self.shipment.totals.total if self.order.is_cod else None,
            'CashOnDeliveryCurrency': self.order.currency if self.order.is_cod else None,
            'ClientInfo': {
                'ShipperAccount': self.carrier_settings.shipper_account,
                'UserName': self.carrier_settings.username,
                'Password': self.carrier_settings.password,
                'CodeStation': 'GSO',
            },
            'CodeCurrency': self.order.currency,
            'CodeService': 'SRV3',
            'CodeShippmentType': 'SHPT2',
            'ConnoteContact': {
                'Email1': self.carrier_settings.account_email,
                'TelMobile': normalize_arabic_phone(self.carrier_settings.telephone),
                # 'WhatsAppNumber': None,
                # 'Email2': None,
                # 'TelHome': None,
            },
            'ConnoteDescription': self.carrier_settings.goods_description,
            'ConnoteNotes': {},
            'ConnotePerformaInvoice': {
                'CONNOTEPERMINV': self._items()
            },
            'ConnotePieces': self.shipment.box_qty,
            'ConnoteProhibited': 'N',
            'ConnoteRef': {
                'Reference1': self.order.code,
                # 'Reference2': None,
            },
            'Consignee': self._consignee(),
            'CostShipment': self.vat_order.vat_custom[1],
            'ItemDetails': {
                'ITEMDETAILS': self._item_details()
            },
            'WayBill': int(self.shipment.tracking_number),
            # 'NeedPickUp': None,
            # 'NeedRoundTrip': None,
            # 'PayMode': None,
            # 'ConnoteInsured': None,
        }

    def _items(self):
        return [
            {
                'CodeHS': '6108390000',
                'CodePackageType': 'PCKT1',
                'Description': self.carrier_settings.goods_description,
                'OrginCountry': 'GB',
                'Quantity': item.shipped_qty,
                'RateUnit': self.vat_order.item_vat_custom(item, precision=3)[1],
            } for item in self.shipment.items
        ]

    def _consignee(self):
        country_code, city_code, city_name = self._prepare_toponym_codes()
        if not country_code:
            pycountry_name = pycountry.countries.get(alpha_2=self.order.shipping_address.country)
            country_code = pycountry_name.alpha_3 if pycountry_name else self.order.shipping_address.country
        city_code = city_code or 'NA'
        city_name = city_name or self.order.shipping_address.city

        phone = normalize_arabic_phone(self.order.shipping_address.phone)
        return {
            'Company': self.carrier_settings.account_name,
            'FromName': self.carrier_settings.account_name,
            'FromAddress': self.carrier_settings.account_address,
            'FromCity': 'NA',
            'FromCodeCountry': self.carrier_settings.account_country,
            'FromTelphone': normalize_arabic_phone(self.carrier_settings.telephone),
            'FromMobile': normalize_arabic_phone(self.carrier_settings.telephone),
            'FromArea': 'NA',
            'FromPinCode': self.carrier_settings.account_post_code if self.carrier_settings.account_post_code else 'NA',
            'FromProvince': 'NA',
            'ToName': replace_characters(self.order.shipping_address.full_name, replacer=u","),
            'ToAddress': normalize_arabic_numbers(replace_characters(u'{}, {}'.format(self.order.shipping_address.address, city_name), replacer=u",")),
            'ToCity': replace_characters(city_code, replacer=u","),
            'ToCodeCountry': country_code,
            'ToMobile': phone,
            'ToTelPhone': normalize_arabic_phone(self.order.shipping_address.fax) or phone,
            'ToArea': 'NA',
            'ToPinCode': 'NA',
            'ToProvince': 'NA',
            'ToCodeSector': 'NA',
            'ToDesignation': 'NA',
            # 'Remarks': None,
            # 'ToCivilID': None,
        }

    def _prepare_toponym_codes(self):
        city_code = None
        city_name = None
        country_code = get_country_code(self.order.shipping_address.country)
        if country_code:
            cdb_cities = [self.order.shipping_address.city]
            cdb_cities.extend(self.order.shipping_address.base_cities)
            city_code, city_name = get_city_code(self.order.shipping_address.country, cdb_cities)
        return country_code, city_code, city_name

    def _item_details(self):
        return [
            {
                'ConnoteHeight': 1,
                'ConnoteLength': 1,
                'ConnoteWeight': 0.5,
                'ConnoteWidth': 1,
                'ScaleWeight': 0.5,
            } for _ in range(self.shipment.box_qty)
        ]

    @property
    def _carrier_qs(self):
        return DBSession.query(Carrier).filter(Carrier.name == enum.CarrierName.postaplus)


def replace_characters(text, replacer):
    if not text:
        return text
    pattern = '[%s]' % re.escape("~`!%^&*=|)}]’;:?><'({[@$\\/+")
    return re.sub(pattern, replacer, text)


def normalize_arabic_numbers(text):
    output = []
    for character in text:
        if character.isdigit():
            character = unidecode(character)
        output.append(character)
    return ''.join(output)
