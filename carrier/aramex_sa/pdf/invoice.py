from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import Paragraph, Table, TableStyle

from pimly.models.carrier.abc.pdf import BaseInvoicePDF
from pimly.utils import helpers as h


class SaudiArabiaInvoicePDF(BaseInvoicePDF):

    def _item_info(self, item, description_style, options_style):
        options = []
        try:
            options = [(opt['label'], opt['value']) for opt in item.additional_info.get('product_options', [])]
        except KeyError:
            pass

        unit_price = self.vat_order.item_channel_sold_price(item)
        return [
            item.code,
            Paragraph(item.name_translation, description_style),
            Paragraph('\n'.join(f'{label}: {value}' for label, value in options), options_style),
            item.shipped_qty,
            h.format_price_attribute(unit_price, self.order.currency),
            h.format_price_attribute(item.shipped_qty * unit_price, self.order.currency)
        ]

    def _invoice_items_table(self):
        description_style = ParagraphStyle(
            'description',
            fontSize=9,
            fontName='XBZar-Bold',
        )

        options_style = ParagraphStyle(
            'options',
            fontSize=9,
            fontName='XBZar',
        )

        total_style = ParagraphStyle(
            'total',
            alignment=TA_RIGHT,
            wordWrap='LTR',
            fontSize=9,
            fontName='Arial'
        )

        table_style = [
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONT', (0, 0), (5, 0), 'XBZar', 9),
            ('FONT', (0, 1), (3, -1), 'XBZar', 9),
            ('FONT', (4, 1), (5, -1), 'Arial', 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 1 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 1 * mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1 * mm),
        ]

        rows = [
            ['SKU', 'Item Description', 'Options', 'Qty', 'Unit Price', 'Subtotal']
        ]

        rows.extend(self._item_info(item, description_style, options_style) for item in self.shipment.items)

        shipped_discount_amount = -1 * self.vat_order.vat_shipped_discount
        shipping_amount = round(self.shipment.totals.shipping / self.vat_order.vat_rate, 2)
        cod_fee = round(self.shipment.totals.cash_on_delivery / self.vat_order.vat_rate, 2)

        vat = self.vat_order.vat_total \
           + (self.shipment.totals.cash_on_delivery - cod_fee) \
           + (self.shipment.totals.shipping - shipping_amount)

        totals_rows = [
            [self._cost_format("Subtotal", self.vat_order.vat_shipped_total, total_style, self.order.currency), '', '', '', '', ''],
            [self._cost_format("Discount Amount", shipped_discount_amount, total_style, self.order.currency), '', '', '', '', ''],
            [self._cost_format("Shipping", shipping_amount, total_style, self.order.currency), '', '', '', '', ''],
            [self._cost_format("COD Fee", cod_fee, total_style, self.order.currency), '', '', '', '', ''],
            [self._cost_format(self.vat_order.vat_label, vat, total_style, self.order.currency), '', '', '', '', ''],
            [self._cost_format("Duty", self.shipment.totals.extra_fee, total_style, self.order.currency), '', '', '', '', ''],
        ]

        for i in range(1, len(totals_rows) + 1):
            table_style.append(('SPAN', (0, -i), (-1, -i)))

        table_style.append(('NOSPLIT', (0, -(len(totals_rows) + 1)), (-1, -1)))
        rows.extend(totals_rows)
        return Table(rows, style=TableStyle(table_style), spaceBefore=5*mm, colWidths=[None, 5*cm, 4*cm, 0.8*cm, None, None])

    def _shipping_terms(self, style):
        services = "COD" if self.order.is_cod else ""
        return Paragraph(f"SHIPPING TERMS: {services}", style)

    def _cost_format(self, title, cost, style, currency=None):
        currency = currency or self.order.base_currency
        cost = h.format_price_attribute(cost, currency, output_format="¤¤ #,##0.###;¤¤ -#,##0.###")
        return Paragraph(f'<font name="Arial-Bold">{title}</font>: {cost}', style)
