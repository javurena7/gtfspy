from gtfspy.routing.inness_journey import JourneyInness
from gtfspy.routing.inness import Inness
from gtfspy.routing.helpers import get_transit_connections, get_walk_network
from gtfspy.routing.multi_objective_pseudo_connection_scan_profiler import MultiObjectivePseudoCSAProfiler
from gtfspy.gtfs import GTFS
import pickle
import os
import yaml

# READ THIS FROM YAML CONFIG FILE
results_path = 'results'
cutoff_time = 2 * 3600

def _compute_stops_inness(stop_I, departure_stops, G, connections, walk_network):

    start_time = G.get_suitable_date_for_daily_extract(ut=True) + 8 * 3600
    end_time = G.get_suitable_date_for_daily_extract(ut=True) + 12 * 3600

    mpCSA = MultiObjectivePseudoCSAProfiler(connections, targets=[stop_I], walk_network=walk_network, end_time_ut=end_time, transfer_margin=120, start_time_ut=start_time, walk_speed=1.5, verbose=True, track_vehicle_legs=True, track_time=True, track_route=True)

    mpCSA.run()
    profiles = mpCSA.stop_profiles
    labels = dict((key, value.get_final_optimal_labels()) for (key, value) in profiles.items())
    walk_times = dict((key, value.get_walk_to_target_duration()) for (key, value) in profiles.items())

    journey_inness_list = []
    inness_per_stop = {}

    for stop in departure_stops:

        JI = JourneyInness(labels[stop], walk_times[stop], start_time, end_time - cutoff_time, stop, G)
        inness_per_stop = _add_inness_stops(inness_per_stop, JI.inness_stop)
        journey_inness_list.append(JI)

    return inness_per_stop, journey_inness_list


def _add_inness_stops(inness_per_stop, new_obs):
    for stop, inness_vals in new_obs.items():
        try:
            inness_per_stop[stop] += inness_vals
        except:
            inness_per_stop[stop] = inness_vals

    return inness_per_stop


def compute_ring_inness(ring_Is=None, ring_id=None, inness_obj=None):
    G = inness_obj.gtfs
    start_time = G.get_suitable_date_for_daily_extract(ut=True) + 8 * 3600
    end_time = G.get_suitable_date_for_daily_extract(ut=True) + 12 * 3600

    connections = get_transit_connections(G, start_time, end_time)
    walk_network = get_walk_network(G)
    inness_per_stop = {}

    for i, stop_I in enumerate(ring_Is):
        print(stop_I, i+1, "/", len(ring_Is))
        if i > 3:
            break
        departure_stops = inness_obj.correct_departures_by_angle(stop_I, ring_Is)
        try:
            stop_inness, journey_inness_list = _compute_stops_inness(stop_I, departure_stops, G, connections, walk_network)
        except:
            raise("FAIL")
            stop_inness = {}
            journey_inness_list = None
        inness_per_stop = _add_inness_stops(inness_per_stop, stop_inness)

        file_name = os.path.join(results_path, "{ring}/stop_{stop}.p".format(ring=str(ring_id), stop=str(stop_I)))

        if journey_inness_list is not None:
            with open(file_name, "wb") as f:
                pickle.dump(journey_inness_list, f)

    inness_per_stop_file_name = os.path.join(results_path, "{ring}_stops.p")
    with open(inness_per_stop_file_name, "wb") as f:
        pickle.dump(inness_per_stop, f)

    return inness_per_stop

def mean_stop_inness(inness_per_stop):
    mean_stop_inness = {}
    for stop, values in inness_per_stop.items():
        tot_prop = sum(x[1] for x in values)
        mean_stop_inness[stop] = sum(x[0] * x[1] for x in values)/tot_prop
    return mean_stop_inness


if __name__=="__main__":
    gtfs_path = "data/lm_daily.sqlite"
    G = GTFS(gtfs_path)
    I = Inness(G)
    I.get_rings()
    ring = I.rings[5][:2]
    compute_ring_inness(ring, "test", I)

