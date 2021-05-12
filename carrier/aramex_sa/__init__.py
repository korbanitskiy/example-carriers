from pimly.models import enum

from ..abc.carrier import AbstractCarrier
from .shipping import AramexSAShippingService

from .tracking import TrackingService


class AramexSA(AbstractCarrier):
    name = enum.CarrierName.aramex_sa
    official_name = "Aramex"
    awb_warning_limit = 5000
    ShippingService = AramexSAShippingService
    TrackingService = TrackingService
