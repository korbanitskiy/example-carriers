from decimal import Decimal
from unidecode import unidecode

from pimly.models import enum
from .api import NaqelOrderAPI
from .pdf import home_collection, invoice
from ..abc.shipping import AbstractShippingService, TrackingNumberMixin
from pimly.models.carrier.naqel.city_codes import get_city_code, CityCodeNotFound
from pimly.utils.vat import VATOrderBeforeShipping


class NaqelShippingService(TrackingNumberMixin, AbstractShippingService):
    carrier_name = enum.CarrierName.naqel

    def can_send_shipment(self, shipment):
        order = shipment.order
        return shipment.delivery_type == enum.DeliveryType.international \
               and order.currency == 'SAR' \
               and self._valid_document_number(order) \
               and self._valid_city_code(order) \
               and self.tracking_number_qs.count() > 0

    def create_shipping_document(self, shipment):
        creator = home_collection.ShipmentPDF(self.settings, shipment)
        return creator.create_document()

    def create_invoice_document(self, shipment):
        creator = invoice.NaqelInvoicePDF(self.settings, shipment)
        return creator.create_document()

    def _valid_city_code(self, order):
        try:
            cdb_cities = [order.shipping_address.city]
            cdb_cities.extend(order.shipping_address.base_cities)
            valid_city_code = get_city_code(order.shipping_address.country, cdb_cities)
        except CityCodeNotFound:
            valid_city_code = None

        return bool(valid_city_code)

    def _valid_document_number(self, order):
        if VATOrderBeforeShipping(order.international_shipment).vat_custom[1] >= Decimal('1000.00'):
            document_number = unidecode(order.document.document_number) if order.document.document_number else None
            return document_number and document_number.isdigit() and len(document_number) == 10 and document_number[0] == '1'

        return True

    def _send_shipment(self, shipment):
        shipment.tracking_number = self.get_tracking_number()
        naqel_api = NaqelOrderAPI(shipment, self.settings)
        naqel_api.send_waybill()
        return shipment.tracking_number

    def _resend_shipment(self, shipment):
        naqel_api = NaqelOrderAPI(shipment, self.settings)
        naqel_api.send_waybill()
