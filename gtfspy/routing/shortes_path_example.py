import gtfspy.routing.inness_journey as ij
from gtfspy.routing.inness import Inness
from gtfspy.routing.helpers import get_transit_connections, get_walk_network
from gtfspy.routing.multi_objective_pseudo_connection_scan_profiler import MultiObjectivePseudoCSAProfiler
from gtfspy.gtfs import GTFS
import pickle
import matplotlib.pyplot as plt
from numpy import mean, std, log
from imp import reload
from pandas import read_pickle
import gtfspy.routing.compute_inness as ci
import networkx as nx

results_path = "results_old"
cutoff_time = 2*3600
gtfs_path = "data/old_daily.sqlite"

G = GTFS(gtfs_path)
I = Inness(G)
# **********************************
# plot the inness of the routes that depart from one point to random points in the city


paths_inness = read_pickle('results_old/all_paths_summary.p') #files on google drive
# format of file: dictionary where keys are (origin_stop, destinaiton_stop), and values are a list with mean inness for [whole_period, rush_hour, nonrush_hour]
plt.ion() #you may need to remove this

# col=0 : mean inness of the whole period
# col=1 : mean inness of rush hour
# col=2 : non-rush hour
fig, ax = ci.plot_origin_inness(paths_inness, G, col=0, title="mean inness")


# ************************************
# plot inness of stops (inness of all the fastest routes that go through that point)
stops_inness = read_pickle('results_old/all_stops_summary.p')

c = ci.mean_stop_inness(stops_inness, col=1)
# col=1: mean inness of whole period
# col=2: iness of rush hour
# col=3: inness of non-rush hour
fig, ax = ci.plot_inness(c, G, "mean inness by stop")


# **************************************
# TODO: obtain inness of all shortest paths of the network
#

start_time = G.get_suitable_date_for_daily_extract(ut=True) + 7 * 3600
end_time = G.get_suitable_date_for_daily_extract(ut=True) + 13 * 3600

connections = get_transit_connections(G, start_time, end_time)
walk_network = get_walk_network(G)

# This will return a networkx object with the stops network (where the weight between edges is the distance)
full_network = ci._get_connections_network(connections, walk_network, G)


# ***************************
# Now, for each edge in the network, we need to compute the inness. If path is the path of stops then do:
JI = ij.JourneyInness(None, None, None, None, None, G, get_inness=False)

# example
path = [1929, 1843, 1686, 1563, 1505, 1333, 1179, 1069, 916, 817, 774, 706, 707, 594, 647, 586, 540, 483, 510, 423, 407, 397]
path_inness = JI.inness(path)

# General stuff that needs to be done:
# TODO: plot distribution of inness (like histogram) both by origin and per stop  before and after the metro
# TODO: correct scales of ci.plot_inness and ci.plot_origin_inness (it must go from -1 to 1)
# TODO: make plot that visualizes differences of inness
# TODO: use that plot to visualize differences in rush hour, and differences before and after metro by origin and by stop
    # NOTE: stops may differ, so you must first find which stops and origins have data for each case to compare
# TODO (possible): create plot from paper that compares inness by degree and radius
    # NOTE: you must select a subsect from path_inness, use an I = Inness(G) object to get the angle, and find out if both stops belong to the same ring
# TODO (possible): if we have the inness of shortest paths, use it as a baseline to compare (a) if the shortest paths changed with the metro and (b), how does it change if instead of using the inness of a path, we "correct" by seeing how it differs from the shortest path
    # Also: get correlation between inness of shortest paths and fastest. if it's not very similar, then it might imply good infraestructure and route diversity
