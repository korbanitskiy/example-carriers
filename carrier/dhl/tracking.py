import transaction
from collections import namedtuple
from datetime import date, timedelta, datetime

from sqlalchemy.orm import selectinload

from pimly.models import DBSession, enum
from pimly.models.orders import Order, OrderShipment
from pimly.models.tracking.enum import MilestoneType, OrderShipmentStatus
from pimly.models.tracking.models import ShipmentMilestone
from pimly.utils import grouper
from ..abc.tracking import AbstractTrackingUpdater
from .api import DHLTrackingAPI

MILESTONES = {
    "AF": MilestoneType.departed_country_of_origin,
    "AR": MilestoneType.arrived_destination_country,
    "BA": MilestoneType.address_research,
    "BL": MilestoneType.address_research,
    "BN": MilestoneType.attempted_contact,
    "CC": MilestoneType.held_for_collection,
    "CD": MilestoneType.customs_clearance,
    "CI": MilestoneType.arrived_destination_country,
    "CM": MilestoneType.address_research,
    "CR": MilestoneType.customs_clearance,
    "DD": MilestoneType.shipment_on_hold,
    "DF": MilestoneType.departed_country_of_origin,
    "DI": MilestoneType.customs_clearance,
    "DM": MilestoneType.shipment_on_hold,
    "DP": MilestoneType.refused,
    "DS": MilestoneType.shipment_on_hold,
    "ES": MilestoneType.added_to_manifest,
    "FD": MilestoneType.arrived_destination_country,
    "HP": MilestoneType.invoice_problem,
    "IC": MilestoneType.customs_clearance,
    "MD": MilestoneType.attempted_delivery,
    "ND": MilestoneType.attempted_delivery,
    "NH": MilestoneType.attempted_delivery,
    "OH": MilestoneType.shipment_on_hold,
    "OK": MilestoneType.delivered,
    "PD": MilestoneType.delivered,
    "PL": MilestoneType.received_by_carrier,
    "PU": MilestoneType.held_for_collection,
    "PY": MilestoneType.invoice_problem,
    "RD": MilestoneType.refused,
    "RR": MilestoneType.address_research,
    "RT": MilestoneType.returned,
    "RW": MilestoneType.added_to_manifest,
    "SA": MilestoneType.added_to_manifest,
    "SC": MilestoneType.customer_delivery_preference_updated,
    "SI": MilestoneType.customs_clearance,
    "SM": MilestoneType.customer_delivery_preference_updated,
    "TP": MilestoneType.delivery_scheduled,
    "UD": MilestoneType.customs_clearance,
    "WC": MilestoneType.out_for_delivery,
    "DUMMY_PU": MilestoneType.data_received_by_carrier,
}


DHLTrackInfo = namedtuple('DHLTrackInfo', [
    'event_code',
    'event_date',
    'description',
    'milestone'
])


