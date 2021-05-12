from pimly.models import enum

from .shipping import NaqelShippingService
from ..abc.carrier import AbstractCarrier
from .tracking import TrackingService


class Naqel(AbstractCarrier):
    name = enum.CarrierName.naqel
    awb_warning_limit = 5000
    ShippingService = NaqelShippingService
    TrackingService = TrackingService
