import datetime
import os

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Image,
)
from reportlab.lib.units import cm, mm

from ...abc.pdf import AbstractShipmentPDF, SimpleDocWithoutPadding, TTR, arabic_text
from pimly.utils import helpers as h
from pimly.utils.vat import VATOrder


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

    def create_document(self):
        story = []
        for i in range(self.shipment.box_qty):
            current_page = i + 1
            story.append(Spacer(0, 2.5*cm))                  # space for static text
            story.append(self._table(current_page))
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
            colWidths=[0.4 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm],
            style=self._table_style,
            hAlign='LEFT',
            spaceAfter=0 * cm,
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
            Paragraph('<para align="center"><font size="32" name="Arial-Bold">{}</font></para>'.format(self.order.shipping_address.country), style),
        ])
        shipment_details.append([
            '',
            Paragraph(u'Custom value:<br/><font name="Arial">{}</font>'.format(
                h.format_price_attribute(VATOrder(self.shipment).vat_custom[1], self.order.currency)
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
            Paragraph(
                u'<font name="XBZar-Bold" size="7">{}, {}, {}, {}</font>'.format(
                    self.carrier_settings.account_name,
                    self.carrier_settings.account_address,
                    self.carrier_settings.account_city,
                    self.carrier_settings.account_post_code,
                ),
                style
            ),
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
        params = {
            'user_name': arabic_text(self.order.shipping_address.full_name),
            'address': arabic_text(self.order.shipping_address.address),
            'city': arabic_text(self.order.shipping_address.city),
            'country': arabic_text(self.order.shipping_address.human_country),
            'phone': self.order.shipping_address.phone,
            'fax': self.order.shipping_address.fax if self.order.shipping_address.fax else '',
        }

        consignee_details.append([
            TTR(u'Consignee Details'),
            Paragraph(u'Account<br/>'
                      u'<font name="Arial" size="8">{user_name}</font><br/>'
                      u'<font name="Arial" size="8">{address}</font><br/>'
                      u'{city}<br/>'
                      u'{country}<br/>'
                      u'T: {phone}<br/>'
                      u'T2: {fax}'.format(**params), style),
            '',
            Paragraph(u'Reference: {}'.format(self.order.code), style),
            ''
        ])
        return consignee_details

    def _static_text(self, canvas, doc):
        canvas.saveState()

        image_max_width = 1.0 * cm
        image_max_height = 1.85 * cm  # 1.85 equivalent of 60 font size for "Barcode" font

        logo_path = os.path.join(self.img_dir, "postaplus_logo.png")

        logo_img = Image(logo_path, image_max_width, image_max_height, kind='proportional')

        height_offset = (image_max_height - logo_img.drawHeight) / 2 if logo_img.drawHeight < image_max_height else 0
        logo_img.drawOn(canvas, 0.3 * cm, doc.height - 2 * cm + height_offset)

        canvas.setFont("Barcode", 60)
        canvas.drawCentredString(doc.width - 5 * cm, doc.height - 2 * cm, u"*{}*".format(self.shipment.tracking_number))
        canvas.setFont("XBZar", 8)
        canvas.drawCentredString(doc.width - 5 * cm, doc.height - 2.3 * cm, self.shipment.tracking_number)
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
        ])
