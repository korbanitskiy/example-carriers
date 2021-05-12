# coding: utf8

import datetime
import os
from copy import copy
from decimal import Decimal

from reportlab.graphics.shapes import Circle, Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak, Image

from pimly.utils import helpers as h
from pimly.utils.vat import VATOrder
from ..api import NaqelOrderAPI
from ..city_codes import get_city_code
from ...abc.pdf import AbstractShipmentPDF, SimpleDocWithoutPadding, TTR, arabic_text


class ShipmentPDF(AbstractShipmentPDF):

    def __init__(self, settings, shipment, **kwargs):
        super().__init__(settings, shipment, **kwargs)
        self.naqel_api = NaqelOrderAPI(self.shipment, settings)
        self.doc = SimpleDocWithoutPadding(
            self._buffer,
            rightMargin=1*mm,
            leftMargin=1*mm,
            topMargin=1*mm,
            bottomMargin=1*mm,
            pagesize=self.pagesize,
            title=self.title,
            showBoundary=True,
        )

    def create_document(self):
        story = []
        for i in range(self.shipment.box_qty):
            current_page = i + 1
            story.append(Spacer(0, 2.5 * cm))                    # space for static text
            story.append(self._table(current_page))
            story.append(self._tracking_number(current_page))
            story.append(PageBreak())
        self.doc.build(story, onFirstPage=self._static_text, onLaterPages=self._static_text)
        self._buffer.seek(0)
        return self._buffer

    def _table(self, current_page):
        style = ParagraphStyle('Table')
        style.wordWrap = 'LTR'
        style.fontName = 'XBZar'
        style.fontSize = 8

        table_data = [[Paragraph(u'Reference', style), '', '', '', '']]
        table_data.extend(self._shipment_details(style, current_page))
        table_data.extend(self._shipper_details(style))
        table_data.extend(self._consignee_details(style))
        table = Table(
            table_data,
            colWidths=[0.4 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm],
            style=self._table_style,
            hAlign='LEFT',
            spaceAfter=0 * cm,
        )
        return table

    def _shipment_details(self, style, current_page):
        shipment_details = []
        shipment_cost = self.shipment.totals.total
        format_cod_value = h.format_price_attribute(shipment_cost, self.order.currency) if shipment_cost else '0'
        circle_drawing = Drawing(10, 10)
        circle_drawing.add(Circle(25, -7.5, 14, fillColor=colors.black))
        order_vat_custom = VATOrder(self.shipment).vat_custom[1]
        clearance_marker = circle_drawing if Decimal('1000.00') < order_vat_custom else ''

        cdb_cities = [self.order.shipping_address.city]
        cdb_cities.extend(self.order.shipping_address.base_cities)
        city_code = get_city_code(self.order.shipping_address.country, cdb_cities)[:3]
        shipment_details.append([
            TTR(u'Shipment details'),
            Paragraph(u'Origin:<br/>'
                      u'<font size="15" name="XBZar-Bold">{}</font>'.format(self.carrier_settings.location), style),
            Paragraph(u'Destination:<br/>'
                      u'<font size="10" name="XBZar-Bold">{}</font>'.format(city_code), style),
            Paragraph(u'Product:<br/>'
                      u'<font size="15" name="XBZar-Bold">{}</font>'.format(self.carrier_settings.product_type), style),
            '',
        ])
        shipment_details.append([
            '',
            Paragraph(u'Weight: <font name="XBZar-Bold">0.5 kg</font><br/>'
                      u'Chargeable: <font name="XBZar-Bold">0.5 kg</font>', style),
            Paragraph(u'Description of goods:<br/>'
                      u'<font size="10" name="XBZar-Bold">{}</font>'.format(self.carrier_settings.goods_description), style),
            '',
            clearance_marker,
        ])
        shipment_details.append([
            '',
            Paragraph(u'Custom value:<br/><font name="Arial">{}</font>'.format(
                h.format_price_attribute(order_vat_custom, self.order.currency)
            ), style),
            Paragraph(u'Goods origin:<br/>{}'.format(self.carrier_settings.goods_origin), style),
            Paragraph(u'COD value:<br/>'
                      u'<font size="8" name="Arial-Bold">{}</font>'.format(format_cod_value), style),
            Paragraph(u'<font name="XBZar-Bold">PCS</font>: '
                      u'<font size="14" name="XBZar-Bold">{}/{}</font>'.format(current_page, self.shipment.box_qty),
                      style),
        ])
        return shipment_details

    def _shipper_details(self, style):
        shipper_details = []
        shipper_details.append([
            TTR(u'Shipper Details'),
            Paragraph(u'Account: <font name="XBZar-Bold" size="7">{}</font><br/>'
                      u'<font name="XBZar-Bold" size="7">{}, {} {}</font>'.format(self.carrier_settings.account_number,
                                                                                  self.carrier_settings.account_name,
                                                                                  self.carrier_settings.account_address,
                                                                                  self.carrier_settings.account_post_code,
                                                                                  ),
                      style),
            '',
            Paragraph(u'Tel:<font name="XBZar-Bold" size="8">{}</font>'.format(self.carrier_settings.telephone), style),
            Paragraph(u'Services:<br/><font name="XBZar-Bold" size="8">{}</font>'.format(self.order.services), style),
        ])
        shipper_details.append([
            '',
            '',
            '',
            '',
            Paragraph(u'Label Date:<br/>'
                      u'<font name="XBZar-Bold" size="8">{}</font>'.format(h.format_date_human(datetime.datetime.now())), style),
        ])
        return shipper_details

    def _consignee_details(self, style):
        consignee_details = []

        center_style = copy(style)
        center_style.alignment = TA_CENTER

        order_district = self.order.shipping_address.district or u''
        cdb_cities = [self.order.shipping_address.city]
        cdb_cities.extend(self.order.shipping_address.base_cities)
        city_code = get_city_code(self.order.shipping_address.country, cdb_cities)[:3]
        user_name = arabic_text(self.order.shipping_address.full_name)
        address = arabic_text(self.order.shipping_address.address)
        district = u'{}<br/>'.format(arabic_text(order_district)) if order_district else u''
        country = arabic_text(self.order.shipping_address.human_country)
        phone = self.order.shipping_address.phone
        fax = self.order.shipping_address.fax if self.order.shipping_address.fax else ''
        city = arabic_text(self.order.shipping_address.city)

        consignee_details.append([
            TTR(u'Consignee Details'),
            Paragraph(u'Account<br/>'
                      u'<font name="XBZar" size="8">{}</font><br/>'
                      u'<font name="XBZar" size="8">{}</font><br/>'.format(user_name, address), style),
            '',
            '',
            ''
        ])

        consignee_details.append([
            '',
            Paragraph(u'{}{}<br/>'.format(district, country), style),
            '',
            Paragraph(u'Reference: {}'.format(self.order.code), style),
            ''
        ])

        consignee_details.append([
            '',
            Paragraph(u'T: {}<br/>T2: {}'.format(phone, fax), style),
            '',
            Paragraph(city, style),
            Paragraph('<font name="XBZar-Bold" size="10">{}</font><br/>{}'.format(city_code, country), center_style)
        ])
        return consignee_details

    def _tracking_number(self, current_page):
        centered_style = ParagraphStyle("centered_text")
        centered_style.wordWrap = 'LTR'
        centered_style.alignment = TA_CENTER
        centered_style.leading = 10

        hawb_number = self.shipment.tracking_number

        return Paragraph(u'<font name="Barcode" size="52">*{hawb_number}{current_page:05d}*</font><br/>'
                         u'<font name="XBZar" size="8">{hawb_number}{current_page:05d}</font><br/>'
                         .format(**locals()), centered_style)

    def _static_text(self, canvas, doc):
        canvas.saveState()
        hawb_number = self.shipment.tracking_number

        logo_path = os.path.join(self.img_dir, "naqel_logo.png")
        logo_img = Image(logo_path, width=2.3*cm, height=1.3*cm, kind='proportional')
        logo_img.drawOn(canvas, 0.5*cm, doc.height - 1.7*cm)

        canvas.setFont("Barcode", 60)
        canvas.drawCentredString(doc.width - 3.5*cm, doc.height - 2*cm, u"*{}*".format(hawb_number))

        canvas.setFont("XBZar", 8)
        canvas.drawCentredString(doc.width - 3.5 * cm, doc.height - 2.3 * cm, hawb_number)

        canvas.restoreState()

    @property
    def _table_style(self):
        return TableStyle([
            # Shipment details
            ('SPAN', (0, 0), (4, 0)),
            ('SPAN', (0, 1), (0, 3)),
            ('SPAN', (3, 1), (4, 1)),
            ('SPAN', (2, 2), (3, 2)),

            ('INNERGRID', (0, 0), (4, 3), 0.25, colors.black),
            ('LINEABOVE', (0, 0), (4, 0), 0.25, colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONT', (0, 1), (0, 3), 'XBZar', 10),
            ('VALIGN', (0, 1), (0, 3), 'MIDDLE'),

            # Shipper Details Style
            ('SPAN', (0, 4), (0, 5)),
            ('SPAN', (1, 4), (2, 5)),
            ('SPAN', (3, 4), (3, 5)),
            ('LINEABOVE', (0, 4), (4, 4), 0.25, colors.black),
            ('LINEBEFORE', (1, 4), (1, 5), 0.25, colors.black),
            ('LINEBEFORE', (4, 4), (4, 5), 0.25, colors.black),
            ('INNERGRID', (4, 4), (4, 5), 0.25, colors.black),
            ('FONT', (0, 4), (0, 5), 'XBZar', 10),
            ('VALIGN', (0, 4), (0, 5), 'BOTTOM'),
            ('VALIGN', (3, 4), (3, 5), 'BOTTOM'),
            ('VALIGN', (1, 4), (2, 4), 'MIDDLE'),
            ('VALIGN', (4, 4), (4, 5), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 4), (0, 5), 1 * mm),
            ('TOPPADDING', (0, 4), (0, 5), 1 * mm),

            # Consignee Details
            ('SPAN', (0, 6), (0, 8)),
            ('SPAN', (1, 6), (3, 6)),
            ('SPAN', (1, 7), (2, 7)),
            ('SPAN', (3, 7), (4, 7)),
            ('SPAN', (1, 8), (2, 8)),
            ('LINEABOVE', (0, 6), (-1, 6), 0.25, colors.black),
            ('LINEBEFORE', (1, 6), (1, 8), 0.25, colors.black),
            ('LINEBELOW', (0, 8), (-1, 8), 0.25, colors.black),
            ('VALIGN', (0, 6), (0, 6), 'BOTTOM'),
            ('VALIGN', (3, 6), (3, 6), 'BOTTOM'),
            ('VALIGN', (4, 6), (4, 6), 'BOTTOM'),
            ('VALIGN', (3, 8), (3, 8), 'BOTTOM'),
            ('FONT', (0, 6), (0, 6), 'XBZar', 10),
        ])
