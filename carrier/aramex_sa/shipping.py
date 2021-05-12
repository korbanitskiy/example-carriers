import base64
import io
import os
from datetime import datetime
from itertools import chain

from lxml import etree
from lxml.builder import E

from pimlib.utils.files import ensure_dir

from pimly.models import enum
from pimly.utils.vat import VATOrder

from .api import AramexSAOrderAPI
from .pdf import home_collection
from .pdf.invoice import SaudiArabiaInvoicePDF
from ..abc.exc import SendingOrderDelayed
from ..abc.shipping import AbstractShippingService, TrackingNumberMixin


class AramexSAShippingService(TrackingNumberMixin, AbstractShippingService):
    carrier_name = enum.CarrierName.aramex_sa

    def __init__(self, settings, channel_code):
        super().__init__(settings, channel_code)
        self.local_path = os.path.join(self.settings['pimly.carriers.main_path'], self.carrier_name.name, 'shipping_files')

    def can_send_shipment(self, shipment):
        return shipment.delivery_type == enum.DeliveryType.local_country and self.tracking_number_qs.count() > 0

    def create_shipping_document(self, shipment):
        pdf_creator = home_collection.ShipmentPDF(self.settings, shipment)
        return pdf_creator.create_document()

    def create_invoice_document(self, shipment):
        pdf_creator = SaudiArabiaInvoicePDF(self.settings, shipment)
        return pdf_creator.create_document()

    def _send_shipment(self, shipment):
        shipment.tracking_number = self.get_tracking_number()
        self._send_shipping_information(shipment)
        return shipment.tracking_number

    def _resend_shipment(self, shipment):
        raise SendingOrderDelayed("Resend for Aramex SA carrier is not allowed")

    def _send_shipping_information(self, shipment):
        shipping_xml = self._create_shipping_xml(shipment)
        self._save_shipping_xml(shipment.order, shipping_xml)
        api = AramexSAOrderAPI(self.settings)
        api.send_shipping_file(shipping_xml)

    def _create_shipping_xml(self, shipment):
        waybill_document = self.create_waybill_document(shipment, carrier_settings=self.carrier_settings)
        shipping_xml = HomeCollectionShippingXML(shipment, waybill_document, self.carrier_settings)
        return shipping_xml.create()

    def _save_shipping_xml(self, order, shipping_xml):
        file_path = os.path.join(self.local_path, f"{order.code}.xml")
        ensure_dir(self.local_path)
        with open(file_path, 'wb') as f:
            f.write(shipping_xml.getvalue())
        shipping_xml.seek(0)


