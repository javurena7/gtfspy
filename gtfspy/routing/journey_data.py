import os
import sqlite3
import pandas as pd
import numpy as np

from gtfspy.routing.connection import Connection
from gtfspy.gtfs import GTFS
from gtfspy.routing.label import LabelTimeAndRoute, LabelTimeWithBoardingsCount, LabelTimeBoardingsAndRoute, \
    compute_pareto_front, LabelGeneric
from gtfspy.routing.fastest_path_analyzer import FastestPathAnalyzer
from gtfspy.routing.node_profile_multiobjective import NodeProfileMultiObjective
from gtfspy.util import timeit


class JourneyDataManager:
    def __init__(self, gtfs_dir, routing_params, journey_db_dir=None, multitarget_routing=False, close_connection=True,
                 track_route=False, track_vehicle_legs=True):
        """

        :param gtfs: GTFS object
        :param list_of_stop_profiles: dict of NodeProfileMultiObjective
        :param multitarget_routing: bool
        """
        self.close_connection = close_connection
        self.routing_params = routing_params
        self.multitarget_routing = multitarget_routing
        self.track_route = track_route
        self.track_vehicle_legs = track_vehicle_legs
        self.gtfs_dir = gtfs_dir
        self.gtfs = GTFS(self.gtfs_dir)
        self.gtfs_meta = self.gtfs.meta
        self.gtfs._dont_close = True
        print('location_name: ', self.gtfs_meta["location_name"])
        self.conn = None
        self.od_pairs = None
        self.targets = None
        self.origins = None
        self.diff_conn = None
        self.journey_parameters = {
            "n_boardings": (float("inf"), 0),
            "journey_duration": ("t_walk", "t_walk"),
            "in_vehicle_duration": (float('inf'), 0),
            "transfer_wait_duration": (float('inf'), 0),
            "walking_duration": ("t_walk", "t_walk"),
            "pre_journey_wait_fp": (float('inf'), 0)}
        self.tables = list(self.journey_parameters.keys())
        self.tables += ["temporal_distance"]

        if journey_db_dir:
            if os.path.isfile(journey_db_dir):
                self.conn = sqlite3.connect(journey_db_dir)
                self.measure_parameters = Parameters(self.conn)
                self._check_that_dbs_match()

            else:
                raise Exception("Database specified does not exist, use run_preparations() method first")

    def __del__(self):
        self.gtfs._dont_close = False
        if self.conn:
            self.conn.close()

    @timeit
    def import_journey_data_single_stop(self, stop_profiles, target_stop):
        cur = self.conn.cursor()
        self.conn.isolation_level = 'EXCLUSIVE'
        cur.execute('PRAGMA synchronous = OFF;')
        if not self.target_in_db(target_stop):
            if self.track_route:
                self._insert_journeys_with_route_into_db(stop_profiles, target_stop=target_stop)
            else:
                self._insert_journeys_into_db_no_route(stop_profiles, target_stop=target_stop)

            if self.close_connection:
                self.conn.close()

        print("Finished import process")

    def target_in_db(self, target_stop):
        return "," + str(target_stop) + "," in self.measure_parameters["target_list"]

    def _check_that_dbs_match(self):
        for key, value in self.measure_parameters.items():
            if key in self.gtfs_meta.keys():
                assert self.gtfs_meta[key] == value

    def _check_last_journey_id(self):
        cur = self.conn.cursor()
        val = cur.execute("select max(journey_id) FROM journeys").fetchone()
        return val[0] if val[0] else 0

    def _insert_journeys_into_db_no_route(self, stop_profiles, target_stop=None):
        # TODO: Change the insertion so that the check last journey id and insertions are in the same transaction block
        """
        con.isolation_level = 'EXCLUSIVE'
        con.execute('BEGIN EXCLUSIVE')
        #exclusive access starts here. Nothing else can r/w the db, do your magic here.
        con.commit()
        """
        print("Collecting journey data")
        journey_id = 1
        journey_list = []
        tot = len(stop_profiles)
        for i, (origin_stop, labels) in enumerate(stop_profiles.items(), start=1):
            #print("\r Stop " + str(i) + " of " + str(tot), end='', flush=True)

            for label in labels:
                assert (isinstance(label, LabelTimeWithBoardingsCount))
                if self.multitarget_routing:
                    target_stop = None

                values = [journey_id,
                          origin_stop,
                          target_stop,
                          int(label.departure_time),
                          int(label.arrival_time_target),
                          label.n_boardings]

                journey_list.append(values)
                journey_id += 1
        print("Inserting journeys into database")
        insert_journeys_stmt = '''INSERT INTO journeys(
              journey_id,
              from_stop_I,
              to_stop_I,
              departure_time,
              arrival_time_target,
              n_boardings) VALUES (%s) ''' % (", ".join(["?" for x in range(6)]))
        #self.conn.executemany(insert_journeys_stmt, journey_list)

        self._execute_function(insert_journeys_stmt, journey_list)
        self.conn.commit()

    @timeit
    def _execute_function(self, statement, rows):
        self.conn.execute('BEGIN EXCLUSIVE')
        last_id = self._check_last_journey_id()
        rows = [[x[0]+last_id] + x[1:] for x in rows]
        self.conn.executemany(statement, rows)

    def _insert_journeys_with_route_into_db(self, stop_profiles, target_stop):
        print("Collecting journey and connection data")
        journey_id = (self._check_last_journey_id() if self._check_last_journey_id() else 0) + 1
        journey_list = []
        connection_list = []
        label = None
        tot = len(stop_profiles)
        for i, (origin_stop, labels) in enumerate(stop_profiles.items(), start=1):
            #print("\r Stop " + str(i) + " of " + str(tot), end='', flush=True)

            assert (isinstance(stop_profiles[origin_stop], list))

            for label in labels:
                assert (isinstance(label, LabelTimeAndRoute) or isinstance(label, LabelTimeBoardingsAndRoute))
                # We need to "unpack" the journey to actually figure out where the trip went
                # (there can be several targets).
                if label.departure_time == label.arrival_time_target:
                    print("Weird label:", label)
                    continue

                target_stop, new_connection_values, route_stops = self._collect_connection_data(journey_id, label)
                if origin_stop == target_stop:
                    continue

                if isinstance(label, LabelTimeBoardingsAndRoute):
                    values = [int(journey_id),
                              int(origin_stop),
                              int(target_stop),
                              int(label.departure_time),
                              int(label.arrival_time_target),
                              label.n_boardings,
                              label.movement_duration,
                              route_stops]
                else:
                    values = [int(journey_id),
                              int(origin_stop),
                              int(target_stop),
                              int(label.departure_time),
                              int(label.arrival_time_target),
                              label.movement_duration,
                              route_stops]

                journey_list.append(values)
                connection_list += new_connection_values
                journey_id += 1

        print()
        print("Inserting journeys into database")
        if label:
            if isinstance(label, LabelTimeBoardingsAndRoute):
                insert_journeys_stmt = '''INSERT INTO journeys(
                      journey_id,
                      from_stop_I,
                      to_stop_I,
                      departure_time,
                      arrival_time_target,
                      n_boardings,
                      movement_duration,
                      route) VALUES (%s) ''' % (", ".join(["?" for x in range(8)]))
            else:
                insert_journeys_stmt = '''INSERT INTO journeys(
                      journey_id,
                      from_stop_I,
                      to_stop_I,
                      departure_time,
                      arrival_time_target,
                      movement_duration,
                      route) VALUES (%s) ''' % (", ".join(["?" for x in range(7)]))
            self.conn.executemany(insert_journeys_stmt, journey_list)

            print("Inserting legs into database")
            insert_legs_stmt = '''INSERT INTO legs(
                                  journey_id,
                                  from_stop_I,
                                  to_stop_I,
                                  departure_time,
                                  arrival_time_target,
                                  trip_I,
                                  seq,
                                  leg_stops) VALUES (%s) ''' % (", ".join(["?" for x in range(8)]))
            self.conn.executemany(insert_legs_stmt, connection_list)
            self.measure_parameters["target_list"] += (str(target_stop) + ",")
            self.conn.commit()

    def _collect_connection_data(self, journey_id, label):
        target_stop = None
        cur_label = label
        seq = 1
        value_list = []
        route_stops = []
        leg_stops = []
        prev_trip_id = None
        connection = None
        leg_departure_time = None
        leg_departure_stop = None
        leg_arrival_time = None
        leg_arrival_stop = None
        while True:
            if isinstance(cur_label.connection, Connection):
                connection = cur_label.connection
                if connection.trip_id:
                    trip_id = connection.trip_id
                else:
                    trip_id = -1

                # In case of new leg
                if prev_trip_id != trip_id:
                    route_stops.append(connection.departure_stop)
                    if prev_trip_id:
                        leg_stops.append(connection.departure_stop)

                        values = (
                            int(journey_id),
                            int(leg_departure_stop),
                            int(leg_arrival_stop),
                            int(leg_departure_time),
                            int(leg_arrival_time),
                            int(prev_trip_id),
                            int(seq),
                            ','.join([str(x) for x in leg_stops])
                                )
                        value_list.append(values)
                        seq += 1
                        leg_stops = []

                    leg_departure_stop = connection.departure_stop
                    leg_departure_time = connection.departure_time
                leg_arrival_time = connection.arrival_time
                leg_arrival_stop = connection.arrival_stop
                leg_stops.append(connection.departure_stop)
                target_stop = connection.arrival_stop
                prev_trip_id = trip_id

            if not cur_label.previous_label:
                leg_stops.append(connection.arrival_stop)
                values = (
                    int(journey_id),
                    int(leg_departure_stop),
                    int(leg_arrival_stop),
                    int(leg_departure_time),
                    int(leg_arrival_time),
                    int(prev_trip_id),
                    int(seq),
                    ','.join([str(x) for x in leg_stops])
                )
                value_list.append(values)
                break

            cur_label = cur_label.previous_label
        route_stops.append(target_stop)
        route_stops = ','.join([str(x) for x in route_stops])
        return target_stop, value_list, route_stops

    def populate_additional_journey_columns(self):
        # self.add_fastest_path_column()
        # self.add_time_to_prev_journey_fp_column()
        self.add_time_measures_to_journey()
        self.calculate_pre_journey_waiting_time()

    def get_od_pairs(self):
        cur = self.conn.cursor()
        if not self.od_pairs:
            cur.execute('SELECT from_stop_I, to_stop_I FROM journeys GROUP BY from_stop_I, to_stop_I')
            self.od_pairs = cur.fetchall()
        return self.od_pairs

    def get_targets(self):
        cur = self.conn.cursor()
        if not self.targets:
            cur.execute('SELECT to_stop_I FROM journeys GROUP BY to_stop_I')
            self.targets = cur.fetchall()
        return self.targets

    def get_origins(self):
        cur = self.conn.cursor()
        if not self.origins:
            cur.execute('SELECT from_stop_I FROM journeys GROUP BY from_stop_I')
            self.origins = cur.fetchall()
        return self.origins

    def get_table_with_coordinates(self, table_name, target=None):
        df = self.get_table_as_dataframe(table_name, target)
        return self.gtfs.add_coordinates_to_df(df, join_column='from_stop_I')

    def get_table_as_dataframe(self, table_name, target=None):
        query = "SELECT * FROM " + table_name
        if target:
            query += " WHERE to_stop_I = %s" % target
        return pd.read_sql_query(query, self.conn)

    @timeit
    def add_fastest_path_column(self):
        print("adding fastest path column")
        cur = self.conn.cursor()
        for target in self.get_targets():
            fastest_path_journey_ids = []
            for origin in self.get_origins():
                cur.execute('SELECT departure_time, arrival_time_target, journey_id FROM journeys '
                            'WHERE from_stop_I = ? AND to_stop_I = ? '
                            'ORDER BY departure_time ASC', (origin[0], target[0]))
                all_trips = cur.fetchall()
                all_labels = [LabelTimeAndRoute(x[0], x[1], x[2], False) for x in all_trips] #putting journey_id as movement_duration
                all_fp_labels = compute_pareto_front(all_labels, finalization=False, ignore_n_boardings=True)
                fastest_path_journey_ids.append(all_fp_labels)

            fastest_path_journey_ids = [(1, x.movement_duration) for sublist in fastest_path_journey_ids for x in sublist]
            cur.executemany("UPDATE journeys SET fastest_path = ? WHERE journey_id = ?", fastest_path_journey_ids)
        self.conn.commit()

    @timeit
    def add_time_to_prev_journey_fp_column(self):
        print("adding pre journey waiting time")
        cur = self.conn.cursor()
        for target in self.get_targets():

            cur.execute('SELECT journey_id, from_stop_I, to_stop_I, departure_time FROM journeys '
                        'WHERE fastest_path = 1 AND to_stop_I = ? '
                        'ORDER BY from_stop_I, to_stop_I, departure_time ', (target[0],))

            all_trips = cur.fetchall()
            time_to_prev_journey = []
            prev_departure_time = None
            prev_origin = None
            prev_destination = None
            for trip in all_trips:
                journey_id = trip[0]
                from_stop_I = trip[1]
                to_stop_I = trip[2]
                departure_time = trip[3]
                if prev_origin != from_stop_I or prev_destination != to_stop_I:
                    prev_departure_time = None
                if prev_departure_time:
                    time_to_prev_journey.append((departure_time - prev_departure_time, journey_id))
                prev_origin = from_stop_I
                prev_destination = to_stop_I
                prev_departure_time = departure_time
            cur.executemany("UPDATE journeys SET pre_journey_wait_fp = ? WHERE journey_id = ?", time_to_prev_journey)
        self.conn.commit()

    @timeit
    def add_time_measures_to_journey(self):
        print("adding journey components")
        cur = self.conn.cursor()
        cur.execute("UPDATE journeys SET journey_duration = arrival_time_target - departure_time")
        cur.execute("UPDATE journeys "
                    "SET "
                    "in_vehicle_duration = "
                    "(SELECT sum(arrival_time_target - departure_time) AS in_vehicle_duration FROM legs "
                    "WHERE journeys.journey_id = legs.journey_id AND trip_I != -1 GROUP BY journey_id)")
        cur.execute("UPDATE journeys "
                    "SET "
                    "walking_duration = "
                    "(SELECT sum(arrival_time_target - departure_time) AS walking_duration FROM legs "
                    "WHERE journeys.journey_id = legs.journey_id AND trip_I < 0 GROUP BY journey_id)")
        cur.execute("UPDATE journeys "
                    "SET transfer_wait_duration = journey_duration - in_vehicle_duration - walking_duration")
        self.conn.commit()

    def journey_label_generator(self):
        conn = self.conn
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        for target in self.get_targets():
            sql = """SELECT journey_id, from_stop_I, to_stop_I, n_boardings, movement_duration, journey_duration,
                      in_vehicle_duration, transfer_wait_duration, walking_duration, departure_time, arrival_time_target
                      FROM journeys WHERE to_stop_I = %s""" % target[0]

            df = pd.read_sql_query(sql, self.conn)
            for origin in self.get_origins():
                selection = df.loc[df['from_stop_I'] == origin[0]]
                journey_labels = []
                for journey in selection.to_dict(orient='records'):
                    journey["pre_journey_wait_fp"] = -1
                    journey_labels.append(LabelGeneric(journey))
                yield journey_labels, (origin[0], target[0])

    def get_node_profile_analyzer(self, target, origin, start_time_dep, end_time_dep):
        sql = """SELECT journey_id, from_stop_I, to_stop_I, n_boardings, movement_duration, journey_duration,
        in_vehicle_duration, transfer_wait_duration, walking_duration, departure_time, arrival_time_target
        FROM journeys WHERE to_stop_I = %s AND from_stop_I = %s""" % (target, origin)
        df = pd.read_sql_query(sql, self.conn)
        journey_labels = []
        for journey in df.to_dict(orient='records'):
            journey_labels.append(LabelGeneric(journey))

        fpa = FastestPathAnalyzer(journey_labels,
                                  start_time_dep,
                                  end_time_dep,
                                  walk_duration=float('inf'),  # walking time
                                  label_props_to_consider=list(self.journey_parameters.keys()))
        return fpa.get_time_analyzer()

    @timeit
    def od_pair_data(self, analysis_start_time, analysis_end_time):
        data_dict = {}

        for prop in self.tables:
            data_dict[prop] = []

        for journey_labels, pairs in self.journey_label_generator():
            kwargs = {"from_stop_I": pairs[0], "to_stop_I": pairs[1]}
            walking_distance = self.gtfs.get_stop_distance(pairs[0], pairs[1])
            if walking_distance:
                walking_duration = walking_distance / self.routing_params["walking_speed"]
            else:
                walking_duration = float("inf")
            fpa = FastestPathAnalyzer(journey_labels,
                                      analysis_start_time,
                                      analysis_end_time,
                                      walk_duration=float('inf'),  # walking time
                                      label_props_to_consider=list(self.journey_parameters.keys()),
                                      **kwargs)
            profile_block = fpa.get_temporal_distance_analyzer()
            data_dict["temporal_distance"].append(profile_block.measures_as_dict())
            fpa.calculate_pre_journey_waiting_times()
            for key, value in self.journey_parameters.items():
                value = [walking_duration if x == "t_walk" else x for x in value]
                profile_block = fpa.get_prop_analyzer_flat(key, value[0], value[1])
                data_dict[key].append(profile_block.measures_as_dict())

        for key, value in data_dict.items():
            self.profile_block_to_database(key, value)

    def calculate_pre_journey_waiting_time(self):
        all_fp_labels = []
        for journey_labels, pairs in self.journey_label_generator():
            if not journey_labels:
                continue
            fpa = FastestPathAnalyzer(journey_labels,
                                      self.measure_parameters["routing_start_time_dep"],
                                      self.measure_parameters["routing_end_time_dep"],
                                      walk_duration=float('inf'))
            fpa.calculate_pre_journey_waiting_times()
            all_fp_labels += fpa.get_fastest_path_labels()
        self.update_journey_from_labels(all_fp_labels, "pre_journey_wait_fp")

    def update_journey_from_labels(self, labels, attribute):
        cur = self.conn.cursor()
        insert_tuples = []
        for label in labels:
            insert_tuples.append((getattr(label, attribute), getattr(label, "journey_id")))

        sql = "UPDATE journeys SET %s = ? WHERE journey_id = ?" % (attribute,)
        cur.executemany(sql, insert_tuples)
        self.conn.commit()

    def profile_block_to_database(self, table, data):
        print("creating table: ", table)
        self.conn.execute("CREATE TABLE IF NOT EXISTS " + table + " (from_stop_I INT, "
                                                                  "to_stop_I INT, "
                                                                  "min INT, "
                                                                  "max INT, "
                                                                  "median INT, "
                                                                  "mean REAL, "
                                                                  "UNIQUE (from_stop_I, to_stop_I))")
        data_tuple = [(x["from_stop_I"], x["to_stop_I"], x["min"], x["max"], x["median"], x["mean"]) for x in data]
        insert_stmt = '''INSERT OR REPLACE INTO ''' + table + ''' (
                              from_stop_I,
                              to_stop_I,
                              min,
                              max,
                              median,
                              mean) VALUES (?, ?, ?, ?, ?, ?) '''
        self.conn.executemany(insert_stmt, data_tuple)
        self.conn.commit()

    @timeit
    def initialize_comparison_tables(self, diff_db_path, before_db_tuple, after_db_tuple):
        self.diff_conn = sqlite3.connect(diff_db_path)

        self.diff_conn = self.attach_database(before_db_tuple[0], name=before_db_tuple[1], conn=self.diff_conn)
        self.diff_conn = self.attach_database(after_db_tuple[0], name=after_db_tuple[1], conn=self.diff_conn)

        for table in self.tables:
            self.diff_conn.execute("CREATE TABLE IF NOT EXISTS diff_" + table +
                                   " (from_stop_I, to_stop_I, diff_min, diff_max, diff_median, diff_mean)")
            insert_stmt = "INSERT OR REPLACE INTO diff_" + table + \
                          "(from_stop_I, to_stop_I, diff_min, diff_max, diff_median, diff_mean) " \
                          "SELECT t1.from_stop_I, t1.to_stop_I, " \
                          "t1.min - t2.min AS diff_min, " \
                          "t1.max - t2.max AS diff_max, " \
                          "t1.median - t2.median AS diff_median, " \
                          "t1.mean - t2.mean AS diff_mean " \
                          "FROM " + before_db_tuple[1] + "." + table + " AS t1, " \
                          + before_db_tuple[1] + "." + table + " AS t2 " \
                                                               "WHERE t1.from_stop_I = t2.from_stop_I " \
                                                               "AND t1.to_stop_I = t2.to_stop_I "
            self.diff_conn.execute(insert_stmt)
            self.diff_conn.commit()

    def attach_database(self, other_db_path, name="other", conn=None):
        if conn:
            cur = conn.cursor()
        else:
            cur = self.conn.cursor()
        cur.execute("ATTACH '%s' AS '%s'" % (str(other_db_path), name))
        cur.execute("PRAGMA database_list")
        print("other database attached:", cur.fetchall())
        return conn

    def initialize_database(self, journey_db_dir):
        assert not os.path.isfile(journey_db_dir)

        self.conn = sqlite3.connect(journey_db_dir)
        self._set_up_database()
        self._initialize_parameter_table()
        print("Database initialized!")
        if self.close_connection:
            self.conn.close()

    def _set_up_database(self):

        self.conn.execute('''CREATE TABLE IF NOT EXISTS parameters(
                     key TEXT UNIQUE,
                     value BLOB)''')
        if self.track_route:

            self.conn.execute('''CREATE TABLE IF NOT EXISTS journeys(
                         journey_id INTEGER PRIMARY KEY,
                         from_stop_I INT,
                         to_stop_I INT,
                         departure_time INT,
                         arrival_time_target INT,
                         n_boardings INT,
                         movement_duration INT,
                         route TEXT,
                         journey_duration INT,
                         pre_journey_wait_fp INT,
                         in_vehicle_duration INT,
                         transfer_wait_duration INT,
                         walking_duration INT,
                         fastest_path INT)''')

            self.conn.execute('''CREATE TABLE IF NOT EXISTS legs(
                         journey_id INT,
                         from_stop_I INT,
                         to_stop_I INT,
                         departure_time INT,
                         arrival_time_target INT,
                         trip_I INT,
                         seq INT,
                         leg_stops TEXT)''')
            """
            self.conn.execute('''CREATE TABLE IF NOT EXISTS nodes(
                         stop_I INT,
                         agg_temp_distances REAL,
                         agg_journey_duration REAL,
                         agg_boardings REAL,
                         agg_transfer_wait REAL,
                         agg_pre_journey_wait REAL,
                         agg_walking_duration REAL)''')

            self.conn.execute('''CREATE TABLE IF NOT EXISTS od_pairs(
                         from_stop_I INT,
                         to_stop_I INT,
                         avg_temp_distance REAL,
                         agg_journey_duration REAL,
                         agg_boardings REAL,
                         agg_transfer_wait REAL,
                         agg_pre_journey_wait REAL,
                         agg_walking_duration REAL)''')


            self.conn.execute('''CREATE TABLE IF NOT EXISTS sections(
                         from_stop_I INT,
                         to_stop_I INT,
                         from_stop_pair_I INT,
                         to_stop_pair_I INT,
                         avg_temp_distance INT,
                         avg_journey_duration INT,
                         n_trips INT)''')

            self.conn.execute('''CREATE TABLE IF NOT EXISTS transfer_nodes(
                         from_stop_I INT,
                         to_stop_I INT,
                         from_stop_pair_I INT,
                         to_stop_pair_I INT,
                         avg_waiting_time INT,
                         n_trips INT)''')
            """
        else:
            self.conn.execute('''CREATE TABLE IF NOT EXISTS journeys(
                         journey_id INTEGER PRIMARY KEY,
                         from_stop_I INT,
                         to_stop_I INT,
                         departure_time INT,
                         arrival_time_target INT,
                         n_boardings INT,
                         time_to_prev_journey_fp INT,
                         fastest_path INT)''')

        self.conn.commit()

    def _initialize_parameter_table(self):

        parameters = Parameters(self.conn)

        parameters["multiple_targets"] = self.multitarget_routing
        parameters["gtfs_dir"] = self.gtfs_dir
        for param in ["location_name",
                      "lat_median",
                      "lon_median",
                      "start_time_ut",
                      "end_time_ut",
                      "start_date",
                      "end_date"]:
            parameters[param] = self.gtfs_meta[param]
        parameters["target_list"] = ","
        for key, value in self.routing_params.items():
            parameters[key] = value
        self.conn.commit()

    def create_indicies(self):
        # Next 3 lines are python 3.6 work-arounds again.
        self.conn.isolation_level = None  # former default of autocommit mode
        cur = self.conn.cursor()
        cur.execute('VACUUM;')
        self.conn.isolation_level = ''  # back to python default
        # end python3.6 workaround
        print("Analyzing...")
        cur.execute('ANALYZE')
        print("Indexing")
        cur = self.conn.cursor()
        cur.execute('CREATE INDEX IF NOT EXISTS idx_journeys_jid ON journeys (journey_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_journeys_fid ON journeys (from_stop_I)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_journeys_tid ON journeys (to_stop_I)')

        if self.track_route:
            cur.execute('CREATE INDEX IF NOT EXISTS idx_legs_jid ON legs (journey_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_legs_trid ON legs (trip_I)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_legs_fid ON legs (from_stop_I)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_legs_tid ON legs (to_stop_I)')
        self.conn.commit()

    def get_journey_legs_to_target(self, target, fastest_path=True, min_boardings=False, all_leg_sections=True,
                                   ignore_walk=False):
        assert not (fastest_path and min_boardings)
        if min_boardings:
            raise NotImplementedError
        self.attach_database(self.gtfs_dir)
        added_constraints = ""
        if fastest_path:
            added_constraints += " AND journeys.pre_journey_wait_fp>=0"
        if ignore_walk:
            added_constraints += " AND legs.trip_I >= 0"
        if all_leg_sections:
            df = self._get_journey_legs_to_target_with_all_sections(target, added_constraints)
        else:

            query = """SELECT from_stop_I, to_stop_I, coalesce(type, -1) AS type,
                        count(*) AS n_trips
                        FROM
                        (SELECT legs.* FROM legs, journeys
                        WHERE journeys.journey_id = legs.journey_id AND journeys.to_stop_I = %s %s) q1
                        LEFT JOIN (SELECT * FROM other.trips, other.routes WHERE trips.route_I = routes.route_I) q2
                        ON q1.trip_I = q2.trip_I
                        GROUP BY from_stop_I, to_stop_I, type""" % (str(target), added_constraints)
            df = pd.read_sql_query(query, self.conn)

        return df

    def _get_journey_legs_to_target_with_all_sections(self, target, added_constraint):
        def gen_pairs(stop_lists):
            for stop_list in stop_lists:
                prev_stop = None
                stop_pair_list = []
                for stop in stop_list:
                    if prev_stop:
                        stop_pair_list.append((int(prev_stop), int(stop)))
                    prev_stop = stop
                yield stop_pair_list

        query = """SELECT leg_stops, coalesce(type, -1) AS type, count(*) AS n_trips FROM
                  (SELECT legs.* FROM legs, journeys
                  WHERE journeys.journey_id = legs.journey_id AND journeys.to_stop_I = %s %s) q1
                    LEFT JOIN (SELECT * FROM other.trips, other.routes WHERE trips.route_I = routes.route_I) q2
                    ON q1.trip_I = q2.trip_I
                    GROUP BY leg_stops, type""" % (str(target), added_constraint)
        orig_df = pd.read_sql_query(query, self.conn)

        df = pd.DataFrame([x for x in gen_pairs(orig_df.leg_stops.str.split(',').tolist())],
                          index=[orig_df.type, orig_df.n_trips]).stack()

        df = df.reset_index()
        df = df.rename(columns={0: "stop_tuple"})
        df[['from_stop_I', 'to_stop_I']] = df['stop_tuple'].apply(pd.Series)

        df = df.groupby(['from_stop_I', 'to_stop_I', 'type']).agg({'n_trips': [np.sum]})
        df = df.reset_index()
        df.columns = df.columns.droplevel(1)
        df_to_return = df[['from_stop_I', 'to_stop_I', 'type', 'n_trips']]

        return df_to_return


