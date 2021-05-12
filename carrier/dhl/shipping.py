from pimly.models import enum
from .api import DHLOrderAPI
from .pdf import invoice
from ..abc.exc import SendingOrderCancelled, SendingOrderDelayed
from ..abc.shipping import AbstractShippingService


class DHLShippingService(AbstractShippingService):
    carrier_name = enum.CarrierName.dhl

    def can_send_shipment(self, shipment):
        return shipment.delivery_type == enum.DeliveryType.international \
                and self._valid_currency(shipment.order) \
                and self._valid_city_code(shipment)

    def create_shipping_document(self, shipment):
        api = DHLOrderAPI(shipment, self.settings)
        return api.shipment_pdf

    def create_invoice_document(self, shipment):
        creator = invoice.DHLInvoicePDF(self.settings, shipment, carrier_settings=self.carrier_settings)
        return creator.create_document()

    def _send_shipment(self, shipment):
        api = DHLOrderAPI(shipment, self.settings)
        invoice_document = self.create_invoice_document(shipment)
        tracking_number = api.send_shipment(shipment.box_qty, invoice_document)
        return tracking_number

    def _resend_shipment(self, shipment):
        raise SendingOrderDelayed("Resend for DHL carrier is not allowed")

    def _valid_currency(self, order):
        return not order.is_cod and order.currency == 'SAR'

    def _valid_city_code(self, shipment):
        dhl_api = DHLOrderAPI(shipment, self.settings)
        try:
            city_code = dhl_api.city_code(translate=False)
        except SendingOrderCancelled:
            return False
        else:
            return city_code is not None
