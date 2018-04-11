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
        self.mean_inness_summary = None
        self.inness_stop = None
        self._inness_dict = None

        self.get_inness()

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
        self._inness_summary()
        self._stop_inness_summary()


    def inness(self, journey):
        return uniform(-1, 1)


    def mean_journey_inness(self):
        if not self._inness_dict:
            self.get_inness()
        journey_variant_inness = [self._inness_dict[j] for j in self.journey_set_variants]
        return sum(i * j for i, j in zip(journey_variant_inness, self.variant_proportions))


    def _inness_summary(self):
        if not self._inness_dict:
            self.get_inness()
        summary = {}
        variant_proportion = {journey_id: prop for journey_id, prop in zip(self.journey_set_variants, self.variant_proportions)}
        for id_num, journey_id in enumerate(self.journey_boarding_stops):
            if journey_id not in summary:
                summary[journey_id] = {}
                summary[journey_id]['stops'] = self.all_journey_stops[id_num]
                summary[journey_id]['inness'] = self._inness_dict[journey_id]
                summary[journey_id]['proportion'] = variant_proportion[journey_id]

        self.mean_inness_summary = summary

    def _stop_inness_summary(self):
        if not self._inness_summary:
            self.get_inness()
        stop_set = set(stop for journey in self.all_journey_stops for stop in journey)
        stops = {}
        for stop in stop_set:
            for journey, journey_dict in self.mean_inness_summary.items():
                if stop in journey_dict['stops']:
                    try:
                        stops[stop].append((journey_dict['inness'], journey_dict['proportion']))
                    except KeyError:
                        stops[stop] = [(journey_dict['inness'], journey_dict['proportion'])]
        self.inness_stop = stops


