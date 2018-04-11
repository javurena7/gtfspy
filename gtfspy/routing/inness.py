from pandas import cut
from gtfspy.util import wgs84_distance
from gtfspy.gtfs import GTFS
from math import acos
from itertools import product
from random import random
from numpy.random import choice
import pickle
# G = GTFS(path/to/sqlite) # '../../data/lm_daily.sqlite'
# I = Inness(G)
# I.get_rings()
# ring = I.rings[5]
# ring_pairs = I.get_ring_pairs(ring)

class Inness(object):
    def __init__(self, gtfs, min_deg=0.17):
        """
        Open an Inness object.
        Parameters:
            (gtfs): GTFS object for which the inness will be computed
        """
        self.gtfs = gtfs
        self.rings = None
        self.city_center = (60.171171, 24.941549) #Rautatientori, Helsinki
        self.distance_to_city_center = None
        self.min_deg = min_deg

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

    def get_rings(self, number=60, max_distance=30):
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
        rings = {}
        for stop, ring in zip(dists_id, cuts):
            try:
                rings[ring].append(stop[0])
            except:
                rings[ring] = [stop[0]]
        self.rings = rings

    def angle_from_city_center(self, stop_1, stop_2):
        """
        Obtain angle (in rad) generated between two stops with an origin in the city center.
        Parameters:
            (stop_1): stop code
            (stop_2): stop code
        """
        lat1, lon1 = self.gtfs.get_stop_coordinates(stop_1)
        lat2, lon2 = self.gtfs.get_stop_coordinates(stop_2)
        latc, lonc = self.city_center
        c = wgs84_distance(lat1, lon1, lat2, lon2)
        a = wgs84_distance(lat1, lon1, latc, lonc)
        b = wgs84_distance(lat2, lon2, latc, lonc)
        cosang = (a**2 + b**2 - c**2)/(2*a*b)
        return acos(cosang)

    def get_ring_pairs(self, ring, sample_size=1.0, min_deg=.17):
        """
        For a ring (list of stop_I), get pairs of stops that are at least min_deg degrees (.17 rad is 10 deg) from each other.
        Note that (stop_1, stop_2) != (stop_2, stop_1), since direction is taken into account for public transportation
        Parameters:
            (ring): int (ring number) or list (of stop_I within that ring)
            (sample_size): expected fraction of pairs to be sampled. Defaults to 1.0, or all the pairs with an angle of more than min_deg
            (min_deg): minimum degree in radians to be included in a pair. Defaults to 0.17 rad, or 10°
        """
        if not self.rings:
            self.get_rings()

        if type(ring) is int:
            ring = self.rings[ring]

        pairs = []
        for stop_1, stop_2 in product(ring, repeat=2):
            if stop_1 != stop_2:
                ang = self.angle_from_city_center(stop_1, stop_2)
                if ang > self.min_deg and random() < sample_size:
                    pairs.append([(stop_1, stop_2), ang])
        return pairs


    def correct_departures_by_angle(self, stop_I, departure_stops, min_deg=None):
        """
        Reutrn stops in departure stops, such that they are at least min_deg randians from stop_I, from the city center
        """

        if min_deg is None:
            min_deg = self.min_deg

        departures = []
        for stop in departure_stops:
            ang = self.angle_from_city_center(stop_I, stop)
            if ang > min_deg:
                departures.append(stop)

        return departures


    def sample_ring_stops(self, ring, sample_size=1.0):
        """
        Given a ring, obtain a sample of target stops
        """

        if not self.rings:
            self.get_rings()

        if type(ring) is int:
            ring = self.rings[ring]

        return choice(self.rings[ring], int(sample_size*len(self.rings[ring])), replace=False)

    def write_rings(self, output_path):
        if not self.rings:
            self.get_rings()
        pickle.dump(self.rings, open(output_path, "wb"))


    def plot_rings(self):
        import matplotlib.pyplot as plt
        if not self.rings:
            self.get_rings()
        fig, ax = plt.subplots(1)
        colors = ['r', 'b', 'k']*int(len(self.rings)/3)
        for ring, color in zip(self.rings.values(), colors):
            for stop in ring:
                lat, lon = self.gtfs.get_stop_coordinates(stop)
                ax.scatter(lon, lat, c=color)
        return fig, ax


