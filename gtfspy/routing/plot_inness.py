from gtfspy.routing.inness_journey import JourneyInness
from gtfspy.routing.inness import Inness
from gtfspy.routing.helpers import get_transit_connections, get_walk_network
from gtfspy.routing.multi_objective_pseudo_connection_scan_profiler import MultiObjectivePseudoCSAProfiler
from gtfspy.gtfs import GTFS
import pickle
import re
import matplotlib.pyplot as plt
import os
from pandas import read_pickle
from gtfspy.routing.compute_inness import _add_inness_stops, mean_stop_inness, plot_inness


results_path = 'results'
cutoff_time = 2 * 3600
gtfs_path = "data/lm_daily.sqlite"
G = GTFS(gtfs_path)
I = Inness(G)
I.get_rings()
ring = "14"

def listfiles(ring): return os.listdir((os.path.join(results_path, str(ring))))
files = listfiles(ring)

def read_JI_list_pickle(path):
    JI_list = read_pickle(path)
    return JI_list

def plot_JI_paths(JI, title="Inness of routes for paths from \n ring 7 km"):
    JI.gtfs = G
    fig = plt.figure()
    ax = fig.add_subplot(111, projection="smopy_axes")
    for path, inness in zip(JI.all_journey_stops, JI.all_journey_inness):
        fig, ax = plot_path(path, fig, ax, inness)
    lat, lon = JI.city_center
    ax.scatter(lon, lat, s=100, c="red")
    ax.set_title(title)
    return fig, ax

def plot_path(path, fig, ax, inness):
    coords = [G.get_stop_coordinates(x) for x in path]
    lats = [x[0] for x in coords]
    lons = [x[1] for x in coords]
    if inness < 0:
        c='b'
    else:
        c='y'
    ax.plot(lons, lats, c=c, zorder=2)
    ax.plot([lons[0], lons[-1]], [lats[0], lats[-1]], c='k')
    return fig, ax

def read_stops_pickles(path, stop_inness={10000: []}):
    i = 0
    for f in os.listdir(path):
        pickle_list = read_pickle(os.path.join(path, f))
        j = 0
        for JI in pickle_list:
            stop_inness = _add_inness_stops(stop_inness, JI.inness_stops)
            i += 1
            j += 1
            print("tot: {0}/{1}, ji: {2}/{3}".format(i, len(os.listdir(path)), j, len(pickle_list)))
    return stop_inness

def read_inness_per_stop_pickles(directory, return_mean = True, num_samples="\d+"):
    re_pattern = "\d+_sample_{}_stops.p$".format(num_samples)
    inness_per_stop = {}
    for f in os.listdir(directory):
        if re.match(re_pattern, f):
            path = os.path.join(directory, f)
            inness_new = pickle.load(open(path, "rb"))
            inness_per_stop = _add_inness_stops(inness_per_stop, inness_new)
    if return_mean:
        return mean_stop_inness(inness_per_stop)
    return inness_per_stop


def plot_inness_difference(mean_inness_new, mean_inness_old):

    mean_inness_diff = {}

    for stop in mean_inness_new:
        try:
            mean_inness_diff[stop] = mean_inness_new[stop] - mean_inness_old[stop]
        except KeyError:
            pass

    coords = [G.get_stop_coordinates(stop) for stop in mean_inness_diff]
    lats = [x[0] for x in coords]
    lons = [x[1] for x in coords]
    diffs = list(mean_inness_diff.values())

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="smopy_axes")
    im = ax.scatter(lons, lats, c=diffs, cmap="seismic", vmin=-2, vmax=2, alpha=.55, zorder=2)
    fig.colorbar(im, ax=ax)

    return fig, ax

