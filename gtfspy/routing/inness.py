import datetime
from pandas import cut
from gtfspy.util import wgs84_distance
from gtfspy.gtfs import GTFS

class Inness(object):
    def __init__(self, gtfs):
        self.gtfs = gtfs
        self.rings = None
        self.city_center = GeoPoint(60.171171, 24.941549) #Rautatientori, Helsinki
        self.distance_to_city_center = None

    def set_city_center(self, value):
        assert type(value) is tuple, "City center must be tuple (lat, long)"
        self.city_center = GeoPoint(value[0], value[1])

    def get_distance_to_city_center(self):
        """
        Get distance from all the bus stops within a 30 km radius to the city center.
        Output:
            (city_center): lists with [stop_I, distance_in_km] for each stop within a 30 km radius
        """
        geo_index = GeoGridIndex(precision=3)
        for lat, lon, ind in zip(self.gtfs.stops().lat, self.gtfs.stops().lon, self.gtfs.stops().stop_I):
            geo_index.add_point(GeoPoint(lat, lon, ref=ind))
        dists = [[x[0].ref, x[1]] for x in geo_index.get_nearest_points(self.city_center, 30, 'km')]
        self.distance_to_city_center = dists

    def get_rings(self, number=90):
        """
        Get rings to calculate innes.
        Input:
            (number): number of equal length rings
        Output:
            (rings): dictionary with rings (keys) and lists with stop_I's within that ring
        """
        if not self.distance_to_city_center:
            self.get_distance_to_city_center()
        dists = [x[1] for x in self.distance_to_city_center]
        cuts = cut(dists, number, labels=False)
        self.cuts = cuts
        rings = {}
        for stop, ring in zip(self.distance_to_city_center, cuts):
            try:
                rings[ring].append(stop[0])
            except:
                rings[ring] = [stop[0]]
        self.rings = rings


