from decimal import Decimal

from pimly.models import enum
from pimly.utils.vat import VATOrderBeforeShipping
from ..abc.shipping import AbstractShippingService, TrackingNumberMixin
from .pdf import home_collection, invoice
from .api import PostaPlusAPI


class PostaPlusShippingService(TrackingNumberMixin, AbstractShippingService):
    carrier_name = enum.CarrierName.postaplus

    def can_send_shipment(self, shipment):
        order = shipment.order
        return shipment.delivery_type == enum.DeliveryType.international \
               and self._valid_country(order, shipment) \
               and self.tracking_number_qs.count() > 0 \
               and self._valid_high_value(order)

    def create_shipping_document(self, shipment):
        creator = home_collection.ShipmentPDF(self.settings, shipment)
        return creator.create_document()

    def create_invoice_document(self, shipment):
        creator = invoice.PostaPlusInvoicePDF(self.settings, shipment)
        return creator.create_document()

    def validate_form(self, form, write_errors):
        valid = super().validate_form(form, write_errors)
        if int(form.data['box_qty']) != 1:
            valid = False
            if write_errors:
                form.errors['box_qty'] = "PostaPlus can ship an order with 1 box only"

        return valid

    def _send_shipment(self, shipment):
        shipment.tracking_number = self.get_tracking_number()
        postaplus_api = PostaPlusAPI(shipment, self.settings)
        postaplus_api.send_order()
        return shipment.tracking_number

    def _resend_shipment(self, shipment):
        postaplus_api = PostaPlusAPI(shipment, self.settings)
        postaplus_api.send_order()

    def _valid_country(self, order, shipment):
        return not (order.shipping_address.country == 'AE' and shipment.totals.extra_fee > 0)

    def _valid_high_value(self, order):
        return not (order.shipping_address.country == 'AE'
                    and order.currency == "AED"
                    and VATOrderBeforeShipping(order.international_shipment).shipped_total >= Decimal('1000'))