class DiffDataManager:
    def __init__(self, diff_db_path):
        self.conn = sqlite3.connect(diff_db_path)

    def initialize_comparison_tables(self, tables, before_db_tuple, after_db_tuple):
        before_db_path = before_db_tuple[0]
        before_db_name = before_db_tuple[1]
        after_db_path = after_db_tuple[0]
        after_db_name = after_db_tuple[1]

        self.conn = self.attach_database(before_db_path, name=before_db_name)
        self.conn = self.attach_database(after_db_path, name=after_db_name)

        for table in tables:
            self.conn.execute("CREATE TABLE IF NOT EXISTS diff_" + table +
                              "(from_stop_I INT, to_stop_I INT, "
                              "diff_min INT, diff_max INT, diff_median INT, diff_mean INT, "
                              "rel_diff_min REAL, rel_diff_max REAL, rel_diff_median REAL, rel_diff_mean REAL)")
            insert_stmt = "INSERT OR REPLACE INTO diff_" + table + \
                          " (from_stop_I, to_stop_I, diff_min, diff_max, diff_median, diff_mean, " \
                          "rel_diff_min, rel_diff_max, rel_diff_median, rel_diff_mean) " \
                          "SELECT " \
                          "t1.from_stop_I, " \
                          "t1.to_stop_I, " \
                          "t1.min - t2.min AS diff_min, " \
                          "t1.max - t2.max AS diff_max, " \
                          "t1.median - t2.median AS diff_median, " \
                          "t1.mean - t2.mean AS diff_mean, " \
                          "(t1.min - t2.min)*1.0/t2.min AS rel_diff_min, " \
                          "(t1.max - t2.max)*1.0/t2.max AS rel_diff_max, " \
                          "(t1.median - t2.median)*1.0/t2.median AS rel_diff_median, " \
                          "(t1.mean - t2.mean)*1.0/t2.mean AS rel_diff_mean " \
                          "FROM " + after_db_name + "." + table + " AS t1, "\
                          + before_db_name + "." + table + \
                          " AS t2 WHERE t1.from_stop_I = t2.from_stop_I AND t1.to_stop_I = t2.to_stop_I "
            self.conn.execute(insert_stmt)
            self.conn.commit()

    def attach_database(self, other_db_path, name="other"):
        cur = self.conn.cursor()
        cur.execute("ATTACH '%s' AS '%s'" % (str(other_db_path), name))
        cur.execute("PRAGMA database_list")
        print("other database attached:", cur.fetchall())
        return self.conn

    def get_table_with_coordinates(self, gtfs, table_name, target=None, use_relative=False):
        df = self.get_table_as_dataframe(table_name, use_relative, target)
        return gtfs.add_coordinates_to_df(df, join_column='from_stop_I')

    def get_table_as_dataframe(self, table_name, use_relative, target=None):
        if use_relative:
            query = "SELECT from_stop_I, to_stop_I, rel_diff_min, rel_diff_max, rel_diff_median, rel_diff_mean FROM "\
                    + table_name
        else:
            query = "SELECT from_stop_I, to_stop_I, diff_min, diff_max, diff_median, diff_mean FROM " + table_name
        if target:
            query += " WHERE to_stop_I = %s" % target
        return pd.read_sql_query(query, self.conn)

    def get_largest_component(self):
        query = """select
                    diff_pre_journey_wait_fp.from_stop_I, diff_pre_journey_wait_fp.to_stop_I,
                    CASE
                    WHEN abs(diff_pre_journey_wait_fp.diff_mean)<180 AND abs(diff_in_vehicle_duration.diff_mean)<180
                    AND   abs(diff_transfer_wait_duration.diff_mean)<180 AND   abs(diff_walking_duration.diff_mean)<180
                    THEN "equal"
                    WHEN abs(diff_pre_journey_wait_fp.diff_mean) > abs(diff_in_vehicle_duration.diff_mean)
                    AND  abs(diff_pre_journey_wait_fp.diff_mean) > abs(diff_transfer_wait_duration.diff_mean)
                    AND  abs(diff_pre_journey_wait_fp.diff_mean) > abs(diff_walking_duration.diff_mean)
                    THEN "journey_wait_fp"
                    WHEN abs(diff_in_vehicle_duration.diff_mean) > abs(diff_pre_journey_wait_fp.diff_mean)
                    AND  abs(diff_in_vehicle_duration.diff_mean) > abs(diff_transfer_wait_duration.diff_mean)
                    AND  abs(diff_in_vehicle_duration.diff_mean) > abs(diff_walking_duration.diff_mean)
                    THEN "in_vehicle_duration"
                    WHEN abs(diff_transfer_wait_duration.diff_mean) > abs(diff_in_vehicle_duration.diff_mean)
                    AND  abs(diff_transfer_wait_duration.diff_mean) > abs(diff_pre_journey_wait_fp.diff_mean)
                     AND  abs(diff_transfer_wait_duration.diff_mean) > abs(diff_walking_duration.diff_mean)
                     THEN "transfer_wait_duration"
                    WHEN abs(diff_walking_duration.diff_mean) > abs(diff_in_vehicle_duration.diff_mean)
                    AND  abs(diff_walking_duration.diff_mean) > abs(diff_transfer_wait_duration.diff_mean)
                    AND  abs(diff_walking_duration.diff_mean) > abs(diff_pre_journey_wait_fp.diff_mean)
                    THEN "walking_duration"
                    ELSE "equal"
                    END as largest_change
                    from diff_pre_journey_wait_fp, diff_in_vehicle_duration, diff_transfer_wait_duration, diff_walking_duration
                    where diff_pre_journey_wait_fp.rowid =diff_in_vehicle_duration.rowid
                    AND diff_pre_journey_wait_fp.rowid = diff_transfer_wait_duration.rowid
                    AND diff_pre_journey_wait_fp.rowid = diff_walking_duration.rowid
                    AND diff_pre_journey_wait_fp.to_stop_I = 7193"""
        pass


