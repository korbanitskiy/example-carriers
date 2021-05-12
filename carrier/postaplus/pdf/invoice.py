# -*- coding:utf-8 -*-

from reportlab.platypus import Paragraph

from ...abc.pdf import arabic_text, BaseInvoicePDF
from pimly.models.translate import Translator
from pimly.utils import helpers as h


class PostaPlusInvoicePDF(BaseInvoicePDF):

    def __init__(self, settings, shipment, **kwargs):
        super().__init__(settings, shipment, **kwargs)
        self.translator = Translator()

    def _billing_address(self, style):
        billing_district = self.order.billing_address.district or u''
        base_city = self.order.billing_address.base_city if self.order.billing_address.base_city != self.order.billing_address.city else None
        translated_name = self.translator.translate(self.order.billing_address.full_name)
        translated_city = base_city or self.translator.translate(self.order.billing_address.city)
        billing_params = {
            'full_name': arabic_text(self.order.billing_address.full_name),
            'address': arabic_text(self.order.billing_address.address),
            'district': u'{}<br/>'.format(arabic_text(billing_district)) if billing_district else u'',
            'city': arabic_text(self.order.billing_address.city),
            'country': arabic_text(self.order.billing_address.human_country),
            'telephone': arabic_text(self.order.billing_address.phone),
            'translated_name': u'{}<br/>'.format(translated_name),
            'translated_city': u'{}<br/>'.format(translated_city),
        }
        return Paragraph(
            u'<font name="XBZar-Bold">Billing Address:</font><br/>'
            u'{full_name}<br/>'
            u'{address}<br/>'
            u'{district}'
            u'{city}<br/>'
            u'{country}<br/>'
            u'<br/>'
            u'{translated_name}'
            u'{translated_city}'
            u'T: {telephone}<br/>'.format(**billing_params),
            style
        )

    def _shipping_address(self, style):
        shipping_district = self.order.shipping_address.district or u''
        base_city = self.order.shipping_address.base_city if self.order.shipping_address.base_city != self.order.shipping_address.city else None
        translated_name = self.translator.translate(self.order.shipping_address.full_name)
        translated_city = base_city or self.translator.translate(self.order.shipping_address.city)
        shipping_params = {
            'full_name': arabic_text(self.order.shipping_address.full_name),
            'address': arabic_text(self.order.shipping_address.address),
            'district': u'{}<br/>'.format(arabic_text(shipping_district)) if shipping_district else u'',
            'city': arabic_text(self.order.shipping_address.city),
            'country': arabic_text(self.order.shipping_address.human_country),
            'telephone': arabic_text(self.order.shipping_address.phone),
            'email': arabic_text(self.order.email),
            'translated_name': u'{}<br/>'.format(translated_name),
            'translated_city': u'{}<br/>'.format(translated_city),
        }
        return Paragraph(
            u'<font name="XBZar-Bold">Shipping Address:</font><br/>'
            u'{full_name}<br/>'
            u'{address}<br/>'
            u'{district}'
            u'{city}<br/>'
            u'{country}<br/>'
            u'<br/>'
            u'{translated_name}'
            u'{translated_city}'
            u'T: {telephone}<br/>'
            u'{email}<br/>'.format(**shipping_params),
            style
        )

    def _item_info(self, item, description_style, options_style):
        options = []
        try:
            options = [(opt['label'], opt['value']) for opt in item.additional_info.get('product_options', [])]
        except KeyError:
            pass

        unit_price = self.vat_order.item_channel_sold_price(item)

        return [
            item.code,
            Paragraph(arabic_text(item.name), description_style),
            Paragraph('\n'.join(f'{label}: {value}' for label, value in options), options_style),
            item.shipped_qty,
            h.format_price_attribute(unit_price, self.order.currency, output_format="¤¤ #,##0.###;¤¤ -#,##0.###"),
            h.format_price_attribute(item.shipped_qty*unit_price, self.order.currency, output_format="¤¤ #,##0.###;¤¤ -#,##0.###")
        ]
