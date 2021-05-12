from pimly.models import enum

from .shipping import PostaPlusShippingService
from .tracking import TrackingService
from ..abc.carrier import AbstractCarrier


class PostaPlus(AbstractCarrier):
    name = enum.CarrierName.postaplus
    awb_warning_limit = 1000
    ShippingService = PostaPlusShippingService
    TrackingService = TrackingService
