from gtfspy.routing.inness_journey import JourneyInness
from gtfspy.routing.inness import Inness
from gtfspy.routing.helpers import get_transit_connections, get_walk_network
from gtfspy.routing.multi_objective_pseudo_connection_scan_profiler import MultiObjectivePseudoCSAProfiler
from gtfspy.gtfs import GTFS
from gtfspy.util import wgs84_distance
import pickle
import matplotlib.pyplot as plt
import os
import yaml
from numpy.random import choice
from numpy import mean, std, log, array
import networkx as nx

# READ THIS FROM YAML CONFIG FILE
results_path = 'results_old'
cutoff_time = 2 * 3600

def _compute_stops_inness(stop_I, ring_stops, departure_stops, G, connections, walk_network):

    start_time = G.get_suitable_date_for_daily_extract(ut=True) + 7 * 3600
    end_time = G.get_suitable_date_for_daily_extract(ut=True) + 13 * 3600
    rush_limit = G.get_suitable_date_for_daily_extract(ut=True) + 9 * 3600
    mpCSA = MultiObjectivePseudoCSAProfiler(connections, targets=[stop_I], walk_network=walk_network, end_time_ut=end_time, transfer_margin=120, start_time_ut=start_time, walk_speed=1.5, verbose=True, track_vehicle_legs=True, track_time=True, track_route=True)

    mpCSA.run()
    profiles = mpCSA.stop_profiles
    labels = dict((key, value.get_final_optimal_labels()) for (key, value) in profiles.items())
    walk_times = dict((key, value.get_walk_to_target_duration()) for (key, value) in profiles.items())

    journey_inness_list = []
    inness_per_stop = {}
    fails = []
    inness_path_summary = {}

    for stop in departure_stops:
        try:
            JI = JourneyInness(labels[stop], walk_times[stop], start_time, end_time - cutoff_time, stop, G, get_inness=True, rush_limit=rush_limit)
            if JI.inness_stops is not None and stop in ring_stops:
                inness_per_stop = _add_inness_stops(inness_per_stop, JI.inness_stops)
            if JI.path_inness_summary is not None:
                path, summary = JI.path_inness_summary
                inness_path_summary[path] = summary
                journey_inness_list.append(JI)
            else:
                fails.append((stop_I, stop))
                print ("Failed: from stop {0} to stop {1}, no journey variants".format(stop, stop_I))
        except:
            print("Failed: from stop {0} to stop {1}".format(str(stop), str(stop_I)))
            fails.append((stop_I, stop))

    return inness_per_stop, inness_path_summary, journey_inness_list, fails


def _add_inness_stops(inness_per_stop, new_obs):
    for stop, inness_vals in new_obs.items():
        try:
            inness_per_stop[stop] += inness_vals
        except:
            inness_per_stop[stop] = inness_vals

    return inness_per_stop


def _get_connections_network(connections, walk_network, G):
    """
    Obtain connections network, used to calculate the Inness of the shortest paths
    """
    net = nx.DiGraph()
    for con in connections:
        arrival_stop = con.arrival_stop
        departure_stop = con.departure_stop
        d = wgs84_stop_distance(arrival_stop, departure_stop, G)
        if net.has_edge(departure_stop, arrival_stop):
            d = min(d, net[departure_stop][arrival_stop]['d'])
        net.add_edge(departure_stop, arrival_stop, d=d)
    for d_stop, a_stop, weight in walk_network.edges_iter(data=True):
        if net.has_edge(d_stop, a_stop):
            d = min(d, weight['d'])
        net.add_edge(d_stop, a_stop, d=d)
    return net


def wgs84_stop_distance(stop_1, stop_2, G):
    lat_1, lon_1 = G.get_stop_coordinates(stop_1)
    lat_2, lon_2 = G.get_stop_coordinates(stop_2)
    return wgs84_distance(lat_1, lon_1, lat_2, lon_2)


def compute_ring_inness(ring_Is=None, ring_id=None, inness_obj=None, total_ring=None):
    G = inness_obj.gtfs
    start_time = G.get_suitable_date_for_daily_extract(ut=True) + 8 * 3600
    end_time = G.get_suitable_date_for_daily_extract(ut=True) + 12 * 3600

    connections = get_transit_connections(G, start_time, end_time)
    walk_network = get_walk_network(G)
    inness_per_stop = {}
    inness_paths_summary = {}
    fails = []
    for i, stop_I in enumerate(ring_Is):
        print(stop_I, i + 1, "/", len(ring_Is))
        ring_stops = inness_obj.correct_departures_by_angle(stop_I, ring_Is)
        departure_stops = inness_obj.correct_departures_by_angle(stop_I, list(G.stops()['stop_I']))
        departure_stops = [stop for stop in departure_stops if wgs84_stop_distance(stop, stop_I, G) > 1000]
        try:
            stop_inness, inness_path_summary, journey_inness_list, new_fails  = _compute_stops_inness(stop_I, ring_stops, departure_stops, G, connections, walk_network)
            fails.append(new_fails)
        except KeyError:
            print("Inness computation failed")
            fails.append(stop_I)
            stop_inness = {}
            inness_path_summary = {}
            journey_inness_list = None
        inness_per_stop = _add_inness_stops(inness_per_stop, stop_inness)
        inness_paths_summary.update(inness_path_summary)
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

    inness_paths_name = os.path.join(results_path, "{ring}_paths.p".format(ring=str(ring_id)))
    with open(inness_paths_name, "wb") as f:
        pickle.dump(inness_paths_summary, f)

    return inness_per_stop

