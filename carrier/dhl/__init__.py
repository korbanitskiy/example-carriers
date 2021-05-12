from pimly.models import enum

from ..abc.carrier import AbstractCarrier
from .shipping import DHLShippingService
from .tracking import TrackingUpdater


class DHL(AbstractCarrier):
    name = enum.CarrierName.dhl
    ShippingService = DHLShippingService
    TrackingService = TrackingUpdater
