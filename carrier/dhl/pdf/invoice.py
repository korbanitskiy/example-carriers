# -*- coding:utf-8 -*-

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    Table,
    TableStyle,
)

from pimly.utils import helpers as h
from ...abc.pdf import BaseInvoicePDF


class DHLInvoicePDF(BaseInvoicePDF):

    def _item_info(self, item, description_style, options_style):
        options = []
        try:
            options = [(opt['label'], opt['value']) for opt in item.additional_info.get('product_options', [])]
        except KeyError:
            pass

        unit_price = self.vat_order.base_item_channel_sold_price(item)

        return [
            item.code,
            Paragraph(item.name_translation, description_style),
            Paragraph('\n'.join(f'{label}: {value}' for label, value in options), options_style),
            item.shipped_qty,
            h.format_price_attribute(unit_price, self.order.base_currency),
            h.format_price_attribute(item.shipped_qty * unit_price, self.order.base_currency)
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
            fontName='Arial',
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

        shipped_items = self.shipment.items
        rows.extend(self._item_info(item, description_style, options_style) for item in shipped_items)

        base_customs_duty = (self.vat_order.base_vat_total or 0) + self.shipment.totals.base_extra_fee
        base_domestic_delivery_charge = self.shipment.totals.base_shipping - self.shipment.totals.base_shipping_discount
        base_total_shipping_cost = 0
        total_shipping_cost = 0
        customs_duty = (self.vat_order.vat_total or 0) + self.shipment.totals.extra_fee
        domestic_delivery_charge = self.shipment.totals.shipping - self.shipment.totals.shipping_discount
        if self.shipment.totals.base_total:
            total_cod = self.vat_order.vat_custom[1] \
                        + total_shipping_cost \
                        + customs_duty \
                        + self.shipment.totals.cash_on_delivery \
                        + domestic_delivery_charge \
                        - self.shipment.totals.store_credit
        else:
            total_cod = 0

        totals_rows = []

        discount_applied, base_vat_custom = self.vat_order.base_vat_custom
        if discount_applied:
            base_shipped_discount_amount = -1 * self.vat_order.base_vat_shipped_discount
            totals_rows.append([self._cost_format("Discount amount", base_shipped_discount_amount, total_style), '', '', '', '', ''])
            totals_rows.append([self._cost_format("Goods value after discount", base_vat_custom, total_style), '', '', '', '', ''])
        else:
            totals_rows.append([self._cost_format("Goods value", base_vat_custom, total_style), '', '', '', '', ''])
        totals_rows.append([self._cost_format("Total shipping cost", base_total_shipping_cost, total_style), '', '', '', '', ''])
        totals_rows.append([self._cost_format("Customs duty", base_customs_duty, total_style), '', '', '', '', ''])
        totals_rows.append([self._cost_format("COD charges", self.shipment.totals.cash_on_delivery, total_style), '', '', '', '', ''])
        totals_rows.append([self._cost_format("Domestic delivery charge", base_domestic_delivery_charge, total_style), '', '', '', '', ''])
        totals_rows.append([self._cost_format("Shipment declared value", base_vat_custom, total_style), '', '', '', '', ''])
        totals_rows.append([self._cost_format("Total COD after store credit", total_cod, total_style, self.order.currency), '', '', '', '', ''])

        for i in range(len(totals_rows)):
            table_style.append(('SPAN', (0, -(i+1)), (-1, -(i+1))))
        table_style.append(('NOSPLIT', (0, -(len(totals_rows)+1)), (-1, -1)))

        rows.extend(totals_rows)

        return Table(rows, style=TableStyle(table_style), spaceBefore=5 * mm, colWidths=[None, 5 * cm, 4 * cm, 0.8 * cm, None, None])

    def _cost_format(self, title, cost, style, currency=None):
        currency = currency or self.order.base_currency
        cost = h.format_price_attribute(cost, currency, output_format="¤¤ #,##0.###;¤¤ -#,##0.###")
        return Paragraph(f'<font name="Arial-Bold">{title}:</font> {cost}', style)
