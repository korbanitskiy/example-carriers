import abc

import transaction

from pimly.models import DBSession
from pimly.utils.helpers import grouper
from ..models import CarrierServicePoint, Carrier


class Location:

    def __init__(self, code, city, country, address, **kwargs):
        self.code = code
        self.city = city
        self.country = country
        self.address = address
        self.latitude = kwargs.get('latitude')
        self.longitude = kwargs.get('longitude')
        self.address_ar = kwargs.get('address_ar')
        self.work_from = kwargs.get('work_from')
        self.work_to = kwargs.get('work_from')
        self.description = kwargs.get('description')
        self.phone = kwargs.get('phone')
        self.zip = kwargs.get('zip')
        self.name = kwargs.get('name') or code


class AbstractServicePointUpdater(metaclass=abc.ABCMeta):

    def __init__(self, settings):
        self.settings = settings

    @property
    @abc.abstractmethod
    def carrier_name(self):
        pass

    @abc.abstractmethod
    def download_service_points(self):
        pass

    def update_service_points(self):
        service_points = self.download_service_points()
        for group in grouper(250, service_points):
            with transaction.manager:
                self._update_service_points([sp for sp in group if sp])

        self._remove_old_service_points(service_points)

    def _update_service_points(self, locations):
        carrier = DBSession.query(Carrier)\
            .filter(Carrier.name == self.carrier_name)\
            .one()

        qs = DBSession.query(CarrierServicePoint) \
            .filter(CarrierServicePoint.carrier == carrier,
                    CarrierServicePoint.code.in_(l.code for l in locations))

        cdb_service_points = {sp.code: sp for sp in qs}
        for location in locations:
            if location.code in cdb_service_points:
                service_point = cdb_service_points[location.code]
            else:
                service_point = CarrierServicePoint(carrier=carrier,
                                                    name=location.name,
                                                    code=location.code)

            service_point.address = location.address
            service_point.country = location.country
            service_point.city = location.city
            service_point.latitude = location.latitude
            service_point.longitude = location.longitude
            service_point.work_from = location.work_from
            service_point.work_to = location.work_to
            service_point.description = location.description
            service_point.zip = location.zip
            service_point.phone = location.phone
            DBSession.add(service_point)
            DBSession.flush()

    def _remove_old_service_points(self, locations):
        if not locations:
            return

        with transaction.manager:
            qs = DBSession.query(CarrierServicePoint) \
                    .join(Carrier)\
                    .filter(Carrier.name == self.carrier_name,
                            CarrierServicePoint.code.notin_(l.code for l in locations))

            for sp in qs:
                DBSession.delete(sp)
