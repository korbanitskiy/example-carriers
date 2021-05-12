import transaction
from _operator import attrgetter
from collections import namedtuple
from datetime import datetime
from itertools import groupby

from sqlalchemy.orm import selectinload

from pimly.models import DBSession, enum
from pimly.models.catalog import Channel
from pimly.models.orders import Order, OrderShipment
from pimly.models.tracking.enum import MilestoneType, OrderShipmentStatus
from pimly.models.tracking.models import ShipmentMilestone
from pimly.utils import grouper
from ..abc.tracking import AbstractTrackingUpdater
from .api import NaqelAPI

MILESTONES = {
    100: MilestoneType.attempted_delivery,
    101: MilestoneType.attempted_delivery,
    102: MilestoneType.attempted_delivery,
    103: MilestoneType.customer_address_updated,
    104: MilestoneType.address_research,
    105: MilestoneType.refused,
    106: MilestoneType.refused,
    107: MilestoneType.refused,
    108: MilestoneType.refused,
    109: MilestoneType.refused,
    110: MilestoneType.refused,
    111: MilestoneType.attempted_delivery,
    112: MilestoneType.shipment_on_hold,
    162: MilestoneType.attempted_delivery,
    163: MilestoneType.held_for_collection,
    164: MilestoneType.attempted_delivery,
    165: MilestoneType.attempted_contact,
    166: MilestoneType.attempted_delivery,
    167: MilestoneType.attempted_delivery,
    168: MilestoneType.attempted_delivery,
    169: MilestoneType.attempted_delivery,
    170: MilestoneType.attempted_delivery,
    171: MilestoneType.attempted_delivery,
    172: MilestoneType.delivered,
    113: MilestoneType.lost,
    114: MilestoneType.started_return_process,
    115: MilestoneType.lost,
    120: MilestoneType.arrived_destination_country,
    121: MilestoneType.received_by_carrier,
    122: MilestoneType.received_by_carrier,
    123: MilestoneType.received_by_carrier,
    124: MilestoneType.received_by_carrier,
    125: MilestoneType.customer_address_updated,
    126: MilestoneType.customer_address_updated,
    127: MilestoneType.shipment_on_hold,
    128: MilestoneType.held_for_collection,
    129: MilestoneType.shipment_on_hold,
    130: MilestoneType.shipment_on_hold,
    131: MilestoneType.shipment_on_hold,
    132: MilestoneType.shipment_on_hold,
    133: MilestoneType.shipment_on_hold,
    134: MilestoneType.address_research,
    135: MilestoneType.shipment_on_hold,
    136: MilestoneType.shipment_on_hold,
    137: MilestoneType.shipment_on_hold,
    138: MilestoneType.shipment_on_hold,
    139: MilestoneType.shipment_on_hold,
    140: MilestoneType.shipment_on_hold,
    9: MilestoneType.returned,
    143: MilestoneType.lost,
    173: MilestoneType.arrived_destination_country,
    144: MilestoneType.customs_clearance,
    145: MilestoneType.customs_clearance,
    146: MilestoneType.customs_clearance,
    147: MilestoneType.customs_clearance,
    148: MilestoneType.customs_clearance,
    149: MilestoneType.customs_clearance,
    150: MilestoneType.customs_clearance,
    151: MilestoneType.customs_clearance,
    152: MilestoneType.customs_clearance,
    153: MilestoneType.customs_clearance,
    154: MilestoneType.customs_clearance,
    155: MilestoneType.customs_clearance,
    156: MilestoneType.customs_clearance,
    157: MilestoneType.cleared_customs,
    158: MilestoneType.cleared_customs,
    159: MilestoneType.cleared_customs,
    160: MilestoneType.cleared_customs,
    161: MilestoneType.cleared_customs,
    174: MilestoneType.customs_clearance,
    175: MilestoneType.customs_clearance,
    176: MilestoneType.customs_clearance,
    177: MilestoneType.customs_clearance,
    178: MilestoneType.customs_clearance,
    179: MilestoneType.customs_clearance,
    180: MilestoneType.customs_clearance,
    181: MilestoneType.customs_clearance,
    182: MilestoneType.customs_clearance,
    183: MilestoneType.customs_clearance,
    184: MilestoneType.customs_clearance,
    185: MilestoneType.customs_clearance,
    186: MilestoneType.customs_clearance,
    187: MilestoneType.customs_clearance,
    188: MilestoneType.customs_clearance,
    189: MilestoneType.customs_clearance,
    190: MilestoneType.customs_clearance,
    191: MilestoneType.started_return_process,
    192: MilestoneType.started_return_process,
    193: MilestoneType.started_return_process,
    194: MilestoneType.started_return_process,
    195: MilestoneType.started_return_process,
    196: MilestoneType.started_return_process,
    197: MilestoneType.started_return_process,
    202: MilestoneType.shipment_on_hold,
    203: MilestoneType.shipment_on_hold,
    207: MilestoneType.shipment_on_hold,
    208: MilestoneType.missing_id,
    209: MilestoneType.missing_id,
    210: MilestoneType.missing_id,
    211: MilestoneType.missing_id,
    213: MilestoneType.cleared_customs,
    214: MilestoneType.started_return_process,
    215: MilestoneType.started_return_process,
    216: MilestoneType.started_return_process,
    217: MilestoneType.started_return_process,
    218: MilestoneType.started_return_process,
    219: MilestoneType.started_return_process,
    220: MilestoneType.started_return_process,
    3: MilestoneType.arrived_destination_country,
    222: MilestoneType.shipment_on_hold,
    223: MilestoneType.shipment_on_hold,
    224: MilestoneType.started_return_process,
    225: MilestoneType.shipment_on_hold,
    7: MilestoneType.delivered,
    5: MilestoneType.out_for_delivery,
    1: MilestoneType.arrived_destination_country,
    0: MilestoneType.data_received_by_carrier,
    27: MilestoneType.data_received_by_carrier,
    28: MilestoneType.data_received_by_carrier,
    29: MilestoneType.held_for_collection,
    30: MilestoneType.customs_clearance,
    31: MilestoneType.arrived_destination_country,
    34: MilestoneType.refused,
    35: MilestoneType.attempted_contact,
    36: MilestoneType.shipment_on_hold,
    37: MilestoneType.held_for_collection,
    38: MilestoneType.address_research,
    39: MilestoneType.attempted_contact,
    40: MilestoneType.attempted_contact,
    41: MilestoneType.customer_address_updated,
    42: MilestoneType.attempted_contact,
    43: MilestoneType.attempted_contact,
    45: MilestoneType.lost,
    226: MilestoneType.arrived_destination_country,
    50: MilestoneType.returned,
    51: MilestoneType.started_return_process,
    52: MilestoneType.started_return_process,
    54: MilestoneType.started_return_process,
    55: MilestoneType.received_by_carrier,
    56: MilestoneType.received_by_carrier,
    57: MilestoneType.received_by_carrier,
}

