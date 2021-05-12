from pimly.models import enum
from .api import SMSAOrderAPI
from ..abc.pdf import BaseInvoicePDF
from ..abc.exc import SendingOrderDelayed
from ..abc.shipping import AbstractShippingService


class SMSAShippingService(AbstractShippingService):
    carrier_name = enum.CarrierName.smsa

    def can_send_shipment(self, shipment):
        order = shipment.order
        return shipment.delivery_type == enum.DeliveryType.international \
               and order.currency == "SAR" \
               and self._valid_city_code(order, shipment)

    def create_shipping_document(self, shipment):
        api = SMSAOrderAPI(shipment, self.settings)
        return api.shipment_pdf

    def create_invoice_document(self, shipment):
        creator = BaseInvoicePDF(self.settings, shipment)
        return creator.create_document()

    def validate_form(self, form, write_errors):
        valid = super().validate_form(form, write_errors)
        if int(form.data['box_qty']) != 1:
            valid = False
            if write_errors:
                form.errors['box_qty'] = "SMSA can ship an order with 1 box only"

        return valid

    def _send_shipment(self, shipment):
        api = SMSAOrderAPI(shipment, self.settings)
        tracking_number = api.send_shipment(box_qty=shipment.box_qty)
        return tracking_number

    def _resend_shipment(self, shipment):
        raise SendingOrderDelayed("Resend for SMSA carrier is not allowed")

    def _valid_city_code(self, order, shipment):
        return order.shipping_method_type == enum.ShippingMethod.click_and_collect \
               or SMSAOrderAPI(shipment, self.settings).valid_city()
