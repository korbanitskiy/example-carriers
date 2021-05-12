import logging
from datetime import datetime
from decimal import Decimal
from unidecode import unidecode

from lxml import etree
from pyramid.settings import asbool
from pyramid.threadlocal import get_current_registry
from zeep import Client, Transport

from pimly.utils.vat import VATOrder
from pimly.models import DBSession, enum
from ..abc.exc import SendingOrderDelayed
from pimly.models.carrier.models import Carrier
from pimly.utils.cache import cached_property
from .city_codes import get_city_code, get_country_code


class NaqelAPI(object):
    staging_url = 'https://example.url.com?WSDL'
    production_url = 'https://live-example.url.com?WSDL'
    exception_log = logging.getLogger('carriers_orders_exceptions')

    def __init__(self, settings=None, channel='default'):
        settings = settings or get_current_registry().settings
        self.production_mode = asbool(settings.get('pimly.order_api.production_mode', False))
        self.url = self.production_url if self.production_mode else self.staging_url
        self.carrier = self._load_carrier()
        self.carrier_settings = self._load_carrier_settings(channel)

    @cached_property
    def client(self):
        return Client(self.url, transport=Transport(timeout=120, operation_timeout=120))

    @cached_property
    def factory(self):
        return self.client.type_factory('ns0')

    @property
    def client_info(self):
        return self.factory.ClientInformation(
            ClientID=self.carrier_settings.client_id,
            Password=self.carrier_settings.password,
            Version='1.0',
            ClientAddress=self.client_adress,
            ClientContact=self.client_contact
        )

    @property
    def client_adress(self):
        return self.factory.ClientAddress(
            PhoneNumber=self.carrier_settings.phone_number,
            FirstAddress=self.carrier_settings.first_address,
            CountryCode=self.carrier_settings.country_code,
            CityCode=self.carrier_settings.city_code
        )

    @property
    def client_contact(self):
        return self.factory.ClientContact(
            Name=self.carrier_settings.name,
            Email=self.carrier_settings.email,
            PhoneNumber=self.carrier_settings.phone_number
        )

    def get_tracking_info(self, order_hawbs):
        order_hawbs = list(order_hawbs)
        try:
            response = self.client.service.TraceByMultiWaybillNo(ClientInfo=self.client_info, WaybillNo=self.factory.ArrayOfInt(order_hawbs))
        except Exception as e:
            self.exception_log.exception("Naqel. An error occurred while receiving tracking response")
            request = self.client.create_message(
                self.client.service,
                "TraceByMultiWaybillNo",
                ClientInfo=self.client_info,
                WaybillNo=self.factory.ArrayOfInt(order_hawbs)
            )
            self.exception_log.error(f"Request: {etree.tostring(request, pretty_print=True)}")
            raise

        return response or []

    def _load_carrier_settings(self, channel):
        return self.carrier.get_settings(channel)

    @staticmethod
    def _load_carrier():
        return DBSession.query(Carrier).filter(Carrier.name == enum.CarrierName.naqel).one()


