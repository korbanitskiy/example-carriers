from datetime import datetime

import redis_lock
from decimal import Decimal
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload, joinedload, load_only
from pimlib.form.crud import RawResponse
from pimlib.ui.decorators import UISuccessResponse, UIErrorResponse, UIRender, ajaxify_action
from pyramid.view import view_defaults, view_config

from pimly.lib.crud import ExtendedCRUDUpdate
from pimly.utils.vat import VATOrderBeforeShipping
from pimly.models.tracking.enum import MilestoneType
from pimly.models.tracking.models import ShipmentMilestone
from carrier.forms import BaseCarrierCompleteForm
from pimly.models.enum import OrderStatus, ShippingMethod
from pimly.models.orders import Order
from carrier.selector import CarrierSelector
from carrier.abc.exc import SendingOrderCancelled
from pimly.models.warehouse.enum import WarehouseProductStatus
from pimly.tasks.send_email import send_shipment_email


@view_defaults(permission='acl_complete')
class OrderComplete(ExtendedCRUDUpdate):
    model_name = 'order'
    base_entity = Order
    render_params = {}
    templates = {'form_ajax': 'order/complete-ajax.mako'}
    form_schema = BaseCarrierCompleteForm
    messages = {
        'not_found': u"No Order found",
        'not_allowed': u"Changing Order not allowed",
        'locked': u"Cannot save locked order. Please wait until lock is released or unlock manually",
        'validation_failed': u"Error updating order. Please check form validation errors",
        'success': u"Order completed successfully",
        'failed': u"Error complete order",
        'no_available_carriers': u"There are no available carriers",
        'invalid_carrier': u"Invalid carrier",
    }

    def __init__(self, request):
        super().__init__(request)
        self.allowed_channel_ids = [channel.id for channel in request.user_info.allowed_channels]
        self.current_shipping_service = None
        self.available_shipping_services = None
        self.success_complete = None
        self.lock = None
        self.international_items = None

    def load_model(self):
        entity_id = self.request.matchdict['id']
        query = self.di.Session.query(self.base_entity) \
            .filter(self.base_entity.id == entity_id,
                    self.base_entity.channel_id.in_(self.allowed_channel_ids)) \
            .options(load_only('code', 'currency', 'status', 'shipping_method_type', 'shipping_info', 'read_only'),
                     selectinload('items').load_only('order_id', 'channel_sold_price', 'discount_amount', 'ordered_qty',
                                                     'shipped_qty', 'cancelled_qty'),
                     selectinload('items').joinedload('returned_items')
                     .load_only('return_id', 'item_id', 'quantity', 'reason', 'comment'),
                     selectinload('items').selectinload('supplier_items')
                     .load_only('item_id', 'ordered_qty', 'missing_qty', 'received_qty'),
                     selectinload('items').selectinload('supplier_items')
                     .joinedload('returned_items')
                     .load_only('supplier_return_id', 'supplier_item_id', 'quantity'),
                     joinedload('shipping_address'),
                     joinedload('international_shipment'),
                     joinedload('channel'))

        return query.first()

    def init_model(self):
        super().init_model()
        self.init_carrier_shipping_service()
        self.init_lock()

    def init_carrier_shipping_service(self):
        self.available_shipping_services = CarrierSelector.get_shipping_services(self.request.registry.settings, self.model.international_shipment)
        if not self.available_shipping_services:
            raise UIErrorResponse(self.messages['no_available_carriers'], url=self.referer_url)

        self.current_shipping_service = self._request_shipping_service() or self.available_shipping_services[0]

    def init_lock(self):
        self.lock = redis_lock.Lock(self.request.redis, self.model.code, expire=5*60)

    def _request_shipping_service(self):
        if not self.request.params.get('carrier_process'):
            return None

        for service in self.available_shipping_services:
            if service.carrier_name.name == self.request.params['carrier_process']:
                return service

        raise UIErrorResponse(self.messages['invalid_carrier'], url=self.referer_url)

    def validate_conditions(self):
        sa_document_need = self.model.shipping_address.country == "SA" and \
                           VATOrderBeforeShipping(self.model.international_shipment).vat_custom_additional >= Decimal('1000') and \
                           not (self.model.document and self.model.document.document_number)

        if sa_document_need:
            raise UIRender('order/no-document-on-complete-ajax.mako', {'order_id': self.model.id})

        if not self.model.can_complete:
            raise UIErrorResponse(self.messages.not_allowed, url=self.referer_url)

        if not self.lock.acquire(blocking=False):
            self.request.session.flash("error;Order is being completed")
            raise UIErrorResponse("Order is being completed", headers={'pim-code': 'success-reload'})
        else:
            self.lock.release()

    def get_fail_message(self, e):
        if isinstance(e, SendingOrderCancelled):
            return str(e)
        elif isinstance(e, SQLAlchemyError):
            return "Temporary application error. Please try again later"
        else:
            return super().get_fail_message(e)

    def set_default_values(self):
        self.form.data['box_qty'] = 1

    def validate(self):
        valid = super().validate()
        if self.model.shipping_method_type == ShippingMethod.click_and_collect \
                and self.form.data['carrier_process'].name != self.model.shipping_info['carrier']:
            valid = False
            self.form.errors['carrier_process'] = f"Carrier can be only: {self.model.shipping_info['carrier']}"

        return valid and self.current_shipping_service.validate_form(self.form, write_errors=True)

    def prepare_view(self):
        params = super().prepare_view()
        params['carriers_options'] = [
            (carrier.carrier_name.name, carrier.carrier_name.value)
            for carrier in self.available_shipping_services
        ]
        params['carrier'] = self.current_shipping_service.carrier_name
        return params

    def default_referer(self):
        return self.request.route_path('order_view', id=self.model.id)

    def save(self):
        if self.lock.acquire(blocking=False):
            try:
                self.di.Session.add(self.model)
                self.international_items = [i for i in self.model.items if i.is_international]
                self.model.set_status(OrderStatus.complete)
                self.set_items_shipped_qty()
                self.update_order_shipment()
                self.di.Session.flush()
                self.after_flush()
            except self.fail_exceptions as e:
                self.fail(e)
            else:
                self.success()
            finally:
                self.lock.reset()

        else:
            raise UIErrorResponse("Order's completing by another user now")

    @property
    def fail_exceptions(self):
        return super().fail_exceptions + (SendingOrderCancelled,)

    def after_flush(self):
        try:
            tracking_number = self.current_shipping_service.send_shipment(self.model.international_shipment)
        except self.current_shipping_service.send_exceptions as e:
            self.request.session.flash(f"error;{e}")
            self.success_complete = False
        else:
            self.model.international_shipment.tracking_number = tracking_number
            self.success_complete = True

        self._update_warehosue_product_status()

        if self.model.international_shipment.can_send_shipping_email:
            send_shipment_email.apply_async(args=(self.model.international_shipment.id,), countdown=10)

        self.di.Session.flush()

    def update_order_shipment(self):
        current_datetime = datetime.utcnow()

        self.model.international_shipment.shipped_date = current_datetime
        self.model.international_shipment.city = self.model.shipping_address.city
        self.model.international_shipment.country = self.model.shipping_address.country
        self.model.international_shipment.box_qty = self.form.data['box_qty']
        self.model.international_shipment.carrier = self.current_shipping_service.carrier

        shipped_milestone = ShipmentMilestone(
            shipment_id=self.model.international_shipment.id,
            is_customer_view=MilestoneType.shipped.args['is_customer_view'],
            milestone=MilestoneType.shipped,
            carrier_code=MilestoneType.shipped.args['code'],
            event_date=current_datetime,
        )
        self.model.international_shipment.milestones.append(shipped_milestone)
        self.model.international_shipment.update_status_info()
        self.model.international_shipment.items = [i for i in self.international_items if i.shipped_qty > 0]

    def set_items_shipped_qty(self):
        for item in self.international_items:
            item.shipped_qty = item.ready_for_shipping_qty()
            self.di.Session.add(item)

    def _update_warehosue_product_status(self):
        warehouse_products = (
            supplier_item.warehouse_product
            for item in self.international_items
            for supplier_item in item.supplier_items
            if supplier_item.warehouse_product
        )

        for wp in warehouse_products:
            wp.status = WarehouseProductStatus.shipped
            self.di.Session.add(wp)

    def success(self):
        ui_params = {
            'code': 'success-reload',
            'url': self.referer_url,
            'tags': self.tags,
        }
        if self.success_complete:
            self.request.session.flash("success;{}".format(self.messages.success))
        raise UISuccessResponse(self.messages.success, **ui_params)

    @view_config(route_name='order_complete_json', renderer='order/complete-ajax.mako')
    @ajaxify_action
    def view(self):
        return self.process()

    @view_config(route_name='order_complete_change_carrier_json', renderer='order/complete-ajax.mako')
    @ajaxify_action
    def change_carrier_form(self):
        try:
            self.parse_referer()
            self.init_model()
            self.init_form()

            available_shipping_services = [
                service
                for service in self.available_shipping_services
                if service.validate_form(self.form, write_errors=False)
            ]

            if not available_shipping_services:
                available_shipping_services = [
                    service
                    for service in self.available_shipping_services
                    if service.carrier_name.name == self.request.params['carrier_process']
                ]

            self.available_shipping_services = available_shipping_services
            params = self.prepare_view()
        except RawResponse as e:
            return e.value
        else:
            raise UIRender(self.template, params)
