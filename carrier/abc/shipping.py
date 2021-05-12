import abc
import logging
import random
import traceback

import requests
from pimly.models import DBSession
from pimly.models.carrier.models import Carrier, CarrierNumber
from pimly.models.orders import OrderShippingTask, OrderShipment
from pyramid.settings import asbool
from sqlalchemy.orm import contains_eager

from . import pdf
from .exc import SendingOrderDelayed


class AbstractShippingService:
    log = logging.getLogger('carriers_orders')
    exception_log = logging.getLogger(__name__)
    send_exceptions = (requests.RequestException, SendingOrderDelayed)
    waybill_pdf_creators = {
        'EG': pdf.EgyptWaybillPDF,
        'SA': pdf.SaudiArabiaWaybillPDF,
        'AE': pdf.ArabEmiratesWaybillPDF,
    }

    def __init__(self, settings, channel_code):
        self.settings = settings
        self.production_mode = asbool(settings.get('pimly.order_api.production_mode', False))
        self.carrier = self._carrier_qs.one()
        self.carrier_settings = self.carrier.get_settings(channel_code)

    @property
    @abc.abstractmethod
    def carrier_name(self):
        pass

    @abc.abstractmethod
    def can_send_shipment(self, shipment):
        """Проверяем может ли керриер глобально отправить этот заказ: подходит ли страна, валюта и т.д."""
        return True

    @abc.abstractmethod
    def create_shipping_document(self, shipment):
        """
            Shipping document - наклейка, которая будет наклеяна на коробку с заказом.
            Каждый керриер имеет уникальный формат
        """
        pass

    @abc.abstractmethod
    def create_invoice_document(self, shipment):
        """
            Invoice document - документ со списком айтемов и их стоимостью.
            Каждый керриер может иметь свой формат
        """
        pass

    def validate_form(self, form, write_errors):
        """
        Проверяем, может ли конретный керриер отправить заказ с выбранными параметрами:
        некоторые могут отправлять заказ только с определенным кол-вом коробок и т.д.
        """
        return True

    def send_shipment(self, shipment):
        """
        Отправка информации по заказу в службу доставки.
        В случае ошибки сохраняет таск на повторную отправку.
        Возвращает трекинг номер заказа.
        """
        try:
            tracking_number = self._send_shipment(shipment)
        except self.send_exceptions as exc:
            self.exception_log.exception(f"Error during sending order {shipment.order.code} to {self.carrier_name.value}")
            self._update_shipping_task(shipment, str(exc), traceback.format_exc())
            raise
        else:
            self.log.info(f"Shipment {shipment.id} for order {shipment.order.code} was sent to {self.carrier_name.value} successfully")
            self._delete_shipping_tasks([shipment])
            return tracking_number

    def resend_shipments(self, shipments=None, need_to_raise_error=True):
        """Повторная отправка заказов, в процессе отправки которых возникли ошибки"""
        shipments = shipments or [task.shipment for task in self._shipping_tasks_qs]
        for shipment in shipments:
            try:
                self._resend_shipment(shipment)
            except self.send_exceptions as exc:
                self._update_shipping_task(shipment, str(exc), traceback.format_exc())
                if need_to_raise_error:
                    raise
            else:
                self.log.info(f"Shipment {shipment.id} for order {shipment.order.code} was sent to {self.carrier_name.value} successfully")
                self._delete_shipping_tasks([shipment])

    def create_waybill_document(self, shipment, **kwargs):
        """
        Waybill document - документ, который отправляется керриеру.
        Это документ со стороны Воги и не зависит от керриера
        """
        if shipment.order.channel.code == 'enigmo':
            creator = pdf.EnigmoWaybillPDF(self.settings, shipment, **kwargs)
        else:
            creator = self.waybill_pdf_creators.get(shipment.order.shipping_address.country, pdf.BaseWaybillPDF)(self.settings, shipment, **kwargs)

        return creator.create_document()

    @abc.abstractmethod
    def _send_shipment(self, shipment):
        """Конкретная реализация отправки заказа для каждого керриера. Возвращает трекинг номер."""
        pass

    @abc.abstractmethod
    def _resend_shipment(self, shipment):
        """Конкретная реализация повторной отправки заказа для каждого керриера"""
        pass

    def _update_shipping_task(self, shipment, reason, traceback_exc):
        """Создание/обновление таска для повторной отправки шипмента"""
        shipping_task = shipment.shipping_task or OrderShippingTask(shipment=shipment)
        shipping_task.message = reason
        shipping_task.traceback = traceback_exc
        DBSession.add(shipping_task)
        DBSession.flush()

    def _delete_shipping_tasks(self, shipments):
        """Удаление успешно отправленных тасков"""
        if shipments:
            DBSession.query(OrderShippingTask)\
                .filter(OrderShippingTask.shipment_id.in_(shipment.id for shipment in shipments))\
                .delete(synchronize_session=False)

    @property
    def _shipping_tasks_qs(self):
        return DBSession.query(OrderShippingTask) \
            .join(OrderShipment) \
            .join(OrderShipment.carrier) \
            .filter(Carrier.name == self.carrier_name) \
            .options(contains_eager(OrderShippingTask.shipment).joinedload(OrderShipment.carrier),
                     contains_eager('shipment').selectinload('items')) \
            .limit(200)

    @property
    def _carrier_qs(self):
        return DBSession.query(Carrier).filter(Carrier.name == self.carrier_name)


class TrackingNumberMixin:
    """Mixin для работы с трекинг номерами, хранящимися в базе данных"""

    @property
    def tracking_number_qs(self):
        return DBSession.query(CarrierNumber.id) \
            .join(Carrier) \
            .filter(Carrier.name == self.carrier_name,
                    CarrierNumber.group_id == self.carrier_settings.group_id)

    def get_tracking_number(self):
        numbers = [x.id for x in self.tracking_number_qs.limit(200)]
        carrier_number = DBSession.query(CarrierNumber) \
            .filter(CarrierNumber.id == random.choice(numbers)) \
            .one()

        tracking_number = carrier_number.number
        DBSession.delete(carrier_number)
        DBSession.flush()

        return tracking_number
