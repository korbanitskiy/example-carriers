import csv
import os
import shutil
import transaction
from _operator import attrgetter
from collections import namedtuple
from datetime import datetime
from itertools import groupby

from pimlib.utils.files import ensure_dir
from pyramid.settings import asbool
from sqlalchemy.orm import selectinload

from pimly.models import DBSession, enum
from pimly.models.orders import Order, OrderShipment
from pimly.models.task_manager.aramex_source import ORDER_EVENT_CATEGORY, TASK_HANDLERS
from pimly.models.tracking.enum import MilestoneType, OrderShipmentStatus
from pimly.models.tracking.models import ShipmentMilestone
from pimly.models.carrier.abc.tracking import AbstractTrackingUpdater
from pimly.utils.downloaders import SFTPLoader
from pimly.utils import grouper

MILESTONES = {
    "SH249": MilestoneType.customer_contacted,
    "SH271": MilestoneType.customer_contacted,
    "SH369": MilestoneType.customer_contacted,
    "SH295": MilestoneType.customer_contacted,
    "SH296": MilestoneType.customer_address_updated,
    "SH034": MilestoneType.delivered_to_customer,
    "SH035": MilestoneType.customs_clearance,
    "SH013": MilestoneType.added_to_manifest,
    "SH041": MilestoneType.cleared_customs,
    "SH280": MilestoneType.customs_clearance,
    "SH005": MilestoneType.delivered,
    "SH006": MilestoneType.delivered_to_customer,
    "SH007": MilestoneType.delivered,
    "SH234": MilestoneType.delivered,
    "SH496": MilestoneType.delivered_to_customer,
    "SH162D11": MilestoneType.attempted_delivery,
    "SH162D13": MilestoneType.attempted_delivery,
    "SH162D16": MilestoneType.attempted_delivery,
    "SH001": MilestoneType.arrived_destination_country,
    "SH003": MilestoneType.out_for_delivery,
    "SH281": MilestoneType.customs_clearance,
    "SH008": MilestoneType.shipment_on_hold,
    "SH156C00": MilestoneType.customs_clearance,
    "SH156C01": MilestoneType.customs_clearance,
    "SH156C02": MilestoneType.customs_clearance,
    "SH156C03": MilestoneType.customs_clearance,
    "SH156C04": MilestoneType.customs_clearance,
    "SH156C05": MilestoneType.customs_clearance,
    "SH156C06": MilestoneType.customs_clearance,
    "SH156C07": MilestoneType.customs_clearance,
    "SH156C08": MilestoneType.customs_clearance,
    "SH156C09": MilestoneType.invoice_problem,
    "SH156C10": MilestoneType.customs_clearance,
    "SH156C11": MilestoneType.customs_clearance,
    "SH156C12": MilestoneType.customs_clearance,
    "SH156C13": MilestoneType.customs_clearance,
    "SH156C14": MilestoneType.customs_clearance,
    "SH156C15": MilestoneType.customs_clearance,
    "SH156C16": MilestoneType.customs_clearance,
    "SH156C17": MilestoneType.customs_clearance,
    "SH156C26": MilestoneType.customs_clearance,
    "SH156C27": MilestoneType.customs_clearance,
    "SH156C28": MilestoneType.customs_clearance,
    "SH156C29": MilestoneType.customs_clearance,
    "SH156C30": MilestoneType.customs_clearance,
    "SH164": MilestoneType.held_for_collection,
    "SH047": MilestoneType.received_by_carrier,
    "SH069": MilestoneType.started_return_process,
    "SH071": MilestoneType.started_return_process,
    "SH162D08": MilestoneType.shipment_on_hold,
    "SH162D10": MilestoneType.shipment_on_hold,
    "SH162D15": MilestoneType.shipment_on_hold,
    "SH162D18": MilestoneType.shipment_on_hold,
    "SH162D34": MilestoneType.shipment_on_hold,
    "SH162D37": MilestoneType.shipment_on_hold,
    "SH162D40": MilestoneType.shipment_on_hold,
    "SH162D41": MilestoneType.shipment_on_hold,
    "SH162G02": MilestoneType.shipment_on_hold,
    "SH162G03": MilestoneType.shipment_on_hold,
    "SH162M01": MilestoneType.shipment_on_hold,
    "SH162M02": MilestoneType.shipment_on_hold,
    "SH162O01": MilestoneType.shipment_on_hold,
    "SH073": MilestoneType.out_for_delivery,
    "SH252": MilestoneType.out_for_delivery,
    "SH033A00": MilestoneType.attempted_delivery,
    "SH033A01": MilestoneType.attempted_delivery,
    "SH033A02": MilestoneType.attempted_delivery,
    "SH033A03": MilestoneType.attempted_delivery,
    "SH033A04": MilestoneType.attempted_delivery,
    "SH033A05": MilestoneType.attempted_delivery,
    "SH033A06": MilestoneType.attempted_delivery,
    "SH033A07": MilestoneType.attempted_delivery,
    "SH033A08": MilestoneType.attempted_delivery,
    "SH033A09": MilestoneType.attempted_delivery,
    "SH033A10": MilestoneType.attempted_delivery,
    "SH033A11": MilestoneType.attempted_delivery,
    "SH033A12": MilestoneType.attempted_delivery,
    "SH033A13": MilestoneType.attempted_delivery,
    "SH033A14": MilestoneType.attempted_delivery,
    "SH033A15": MilestoneType.attempted_delivery,
    "SH033A16": MilestoneType.attempted_delivery,
    "SH033A17": MilestoneType.refused,
    "SH033A18": MilestoneType.refused,
    "SH033A19": MilestoneType.refused,
    "SH033A20": MilestoneType.attempted_delivery,
    "SH033A21": MilestoneType.attempted_delivery,
    "SH033A22": MilestoneType.attempted_delivery,
    "SH033A23": MilestoneType.refused,
    "SH043U00": MilestoneType.attempted_delivery,
    "SH043U01": MilestoneType.attempted_delivery,
    "SH043U02": MilestoneType.attempted_delivery,
    "SH043U05": MilestoneType.shipment_on_hold,
    "SH043U07": MilestoneType.attempted_delivery,
    "SH043U09": MilestoneType.attempted_delivery,
    "SH043U10": MilestoneType.refused,
    "SH043U18": MilestoneType.attempted_delivery,
    "SH043U19": MilestoneType.attempted_delivery,
    "SH043U20": MilestoneType.attempted_delivery,
    "SH294U11": MilestoneType.attempted_contact,
    "SH294U12": MilestoneType.address_research,
    "SH294U13": MilestoneType.attempted_contact,
    "SH294U14": MilestoneType.attempted_contact,
    "SH294U15": MilestoneType.attempted_contact,
    "SH294U16": MilestoneType.attempted_contact,
    "SH294U17": MilestoneType.attempted_contact,
    "SH237": MilestoneType.lost,
    "SH237D20": MilestoneType.lost,
    "SH237D21": MilestoneType.lost,
    "SH237D22": MilestoneType.lost,
    "SH237D23": MilestoneType.lost,
    "SH237D24": MilestoneType.lost,
    "SH237D25": MilestoneType.lost,
    "SH237D27": MilestoneType.lost,
    "SH237D35": MilestoneType.lost,
    "SH022": MilestoneType.departed_country_of_origin,
    "SH534": MilestoneType.delivered_to_customer,
}


