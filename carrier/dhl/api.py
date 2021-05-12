import logging
import os
import uuid
import io
from base64 import b64decode, b64encode
from datetime import datetime, timedelta

import requests

from pimly.models import DBSession, enum
from pimly.models.carrier.models import Carrier
from pimly.models.translate import Translator
from pimly.utils import ensure_dir
from pimly.utils.vat import VATOrder
from .city_codes import CityCodeNotFound, get_city_code
from ..abc.exc import SendingOrderCancelled


class DHLTrackingAPI:
    exception_log = logging.getLogger('carriers_orders_exceptions')
    log = logging.getLogger('carriers_orders')

    def __init__(self, settings):
        self.username = settings['pimly.dhl.api.login']
        self.password = settings['pimly.dhl.api.password']
        self.api_url = settings['pimly.dhl.order_api.url']

    def get_tracking(self, tracking_numbers):
        response = requests.post(
            url=self.api_url + "TrackingRequest",
            auth=(self.username, self.password),
            json=self.tracking_request(tracking_numbers),
        )
        try:
            return self._parse_tracking_response(response)
        except KeyError as e:
            self.exception_log.exception(f"""
                DHL Request: {response.request.body}
                DHL Response: {response.json()}
            """)
            raise SendingOrderCancelled(f"Missing key in API response: {e}")
        except SendingOrderCancelled:
            self.exception_log.exception(f"""
                DHL Request: {response.request.body}
                DHL Response: {response.json()}
            """)
            raise

    def tracking_request(self, tracking_numbers):
        message_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        message_reference = uuid.uuid1().hex[:28]
        return {
            "trackShipmentRequest": {
                "trackingRequest": {
                    "TrackingRequest": {
                        "Request": {
                            "ServiceHeader": {
                                "MessageTime": message_time,
                                "MessageReference": message_reference
                            }
                        },
                        "AWBNumber": {
                            "ArrayOfAWBNumberItem": tracking_numbers
                        },
                        "LevelOfDetails": "ALL_CHECKPOINTS",
                        "PiecesEnabled": "B"
                    }
                }
            }
        }

    def _parse_tracking_response(self, response):
        if response.status_code != 200:
            raise SendingOrderCancelled(f"Invalid DHL Response ({response.status_code})")

        response_json = response.json()
        array_of_awb_info_item = response_json["trackShipmentRequestResponse"]["trackingResponse"]["TrackingResponse"]["AWBInfo"]["ArrayOfAWBInfoItem"]
        tracking_info = array_of_awb_info_item if isinstance(array_of_awb_info_item, list) else [array_of_awb_info_item]

        error = len(tracking_info) == 1 and tracking_info[0]["Status"]["ActionStatus"] != "Success"
        if error:
            array_of_condition_item = tracking_info[0]["Status"]["Condition"]["ArrayOfConditionItem"]
            errors = array_of_condition_item if isinstance(array_of_condition_item, list) else [array_of_condition_item]
            raise SendingOrderCancelled(f"Invalid DHL Request: {'; '.join([error['ConditionData'] for error in errors])}")

        return tracking_info