class TrackingUpdater(AbstractTrackingUpdater):
    carrier_name = enum.CarrierName.dhl

    def __init__(self, settings, **kwargs):
        super().__init__(settings, **kwargs)
        self.channel_id = kwargs['channel_id']

    def update_trackings(self):
        tracking_numbers = [order_shipment.tracking_number for order_shipment in self._tracking_qs]
        self.log.info(f"Trying to update tracking info for DHL orders: {len(tracking_numbers)}")
        for group in grouper(100, tracking_numbers):
            orders_tracking_info = self._get_orders_tracking_info([tracking_number for tracking_number in group if tracking_number])
            self._update_shipment_milestones(orders_tracking_info)

            delivered_tracking_numbers = [tracking['hawb'] for tracking in orders_tracking_info if tracking['is_delivered']]
            self._set_delivered_status(delivered_tracking_numbers)
            self._update_shipment_delivery_date(delivered_tracking_numbers)

    def _get_orders_tracking_info(self, tracking_numbers):
        api = DHLTrackingAPI(self.settings)
        orders_tracking_info = []
        for carrier_events in api.get_tracking(tracking_numbers):
            tracking_number = str(carrier_events["AWBNumber"])

            action_status = carrier_events["Status"]["ActionStatus"]
            if action_status != "Success":
                self.log.error(f"DHL: Error during parse tracking info for {tracking_number} awb. {action_status}")
                continue

            if "ShipmentEvent" not in carrier_events["ShipmentInfo"]:
                self.log.info(f"DHL: Empty ShipmentEvent info for {tracking_number} awb")
                continue

            tracking_info = []
            shipment_event_items = carrier_events["ShipmentInfo"]["ShipmentEvent"]["ArrayOfShipmentEventItem"]
            shipment_event_items = shipment_event_items if isinstance(shipment_event_items, list) else [shipment_event_items]
            for event in shipment_event_items:
                event_code = event['ServiceEvent']['EventCode']
                milestone = MILESTONES.get(event_code)
                if milestone:
                    tracking_info.append(DHLTrackInfo(
                        milestone=milestone,
                        event_code=event_code,
                        event_date=datetime.strptime(f"{event['Date']}T{event['Time']}", "%Y-%m-%dT%H:%M:%S"),
                        description=event['ServiceEvent']['Description'],
                    ))
            if tracking_info:
                orders_tracking_info.append({
                    'hawb': tracking_number,
                    'is_delivered': self._check_delivered_status(tracking_info),
                    'tracking_info': tracking_info
                })
        return orders_tracking_info

    def _update_shipment_milestones(self, orders_tracking_info):
        for order_tracking in orders_tracking_info:
            with transaction.manager:
                order_shipment = DBSession.query(OrderShipment) \
                    .filter(OrderShipment.status_history.isnot(None),
                            ~OrderShipment.current_status.in_([OrderShipmentStatus.delivered,
                                                               OrderShipmentStatus.returned]),
                            OrderShipment.carrier_id == self.carrier_id,
                            OrderShipment.tracking_number == order_tracking['hawb']) \
                    .first()
                if not order_shipment:
                    continue

                milestones = [ShipmentMilestone(
                    shipment_id=order_shipment.id,
                    is_customer_view=tracking.milestone.args['is_customer_view'],
                    milestone=tracking.milestone,
                    carrier_code=tracking.event_code,
                    event_date=tracking.event_date,
                    description=tracking.description)
                    for tracking in order_tracking['tracking_info']]
                new_milestones = order_shipment.filter_milestones(milestones)
                # Sort for the further correct addition of ShipmentNotification
                new_milestones.sort()
                DBSession.add_all(new_milestones)
                DBSession.refresh(order_shipment)
                order_shipment.update_status_info()

    def _check_delivered_status(self, milestones):
        for milestone in milestones:
            if MilestoneType.is_delivered_milestone(milestone.milestone):
                return True
        return False

    def _set_delivered_status(self, delivered_tracking_numbers):
        order_shipment_qs = DBSession.query(OrderShipment.order_id) \
            .filter(OrderShipment.tracking_number.in_(delivered_tracking_numbers),
                    OrderShipment.carrier_id == self.carrier_id)

        for group in grouper(100, [order_shipment.order_id for order_shipment in order_shipment_qs]):
            delivered_order_ids = list(filter(None, group))
            with transaction.manager:
                order_qs = DBSession.query(Order) \
                    .filter(Order.id.in_(delivered_order_ids)) \
                    .options(selectinload('shipments').load_only('current_status'))
                for order in order_qs:
                    if all(sh.current_status == OrderShipmentStatus.delivered for sh in order.shipments):
                        order.status = enum.OrderStatus.delivered
                        DBSession.flush()
            self.log.info(f"DHL. Set delivered status for orders (id): {delivered_order_ids}")

    def _update_shipment_delivery_date(self, delivered_tracking_numbers):
        with transaction.manager:
            DBSession.query(OrderShipment) \
                .filter(OrderShipment.tracking_number.in_(delivered_tracking_numbers),
                        OrderShipment.current_status == OrderShipmentStatus.delivered) \
                .update({OrderShipment.delivered_date: datetime.utcnow()},
                        synchronize_session=False)

    @property
    def _tracking_qs(self):
        qs = DBSession.query(OrderShipment.tracking_number) \
            .join(Order) \
            .filter(Order.channel_id == self.channel_id,
                    OrderShipment.carrier_id == self.carrier_id,
                    Order.status.in_([enum.OrderStatus.complete,
                                      enum.OrderStatus.not_delivered]))
        if self.tracking_numbers:
            qs = qs.filter(OrderShipment.tracking_number.in_(self.tracking_numbers))
        else:
            date_checking = date.today() - timedelta(days=60)
            qs = qs.filter(OrderShipment.tracking_number.isnot(None),
                           OrderShipment.shipped_date >= date_checking)
        return qs