def mean_stop_inness(inness_per_stop, min_samples = 5, col=1):
    mean_stop_inness = {}
    for stop, values in inness_per_stop.items():
        tot_prop = sum(x[col] for x in values)
        if len(values) >= min_samples and tot_prop > 0:
            if col < 4:
                mean_stop_inness[stop] = sum(x[0] * x[col] for x in values)/tot_prop
            else:
                mean_stop_inness[stop] = sum(x[0] * x[2]/x[3] for x in values if x[3] != 0)/sum(x[2]/x[3] for x in values if x[3] != 0)
    return mean_stop_inness


def number_of_routes_per_stop(inness_per_stop):
    num_of_stops = {}
    for stop, values in inness_per_stop.items():
        num_of_stops[stop] = log(sum(x[1] for x in values))
    mean_v = mean([x for x in num_of_stops.values()])
    sd_v = std([x for x in num_of_stops.values()])
    return {stop: (value - mean_v)/sd_v for stop, value in num_of_stops.items()}


def plot_inness(mean_inness_per_stop, G, title="Mean inness for rings"):
    fig = plt.figure()
    ax = fig.add_subplot(111, projection="smopy_axes")
    coords = [G.get_stop_coordinates(stop) for stop in mean_inness_per_stop.keys()]
    inness = list(mean_inness_per_stop.values())
    lats = [x[0] for x in coords]
    lons = [x[1] for x in coords]
    im = ax.scatter(lons, lats, c=inness, cmap="bwr", alpha=.55, zorder=2)
    ax.add_scale_bar()
    ax.set_title(title)
    fig.colorbar(im, ax=ax)
    return fig, ax

def plot_origin_inness(paths, G, col=1, title='Mean innes of origin', plot_destinations=False):
    fig = plt.figure()
    ax = fig.add_subplot(111, projection="smopy_axes")
    summary = {}
    for key, val in paths.items():
        try:
            summary[key[0]].append(val[col])
        except KeyError:
            summary[key[0]] = [val[col]]
    inness = [sum(x)/len(x) for x in summary.values()]
    coords_from = [G.get_stop_coordinates(stop) for stop in summary.keys()]
    lats = [x[0] for x in coords_from]
    lons = [x[1] for x in coords_from]
    im = ax.scatter(lons, lats, c=inness, cmap="bwr", alpha=.55)
    if plot_destinations:
        coords_to = [G.get_stop_coordinates(stop) for stop in list(set([k[1] for k in paths]))]
        lats = [x[0] for x in coords_to]
        lons = [x[1] for x in coords_to]
        ax.scatter(lons, lats, c='k')
    ax.add_scale_bar()
    ax.set_title(title)
    fig.colorbar(im, ax=ax)
    return fig, ax

def get_stops_sample(ring, sample_size, I):
    ring = ring.copy()
    sample = [choice(ring)]
    while len(sample) < sample_size and len(ring) > 0:
        test_stop = choice(ring)
        ring.remove(test_stop)
        angs = [I.angle_from_city_center(test_stop, stop) for stop in sample]
        if all(array(angs) > I.min_deg*.5):
            sample.append(test_stop)
    return sample


if __name__=="__main__":
    from gtfspy.gtfs import GTFS
    from gtfspy.routing.inness import Inness
    from numpy.random import choice
    gtfs_path = "data/old_daily.sqlite"
    G = GTFS(gtfs_path)
    I = Inness(G)
    I.get_rings()
    rings = [31, 32, 33, 34, 36, 37, 38, 39, 41, 42, 43, 44, 46, 47, 48, 49, 51, 52, 53, 54]
    #[1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19, 21, 22, 23, 24, 26, 27, 28, 29] #[10, 20, 30]
    sample_size = 5
    for ring_idx in rings:
        ring = I.rings[ring_idx]
        ring_sample = get_stops_sample(ring.copy(), sample_size, I)
        ring_id = "{}_sample_{}".format(str(ring_idx), str(sample_size))
        full_path = os.path.join(results_path, ring_id)
        with  open(full_path + "_sample_stops.p", "wb") as f:
            pickle.dump(ring_sample, f)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        compute_ring_inness(ring_sample, ring_id, I, ring.copy())