AramexTrackInfo = namedtuple('AramexTrackInfo', [
    'order_awb',
    'milestone',
    'task_type',
    'event_code',
    'action_date',
    'msg1',
    'msg2',
])


class TrackingService(AbstractTrackingUpdater):
    carrier_name = enum.CarrierName.aramex
    remote_dir = "carriers/aramex/tracking_numbers/"

    def __init__(self, settings, **kwargs):
        super().__init__(settings, **kwargs)
        self.src_path = os.path.join(self.settings['pimly.carriers.main_path'], self.carrier_name.name, 'task_events')
        self.archive_path = os.path.join(self.src_path, 'Archive')
        self.production_mode = asbool(settings['pimly.order_api.production_mode'])
        ensure_dir(self.archive_path)
        self.loader = SFTPLoader(
            host=settings['pimly.feed.sftp.server'],
            login=settings['pimly.feed.sftp.user'],
            password=settings['pimly.feed.sftp.password'],
        )

    def update_trackings(self):
        self.loader.download_files(self.remote_dir, self.src_path, remove_src=self.production_mode, timeout=60)
        files = (os.path.join(self.src_path, f) for f in os.listdir(self.src_path))
        for file_path in filter(os.path.isfile, files):
            self.log.info(f"Aramex. Process file: {file_path}")

            order_trackings = self._parse_file(file_path)
            self._update_shipment_milestones(order_trackings)

            delivered_tracking_numbers = [tracking['hawb'] for tracking in order_trackings if tracking['is_delivered']]
            self._set_delivered_status(delivered_tracking_numbers)
            self._update_shipment_delivery_date(delivered_tracking_numbers)
            self._create_order_tasks(order_trackings)
            self._archive_file(file_path)

    def _parse_file(self, file_path):
        with open(file_path, encoding='utf-8-sig') as src:
            reader = csv.DictReader(src, skipinitialspace=True)
            tracking_events = filter(None, (self._parse_row(row) for row in reader))
            tracking_events = sorted(tracking_events, key=attrgetter('order_awb'))

        order_events = []
        for awb, events in groupby(tracking_events, key=attrgetter('order_awb')):
            awb_events = list(events)
            order_events.append({
                'hawb': awb,
                'is_delivered': self._check_delivered_status(awb_events),
                'tracking_info': awb_events
            })

        return order_events

    def _parse_row(self, track):
        pin_number = track['PINumber'].replace(' ', '') if track['PINumber'] else ''
        problem_code = track['ProblemCode'].replace(' ', '') if track['ProblemCode'] else ''
        event_code = f"{pin_number}{problem_code}"
        milestone = MILESTONES.get(event_code.upper())
        if not milestone:
            return None

        action_date = track['ActionDate'].strip() if track['ActionDate'] else ''
        action_time = track['ActionTime'].strip() if track['ActionTime'] else ''

        try:
            event_date = datetime.strptime(f"{action_date}T{action_time}", "%d/%m/%yT%H:%M")
        except ValueError:
            self.exception_log.exception("Aramex: Error during parse file. [Event Date format]")
            return None

        comment1 = track['Comment1'].strip() if track['Comment1'] else ''
        comment2 = track['Comment2'].strip() if track['Comment2'] else ''

        return AramexTrackInfo(
            order_awb=track['AWB'].replace(' ', '') if track['AWB'] else '',
            task_type=ORDER_EVENT_CATEGORY.get(event_code),
            milestone=milestone,
            event_code=event_code,
            action_date=event_date,
            msg1=comment1,
            msg2=comment2
        )

    def _check_delivered_status(self, order_tracking):
        for tracking in order_tracking:
            if MilestoneType.is_delivered_milestone(tracking.milestone):
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
                        event_date=tracking.action_date,
                        description=". ".join(filter(None, [tracking.msg1, tracking.msg2])))
                    for tracking in order_tracking['tracking_info']]
                new_milestones = order_shipment.filter_milestones(milestones)
                # Sort for the further correct addition of ShipmentNotification
                new_milestones.sort()
                DBSession.add_all(new_milestones)
                DBSession.refresh(order_shipment)
                order_shipment.update_status_info()

    def _create_order_tasks(self, orders_tracking_info):
        event_tasks = {}
        for order_tracking in orders_tracking_info:
            for tracking in order_tracking['tracking_info']:
                if tracking.task_type:
                    event_tasks.setdefault(tracking.task_type, []).append(tracking)

        for event_type, events in event_tasks.items():
            Handler = TASK_HANDLERS[event_type]
            handler = Handler()
            handler.create_tasks(events)

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
                self.log.info(f"Aramex. Set delivered status for orders (id): {delivered_order_ids}")

    def _update_shipment_delivery_date(self, delivered_tracking_numbers):
        with transaction.manager:
            DBSession.query(OrderShipment) \
                .filter(OrderShipment.tracking_number.in_(delivered_tracking_numbers),
                        OrderShipment.current_status == OrderShipmentStatus.delivered) \
                .update({OrderShipment.delivered_date: datetime.utcnow()},
                        synchronize_session=False)

    def _archive_file(self, file_path):
        current_time = datetime.utcnow().strftime("%Y-%m-%d_%H:%M")
        file_name = os.path.basename(file_path)
        unique_name = f"{current_time}-{file_name}"
        dst = os.path.join(self.archive_path, unique_name)
        shutil.copyfile(file_path, dst)
        os.remove(file_path)
