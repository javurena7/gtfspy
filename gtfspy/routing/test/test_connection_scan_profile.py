import unittest

import networkx

from gtfspy.routing.connection_scan_profile import ConnectionScanProfiler
from gtfspy.routing.models import ParetoTuple, Connection

# noinspection PyAttributeOutsideInit


class ConnectionScanProfileTest(unittest.TestCase):

    def setUp(self):
        event_list_raw_data = [
            (2, 4, 40, 50, "trip_6"),
            (1, 3, 32, 40, "trip_5"),
            (3, 4, 32, 35, "trip_4"),
            (2, 3, 25, 30, "trip_3"),
            (1, 2, 10, 20, "trip_2"),
            (0, 1, 0, 10, "trip_1")
        ]
        self.transit_connections = map(lambda el: Connection(*el), event_list_raw_data)
        self.walk_network = networkx.Graph()
        self.walk_network.add_edge(1, 2, {"distance_shape": 20})
        self.walk_network.add_edge(3, 4, {"distance_shape": 15})
        self.walk_speed = 1
        self.source_stop = 1
        self.target_stop = 4
        self.transfer_margin = 0
        self.start_time = 0
        self.end_time = 50

    def test_basics(self):
        csa_profile = ConnectionScanProfiler(self.transit_connections, self.target_stop,
                                             self.start_time, self.end_time, self.transfer_margin,
                                             self.walk_network, self.walk_speed)
        csa_profile.run()

        stop_3_pareto_tuples = csa_profile.stop_profiles[3].get_pareto_tuples()
        self.assertEqual(len(stop_3_pareto_tuples), 1)
        self.assertIn(ParetoTuple(32, 35), stop_3_pareto_tuples)

        stop_2_pareto_tuples = csa_profile.stop_profiles[2].get_pareto_tuples()
        self.assertEqual(len(stop_2_pareto_tuples), 2)
        self.assertIn(ParetoTuple(40, 50), stop_2_pareto_tuples)
        self.assertIn(ParetoTuple(25, 35), stop_2_pareto_tuples)

        source_stop_profile = csa_profile.stop_profiles[self.source_stop]
        source_stop_pareto_optimal_tuples = source_stop_profile.get_pareto_tuples()

        pareto_tuples = set()
        pareto_tuples.add(ParetoTuple(departure_time=10, arrival_time_target=35))
        pareto_tuples.add(ParetoTuple(departure_time=20, arrival_time_target=50))
        pareto_tuples.add(ParetoTuple(departure_time=32, arrival_time_target=55))

        self._assert_pareto_tuple_sets_equal(
            pareto_tuples,
            source_stop_pareto_optimal_tuples
        )

    def test_wrong_event_data_ordering(self):
        event_list_wrong_ordering = [
            (0, 1, 0, 10, "trip_1"),
            (1, 2, 10, 20, "trip_2"),
            (2, 3, 25, 30, "trip_3"),
            (3, 4, 32, 35, "trip_4"),
            (1, 3, 32, 40, "trip_5"),
            (2, 4, 40, 50, "trip_5")
        ]
        csa_profile = ConnectionScanProfiler(event_list_wrong_ordering, self.target_stop,
                                             self.start_time, self.end_time, self.transfer_margin,
                                             self.walk_network, self.walk_speed)
        self.assertRaises(AssertionError, csa_profile.run)

    def test_simple(self):
        event_list_raw_data = [
            (2, 4, 40, 50, "trip_5"),
        ]
        transit_connections = map(lambda el: Connection(*el), event_list_raw_data)
        walk_network = networkx.Graph()
        walk_network.add_edge(1, 2, {"distance_shape": 20})
        walk_network.add_edge(3, 4, {"distance_shape": 15})
        walk_speed = 1
        source_stop = 1
        target_stop = 4
        transfer_margin = 0
        start_time = 0
        end_time = 50

        pareto_tuples = set()
        pareto_tuples.add(ParetoTuple(departure_time=20, arrival_time_target=50))

        csa_profile = ConnectionScanProfiler(transit_connections, target_stop,
                                             start_time, end_time, transfer_margin,
                                             walk_network, walk_speed)
        csa_profile.run()
        source_stop_profile = csa_profile.stop_profiles[source_stop]
        source_stop_pareto_tuples = source_stop_profile.get_pareto_tuples()

        self._assert_pareto_tuple_sets_equal(
            pareto_tuples,
            source_stop_pareto_tuples
        )

    def test_last_leg_is_walk(self):
        event_list_raw_data = [
            (0, 1, 0, 10, "trip_1")
        ]
        transit_connections = map(lambda el: Connection(*el), event_list_raw_data)
        walk_network = networkx.Graph()
        walk_network.add_edge(1, 2, {"distance_shape": 20})

        walk_speed = 1
        source_stop = 0
        target_stop = 2
        transfer_margin = 0
        start_time = 0
        end_time = 50
        pareto_tuples = set()
        pareto_tuples.add(ParetoTuple(departure_time=0, arrival_time_target=30))

        csa_profile = ConnectionScanProfiler(transit_connections, target_stop,
                                             start_time, end_time, transfer_margin,
                                             walk_network, walk_speed)
        csa_profile.run()
        found_tuples = csa_profile.stop_profiles[source_stop].get_pareto_tuples()
        self._assert_pareto_tuple_sets_equal(found_tuples, pareto_tuples)

    def _assert_pareto_tuple_sets_equal(self, found_tuples, should_be_tuples):
        for found_tuple in found_tuples:
            self.assertIn(found_tuple, should_be_tuples)
        for should_be_tuple in should_be_tuples:
            self.assertIn(should_be_tuple, found_tuples)