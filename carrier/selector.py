import logging
import operator
import random

from src.pimly.models.enum import CarrierName
from .models import CarrierPriority
from .aramex import Aramex
from .aramex_sa import AramexSA
from .naqel import Naqel
from .postaplus import PostaPlus
from .smsa import SMSA
from .dhl import DHL

log = logging.getLogger(__name__)


class CarrierSelector:
    _carriers = {
        carrier.name.name: carrier()
        for carrier in (Aramex,
                        AramexSA,
                        Naqel,
                        PostaPlus,
                        SMSA,
                        DHL,
                        )
    }

    @classmethod
    def get_shipping_services(cls, settings, shipment):
        """Выбор керриеров, которые могут отправить заказ"""
        shipping_services = []
        order = shipment.order
        if order.shipping_info.get('carrier'):
            customer_selected_carrier = CarrierName.from_raw(order.shipping_info['carrier'])
        else:
            customer_selected_carrier = None

        carriers_priorities = CarrierPriority.country_priorities(order.channel_id, order.shipping_address.country)
        for carrier_name, priority in carriers_priorities:
            if customer_selected_carrier and customer_selected_carrier != carrier_name:
                continue

            try:
                carrier = cls.get_carrier(carrier_name)
                shipping_service = carrier.ShippingService(settings, order.channel.code)
                if shipping_service.can_send_shipment(shipment):
                    shipping_services.append((shipping_service, priority))
            except Exception:
                log.exception(f"Can not check carrier shipping availability: {carrier_name}")

        if len(shipping_services) > 1:
            significant_carriers = random.choices(shipping_services, weights=[p[1] for p in shipping_services])
            shipping_services.remove(significant_carriers[0])
            shipping_services.insert(0, significant_carriers[0])

        return [shipping_service for shipping_service, priority in shipping_services]

    @classmethod
    def get_local_shipping_services(cls, settings, shipment):
        """Выбор керриеров, которые могут отправить локальный заказ."""
        shipping_services = []
        order = shipment.order
        for carrier_name, carrier in cls._carriers.items():
            try:
                shipping_service = carrier.ShippingService(settings, order.channel.code)
                if shipping_service.can_send_shipment(shipment):
                    shipping_services.append(shipping_service)
            except Exception:
                log.exception(f"Can not check carrier shipping availability: {carrier_name}")

        return shipping_services

    @classmethod
    def get_carrier(cls, carrier_name):
        if hasattr(carrier_name, 'name'):
            carrier_name = carrier_name.name

        return cls._carriers[carrier_name]

    @classmethod
    def get_service_point_carriers(cls):
        """Выбор слжуб доставки, у которых есть service points (пункты выдачи товаров)"""
        return [carrier for carrier in cls._carriers.values() if carrier.ServicePointUpdater]
