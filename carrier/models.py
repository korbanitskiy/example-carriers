from collections import namedtuple
from itertools import chain

from sqlalchemy import (
    Column,
    ForeignKey,
    Unicode,
    Integer,
    Boolean,
    UniqueConstraint,
    UnicodeText,
    desc
)
from sqlalchemy.orm import relation, backref
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict

from pimlib.db.types import DeclSource
from pimlib.db.utils import db_created, db_updated

from pimly.models.catalog import Channel
from pimly.utils.helpers import country_names
from .settings import RetailerAddress
from src.pimly.models import enum, Base, DBSession


class Carrier(Base):
    __tablename__ = 'carrier'
    __cache_tags__ = ['carrier']

    id = Column(Integer, primary_key=True, doc=u'ID', info={'skip_filters': True})

    name = Column(DeclSource(Unicode(255), enum.CarrierName), nullable=False, index=True, doc=u'Name')
    settings = Column(MutableDict.as_mutable(JSONB), doc=u'Settings')
    retailer_addresses = Column(MutableDict.as_mutable(JSONB), doc=u'Retailer Addresses')

    def get_settings(self, channel_code='default'):
        field_names = set(chain.from_iterable(self.name.args['settings_fields'].values()))

        carrier_settings = namedtuple("ChannelSettings", field_names)
        default_settings = self.settings['default']
        channel_settings = self.settings.get(channel_code, {})
        for name in field_names:
            value = channel_settings.get(name, default_settings.get(name))
            setattr(carrier_settings, name, value)

        return carrier_settings

    def get_retailer_addresses(self, country_code='default'):
        field_names = list(chain.from_iterable(RetailerAddress.values()))
        carrier_retailer_addresses = namedtuple("ChannelRetailerAddress", field_names)
        default_retailer_addresses = self.retailer_addresses['default']
        channel_retailer_addresses = self.retailer_addresses.get(country_code, {})
        for name in field_names:
            value = channel_retailer_addresses.get(name, default_retailer_addresses.get(name))
            setattr(carrier_retailer_addresses, name, value)

        return carrier_retailer_addresses