class NaqelOrderAPI(NaqelAPI):

    def __init__(self, shipment, settings=None, **kwargs):
        self.shipment = shipment
        self.order = shipment.order
        super().__init__(settings, channel=self.order.channel.code)
        self.vat_order = VATOrder(self.shipment)
        self.order_vat_custom = self.vat_order.vat_custom[1]
        self.tracking_number = self.shipment.tracking_number

    def send_waybill(self):
        try:
            manifest = self._create_manifest()
        except Exception as e:
            raise SendingOrderDelayed(f"Manifest couldn't be created at NaqelAPI: {e}")

        try:
            response = self.client.service.UpdateWaybill(manifest, self.tracking_number)
        except Exception as e:
            self.exception_log.exception(e)
            request = self.client.create_message(
                self.client.service,
                "UpdateWaybill",
                ManifestShipmentDetails=manifest,
                WaybillNo=self.tracking_number
            )
            self.exception_log.error(f"Request: {etree.tostring(request, pretty_print=True)}")
            raise SendingOrderDelayed(f"Manifest couldn't be send to NaqelAPI: {e}")

        if response.HasError:
            request = self.client.create_message(
                self.client.service,
                "UpdateWaybill",
                ManifestShipmentDetails=manifest,
                WaybillNo=self.tracking_number
            )
            self.exception_log.error(f"Request: {etree.tostring(request, pretty_print=True)}")
            raise SendingOrderDelayed(f"Invalid response for order {self.order.code}: {response.Message}")

    def _create_manifest(self):
        info = {
            'ClientInfo': self.client_info,
            'ConsigneeInfo': self.consignee_info,
            '_CommercialInvoice': self.commercial_invoice,
            'Latitude': self.order.shipping_address.latitude or None,
            'Longitude': self.order.shipping_address.longitude or None,
            'BillingType': 5 if self.order.is_cod else 1,
            'PicesCount': self.shipment.box_qty,
            'Weight': 0.1 * self.order.shipped_qty,
            'CODCharge': self.shipment.totals.total or 0,
            'LoadTypeID': 56,
            'DeclareValue': self.order_vat_custom,
            'GoodDesc': 'wearing apparel',
            'RefNo': str(self.order.code),
            'GeneratePiecesBarCodes': False,
            'CreateBooking': False,
            'CurrenyID': 1,
        }

        if self.production_mode:
            # info['HSCode'] = '62105000'
            info['IsCustomDutyPayByConsignee'] = False if self.order.is_frdm else True

        return self.factory.ManifestShipmentDetails(**info)

    @property
    def commercial_invoice(self):
        district = self.order.shipping_address.district or ''
        return self.factory.CommercialInvoice(
            CommercialInvoiceDetailList=self.commercial_invoice_detail_list,
            RefNo=self.order.code,
            InvoiceNo=self.tracking_number,
            InvoiceDate=datetime.utcnow(),
            Consignee=self.order.shipping_address.full_name,
            ConsigneeAddress=f"{district}, {self.order.shipping_address.address}",
            ConsigneeEmail=self.order.email,
            MobileNo=self.order.shipping_address.fax or None,
            Phone=self.order.shipping_address.phone,
            TotalCost=self.order_vat_custom,
            CurrencyCode='SAR',
        )

    @property
    def commercial_invoice_detail_list(self):
        shipped_items = self.shipment.items
        return self.factory.ArrayOfCommercialInvoiceDetail([self.commercial_invoice_detail(item) for item in shipped_items])

    def commercial_invoice_detail(self, item):
        product_type = item.product_type or 'wearing apparel'
        return self.factory.CommercialInvoiceDetail(
            Quantity=item.shipped_qty,
            UnitType='Pieces',
            CountryofManufacture='GB',
            Description=f"{item.code}-{product_type}",
            UnitCost=self.vat_order.item_vat_custom(item)[1],
            CustomsCommodityCode='62105000',
            Currency='SAR'
        )

    @property
    def consignee_info(self):
        district = self.order.shipping_address.district or ''
        if self.order_vat_custom >= Decimal('1000.00'):
            document_number = unidecode(self.order.document.document_number)
        else:
            document_number = '1000000000'

        cdb_cities = [self.order.shipping_address.city]
        cdb_cities.extend(self.order.shipping_address.base_cities)
        return self.factory.ConsigneeInformation(
            ConsigneeName=self.order.shipping_address.full_name,
            Email=self.order.email,
            PhoneNumber=self.order.shipping_address.phone,
            Mobile=self.order.shipping_address.fax or None,
            Address=f"{district}, {self.order.shipping_address.address}",
            CountryCode=get_country_code(self.order.shipping_address.country),
            CityCode=get_city_code(self.order.shipping_address.country, cdb_cities),
            ConsigneeNationalID=document_number
        )
