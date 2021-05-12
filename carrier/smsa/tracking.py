import time
import transaction
from datetime import datetime

from sqlalchemy.orm import joinedload

from pimly.utils import grouper
from pimly.models import DBSession, enum
from pimly.models.orders import Order, OrderShipment
from pimly.models.tracking.models import ShipmentMilestone
from pimly.models.tracking.enum import MilestoneType, OrderShipmentStatus
from .api import SMSAOrderAPI
from ..abc.tracking import AbstractTrackingUpdater
from ..abc.exc import SendingOrderCancelled


MILESTONES = {
    "proof of delivery captured": MilestoneType.delivered,
    "picked up": MilestoneType.received_by_carrier,
    "delivery exception": MilestoneType.attempted_delivery,
    "departed form origin": MilestoneType.departed_country_of_origin,
    "out for delivery": MilestoneType.out_for_delivery,
    "clearance delay": MilestoneType.customs_clearance,
    "customs released": MilestoneType.cleared_customs,
    "in clearance processing": MilestoneType.customs_clearance,
    "on hold": MilestoneType.shipment_on_hold,
    "collected from retail": MilestoneType.delivered_to_customer,
    "customer broker clearance": MilestoneType.customs_clearance,
    "undeliverable address": MilestoneType.address_research,
    "recipient not available": MilestoneType.attempted_delivery,
    "recipient not available at residence": MilestoneType.attempted_delivery,
    "reroute request": MilestoneType.customer_address_updated,
    "returned to client": MilestoneType.started_return_process,
    "consignee no response": MilestoneType.attempted_contact,
    "consignee mobile off": MilestoneType.attempted_contact,
    "no contact number": MilestoneType.attempted_contact,
    "incorrect contact number": MilestoneType.attempted_contact,
    "consignee contact out of service": MilestoneType.attempted_contact,
    "consignee not available": MilestoneType.attempted_contact,
    "consignee unknown": MilestoneType.attempted_contact,
    "consignee address changed ": MilestoneType.customer_address_updated,
    "consignee request to call later": MilestoneType.attempted_contact,
    "consignee did not wait": MilestoneType.attempted_delivery,
    "consignee out of city / country": MilestoneType.attempted_delivery,
    "incorrect delivery address": MilestoneType.address_research,
    "consignee address changed": MilestoneType.attempted_delivery,
    "consignee do not want the shipment": MilestoneType.refused,
    "refused due to incorrect cod amount": MilestoneType.refused,
    "refused due to duplicate shipment": MilestoneType.refused,
    "consignee request to open before pod": MilestoneType.refused,
    "refused due to contents mismatch": MilestoneType.refused,
    "shipment refuse by recipient": MilestoneType.refused,
    "consignee unable to pay custom duty": MilestoneType.refused,
    "consignee unable to pay cod charges": MilestoneType.refused,
    "consignee refuse to pay custom duty": MilestoneType.refused,
    "consignee refuse to pay cod charges": MilestoneType.refused,
    "shipment on hold": MilestoneType.shipment_on_hold,
    "awaiting consignee for collection": MilestoneType.held_for_collection,
    "at smsa retail center": MilestoneType.held_for_collection,
    "return process started": MilestoneType.started_return_process,
    "data received": MilestoneType.data_received_by_carrier,
}


class TrackingUpdater(AbstractTrackingUpdater):
    carrier_name = enum.CarrierName.smsa

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
                    .options(joinedload('order'),
                             joinedload('carrier'))

                for shipment in qs:
                    try:
                        api = SMSAOrderAPI(shipment, self.settings)
                        milestones = self._create_milestones(shipment.id, api.get_order_tracking_info())
                        new_milestones = shipment.filter_milestones(milestones)
                        time.sleep(2)

                        if self._check_delivered_status(new_milestones):
                            delivered_shipment_ids.append(shipment.id)

                        # Sort for the further correct addition of ShipmentNotification
                        new_milestones.sort()
                        DBSession.add_all(new_milestones)
                        DBSession.refresh(shipment)
                        shipment.update_status_info()

                    except SendingOrderCancelled as e:
                        self.exception_log.exception(e)

            self._set_order_delivered_status(delivered_shipment_ids)
            self._update_shipment_delivery_date(delivered_shipment_ids)

    def _create_milestones(self, shipment_id, tracking_info):
        shipment_milestones = []
        for tracking in tracking_info:
            milestone = MILESTONES.get(tracking.event_code.lower(), None)
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
        return any(MilestoneType.is_delivered_milestone(m.milestone) for m in milestones)

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
        qs = DBSession.query(OrderShipment.id)\
            .join(Order)\
            .filter(Order.channel_id == self.channel_id,
                    OrderShipment.carrier_id == self.carrier_id,
                    Order.status.in_([enum.OrderStatus.complete,
                                      enum.OrderStatus.not_delivered]))

        if self.tracking_numbers:
            qs = qs.filter(OrderShipment.tracking_number.in_(self.tracking_numbers))
        else:
            qs = qs.filter(OrderShipment.tracking_number.isnot(None),
                           OrderShipment.shipped_date.between(self.from_date, self.to_date))
        return qs
