import abc


class AbstractCarrier:
    awb_warning_limit = 0
    DeliveredUpdater = None
    TrackingService = None
    ServicePointUpdater = None

    @property
    @abc.abstractmethod
    def name(self):
        pass

    @property
    @abc.abstractmethod
    def ShippingService(self):
        pass

