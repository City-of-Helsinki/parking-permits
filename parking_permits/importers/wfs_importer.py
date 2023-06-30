import abc
import logging

import requests
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry

logger = logging.getLogger("db")


class WfsImporter(metaclass=abc.ABCMeta):
    wfs_url = settings.KAMI_URL

    @property
    @abc.abstractmethod
    def wfs_typename(self):
        pass

    def download_and_parse(self):
        response = self._download()
        return self._parse_response(response)

    def _download(self):
        logger.info("Getting data from the server.")
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "OUTPUTFORMAT": "json",
            "REQUEST": "GetFeature",
            "srsName": "EPSG:4326",
            "TYPENAME": self.wfs_typename,
        }
        response = requests.get(self.wfs_url, params=params)
        value = response.json()
        return value["features"]

    def _parse_response(self, features):
        logger.info("Parsing Data.")
        for feature in features:
            yield self._parse_feature(feature)

    @abc.abstractmethod
    def _parse_feature(self, feature):
        pass

    def convert_to_geosgeometry(self, geometry):
        return GEOSGeometry(str(geometry))
