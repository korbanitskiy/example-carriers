import hmac
import hashlib
import requests
import base64

from pyramid.settings import asbool
from ..abc.exc import SendingOrderDelayed


class AramexSAOrderAPI:
    staging_url = 'https://example.url.com'
    production_url = 'https://live-example.url.com'
    allowed_statuses = {200, 201, 202, 203, 204, 205, 206, 207, 226}

    def __init__(self, settings):
        self.production_mode = asbool(settings.get('pimly.order_api.production_mode', False))
        self.username = settings['pimly.aramex_name']
        self.password = settings['pimly.aramex_password']
        self.api_key = settings['pimly.aramex_api_key']

    def send_shipping_file(self, shipping_xml):
        body = shipping_xml.getvalue()
        hmac_sha256 = hmac.new(key=bytes(self.api_key, 'utf-8'), msg=body, digestmod=hashlib.sha256)
        try:
            response = requests.post(
                self.api_url,
                auth=(self.username, self.password),
                data=body,
                headers={
                    'Content-Type': 'application/xml',
                    'x-hmac-sha256': base64.b64encode(hmac_sha256.digest()).decode(),
                },
                timeout=60
            )
        except requests.exceptions.RequestException as e:
            raise SendingOrderDelayed(f"Aramex SA service not available: {e}")
        else:
            if response.status_code not in self.allowed_statuses:
                raise SendingOrderDelayed(f"""
                    Invalid response code: {response.status_code},
                    Request: {response.request.body},
                    Response: {response.text}
                """)

    @property
    def api_url(self):
        if self.production_mode:
            return self.production_url

        return self.staging_url
