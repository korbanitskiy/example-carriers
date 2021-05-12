from formencode import validators, Pipe
from pimly.lib.form import Schema

from pimly.models import enum


class BaseCarrierCompleteForm(Schema):
    filter_extra_fields = True
    allow_extra_fields = True

    carrier_process = validators.DictConverter(enum.CarrierName.dict(), not_empty=True)
    box_qty = Pipe(validators.Int(min=1))
