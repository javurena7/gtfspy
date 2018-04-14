import datetime
import geojson
from pandas import cut
from geoindex import GeoGridIndex, GeoPoint
from gtfspy.routing.journey_path_analyzer import NodeJourneyPathAnalyzer
from gtfspy.util import wgs84_distance
import matplotlib.pyplot as plt
from gtfspy.route_types import ROUTE_TYPE_TO_COLOR
from numpy import inf

from numpy.random import uniform # while we get a real inness function

# EXAMPLE PATH
# path = [1929, 1843, 1686, 1563, 1505, 1333, 1179, 1069, 916, 817, 774, 706, 707, 594, 647, 586, 540, 483, 510, 423, 407, 397]


class JourneyInness(NodeJourneyPathAnalyzer):
    def __init__(self, labels, walk_to_target_duration, start_time_dep, end_time_dep, origin_stop, gtfs):
        super().__init__(labels, walk_to_target_duration, start_time_dep, end_time_dep, origin_stop)
        self.gtfs = gtfs
        self.rings = None
        self.city_center = (60.171171, 24.941549) #Rautatientori, Helsinki
        self.distance_to_city_center = None
        self.all_journey_inness = []
        self.path_coordinates = None
        self.all_journey_coordinates = [self._path_coordinates(path) for path in self.all_journey_stops]
        self.inness_stops = None
        self._inness_dict = None
        self.inness_summary = None

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

    def crossed(self, x, y, xi, xf):
        """
        Auxiliary check if the current edge crosses the line determined
        by the origin and destination node
        """

        if isinstance(x, int):
            X1, Y1 = self.gtfs.get_stop_coordinates(x)
        else:
            X1, Y1 = x
        if isinstance(y, int):
            X2, Y2 = self.gtfs.get_stop_coordinates(y)
        else:
            X2, Y2 = y
        if isinstance(xi, int):
            X3, Y3 = self.gtfs.get_stop_coordinates(xi)
        else:
            X3, Y3 = xi
        if isinstance(xf, int):
            X4, Y4 = self.gtfs.get_stop_coordinates(xf)
        else:
            X4, Y4 = xf
        if (max(X1, X2) < min(X3, X4)):
            return False
        try:
            A1 = (Y1 - Y2)/(X1 - X2)
        except ZeroDivisionError:
            A1 = inf
        try:
            A2 = (Y3 - Y4)/(X3 - X4)
        except ZeroDivisionError:
            A2 = inf
        b1 = Y1 - A1 * X1
        b2 = Y3- A2 * X3
        if A1 == A2:
            return False

        try:
            Xa = (b2 - b1) / (A1 - A2)
        except:
            Xa = inf
        if Xa < max(min(X1, X2), min(X3, X4)) or Xa > min(max(X1, X2), max(X3, X4)):
            return False
        return True


    def intersection(self, stop_1, stop_2, stop_3, stop_4):
        """
        Calculate intersection of two lines
        """
        if isinstance(stop_1, int):
            x1, y1 = self.gtfs.get_stop_coordinates(stop_1)
        else:
            x1, y1 = stop_1
        if isinstance(stop_2, int):
            x2, y2 = self.gtfs.get_stop_coordinates(stop_2)
        else:
            x2, y2 = stop_2
        if isinstance(stop_3, int):
            x3, y3 = self.gtfs.get_stop_coordinates(stop_3)
        else:
            x3, y3 = stop_3
        if isinstance(stop_4, int):
            x4, y4 = self.gtfs.get_stop_coordinates(stop_4)
        else:
            x4, y4 = stop_4
        denom = ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4))
        c1 = (x1 * y2 - y1 * x2)
        c2 = (x3 * y4 - y3 * x4)
        xc = (c1 * (x3 - x4) - (x1 - x2) * c2) / denom
        yc = (c1 * (y3 - y4) - (y1 - y2) * c2) / denom
        return xc, yc


    def get_area(self, path):
        """
        The shoelace formula for the are of a polygon
        """
        x1, y1 = path[len(path)-1]
        x2, y2 = path[0]
        A = (x2 + x1) * (y2 - y1)
        for n in range(len(path)-1):
            x1, y1 = path[n]
            x2, y2 = path[n+1]
            A += (x2 + x1) * (y2 - y1)
        return 0.5*abs(A)


    def inness(self, path):
        """
        Calculate inness for a path. The pair is the first and last
        element in 'path', angle is the angle between them (on the ring)
        and r is the radius of the ring.
        """
        path = self._path_coordinates(path)
        stop_int, stop_fnl = path[0], path[-1]
        slope, cte = self._get_line_params(stop_int, stop_fnl)
        inness = 0.0
        corners = []
        total_area = 0.0
        for stop_0, stop_1 in zip(path[:-1], path[1:]):
            corners.append(stop_0)
            if self.crossed(stop_int, stop_fnl, stop_0, stop_1):
                stop_c = self.intersection(stop_int, stop_fnl, stop_0, stop_1)
                corners.append(stop_c)
                sign = self._get_inness_path_sign(stop_0, slope, cte)
                area = self.get_area(corners)
                inness += sign * area
                total_area += area
                corners = [stop_c]
        if total_area == 0.0:
            return 0.0
        return inness/total_area


    def _get_line_params(self, stop_int, stop_fnl):

        slope = (stop_int[1] - stop_fnl[1])/(stop_int[0] - stop_fnl[0])
        cte = -slope*stop_fnl[0] + stop_fnl[1]

        return slope, cte

    def _get_inness_path_sign(self, stop_0, slope, cte):

        ref = self.city_center[1] > slope*self.city_center[0] + cte
        new = stop_0[1] > slope*stop_0[0] + cte

        if ref == new :
            return 1
        else:
            return -1

    def plot_path(self, path):
        plt.ion()
        fig = plt.figure()
        ax = fig.add_subplot(111, projection="smopy_axes")
        path = self._path_coordinates(path)
        lats = [x[0] for x in path]
        lons = [x[1] for x in path]

        ax.plot(lons, lats, c='b', zorder=1)
        ax.scatter(lons, lats, c='k')
        ax.plot([lons[0], lons[-1]], [lats[0], lats[-1]], c='k', zorder=1)
        ax.add_scale_bar()
        return fig, ax

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

        self.inness_summary = summary

    def _stop_inness_summary(self):
        if not self._inness_summary:
            self.get_inness()
        stop_set = set(stop for journey in self.all_journey_stops for stop in journey)
        stops = {}
        for stop in stop_set:
            for journey, journey_dict in self.inness_summary.items():
                if stop in journey_dict['stops']:
                    try:
                        stops[stop].append((journey_dict['inness'], journey_dict['proportion']))
                    except KeyError:
                        stops[stop] = [(journey_dict['inness'], journey_dict['proportion'])]
        self.inness_stops = stops