class Parameters(object):
    """
    This provides dictionary protocol for updating parameters table, similar to GTFS metadata ("meta table").
    """

    def __init__(self, conn):
        self._conn = conn

    def __setitem__(self, key, value):
        self._conn.execute("INSERT OR REPLACE INTO parameters('key', 'value') VALUES (?, ?)", (key, value))
        self._conn.commit()

    def __getitem__(self, key):
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM parameters WHERE key=?", (key,))
        val = cur.fetchone()
        if not val:
            raise KeyError("This journey db does not have parameter: %s" % key)
        return val[0]

    def __delitem__(self, key):
        self._conn.execute("DELETE FROM parameters WHERE key=?", (key,))
        self._conn.commit()

    def __iter__(self):
        cur = self._conn.execute('SELECT key FROM parameters ORDER BY key')
        return (x[0] for x in cur)

    def __contains__(self, key):
        val = self._conn.execute('SELECT value FROM parameters WHERE key=?',
                                 (key,)).fetchone()
        return val is not None

    def get(self, key, default=None):
        val = self._conn.execute('SELECT value FROM parameters WHERE key=?',
                                 (key,)).fetchone()
        if not val:
            return default
        return val[0]

    def items(self):
        cur = self._conn.execute('SELECT key, value FROM parameters ORDER BY key')
        return cur

    def keys(self):
        cur = self._conn.execute('SELECT key FROM metadata ORDER BY key')
        return cur

    def values(self):
        cur = self._conn.execute('SELECT value FROM metadata ORDER BY key')
        return cur