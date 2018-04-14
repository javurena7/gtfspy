from gtfspy.routing.inness_journey import JourneyInness
from gtfspy.routing.inness import Inness
from gtfspy.routing.helpers import get_transit_connections, get_walk_network
from gtfspy.routing.multi_objective_pseudo_connection_scan_profiler import MultiObjectivePseudoCSAProfiler
from gtfspy.gtfs import GTFS
import pickle
import matplotlib.pyplot as plt
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
    fails = []

    for stop in departure_stops:
        try:
            JI = JourneyInness(labels[stop], walk_times[stop], start_time, end_time - cutoff_time, stop, G)
            inness_per_stop = _add_inness_stops(inness_per_stop, JI.inness_stops)
            journey_inness_list.append(JI)
        except:
            print("Failed: from stop {0} to stop {1}".format(str(stop), str(stop_I)))

            fails.append((stop_I, stop))

    return inness_per_stop, journey_inness_list, fails


def _add_inness_stops(inness_per_stop, new_obs):
    for stop, inness_vals in new_obs.items():
        try:
            inness_per_stop[stop] += inness_vals
        except:
            inness_per_stop[stop] = inness_vals

    return inness_per_stop


def compute_ring_inness(ring_Is=None, ring_id=None, inness_obj=None, total_ring=None):
    G = inness_obj.gtfs
    start_time = G.get_suitable_date_for_daily_extract(ut=True) + 8 * 3600
    end_time = G.get_suitable_date_for_daily_extract(ut=True) + 12 * 3600

    connections = get_transit_connections(G, start_time, end_time)
    walk_network = get_walk_network(G)
    inness_per_stop = {}
    fails = []
    for i, stop_I in enumerate(ring_Is):
        print(stop_I, i + 1, "/", len(ring_Is))
        departure_stops = inness_obj.correct_departures_by_angle(stop_I, total_ring)
        try:
            stop_inness, journey_inness_list, new_fails  = _compute_stops_inness(stop_I, departure_stops, G, connections, walk_network)
            fails.append(new_fails)
        except KeyError:
            print("Inness computation failed")
            fails.append(stop_I)
            stop_inness = {}
            journey_inness_list = None
        inness_per_stop = _add_inness_stops(inness_per_stop, stop_inness)

        file_name = os.path.join(results_path, "{ring}/stop_{stop}.p".format(ring=str(ring_id), stop=str(stop_I)))

        if journey_inness_list is not None:
            print("Writing file: {filen}".format(filen=file_name))
            with open(file_name, "wb") as f:
                pickle.dump(journey_inness_list, f)

    inness_per_stop_file_name = os.path.join(results_path, "{ring}_stops.p".format(ring=str(ring_id)))
    with open(inness_per_stop_file_name, "wb") as f:
        pickle.dump(inness_per_stop, f)

    fails_name = os.path.join(results_path, "{ring}_fails.p".format(ring=str(ring_id)))
    with open(fails_name, "wb") as f:
        pickle.dump(fails, f)

    return inness_per_stop

def mean_stop_inness(inness_per_stop):
    mean_stop_inness = {}
    for stop, values in inness_per_stop.items():
        if len(values) > 4:
            tot_prop = sum(x[1] for x in values)
            mean_stop_inness[stop] = sum(x[0] * x[1] for x in values)/tot_prop
    return mean_stop_inness

def plot_inness(mean_inness_per_stop, G):
    fig = plt.figure()
    ax = fig.add_subplot(111, projection="smopy_axes")
    coords = [G.get_stop_coordinates(stop) for stop in mean_inness_per_stop.keys()]
    inness = list(mean_inness_per_stop.values())
    lats = [x[0] for x in coords]
    lons = [x[1] for x in coords]
    im = ax.scatter(lons, lats, c=inness, alpha=.55, zorder=2)
    ax.add_scale_bar()
    ax.set_title("Mean inness for rings 3.5 and  7 km from \n Rautatientori")
    fig.colorbar(im, ax=ax)
    return fig, ax


if __name__=="__main__":
    from gtfspy.gtfs import GTFS
    from gtfspy.routing.inness import Inness
    from numpy.random import choice
    gtfs_path = "data/lm_daily.sqlite"
    G = GTFS(gtfs_path)
    I = Inness(G)
    I.get_rings()
    #rings = [36, 15, 3]#[3, 6, 10, 15, 25, 30, 36, 43, 59] [10, 30, 59][6, 25, 43][36, 15, 3]
    rings = [8, 27, 48, 55]#[2, 5, 8, 17, 22, 27, 33, 40, 48, 55][2, 17, 33][5, 22, 40][8, 27, 48, 55]
    for ring_idx in rings:
        ring = I.rings[ring_idx]
        ring_sample = list(choice(ring, 25))
        ring_id = "{}_sample_25".format(str(ring_idx))
        full_path = os.path.join(results_path, ring_id)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        compute_ring_inness(ring_sample, ring_id, I, ring)

