from pimly.models.enum import CarrierName

from .api import SMSAAPI
from ..abc.service_point import AbstractServicePointUpdater


class ServicePointUpdater(AbstractServicePointUpdater):
    carrier_name = CarrierName.smsa

    def download_service_points(self):
        return SMSAAPI(self.settings).get_service_points()
