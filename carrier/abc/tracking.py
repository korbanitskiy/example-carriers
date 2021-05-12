import abc
import logging
from datetime import date, timedelta

from pimly import DBSession
from pimly.utils.cache import cached_property
from pimly.models.carrier.models import Carrier


class AbstractTrackingUpdater:
    log = logging.getLogger('carriers_orders')
    exception_log = logging.getLogger('carriers_orders_exceptions')

    def __init__(self, settings, **kwargs):
        self.settings = settings
        self.to_date = kwargs.get('to_date') or (date.today() + timedelta(days=1))
        self.from_date = kwargs.get('from_date') or (self.to_date - timedelta(days=30))
        self.tracking_numbers = kwargs.get('tracking_numbers')

    @abc.abstractmethod
    def update_trackings(self):
        pass

    @property
    @abc.abstractmethod
    def carrier_name(self):
        pass

    @cached_property
    def carrier_id(self):
        carrier = DBSession.query(Carrier.id)\
            .filter(Carrier.name == self.carrier_name)\
            .one()

        return carrier.id
