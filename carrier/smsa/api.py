import io
import logging
import os
from collections import namedtuple
from datetime import datetime
from xml.etree import ElementTree

from lxml.etree import tostring
from pdfrw import PdfReader, PdfWriter
from pyramid.settings import asbool
from pyramid.threadlocal import get_current_registry
from zeep import Client, Transport
from pimlib.cache import cache_tag
from pimlib.utils.files import ensure_dir

from pimly.models import DBSession
from pimly.models import enum
from pimly.models.carrier.models import Carrier
from pimly.utils.cache import cached_property
from pimly.utils.vat import VATOrder
from ..abc.exc import SendingOrderCancelled
from ..abc.service_point import Location
from .city_codes import CITY_CODES


class SMSAAPI:
    production_url = 'http://example.url.com?WSDL'
    log = logging.getLogger('carriers_orders')
    exception_log = logging.getLogger('carriers_orders_exceptions')

    def __init__(self, settings=None, channel='default'):
        self.settings = settings or get_current_registry().settings
        self.production_mode = asbool(self.settings.get('pimly.order_api.production_mode', False))
        self.url = self.production_url
        self.carrier = self._load_carrier()
        self.carrier_settings = self.carrier.get_settings(channel)
        self.passkey = self.carrier_settings.passkey if self.production_mode else 'Testing1'

    @cached_property
    def client(self):
        return Client(self.url, transport=Transport(timeout=120, operation_timeout=30))

    @property
    @cache_tag('get_cities', expiration_time=4*60*60)
    def cities(self):
        cities = []
        self.client.settings.raw_response = True
        try:
            response = self.client.service.getRTLCities(self.passkey)
            root = ElementTree.fromstring(response.text)
            cities = [tag.find('rCity').text for tag in root.iter("RetailCities")]
            cities = [city_name.title() for city_name in cities]
        except Exception as e:
            self.exception_log.exception(e)
        finally:
            self.client.settings.raw_response = False
        return cities

    def get_service_points(self):
        self.client.settings.raw_response = True
        service_points = []
        try:
            response = self.client.service.getAllRetails(self.passkey)
            root = ElementTree.fromstring(response.content)
            for tag in root.iter("RetailsList"):
                coordinates = tag.find("rGPSPt").text.split(',')
                city = tag.find("rCity").text
                code = tag.find("rCode").text
                name = f"{code}, {city}"
                service_points.append(
                    Location(code=code,
                             city=city,
                             name=name,
                             address=tag.find("rAddrEng").text,
                             address_ar=tag.find("rAddrAr").text,
                             latitude=coordinates[0],
                             longitude=coordinates[1],
                             phone=tag.find("rPhone").text,
                             country="SA",
                             )
                )
        except Exception as e:
            self.exception_log.exception(e)
            raise
        else:
            return service_points
        finally:
            self.client.settings.raw_response = False

    def _load_carrier(self):
        return DBSession.query(Carrier)\
            .filter(Carrier.name == enum.CarrierName.smsa)\
            .one()


SMSATrackInfo = namedtuple('SMSATrackInfo', [
    'event_code',
    'event_date',
    'description',
])


