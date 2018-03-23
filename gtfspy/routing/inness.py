import datetime
import geojson
from geoindex import GeoGridIndex, GeoPoint
from gtfspy.routing.journey_path_analyzer import NodeJourneyPathAnalyzer


class JourneyInness(NodeJourneyPathAnalyzer):
    def __init__(self, labels, walk_to_target_duration, start_time_dep, end_time_dep, origin_stop, gtfs):
        super().__init__(labels, walk_to_target_duration, start_time_dep, end_time_dep, origin_stop)
        self.gtfs = gtfs
        self.radius = None
        self.city_center = GeoPoint(60.171171, 24.941549)

    def set_city_center(self, value):
        assert type(value) is tuple, "City center must be tuple (lat, long)"
        self.city_center = GeoPoint(value)

    def distance_to_city_center(self):
        geo_index = GeoGridIndex()
        for lat, lon, ind in zip(self.gtfs.stops().lat, self.gtfs.stops().lon, self.gtfs.stops().stop_I):
            geo_index.addPoint(GeoPoint(lat, lon, ref=ind)

        dists = [(x[0].ref, x[1]) for geo_index.get_nearest_points(self.city_center, 30, 'km')]
        return dists









