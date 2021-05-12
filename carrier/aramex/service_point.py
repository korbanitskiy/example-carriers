import requests
from pyramid.settings import asbool

from pimly.models import DBSession
from pimly.models.enum import CarrierName
from ..abc.service_point import Location, AbstractServicePointUpdater
from ..models import Carrier


class ServicePointUpdater(AbstractServicePointUpdater):
    countries = ['SA', 'IQ']
    carrier_name = CarrierName.aramex

    def __init__(self, settings):
        super().__init__(settings)
        self.api = ServicePointAPI(settings)

    def download_service_points(self):
        service_points = []
        for country_code in self.countries:
            service_points.extend(self.api.get_locations(country_code))
        return service_points


class ServicePointAPI:
    staging_url = "https://example.url.com"
    production_url = "https://live-example.url.com"

    def __init__(self, settings):
        production_mode = asbool(settings.get('pimly.order_api.production_mode', False))
        self.url = self.production_url if production_mode else self.staging_url

    def get_locations(self, country_code):
        response = requests.post(
            self.url,
            timeout=60,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=self._body(country_code)
        )

        if response.status_code != 200:
            raise ValueError(f"Invalid response code: {response.status_code}. Response: {response.text}")

        response_json = response.json()
        if response_json.get('HasErrors'):
            raise ValueError(';'.join(note['Message'] for note in response_json['Notifications']))

        processed_locations = set()
        for info in response_json['Locations']:
            code = f"{info['Description']} - {info['ID']}"
            if code not in processed_locations:
                processed_locations.add(code)
                address_lines = (info['Address']['Line1'], info['Address']['Line2'], info['Address']['Line3'])
                yield Location(
                    code=code,
                    name=info['Description'],
                    city=info['Address']['City'],
                    country=info['Address']['CountryCode'],
                    latitude=info['Address']['Latitude'],
                    longitude=info['Address']['Longitude'],
                    address=' '.join(filter(None, address_lines)),
                    work_from=info['WorkingHours'].split('-')[0] if info['WorkingHours'] else None,
                    work_to=info['WorkingHours'].split('-')[1] if info['WorkingHours'] else None,
                    description=info['Description'],
                    zip=info['Address']['PostCode'],
                    phone=info['Telephone']
                )

    def _body(self, country_code):
        carrier = DBSession.query(Carrier).filter(Carrier.name == CarrierName.aramex).one()
        carrier_settings = carrier.get_settings()
        return {
            'ClientInfo': {
                'UserName': carrier_settings.sp_username,
                'Password': carrier_settings.sp_password,
                'AccountNumber': carrier_settings.sp_account_number,
                'AccountPin': carrier_settings.sp_pin,
                'AccountEntity': carrier_settings.sp_account_entity,
                'AccountCountryCode': carrier_settings.sp_country_code,
                'Version': "v1",
            },
            'CountryCode': country_code,
        }
