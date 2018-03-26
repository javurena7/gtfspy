from pandas import cut
from gtfspy.util import wgs84_distance
from gtfspy.gtfs import GTFS

# G = GTFS(path/to/sqlite)
# I = Inness(G)
# I.get_rings()
# I.rings

class Inness(object):
    def __init__(self, gtfs):
        self.gtfs = gtfs
        self.rings = None
        self.city_center = (60.171171, 24.941549) #Rautatientori, Helsinki
        self.distance_to_city_center = None

    def set_city_center(self, value):
        assert type(value) is tuple, "City center must be tuple (lat, long)"
        self.city_center = value

    def get_distance_to_city_center(self):
        """
        Get distance from all the stops to the city center.
        Output:
            (city_center): lists with [stop_I, distance_in_km] for each stop within a 30 km radius
        """
        dists = []
        latc, lonc = self.city_center
        for lat, lon, ind in zip(self.gtfs.stops().lat, self.gtfs.stops().lon, self.gtfs.stops().stop_I):
            dists.append([ind, wgs84_distance(lat, lon, latc, lonc)/1000.])
        self.distance_to_city_center = dists

    def get_rings(self, number=90, max_distance=30):
        """
        Get rings to calculate innes.
        Input:
            (number): number of equal length rings
            (max_distance): maximum distance in km
        Output:
            (rings): dictionary with rings (keys) and lists with stop_I's within that ring
        """
        if not self.distance_to_city_center:
            self.get_distance_to_city_center()
        dists_id = [x for x in self.distance_to_city_center if x[1] < max_distance]
        assert len(dists_id) > 0, "Reset city center - beyond any data point"
        dists = [x[1] for x in dists_id]
        cuts = cut(dists, number, labels=False)
        self.cuts = cuts
        rings = {}
        for stop, ring in zip(dists_ie, cuts):
            try:
                rings[ring].append(stop[0])
            except:
                rings[ring] = [stop[0]]
        self.rings = rings