class SMSAOrderAPI(SMSAAPI):

    def __init__(self, shipment, settings=None, **kwargs):
        self.shipment = shipment
        self.order = shipment.order
        super().__init__(settings, channel=self.order.channel.code)
        self.pdf_path = os.path.join(self.settings['pimly.carriers.main_path'], enum.CarrierName.smsa.name, 'shipping_pdf')
        ensure_dir(self.pdf_path)

        if self.order.shipping_method_type == enum.ShippingMethod.click_and_collect:
            self.passkey = self.carrier_settings.cc_passkey if self.production_mode else "Testing1"

    def _load_carrier(self):
        return self.shipment.carrier or super()._load_carrier()

    def send_shipment(self, box_qty, **kwargs):
        try:
            self.client.settings.raw_response = False
            tracking_number = self.client.service.addShip(**self._create_info(box_qty, **kwargs))
        except Exception as e:
            self.exception_log.exception(e)
            raise SendingOrderCancelled(f"Shipping couldn't be send to SMSA: {e}")

        if 'Failed' in tracking_number:
            raise SendingOrderCancelled(f"Invalid tracking number '{tracking_number}' for order {self.order.code}")

        return tracking_number

    @property
    def shipment_pdf(self):
        origin_shipment = self.client.service.getPDF(awbNo=self.shipment.tracking_number, passKey=self.passkey)
        reader = PdfReader(fdata=origin_shipment)

        boxes_shipment_pdf = io.BytesIO()
        writer = PdfWriter()
        for _ in range(self.shipment.box_qty):
            writer.addpage(reader.pages[0])
            writer.write(boxes_shipment_pdf)

        return boxes_shipment_pdf

    def valid_city(self):
        return self.order_city_name is not None

    @property
    def order_city_name(self):
        cdb_cities = [self.order.shipping_address.city]

        if self.order.shipping_method_type != enum.ShippingMethod.click_and_collect:
            cdb_cities.extend(self.order.shipping_address.base_cities)

        for city in cdb_cities:
            city = city.strip().title()
            city = CITY_CODES.get(city, city)
            if city in self.cities:
                return city

    def _create_info(self, box_qty, **kwargs):
        postcode = self.order.shipping_address.postcode
        coordinates = [
            self.order.shipping_address.latitude,
            self.order.shipping_address.longitude
        ]

        if self.order.shipping_method_type == enum.ShippingMethod.click_and_collect:
            shipping_type = "HAL"
            location_code = self.order.shipping_info['code']
            address = ' '.join(["HAL", "@", self.order.shipping_address.address])
            username = self.carrier_settings.cc_name

        else:
            shipping_type = "DLV"
            location_code = None
            address = [
                self.order.shipping_address.district,
                self.order.shipping_address.address,
                self.order.shipping_address.postcode
            ]
            address = ', '.join(filter(None, address))
            username = self.carrier_settings.name

        coordinates = [c for c in coordinates if c]
        coordinates = ','.join(coordinates) if len(coordinates) == 2 else ''

        info = {
            'idNo': '',
            'harmCode': '',
            'passKey': self.passkey,
            'refNo': self.order.code,
            'sentDate': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            'shipType': shipping_type,
            'PCs': box_qty,
            'itemDesc': 'Wearing apparel',
            'cntry': 'KSA',
            'cPOBox': postcode or '',

            'cName': self.order.shipping_address.full_name,
            'cCity': self.order_city_name,
            'cZip': postcode or '',
            'cEmail': self.order.email,
            'cMobile': self.order.shipping_address.phone,
            'cTel1': self.order.shipping_address.fax or '',
            'cTel2': '',
            'cAddr1': address,
            'cAddr2': location_code or '',

            'carrValue': '1.75' if self.order.shipping_amount else '0',
            'carrCurr': 'USD',
            'codAmt': self.shipment.totals.total or 0,
            'custVal': VATOrder(self.shipment).vat_custom[1],
            'custCurr': self.order.currency,
            'insrAmt': '0',
            'insrCurr': 'USD',
            'weight': 0.1 * self.order.shipped_qty,

            'sName': username,
            'sContact': self.carrier_settings.contact_name,
            'sAddr1': self.carrier_settings.first_address,
            'sAddr2': '',
            'sCity': self.carrier_settings.city,
            'sPhone': self.carrier_settings.phone_number,
            'sCntry': self.carrier_settings.country_code,
            'prefDelvDate': '',
            'gpsPoints': coordinates,

        }
        return info

    def get_order_tracking_info(self):
        try:
            self.client.settings.raw_response = True
            response = self.client.service.getTracking(
                passkey=self.passkey,
                awbNo=self.shipment.tracking_number
            )
        except Exception as e:
            self.exception_log.exception(f"SMSA. An error occurred while receiving tracking response for order {self.order.code}")
            raise SendingOrderCancelled(f"SMSA. Getting tracking info failed with error: {e}")

        root = ElementTree.fromstring(response.content)
        if not root:
            self.exception_log.error(f"SMSA. Response for order {self.order.code} has error message: {response}")
            request = self.client.create_message(
                self.client.service,
                "getStatus",
                passkey=self.passkey,
                awbNo=self.shipment.tracking_number
            )
            self.exception_log.error(f"Request: {tostring(request, pretty_print=True)}")
            raise SendingOrderCancelled(f"Shipment Tracking Failed. Response: {response}")

        tracking_info = []
        for track in root.iter("Tracking"):
            try:
                event_date = datetime.strptime(track.find('Date').text, '%d %b %Y %H:%M')
                tracking_info.append(SMSATrackInfo(
                    event_code=track.find('Activity').text,
                    event_date=event_date,
                    description=track.find("Details").text
                ))
            except ValueError as e:
                self.exception_log.exception("SMSA: Error during parse Response. [Event Date format]")

        return tracking_info