class HomeCollectionShippingXML:

    def __init__(self, shipment, waybill_document, carrier_settings):
        self.shipment = shipment
        self.order = shipment.order
        self.vat_order = VATOrder(shipment)
        self.waybill_document = waybill_document
        self.carrier_settings = carrier_settings
        self.time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        self.entity_id = self.carrier_settings.entity_id
        self.entity_pin = self.carrier_settings.entity_pin
        self.account_number = self.carrier_settings.account_number
        self.account_post_code = self.carrier_settings.account_post_code

    def create(self):
        buffer = io.BytesIO()
        document = etree.ElementTree(
            E.InfoLinkDocument(
                self._access_request(),
                self._hawb(),
            )
        )
        document.write(buffer)
        buffer.seek(0)
        return buffer

    def _access_request(self):
        return E.AccessRequest(
            E.DocumentType('215'),
            E.EntityID(self.entity_id),
            E.EntityPIN(self.entity_pin),
            E.Version('1.00'),
            E.TimeStamp(self.time),
            E.ReplyEmailAddress(),
            E.Reference1(),
            E.Reference2(),
            E.Reference3(),
            E.Reference4(),
            E.Reference5(),
        )

    def _hawb(self):
        hawbs = chain(
            self._order_info(),
            self._shipper_info(),
            self._consignee_info(),
            self._remarks(),
            self._items(),
        )
        return E.HAWB(*hawbs)

    def _order_info(self):
        return [
            E.HAWBNumber(self.shipment.tracking_number),
            E.ForeignHAWBNumber(),
            E.HAWBOriginEntity(self.carrier_settings.location),
            E.OriginLocationCode(self.carrier_settings.location),
            E.ProductType(self.carrier_settings.product_type),
            E.PickupDate(self.time),
            E.Pieces(str(self.shipment.box_qty)),
            E.HAWBWeight('0.5'),
            E.ChargeableWeight('0.5'),
            E.HAWBWeightUnit('KG'),
            E.Cube(),
            E.CubeUnit('m3'),
            E.HAWBProductGroup(self.carrier_settings.product_group),
            E.PaymentType('P'),
            E.CommodityCountryCode(self.carrier_settings.goods_origin),
            E.CommodityDescription(self.carrier_settings.goods_description),
            E.CustomsAmount(str(self.vat_order.vat_custom_additional)),
            E.CustomsCurrencyCode(str(self.order.currency))
        ]

    def _shipper_info(self):
        return [
            E.ShipperName(self.carrier_settings.account_name),
            E.ShipperAddress(self.carrier_settings.account_address),
            E.ShipperNumber(self.account_number),
            E.ShipperReference(self.order.code),
            E.ShipperReference2(),
            E.ShipperTelephone('0'),
            E.ShipperCity(self.carrier_settings.account_city),
            E.ShipperZipCode(self.account_post_code),
            E.ShipperCountry(),
            E.ShipperCountryCode(self.carrier_settings.goods_origin),
            E.SentBy(self.carrier_settings.account_name),
        ]

    def _consignee_info(self):
        return [
            E.ConsigneeName(self.order.shipping_address.full_name),
            E.ConsigneeAddress(f"{self.order.shipping_address.district or ''}, {self.order.shipping_address.address}, {self.order.shipping_address.city}"),
            E.ConsigneeCity(self.order.shipping_address.base_city or self.order.shipping_address.city),
            E.ConsigneeZipCode(self.order.shipping_address.postcode or ''),
            E.ConsigneeCountryCode(self.order.shipping_address.country),
            E.ConsigneeTelephone(self.order.shipping_address.phone),
            E.ConsTelephone2(self.order.shipping_address.fax or ''),
            E.ConsLatitude(self.order.shipping_address.latitude or ''),
            E.ConsLongitude(self.order.shipping_address.longitude or ''),
            E.ConsigneeEmail(self.order.email or ''),
            E.ConsigneeReference(),
            E.ConsigneeReference2(self.order.email or ''),
            E.AttentionOf(self.order.shipping_address.full_name),
        ]

    def _remarks(self):
        return [
            E.HAWBThirdPartyEntity(),
            E.ThirdPartyNumber(),
            E.ThirdPartyReference(),
            E.HAWBRemarks(self.carrier_settings.goods_description),
            E.HAWBRef1(),
            E.Services(self.order.services),
            E.CODValue(str(self.shipment.totals.total or '')),
            E.CODCurrencyCode(self.order.currency),
            E.SourceId('2'),
            E.TransportType('2'),
            E.AdditionalProperties(
                E.CustomsClearance(
                    E.ConsigneeTaxIDVATEINNumber(self.order.document.document_number if self.order.document else '')
                )
            ),
            E.Invoice(base64.b64encode(self.waybill_document.getvalue()).decode()),
        ]

    def _items(self):
        return [
            E.HAWBItem(
                E.ItemsPieces(str(item.shipped_qty)),
                E.Wgt_Chargeable('0'),
                E.CommodityNo(item.hs_code or ''),
                E.ItemsDescription(item.name),
                E.ItemsCustomsValue(str(self.vat_order.item_vat_custom(item)[1] * item.shipped_qty)),
                E.ItemNumber(item.code),
                E.MarksAndNumbers('Yes' if item.is_transit else 'No'),
            )
            for item in self.shipment.items
        ]
