import transaction
from datetime import date, timedelta, datetime

from sqlalchemy.orm import joinedload

from pimly.models import DBSession, enum
from pimly.models.orders import Order, OrderShipment
from pimly.models.tracking.enum import MilestoneType, OrderShipmentStatus
from pimly.models.tracking.models import ShipmentMilestone
from pimly.utils import grouper
from .api import PostaPlusAPI
from ..abc.tracking import AbstractTrackingUpdater
from ..abc.exc import SendingOrderCancelled

MILESTONES = {
    "AS": MilestoneType.received_by_carrier,
    "BA": MilestoneType.address_research,
    "CL": MilestoneType.customer_address_updated,
    "CM": MilestoneType.attempted_delivery,
    "CNM": MilestoneType.customs_clearance,
    "CUSCLRD": MilestoneType.cleared_customs,
    "DCR": MilestoneType.customs_clearance,
    "DELIVERED": MilestoneType.delivered,
    "DESTROYED": MilestoneType.lost,
    "DR": MilestoneType.arrived_destination_country,
    "HD@CUS": MilestoneType.customs_clearance,
    "ICA": MilestoneType.address_research,
    "OH": MilestoneType.shipment_on_hold,
    "OS": MilestoneType.departed_country_of_origin,
    "PL": MilestoneType.attempted_delivery,
    "PU": MilestoneType.delivered_to_customer,
    "RAD": MilestoneType.arrived_destination_country,
    "RC": MilestoneType.cleared_customs,
    "RS": MilestoneType.refused,
    "RTC": MilestoneType.started_return_process,
    "TC": MilestoneType.attempted_contact,
    "UNCLR": MilestoneType.customs_clearance,
    "WC": MilestoneType.out_for_delivery,
    "FD": MilestoneType.customer_delivery_preference_updated,
    "SDO": MilestoneType.departed_country_of_origin,
    "HD@CUSDOC": MilestoneType.customs_clearance,
    "HD@CUSPRB": MilestoneType.customs_clearance,
    "HD@MINAPR": MilestoneType.customs_clearance,
    "CLR": MilestoneType.cleared_customs,
    "SKCRT": MilestoneType.started_return_process,
    "PROHIBIT": MilestoneType.customs_clearance,
    "SKCRS": MilestoneType.started_return_process,
    "RFCUSCHG": MilestoneType.refused,
    "SKYRS": MilestoneType.started_return_process,
    "OH@RTO": MilestoneType.started_return_process,
    "OH@COLLECT": MilestoneType.held_for_collection,
    "NA": MilestoneType.attempted_delivery,
}


class TrackingService(AbstractTrackingUpdater):
    carrier_name = enum.CarrierName.postaplus

    def __init__(self, settings, **kwargs):
        super().__init__(settings, **kwargs)
        self.channel_id = kwargs['channel_id']

    def update_trackings(self):
        shipment_ids = [shipment.id for shipment in self._tracking_qs]
        for group in grouper(100, shipment_ids):
            delivered_shipment_ids = []
            with transaction.manager:
                qs = DBSession.query(OrderShipment) \
                    .filter(OrderShipment.id.in_(filter(None, group))) \
                    .options(joinedload('carrier'),
                             joinedload('order'))

                for shipment in qs:
                    try:
                        api = PostaPlusAPI(shipment, self.settings)
                        milestones = self._create_milestones(shipment.id, api.get_shipping_tracking_info())
                        new_milestones = shipment.filter_milestones(milestones)

                        if self._check_delivered_status(new_milestones):
                            delivered_shipment_ids.append(shipment.id)

                        # Sort for the further correct addition of ShipmentNotification
                        new_milestones.sort()
                        DBSession.add_all(new_milestones)
                        DBSession.refresh(shipment)
                        shipment.update_status_info()

                    except SendingOrderCancelled as e:
                        self.exception_log.exception(
                            f"Postaplus. Carrier Exception for order: {shipment.order.code}. Error: {e}")

            self._set_order_delivered_status(delivered_shipment_ids)
            self._update_shipment_delivery_date(delivered_shipment_ids)

    def _create_milestones(self, shipment_id, tracking_info):
        shipment_milestones = []
        for tracking in tracking_info:
            milestone = MILESTONES.get(tracking.event_code.upper())
            if not milestone:
                continue
            shipment_milestones.append(ShipmentMilestone(
                shipment_id=shipment_id,
                is_customer_view=milestone.args['is_customer_view'],
                milestone=milestone,
                carrier_code=tracking.event_code,
                event_date=tracking.event_date,
                description=tracking.description
            ))
        return shipment_milestones

    def _check_delivered_status(self, milestones):
        for milestone in milestones:
            if MilestoneType.is_delivered_milestone(milestone.milestone):
                return True
        return False

    def _set_order_delivered_status(self, delivered_shipment_ids):
        if not delivered_shipment_ids:
            return

        with transaction.manager:
            order_qs = DBSession.query(Order) \
                .filter(Order.shipments.any(OrderShipment.id.in_(delivered_shipment_ids)))
            for order in order_qs:
                if all(sh.current_status == OrderShipmentStatus.delivered for sh in order.shipments):
                    order.status = enum.OrderStatus.delivered
                    DBSession.flush()

    def _update_shipment_delivery_date(self, delivered_shipment_ids):
        with transaction.manager:
            DBSession.query(OrderShipment) \
                .filter(OrderShipment.id.in_(delivered_shipment_ids),
                        OrderShipment.current_status == OrderShipmentStatus.delivered) \
                .update({OrderShipment.delivered_date: datetime.utcnow()},
                        synchronize_session=False)

    @property
    def _tracking_qs(self):
        qs = DBSession.query(OrderShipment.id) \
            .join(Order) \
            .filter(Order.channel_id == self.channel_id,
                    OrderShipment.carrier_id == self.carrier_id,
                    Order.status.in_([enum.OrderStatus.complete,
                                      enum.OrderStatus.not_delivered]))

        if self.tracking_numbers:
            qs = qs.filter(OrderShipment.tracking_number.in_(self.tracking_numbers))
        else:
            date_checking = date.today() - timedelta(days=60)
            qs = qs.filter(OrderShipment.shipped_date >= date_checking)
        return qs