class DHLOrderAPI:
    exception_log = logging.getLogger('carriers_orders_exceptions')
    log = logging.getLogger('carriers_orders')
    PAPERLESS_COUNTRIES = ('BH', 'OM', 'SA', 'AE')

    def __init__(self, shipment, settings, channel='default'):
        self.shipment = shipment
        self.order = shipment.order
        self.api_url = settings['pimly.dhl.order_api.url']
        self.username = settings['pimly.dhl.api.login']
        self.password = settings['pimly.dhl.api.password']
        self.shipping_pdf_path = os.path.join(
            settings['pimly.carriers.main_path'],
            enum.CarrierName.dhl.name,
            'shipping_pdf',
        )
        self.carrier = self._carrier_qs.one()
        self.carrier_settings = self.carrier.get_settings(channel)
        self.translator = Translator()
        ensure_dir(self.shipping_pdf_path)

        if self.order.is_cod:
            self.account = self.carrier_settings.cod_account
        else:
            self.account = self.carrier_settings.pp_account

    def send_shipment(self, box_qty, invoice_pdf):
        response = requests.post(
            url=self.api_url + "ShipmentRequest",
            auth=(self.username, self.password),
            json=self.shipment_request(box_qty, invoice_pdf),
        )
        try:
            tracking_number, shipment_image = self._parse_response(response)
        except KeyError as e:
            self.exception_log.exception(f"""
                DHL Request: {response.request.body}
                DHL Response: {response.json()}
            """)
            raise SendingOrderCancelled(f"Missing key in API response: {e}")
        except SendingOrderCancelled:
            self.exception_log.exception(f"""
                DHL Request: {response.request.body}
                DHL Response: {response.json()}
            """)
            raise
        else:
            self.log.info(f"""
                DHL Request: {response.request.body}
                DHL Response: {response.json()}
            """)
            self.shipment_pdf = shipment_image
            return tracking_number

    def shipment_request(self, box_qty, invoice_pdf):
        shipment_time = datetime.utcnow() + timedelta(hours=1)
        return {
            "ShipmentRequest": {
                "RequestedShipment": {
                    "ShipmentInfo": self._shipment_info(invoice_pdf),
                    "ShipTimestamp": shipment_time.strftime("%Y-%m-%dT%H:%M:%S GMT+00:00"),
                    "PaymentInfo": "DAP",
                    "InternationalDetail": {
                        "Commodities": self._commodities(box_qty),
                        "Content": "NON_DOCUMENTS"
                    },
                    "Ship": {
                        "Shipper": self._shipper(),
                        "Recipient": self._recipient(),
                    },
                    "Packages": self._packages(box_qty),
                }
            }
        }

    def _shipment_info(self, invoice_pdf):
        return {
            "DropOffType": "REGULAR_PICKUP",
            "ServiceType": "P",
            "Currency": self.order.base_currency,
            "UnitOfMeasurement": "SI",
            "LabelType": "PDF",
            "LabelTemplate": "ECOM26_84_001",
            "Billing": {
                "ShipperAccountNumber": self.account,
                "ShippingPaymentType": "S"
            },
            **self._paperless(invoice_pdf),
            **self._label_options(),
        }

    def _paperless(self, invoice_pdf):
        if self.order.shipping_address.country not in self.PAPERLESS_COUNTRIES:
            return {}
        else:
            return {
                "PaperlessTradeEnabled": True,
                "SpecialServices": {
                    "Service": {
                        "ServiceType": "WY"
                    }
                },
                "DocumentImages": [
                    {
                        "DocumentImage": {
                            "DocumentImageType": "INV",
                            "DocumentImage": b64encode(invoice_pdf.read()).decode(),
                            "DocumentImageFormat": "PDF",
                        }
                    }
                ]
            }

    def _label_options(self):
        if self.order.is_cod:
            return {
                "LabelOptions": {
                    "CustomerLogo": {
                        "LogoImage": COD_LOGO_IMAGE,
                        "LogoImageFormat": "PNG",
                    }
                }
            }

        return {}

    def _commodities(self, box_qty):
        shipped_items = [item for item in self.shipment.items if item.shipped_qty > 0]
        description = None
        if len(shipped_items) == 1:
            description = shipped_items[0].product_type

        return {
            "NumberOfPieces": box_qty,
            "Description": description or "Clothes,shoes,cosmetics",
            "CustomsValue": VATOrder(self.shipment).base_vat_custom[1]
        }

    def _shipper(self):
        return {
            "Contact": {
                "PersonName": self.carrier_settings.company,
                "CompanyName": self.carrier_settings.company,
                "PhoneNumber": self.carrier_settings.phone,
                "EmailAddress": self.carrier_settings.email,
            },
            "Address": {
                "StreetLines": self.carrier_settings.address1,
                "StreetLines2": self.carrier_settings.address2,
                "StreetLines3": self.carrier_settings.address3,
                "City": self.carrier_settings.city,
                "PostalCode": self.carrier_settings.postcode,
                "CountryCode": self.carrier_settings.country,
            }
        }

    def _recipient(self):
        full_name = self.translator.translate(self.order.shipping_address.full_name)
        address = self.translator.translate(self.order.shipping_address.address)
        district = self.translator.translate(self.order.shipping_address.district or '')
        address = ' '.join(filter(None, [district, address]))

        if self.order.shipping_address.country == 'SA' \
                and self.order.document\
                and self.order.document.document_number:
            document = {
                "RegistrationNumbers": {
                    "RegistrationNumber": {
                        "Number": self.order.document.document_number,
                        "NumberTypeCode": "VAT",
                        "NumberIssuerCountryCode": "SA"
                    }
                }
            }
        else:
            document = {}

        return {
            "Contact": {
                "PersonName": full_name,
                "CompanyName": full_name,
                "PhoneNumber": self.order.shipping_address.phone,
                "EmailAddress": self.order.email,
            },
            "Address": {
                "StreetLines": address[:45],
                "StreetLines2": address[45:90] or '-',
                "StreetLines3": self.shipment.totals.total if self.order.is_cod else '-',
                "City": self.city_code(translate=True),
                "StateOrProvinceCode": district,
                "PostalCode": self.order.shipping_address.postcode,
                "CountryCode": self.order.shipping_address.country,
            },
            **document,
        }

    def _packages(self, box_qty):
        return {
            "RequestedPackages": [
                {
                    "@number": str(i + 1),
                    "Weight": round(self.order.shipped_qty * 0.1, 1),
                    "Dimensions": {
                        "Length": 10,
                        "Width": 10,
                        "Height": 10,
                    },
                    "CustomerReferences": self.order.code,
                } for i in range(box_qty)
            ]
        }

    def _parse_response(self, response):
        response_json = response.json()
        errors = [note["Message"] for note in response_json["ShipmentResponse"]["Notification"] if note["Message"]]

        if response.status_code != 200 or errors:
            raise SendingOrderCancelled(f"Invalid DHL Response ({response.status_code}): {' '.join(errors)}")

        tracking_number = response_json["ShipmentResponse"]["ShipmentIdentificationNumber"]
        shipment_image_64 = response_json["ShipmentResponse"]["LabelImage"][0]["GraphicImage"]

        return tracking_number, shipment_image_64

    @property
    def shipment_pdf(self):
        file_path = os.path.join(self.shipping_pdf_path, self.order.code + '.pdf')
        buffer = io.BytesIO()
        with open(file_path, "rb") as pdf_file:
            buffer.write(pdf_file.read())

        return buffer

    @shipment_pdf.setter
    def shipment_pdf(self, image_str_64):
        file_path = os.path.join(self.shipping_pdf_path, self.order.code + '.pdf')
        with open(file_path, "wb") as pdf_file:
            pdf_file.write(b64decode(image_str_64, validate=True))

    def city_code(self, translate=False):
        cdb_cities = [self.order.shipping_address.city]
        cdb_cities.extend(self.order.shipping_address.base_cities)
        if translate:
            cdb_cities = [self.translator.translate(city) for city in cdb_cities]

        try:
            city_code = get_city_code(self.order.shipping_address.country, cdb_cities)
        except CityCodeNotFound:
            raise SendingOrderCancelled(f"Invalid destination: City code for city '{self.order.shipping_address.city}' was not found")
        else:
            return city_code

    @property
    def _carrier_qs(self):
        return DBSession.query(Carrier)\
            .filter(Carrier.name == enum.CarrierName.dhl)


COD_LOGO_IMAGE = """
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
"""