class CarrierGroup(Base):
    __tablename__ = 'carrier_group'
    __cache_tags__ = ['carrier_group']

    id = Column(Integer, primary_key=True, doc=u'ID', info={'skip_filters': True})

    name = Column(Unicode(64), nullable=False, index=True, unique=True, doc='Name')
    carrier_id = Column(Integer, ForeignKey('carrier.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})

    carrier = relation(Carrier, backref=backref('carrier_groups', cascade='all, delete-orphan'), info={'skip_filters': True})

    @classmethod
    def html_options(cls, id_attr='id', empty=False, title='', carrier_name=None):
        query = DBSession.query(getattr(cls, id_attr), cls.name)
        if carrier_name:
            carrier_id = DBSession.query(Carrier.id).filter(Carrier.name == carrier_name)
            query = query.filter(cls.carrier_id == carrier_id)
        values = [(getattr(opt, id_attr), opt.name) for opt in query]
        if empty:
            values.insert(0, ('', title))
        return values


class CarrierReturnGroup(Base):
    __tablename__ = 'carrier_return_group'
    __cache_tags__ = ['carrier_return_group']

    id = Column(Integer, primary_key=True, doc=u'ID', info={'skip_filters': True})

    name = Column(Unicode(64), nullable=False, index=True, unique=True, doc='Name')
    carrier_id = Column(Integer, ForeignKey('carrier.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})

    carrier = relation(Carrier, backref=backref('carrier_return_groups', cascade='all, delete-orphan'), info={'skip_filters': True})

    @classmethod
    def html_options(cls, id_attr='id', empty=False, title='', carrier_name=None):
        query = DBSession.query(getattr(cls, id_attr), cls.name)
        if carrier_name:
            carrier_id = DBSession.query(Carrier.id).filter(Carrier.name == carrier_name)
            query = query.filter(cls.carrier_id == carrier_id)
        values = [(getattr(opt, id_attr), opt.name) for opt in query]
        if empty:
            values.insert(0, ('', title))
        return values


class CarrierNumber(Base):
    __tablename__ = 'carrier_number'
    __cache_tags__ = ['carrier_number']

    id = Column(Integer, primary_key=True, doc=u'ID', info={'skip_filters': True})
    carrier_id = Column(Integer, ForeignKey('carrier.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})
    group_id = Column(Integer, ForeignKey('carrier_group.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})

    number = Column(Unicode(), nullable=False, doc='Number')

    carrier = relation(Carrier, info={'skip_filters': True})
    group = relation(CarrierGroup, backref=backref('carrier_numbers', cascade='all, delete-orphan'), info={'skip_filters': True})


class CarrierReturnNumber(Base):
    __tablename__ = 'carrier_return_number'
    __cache_tags__ = ['carrier_return_number']

    id = Column(Integer, primary_key=True, doc=u'ID', info={'skip_filters': True})
    carrier_id = Column(Integer, ForeignKey('carrier.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})
    return_group_id = Column(Integer, ForeignKey('carrier_return_group.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})

    number = Column(Unicode(), nullable=False, doc='Number')

    carrier = relation(Carrier, info={'skip_filters': True})
    return_group = relation(CarrierReturnGroup, backref=backref('carrier_return_numbers', cascade='all, delete-orphan'), info={'skip_filters': True})


class CarrierServicePoint(Base):
    __tablename__ = 'carrier_service_point'
    __cache_tags__ = ['carrier_service_point']
    __table_args__ = (
        UniqueConstraint('code', 'carrier_id', name='uck_carrier_service_point_name_carrier'),
    )

    id = Column(Integer, primary_key=True, doc=u'ID', info={'skip_filters': True})
    carrier_id = Column(Integer, ForeignKey('carrier.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})

    name = Column(Unicode(255), nullable=False, doc=u'Name')
    is_active = Column(Boolean, nullable=False, default=True, server_default='true', doc=u'Is active')
    code = Column(Unicode(255), nullable=False, index=True, doc=u'Code')
    zip = Column(Unicode(128), nullable=True, doc=u'Zip Code')
    phone = Column(Unicode(128), nullable=True, doc=u'Phone')
    country = Column(Unicode(), index=True, doc=u'Country')
    city = Column(Unicode(), doc=u'City')
    address = Column(Unicode(), doc=u'Address')
    description = Column(UnicodeText, doc=u'Description')
    latitude = Column(Unicode(), doc=u'Latitude')
    longitude = Column(Unicode(), doc=u'Longitude')
    work_from = Column(Unicode(32), doc=u'Work from')
    work_to = Column(Unicode(32), doc=u'Work to')

    created = db_created()
    updated = db_updated()

    carrier = relation(Carrier, doc=u'Carrier', info={'skip_filters': True})

    def to_json(self):
        info = {
            'name': self.name,
            'is_active': self.is_active,
            'code': self.code,
            'phone': self.phone,
            'zip': self.zip,
            'work_from': self.work_from,
            'work_to': self.work_to,
            'description': self.description,
            'carrier': self.carrier.name.name,
            'address': {
                'city': self.city,
                'country': self.country,
                'address': self.address
            },
            'coordinates': {
                'lat': self.latitude,
                'lng': self.longitude
            }
        }
        return info


class CarrierPriority(Base):
    __tablename__ = 'carrier_priority'
    __cache_tags__ = ['carrier_priority']
    __table_args__ = (
        UniqueConstraint('channel_id', 'country_code', 'carrier_id', name='uck_carrier_priority_channel_country_carrier'),
    )

    id = Column(Integer, primary_key=True, doc=u'ID', info={'skip_filters': True})
    channel_id = Column(Integer, ForeignKey('channel.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})
    carrier_id = Column(Integer, ForeignKey('carrier.id', onupdate='CASCADE', ondelete='CASCADE'), index=True, nullable=False, info={'skip_filters': True})

    country_code = Column(Unicode(2), nullable=False, index=True, doc=u'Country Code')
    priority = Column(Integer, nullable=False, doc=u'Priority')

    carrier = relation(Carrier, doc=u"Carrier")
    channel = relation(Channel, doc=u"Channel")

    @property
    def human_country(self):
        return country_names.get(self.country_code, self.country_code)

    @classmethod
    def country_priorities(cls, channel_id, country_code):
        qs = DBSession.query(Carrier.name, cls.priority) \
            .join(cls) \
            .filter(cls.channel_id == channel_id,
                    cls.country_code == country_code) \
            .order_by(desc(cls.priority))

        return [(carrier.name, carrier.priority) for carrier in qs]