NaqelTrackInfo = namedtuple('NaqelTrackInfo', [
    'event_code',
    'event_date',
    'description',
    'hawb',
    'milestone'
])


class TrackingService(AbstractTrackingUpdater):
    carrier_name = enum.CarrierName.naqel

    def __init__(self, settings, **kwargs):
        super().__init__(settings, **kwargs)
        self.channel_id = kwargs['channel_id']
        self.channel_code = DBSession.query(Channel.code).filter(Channel.id == self.channel_id).scalar()

    def update_trackings(self):
        order_awbs = [order_shipment.tracking_number for order_shipment in self._tracking_qs]
        for group in grouper(10, order_awbs):
            orders_tracking_info = self._get_events(filter(None, group))
            self._update_shipment_milestones(orders_tracking_info)

            delivered_tracking_numbers = [tracking['hawb'] for tracking in orders_tracking_info if tracking['is_delivered']]
            self._set_delivered_status(delivered_tracking_numbers)
            self._update_shipment_delivery_date(delivered_tracking_numbers)

    def _get_events(self, hawbs):
        naqel_api = NaqelAPI(self.settings, self.channel_code)
        carrier_events = naqel_api.get_tracking_info(hawbs)
        events = [self._parse_events(event) for event in carrier_events]
        orders_tracking_info = []
        for hawb, events_by_hawb in groupby(filter(None,events), key=attrgetter('hawb')):
            tracking_info = list(events_by_hawb)
            orders_tracking_info.append({
                'hawb': hawb,
                'is_delivered': self._check_delivered_status(tracking_info),
                'tracking_info': tracking_info
            })
        return orders_tracking_info

    @staticmethod
    def _parse_events(event):
        milestone = MILESTONES.get(event['ActivityCode'])
        if milestone:
            return NaqelTrackInfo(
                hawb=str(event['WaybillNo']),
                milestone=milestone,
                event_code=str(event['ActivityCode']),
                event_date=event['Date'],
                description=event['Activity'],
            )
        else:
            return None

    @staticmethod
    def _check_delivered_status(milestones):
        for milestone in milestones:
            if MilestoneType.is_delivered_milestone(milestone.milestone):
                return True
        return False

    def _update_shipment_milestones(self, orders_tracking_info):
        for order_tracking in orders_tracking_info:
            with transaction.manager:
                order_shipment = DBSession.query(OrderShipment) \
                    .filter(OrderShipment.status_history != None,
                            ~OrderShipment.current_status.in_([OrderShipmentStatus.delivered, OrderShipmentStatus.returned]),
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
            self.log.info(f"Naqel. Set delivered status for orders (id): {delivered_order_ids}")

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
            qs = qs.filter(OrderShipment.tracking_number.isnot(None),
                           OrderShipment.shipped_date.between(self.from_date, self.to_date))
        return qs
