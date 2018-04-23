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
# **********************************
# to plot what we have so far

paths_inness = read_pickle('results_old/all_paths_summary.p') #this is the file that I sent on google drive, just fix the path
plt.ion() #you may need to remove this
fig, ax = ci.plot_origin_inness(paths_inness, G, col=0, title="mean inness")

# **************************************
# to access the network

start_time = G.get_suitable_date_for_daily_extract(ut=True) + 7 * 3600
end_time = G.get_suitable_date_for_daily_extract(ut=True) + 13 * 3600

connections = get_transit_connections(G, start_time, end_time)
walk_network = get_walk_network(G)

# This will return a networkx object with the stops network (where the weight between edges is the distance)
full_network = ci._get_connections_network(connections, walk_network, G)


# ***************************
# Now, for each edge in the network, we need to compute the inness. If path is the path of stops then do:
JI = ij.JourneyInness(None, None, None, None, None, G, get_inness=False)


path = [1929, 1843, 1686, 1563, 1505, 1333, 1179, 1069, 916, 817, 774, 706, 707, 594, 647, 586, 540, 483, 510, 423, 407, 397]
path_inness = JI.inness(path)

