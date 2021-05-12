from pimly.models import enum

from ..abc.carrier import AbstractCarrier
from .shipping import AramexShippingService

from .tracking import TrackingService
from .service_point import ServicePointUpdater


class Aramex(AbstractCarrier):
    name = enum.CarrierName.aramex
    awb_warning_limit = 6000
    ShippingService = AramexShippingService
    TrackingService = TrackingService
    ServicePointUpdater = ServicePointUpdater
