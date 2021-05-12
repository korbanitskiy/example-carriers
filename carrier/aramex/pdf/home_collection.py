import datetime

from reportlab.lib import colors, enums
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.graphics.barcode import code128
from reportlab.platypus import (
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

from pimly.utils import helpers as h
from pimly.utils.vat import VATOrder
from ...abc.pdf import AbstractShipmentPDF, SimpleDocWithoutPadding, TTR, arabic_text
from .routing_code import routing_code


class ShipmentPDF(AbstractShipmentPDF):

    def __init__(self, settings, shipment, **kwargs):
        super().__init__(settings, shipment, **kwargs)
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
        self.routing_code = routing_code(self.order)

    def create_document(self):
        story = []
        for i in range(self.shipment.box_qty):
            current_page = i + 1
            story.append(Spacer(0, 2.5*cm))                   # space for static text
            story.append(self._table(current_page))
            story.append(self._remarks)
            story.append(PageBreak())
        self.doc.build(story, onFirstPage=self._static_text, onLaterPages=self._static_text)
        self._buffer.seek(0)
        return self._buffer

    def _table(self, current_number):
        style = ParagraphStyle('Table')
        style.wordWrap = 'LTR'
        style.fontName = 'XBZar'
        style.fontSize = 8

        table_data = [[Paragraph(u'Reference', style), '', '', '', '']]
        table_data.extend(self._shipment_details(style, current_number))
        table_data.extend(self._shiper_details(style))
        table_data.extend(self._consignee_details(style))
        table = Table(
            data=table_data,
            colWidths=[0.4*cm, 2*cm, 2*cm, 2*cm, 2*cm],
            style=self._table_style,
            hAlign='LEFT',
        )
        return table

    def _shipment_details(self, style, current_number):
        shipment_details = []
        shipment_cost = self.shipment.totals.total
        format_cod_value = h.format_price_attribute(shipment_cost, self.order.currency) if shipment_cost else ''

        shipment_details.append([
            TTR(u'Shipment details'),
            Paragraph(u'Origin:<br/>'
                      u'<font size="15" name="XBZar-Bold">{}</font>'.format(self.carrier_settings.location), style),
            Paragraph(u'Destination:<br/>'
                      u'<font size="10" name="XBZar-Bold">{}</font>'.format(self.order.shipping_address.human_country), style),
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
            self._routing(self.routing_code) if self.routing_code else '',
        ])
        shipment_details.append([
            '',
            Paragraph(u'Custom value:<br/><font name="Arial">{}</font>'.format(
                h.format_price_attribute(VATOrder(self.shipment).vat_custom_additional, self.order.currency)
            ), style),
            Paragraph(u'Goods origin:<br/>{}'.format(self.carrier_settings.goods_origin), style),
            Paragraph(u'COD value:<br/>'
                      u'<font size="8" name="Arial-Bold">{}</font>'.format(format_cod_value), style),
            Paragraph(u'<font name="XBZar-Bold">PCS</font>: '
                      u'<font size="14" name="XBZar-Bold">{}/{}</font>'.format(current_number, self.shipment.box_qty),
                      style),
        ])
        return shipment_details

    def _shiper_details(self, style):
        shiper_details = []
        shiper_details.append([
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
        shiper_details.append([
            '',
            '',
            '',
            '',
            Paragraph(u'Pickup Date:<br/>'
                      u'<font name="XBZar-Bold" size="8">{}</font>'.format(h.format_date_human(datetime.datetime.now())), style),
        ])
        return shiper_details

    def _consignee_details(self, style):
        consignee_details = []
        district = self.order.shipping_address.district or u''
        location = 'Geolocation provided' if self.order.shipping_address.latitude and self.order.shipping_address.longitude else ''
        params = {
            'user_name': arabic_text(self.order.shipping_address.full_name),
            'address': arabic_text(self.order.shipping_address.address),
            'district': u'{}<br/>'.format(arabic_text(district)) if district else u'',
            'city': arabic_text(self.order.shipping_address.city),
            'zip_code': u'{}<br/>'.format(self.order.shipping_address.postcode) if self.order.shipping_address.postcode else u'',
            'country': arabic_text(self.order.shipping_address.human_country),
            'phone': self.order.shipping_address.phone,
            'fax': self.order.shipping_address.fax if self.order.shipping_address.fax else '',
        }

        consignee_details.append([
            TTR(u'Consignee Details'),
            Paragraph(u'Account<br/>'
                      u'<font name="Arial-Uni" size="8">{user_name}</font><br/>'
                      u'<font name="Arial-Uni" size="8">{address}</font><br/>'
                      u'<font name="Arial-Uni" size="8">{district}</font>'
                      u'<font name="Arial-Uni" size="8">{city}</font><br/>'
                      u'{zip_code}'
                      u'<font name="Arial-Uni" size="8">{country}</font><br/>'
                      u'T: {phone}<br/>'
                      u'T2: {fax}'.format(**params), style),
            '',
            Paragraph(u'Reference: {order_code}<br/>{location}'.format(order_code=self.order.code, location=location), style),
            ''
        ])
        return consignee_details

    def _static_text(self, canvas, doc):
        barcode = code128.Code128(
            self.shipment.tracking_number,
            quiet=True,
            humanReadable=True,
            fontSize=8,
            fontName='XBZar',
            checksum=0,
            barWidth=1.6,
            barHeight=19 * mm
        )
        barcode.drawOn(canvas, doc.width / 2 - barcode.width / 2, doc.height - 2 * cm)

        canvas.saveState()
        canvas.setFont('XBZar', 8)
        canvas.drawString(2 * mm, 2 * mm, u"Printed on {}".format(h.format_datetime_human_short(datetime.datetime.now())))
        canvas.restoreState()

    @property
    def _remarks(self):
        style = ParagraphStyle('Remark')
        style.fontName = 'XBZar'
        style.wordWrap = 'LTR'
        style.fontSize = 12
        style.leftIndent = 2 * mm
        return Paragraph(u"Remarks: Please deliver on Free Domicile Basis", style)

    @staticmethod
    def _routing(code):
        style = ParagraphStyle(
            'routing_code',
            fontName='Arial-Bold',
            fontSize=20,
            alignment=enums.TA_CENTER,
            textColor=colors.white,
            backColor=colors.black,
        )
        return Paragraph(code, style)

    @property
    def _table_style(self):
        table_style = [
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
            ('SPAN', (1, 6), (2, 6)),
            ('SPAN', (3, 6), (4, 6)),
            ('LINEABOVE', (0, 6), (4, 6), 0.25, colors.black),
            ('LINEBEFORE', (1, 6), (1, 6), 0.25, colors.black),
            ('LINEBELOW', (0, 6), (-1, 6), 0.25, colors.black),
            ('VALIGN', (0, 6), (0, 6), 'BOTTOM'),
            ('FONT', (0, 6), (0, 6), 'XBZar', 10),
            ('BOTTOMPADDING', (0, 6), (0, 6), 1 * mm),
            ('TOPPADDING', (0, 6), (0, 6), 1 * mm),
            ('VALIGN', (1, 6), (4, 6), 'MIDDLE'),
            ('VALIGN', (4, 2), (4, 2), 'MIDDLE'),
            ('BOTTOMPADDING', (4, 2), (4, 2), 5 * mm),
        ]
        if self.routing_code:
            table_style.append(('BACKGROUND', (4, 2), (4, 2), colors.black))
        return TableStyle(table_style)
