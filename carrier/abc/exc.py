class SendingOrderCancelled(Exception):
    """Отмена отправки заказа керриеру"""
    pass


class SendingOrderDelayed(Exception):
    """Отправка заказа керриеру будет повторена со временем"""
    pass
