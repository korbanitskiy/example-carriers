# -*- coding:utf-8 -*-

import datetime
import os

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    Paragraph,
    Table,
    TableStyle,
    Image,
    Spacer,
)

from pimly.utils import helpers as h
from pimly.utils.vat import VATOrder
from .base import AbstractInvoicePDF, SimpleDocWithoutPadding, arabic_text, PDFTotals


class BaseInvoicePDF(AbstractInvoicePDF):
    register_info = "Registered in England | "

    def __init__(self, settings, shipment, **kwargs):
        super().__init__(settings, shipment, **kwargs)
        self.vat_order = VATOrder(shipment)
        self.doc = SimpleDocWithoutPadding(
            self._buffer,
            rightMargin=1*cm,
            leftMargin=1*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm,
            pagesize=self.pagesize,
            title=self.title,
        )

    def create_document(self):
        story = [
            self._logo(),
            self._invoice_table(),
            self._invoice_items_table(),
        ]

        self.doc.build(story, onFirstPage=self.static_text, onLaterPages=self.static_text)
        self._buffer.seek(0)
        return self._buffer

    def _logo(self):
        logo_path = os.path.join(self.img_dir, 'logo-vogacloset.png')
        return Image(logo_path, hAlign='LEFT', width=3.5*cm, height=0.5*cm)

    def _invoice_table(self):
        style = ParagraphStyle("normal")
        style.fontSize = 10
        style.fontName = 'Arial-Uni'

        rows = [
            [self._header(), None],
            [self._billing_address(style), self._shipping_address(style)],
            [self._carrier_tracking(style), self._shipping_terms(style)]
        ]

        table_style = TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('SPAN', (0, 0), (1, 0)),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
        ])

        return Table(rows, style=table_style, colWidths=[self.doc.width / 2, self.doc.width / 2], spaceBefore=5 * mm)

    def _header(self):
        centered_style = ParagraphStyle("centered_text")
        centered_style.alignment = TA_CENTER
        centered_style.leading = 16
        params = {
            'order_code': self.order.channel_code,
            'order_date': h.format_datetime(self.order.date),
            'shipped_date': h.format_date_human(datetime.datetime.now()),
        }
        return Paragraph(
            '<font name="XBZar-Bold" size="14">Invoice for Order #{order_code}</font><br/>'
            '<font name="XBZar" size="14">Order date {order_date}</font><br/>'
            '<font name="XBZar" size="14">Shipped date {shipped_date}</font><br/>'.format(**params),
            centered_style
        )

    def _billing_address(self, style):
        billing_district = self.order.billing_address.district or u''
        billing_params = {
            'full_name': arabic_text(self.order.billing_address.full_name),
            'address': arabic_text(self.order.billing_address.address),
            'district': u'{}<br/>'.format(arabic_text(billing_district)) if billing_district else u'',
            'city': arabic_text(self.order.billing_address.city),
            'country': arabic_text(self.order.billing_address.human_country),
            'telephone': arabic_text(self.order.billing_address.phone),
        }
        return Paragraph(
            u'<font name="XBZar-Bold">Billing Address:</font><br/>'
            u'{full_name}<br/>'
            u'{address}<br/>'
            u'{district}'
            u'{city}<br/>'
            u'{country}<br/>'
            u'T: {telephone}<br/>'.format(**billing_params),
            style
        )

    def _shipping_address(self, style):
        shipping_district = self.order.shipping_address.district or u''
        shipping_params = {
            'full_name': arabic_text(self.order.shipping_address.full_name),
            'address': arabic_text(self.order.shipping_address.address),
            'district': u'{}<br/>'.format(arabic_text(shipping_district)) if shipping_district else u'',
            'city': arabic_text(self.order.shipping_address.city),
            'country': arabic_text(self.order.shipping_address.human_country),
            'telephone': arabic_text(self.order.shipping_address.phone),
            'email': arabic_text(self.order.email)
        }
        return Paragraph(
            u'<font name="XBZar-Bold">Shipping Address:</font><br/>'
            u'{full_name}<br/>'
            u'{address}<br/>'
            u'{district}'
            u'{city}<br/>'
            u'{country}<br/>'
            u'T: {telephone}<br/>'
            u'{email}<br/>'.format(**shipping_params),
            style
        )

    def _carrier_tracking(self, style):
        return Paragraph(f"CARRIER TRACKING #: {self.shipment.tracking_number}", style)

    def _shipping_terms(self, style):
        return Paragraph(u'SHIPPING TERMS: {}'.format(self.order.services), style)

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

        totals_rows = []

        order_total = self._order_total(total_style)
        if order_total.discount_text:
            totals_rows.append([order_total.discount_text, '', '', '', '', ''])
        totals_rows.append([order_total.invoice_text, '', '', '', '', ''])
        if order_total.vat_text:
            totals_rows.append([order_total.vat_text, '', '', '', '', ''])

        for i in range(len(totals_rows)):
            table_style.append(('SPAN', (0, -(i+1)), (-1, -(i+1))))
        table_style.append(('NOSPLIT', (0, -(len(totals_rows)+1)), (-1, -1)))

        rows.extend(totals_rows)

        return Table(rows, style=TableStyle(table_style), spaceBefore=5*mm, colWidths=[None, 5 * cm, 4 * cm, 0.8 * cm, None, None])

    def _item_info(self, item, description_style, options_style):
        options = []
        try:
            options = [(opt['label'], opt['value']) for opt in item.additional_info.get('product_options', [])]
        except KeyError:
            pass

        unit_price = self.vat_order.item_channel_sold_price(item)

        return [
            item.code,
            Paragraph(arabic_text(item.name_translation), description_style),
            Paragraph('\n'.join(f'{label}: {value}' for label, value in options), options_style),
            item.shipped_qty,
            h.format_price_attribute(unit_price, self.order.currency, output_format="???? #,##0.###;???? -#,##0.###"),
            h.format_price_attribute(item.shipped_qty*unit_price, self.order.currency, output_format="???? #,##0.###;???? -#,##0.###")
        ]

    def _order_total(self, style):
        if self.vat_order.vat_total is not None:
            vat = h.format_price_attribute(self.vat_order.vat_total, self.order.currency, output_format=u"???? #,##0.###;???? -#,##0.###")
            vat_text = Paragraph(u'<font name="Arial-Bold">{}:</font> {}'.format(self.vat_order.vat_label, vat), style)
        else:
            vat_text = None

        discount_applied, order_vat_custom = self.vat_order.vat_custom
        order_vat_discount = self.vat_order.vat_shipped_discount
        invoice = h.format_price_attribute(order_vat_custom, self.order.currency, output_format=u"???? #,##0.###;???? -#,##0.###")
        if order_vat_discount and discount_applied:
            discount = h.format_price_attribute(-1 * order_vat_discount, self.order.currency, output_format=u"???? #,##0.###;???? -#,##0.###")
            discount_text = Paragraph(u'<font name="Arial-Bold">Discount amount:</font> {}'.format(discount), style)
            invoice_text = Paragraph(u'<font name="Arial-Bold">Total after discount:</font> {}'.format(invoice), style)
        else:
            discount_text = None
            invoice_text = Paragraph(u'<font name="Arial-Bold">Total:</font> {}'.format(invoice), style)
        return PDFTotals(vat_text, discount_text, invoice_text)

    def static_text(self, canvas, doc):
        canvas.setFont("XBZar", 8)
        canvas.drawString(doc.leftMargin, doc.bottomMargin - 0.5 * cm, self.register_info)


