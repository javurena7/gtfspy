import datetime
import geojson
from pandas import cut
from geoindex import GeoGridIndex, GeoPoint
from gtfspy.routing.journey_path_analyzer import NodeJourneyPathAnalyzer
from gtfspy.util import wgs84_distance

from numpy.random import uniform # while we get a real inness function

class JourneyInness(NodeJourneyPathAnalyzer):
    def __init__(self, labels, walk_to_target_duration, start_time_dep, end_time_dep, origin_stop, gtfs):
        super().__init__(labels, walk_to_target_duration, start_time_dep, end_time_dep, origin_stop)
        self.gtfs = gtfs
        self.rings = None
        self.city_center = GeoPoint(60.171171, 24.941549) #Rautatientori, Helsinki
        self.distance_to_city_center = None
        self.all_journey_inness = []
        self.path_coordinates = None
        self.all_journey_coordinates = [self._path_coordinates(path) for path in self.all_journey_stops]

        self._inness_dict = None

    def _path_coordinates(self, path):
        assert self.gtfs is not None
        return [self.gtfs.get_stop_coordinates(stop) for stop in path]

    def get_inness(self):
        """
        Obtain inness for all pareto-optimal paths
        """
        inness_dict = {}
        all_journey_inness = []
        for journey_id, journey in zip(self.journey_boarding_stops, self.all_journey_stops):
            try:
                all_journey_inness.append(inness_dict[journey_id])
            except KeyError:
                inness_dict[journey_id] = self.inness(journey)
                all_journey_inness.append(inness_dict[journey_id])
        self.all_journey_inness = all_journey_inness
        self._inness_dict = inness_dict


    def inness(self, journey):
        return uniform(-1, 1)

    def mean_journey_inness(self):
        if not self._inness_dict:
            self.get_inness()
        journey_variant_inness = [self._inness_dict[j] for j in self.journey_set_variants]
        return sum(i * j for i, j in zip(journey_variant_inness, self.variant_proportions))


