from pimly.models import enum

from ..abc.carrier import AbstractCarrier
from .shipping import SMSAShippingService
from .tracking import TrackingUpdater
from .service_point import ServicePointUpdater


class SMSA(AbstractCarrier):
    name = enum.CarrierName.smsa
    awb_warning_limit = 0
    ShippingService = SMSAShippingService
    TrackingService = TrackingUpdater
    ServicePointUpdater = ServicePointUpdater