class EnigmoInvoicePDF(BaseInvoicePDF):
    register_info = "Registered in England | "

    def _logo(self):
        return Spacer(width=1, height=1, isGlue=True)

    def _shipping_address(self, style):
        shipping_district = self.order.shipping_address.district or u''
        shipping_params = {
            'full_name': arabic_text(self.order.shipping_address.full_name),
            'address': arabic_text(self.order.shipping_address.address),
            'district': u'{}<br/>'.format(arabic_text(shipping_district)) if shipping_district else u'',
            'city': arabic_text(self.order.shipping_address.city),
            'country': arabic_text(self.order.shipping_address.human_country),
            'telephone': arabic_text(self.order.shipping_address.phone),
        }
        return Paragraph(
            u'<font name="XBZar-Bold">Shipping Address:</font><br/>'
            u'{full_name}<br/>'
            u'{address}<br/>'
            u'{district}'
            u'{city}<br/>'
            u'{country}<br/>'
            u'T: {telephone}<br/>'.format(**shipping_params),
            style
        )


class BoohooMENAInvoicePDF(BaseInvoicePDF):
    register_info = "Registered in England | "

    def _logo(self):
        logo_path = os.path.join(self.img_dir, 'logo-boohoo.png')
        return Image(logo_path, hAlign='LEFT', width=3.5 * cm, height=0.9 * cm)
