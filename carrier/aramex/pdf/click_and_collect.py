from reportlab.graphics.barcode import code128
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import white, black
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    Table,
    TableStyle,
    PageBreak,
)

from pimly.utils import helpers as h
from pimly.utils.vat import VATOrder
from ...abc.pdf import AbstractShipmentPDF, SimpleDocWithoutPadding, arabic_text
from .routing_code import routing_code


class ShipmentPDF(AbstractShipmentPDF):
    pagesize = (144 * mm, 102 * mm)

    def __init__(self, settings, shipment, **kwargs):
        super().__init__(settings, shipment, **kwargs)
        self.doc = SimpleDocWithoutPadding(
            self._buffer,
            rightMargin=1 * mm,
            leftMargin=1 * mm,
            topMargin=1 * mm,
            bottomMargin=1 * mm,
            pagesize=self.pagesize,
            title=self.title,
        )
        self.routing_code = routing_code(self.order)

    def create_document(self):
        story = []
        for i in range(self.shipment.box_qty):
            current_page = i + 1
            story.append(self._black_back_color("Hold for Pick Up at Branch"))
            story.append(self._header_table(current_page))
            story.append(self._shipping_info())
            story.append(PageBreak())

        self.doc.build(story)
        self._buffer.seek(0)
        return self._buffer

    def _header_table(self, page_num):
        style = ParagraphStyle('header_table')
        style.fontName = 'Arial'
        style.fontSize = 8
        style.spaceAfter = 2 * mm

        routing_style = ParagraphStyle(
            'routing_code',
            fontName='Arial-Bold',
            fontSize=22,
            alignment=TA_CENTER,
            spaceBefore=0,
        )

        bold = '<font name="Arial-Bold" size="10">{}</font><br/>'
        params = {
            'product_type': bold.format('CAC'),
            'origin': bold.format('LON'),
            'payment_type': bold.format('P'),
            'date': bold.format(h.format_date_human(self.shipment.shipped_date)),
            'foreign_ref': bold.format(self.order.code),
            'product_group': bold.format('EXP'),
            'destination': bold.format(self.order.shipping_address.country),
            'pieces': bold.format(f'{page_num}/{self.shipment.box_qty}'),
        }
        rows = []
        rows.append([
            [
                Paragraph('Product Type: {product_type}'.format(**params), style),
                Paragraph('Origin: {origin}'.format(**params), style),
                Paragraph('Payment type: {payment_type}'.format(**params), style),
                Paragraph('Date: {date}'.format(**params), style),
                Paragraph('Foreign Ref: {foreign_ref}'.format(**params), style)
             ],
            [
                Paragraph('Product Group: {product_group}'.format(**params), style),
                Paragraph('Destination: {destination}'.format(**params), style),
                Paragraph('Pieces: {pieces}'.format(**params), style),
                Paragraph('Ref1: {foreign_ref}'.format(**params), style),
            ],
            self._barcode()
        ])
        rows.append([
            '',
            '',
            Paragraph(self.routing_code, routing_style) if self.routing_code else ''
        ])

        table_style = TableStyle([
            ('SPAN', (0, 0), (0, 1)),
            ('SPAN', (1, 0), (1, 1)),
            ('BOX', (0, 0), (-1, -1), 0.5, black),
            ('GRID', (-1, 0), (-1, -1), 0.5, black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
            ('TOPPADDING', (-1, -1), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, -1), (0, -1), 0),
        ])

        table = Table(
            data=rows,
            style=table_style,
            hAlign='LEFT',
            spaceAfter=0*mm,
            spaceBefore=0*mm,
            colWidths=[None, None, 6.3*cm],
            rowHeights=(2.3 * cm, 1 * cm),
        )
        return table

    def _barcode(self):
        barcode = code128.Code128(
            self.shipment.tracking_number,
            quiet=True,
            humanReadable=True,
            fontSize=20,
            fontName='Arial',
            checksum=0,
            barWidth=1.18,
            barHeight=15 * mm
        )

        return barcode

    @staticmethod
    def _black_back_color(label, border_padding=(0, 0.25), font_name='Arial-Bold', align_left=False):
        style = ParagraphStyle(
            'black',
            fontName=font_name,
            fontSize=16,
            leading=20,
            borderPadding=border_padding,
            alignment=TA_LEFT if align_left else TA_CENTER,
            textColor=white,
            backColor=black,
            spaceAfter=0,
        )

        return Paragraph(label, style)

    def _shipping_info(self):
        style = ParagraphStyle(
            'shipping_info',
            fontName='Arial',
            fontSize=8,
            spaceAfter=0,
            spaceBefore=0,
        )
        bold = '<font name="Arial-Bold">{}</font><br/>'
        carrier_settings = self.shipment.carrier.get_settings(self.order.channel.code)
        shipment_cost = self.shipment.totals.total
        params = {
            'weight': '0.5 KG',
            'goods_value': h.format_price_attribute(VATOrder(self.shipment).vat_custom_additional, self.order.currency),
            'cod': h.format_price_attribute(shipment_cost, self.order.currency) if shipment_cost else '',
            'services': self.order.services,
            'description': 'Clothing items',
            'acc_name': carrier_settings.account_name,
            'acc_number': carrier_settings.account_number,
            'user_name': arabic_text(self.order.shipping_address.full_name),
            'user_phone': self.order.shipping_address.phone,
            'point_name': self.order.shipping_info['description'],
            'point_city': self.order.shipping_info['address']['city'],
            'point_phone': self.order.shipping_info['phone'],
            'point_address': '{}; {}'.format(
                self.order.shipping_info['address']['address'],
                self.order.shipping_info['description'],
            )
        }
        rows = [[
            Paragraph(bold.format('Weight'), style), Paragraph('{weight}'.format(**params), style),
            Paragraph(bold.format('Chargeable'), style), Paragraph('{weight}'.format(**params), style),
        ], [
            Paragraph(bold.format('Goods value'), style), Paragraph('{goods_value}'.format(**params), style),
            Paragraph(bold.format('COD Amount'), style), Paragraph('{cod}'.format(**params), style),
        ], [
            Paragraph(bold.format('Services'), style), Paragraph('{services}'.format(**params), style),
            Paragraph(bold.format('Description'), style), Paragraph('{description}'.format(**params), style),
        ], [
            Paragraph(bold.format('Account name'), style), Paragraph('{acc_name}'.format(**params), style),
            Paragraph(bold.format('Account #'), style), Paragraph('{acc_number}'.format(**params), style),
        ], [
            Paragraph(bold.format('Cnee Name'), style), Paragraph('{user_name}'.format(**params), style),
            Paragraph(bold.format('Cnee Phone #'), style), Paragraph('{user_phone}'.format(**params), style),
        ], [
            self._black_back_color("PKUP", align_left=True),
            self._black_back_color('{point_name}'.format(**params), font_name='Arial', align_left=True)
        ], [
            Paragraph(bold.format('Branch entity'), style), Paragraph("", style),
            Paragraph(bold.format('Branch City'), style), Paragraph('{point_city}'.format(**params), style),
        ], [
            Paragraph(bold.format('Branch number'), style), Paragraph('{point_phone}'.format(**params), style),
            Paragraph(bold.format('Branch Address'), style), Paragraph('{point_address}'.format(**params), style),
        ]]
        table_style = [
            ('SPAN', (1, 5), (-1, 5)),
            ('BOX', (0, 0), (-1, -1), 0.5, black),
            ('GRID', (0, 0), (-1, -1), 0.5, black),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 5), (-1, 5), black)
        ]

        table = Table(
            data=rows,
            style=TableStyle(table_style),
            spaceBefore=0 * mm,
            hAlign='LEFT',
            spaceAfter=0 * mm,
            colWidths=[2.7*cm, None, 2.8*cm, 5*cm]
        )

        return table
