# -*- coding:utf-8 -*-
import abc
import io
from functools import partial
from collections import namedtuple
import os
import unicodedata

from arabic_reshaper import reshape
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Flowable,
)


class AbstractPDF(metaclass=abc.ABCMeta):

    def __init__(self, settings):
        self.settings = settings
        self.width, self.height = self.pagesize
        self.base_dir = self.settings['webassets.base_dir']
        self.img_dir = os.path.join(self.base_dir, 'img')
        self.font_dir = os.path.join(self.base_dir, 'fonts', 'pdf')
        self._buffer = io.BytesIO()
        self._register_fonts()

    @abc.abstractmethod
    def create_document(self):
        pass

    @property
    @abc.abstractmethod
    def pagesize(self):
        pass

    def _register_fonts(self):
        path = partial(os.path.join, self.font_dir)
        fonts = [
            ("Barcode", path('barcode.ttf')),
            ("Arial", path('arial_font', 'Arial.ttf')),
            ("Arial-Bold", path('arial_font', 'Arialbd.ttf')),
            ("Arial-Uni", path('arial_font', 'ARIALUNI.TTF')),
            ("XBZar", path('XBZarFont', 'XBZar.ttf')),
            ("XBZar-Bold", path('XBZarFont', 'XBZarBd.ttf')),
        ]
        for font_name, file_path in fonts:
            pdfmetrics.registerFont(TTFont(font_name, file_path))


class AbstractShipmentPDF(AbstractPDF, metaclass=abc.ABCMeta):
    pagesize = (102 * mm, 144 * mm)

    def __init__(self, settings, shipment, **kwargs):
        super().__init__(settings)
        self.shipment = shipment
        self.order = shipment.order
        self.carrier_settings = kwargs.get('carrier_settings') or shipment.carrier.get_settings(self.order.channel.code)
        self.title = kwargs.get('title') or f"shipment-{self.order.code}"


class AbstractInvoicePDF(AbstractPDF, metaclass=abc.ABCMeta):
    pagesize = A4

    def __init__(self, settings, shipment, **kwargs):
        super().__init__(settings)
        self.shipment = shipment
        self.order = shipment.order
        self.carrier_settings = kwargs.get('carrier_settings') or self.shipment.carrier.get_settings(self.order.channel.code)
        self.title = kwargs.get('title') or f"invoice-{self.order.code}"


class SimpleDocWithoutPadding(SimpleDocTemplate):

    def addPageTemplates(self, pageTemplates):
        if pageTemplates:
            f = pageTemplates[0].frames[0]
            f._leftPadding = f._rightPadding = f._topPadding = f._bottomPadding = 0
            f._geom()
        SimpleDocTemplate.addPageTemplates(self, pageTemplates)


def arabic_text(text):
    # http://stackoverflow.com/questions/8222517/use-of-arabic-rtl-in-reportlab
    is_arabic = False
    is_bidi = False
    wr_text = text

    for c in wr_text:
        cat = unicodedata.bidirectional(c)
        # detect is Arabic Letter or Arabic Number
        if cat == "AL" or cat == "AN":
            is_arabic = True
            is_bidi = True
            break
        elif cat == "R" or cat == "RLE" or cat == "RLO":
            is_bidi = True

    if is_arabic:
        wr_text = reshape(wr_text)

    if is_bidi:
        wr_text = get_display(wr_text)

    return wr_text


PDFTotals = namedtuple('PDFTotals', ['vat_text', 'discount_text', 'invoice_text'])


# TableTextRotate
class TTR(Flowable):
    """
    Rotates a text in a table cell
    http://stackoverflow.com/questions/13061545/rotated-document-with-reportlab-vertical-text
    """

    def __init__(self, text):
        Flowable.__init__(self)
        self.text = text

    def draw(self):
        self.canv.saveState()
        self.canv.rotate(90)
        self.canv.translate(1, - self.canv._fontsize / 1.2)
        self.canv.drawString(0, 0, self.text)
        self.canv.restoreState()

    def wrap(self, aW, aH):
        canv = self.canv
        fn, fs = canv._fontname, canv._fontsize
        return canv._leading, 1 + canv.stringWidth(self.text, fn, fs)
