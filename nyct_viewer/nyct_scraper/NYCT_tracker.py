import pandas as pd
import numpy as np
# GTFS protobuf wrapper was generated using protoc and https://developers.google.com/transit/gtfs-realtime/gtfs-realtime.proto
# The NYCT extensions to GTFS are also compiled from this protobuf: http://datamine.mta.info/sites/all/files/pdfs/nyct-subway.proto.txt
try:
    import gtfs_realtime_pb2
    import nyct_subway_pb2
except ImportError:
    from . import gtfs_realtime_pb2
    from . import nyct_subway_pb2
import requests
import copy
import os
import time
from sqlalchemy import create_engine


def generate_trip_info(trip):
    nyct_trip = trip.Extensions[nyct_subway_pb2.nyct_trip_descriptor]
    data = {}
    data['trip_id'] = trip.trip_id
    data['is_assigned'] = nyct_trip.is_assigned
    data['train_id'] = nyct_trip.train_id
    data['direction'] = nyct_trip.direction
    data['route_id'] = trip.route_id
    data['alert'] = False
    # If vehicle data is never reported, let's set some defaults
    data['timestamp'] = -1
    data['current_stop_sequence'] = -1
    data['current_status'] = -1
    return data


def copy_into_trips(trips, trip_data, feed_query_time):
    tid = trip_data['trip_id']+"_"+str(feed_query_time)
    if tid not in trips:
        trips[tid] = trip_data
    else:
        trips[tid].update(trip_data)
    return trips


def parse_feed(feed):
    unknown = []
    trips_raw = {}
    updates_raw = {}
    feed_query_time = feed.header.timestamp
    for idx in range(len(feed.entity)):
        entity = feed.entity[idx]
        if entity.HasField("vehicle"):
            data = generate_trip_info(entity.vehicle.trip)
            data['timestamp'] = entity.vehicle.timestamp
            data['current_stop_sequence'] = entity.vehicle.current_stop_sequence
            data['current_status'] = entity.vehicle.current_status
            trips_raw = copy_into_trips(trips_raw, data, feed_query_time)
        elif entity.HasField("trip_update"):
            data = generate_trip_info(entity.trip_update.trip)
            for update in entity.trip_update.stop_time_update:
                trip_update = {}
                trip_update['trip_id'] = entity.trip_update.trip.trip_id
                trip_update['arrival'] = update.arrival.time
                trip_update['departure'] = update.departure.time
                trip_update['stop'] = update.stop_id
                trip_update['schedule_relationship'] = update.schedule_relationship
                nyct_update = update.Extensions[nyct_subway_pb2.nyct_stop_time_update]
                trip_update['scheduled_track'] = nyct_update.scheduled_track
                trip_update['actual_track'] = nyct_update.actual_track
                updates_raw[trip_update['trip_id']+"_"+trip_update['stop']+"_"+str(feed_query_time)] = trip_update
            data['curr_stop'] = entity.trip_update.stop_time_update[0].stop_id
            data['curr_stop_time'] = entity.trip_update.stop_time_update[0].departure.time
            if len(entity.trip_update.stop_time_update) > 1:
                data['next_stop'] = entity.trip_update.stop_time_update[1].stop_id
                data['next_stop_time'] = entity.trip_update.stop_time_update[1].departure.time
            else:
                data['next_stop'] = data['curr_stop']
                data['next_stop_time'] = data['curr_stop_time']
            trips_raw = copy_into_trips(trips_raw, data, feed_query_time)
        elif entity.HasField("alert"):
            for selector in entity.alert.informed_entity:
                data = generate_trip_info(selector.trip)
                data['alert'] = True
                trips_raw = copy_into_trips(trips_raw, data, feed_query_time)
                # Really not much else we know here, soooo
        else:
            unknown.append(entity.SerializeToString())
    trips = pd.DataFrame(index=list(trips_raw.keys()), data=list(trips_raw.values())).sort_values('curr_stop_time')
    trips['at_station'] = (trips.timestamp == trips.curr_stop_time)
    trips['progress'] = ((trips.timestamp - trips.curr_stop_time)/(trips.next_stop_time - trips.curr_stop_time))
    updates = pd.DataFrame(index=list(updates_raw.keys()), data=list(updates_raw.values())).sort_values('departure')
    return trips, updates, unknown


class NYCT_Tracker(object):
    # The following is from: http://datamine.mta.info/list-of-feeds
    LINE_ID = {
        '123456S': 1,
        'ACEHS': 26,
        'NQRW': 16,
        'BDFM': 21,
        'L': 2,
        'G': 31,
        'JZ': 36,
        '7': 51,
    }
    # From: https://en.wikipedia.org/wiki/New_York_City_Subway_nomenclature
    LINE_COLOR = {
        'ACE': '#2850ad',
        'BDFM': '#ff6319',
        'G': '#6cbe45',
        'L': '#a7a9ac',
        'JZ': '#996633',
        'NQRW': '#fccc0a',
        '123': '#ee352e',
        '456': '#00933c',
        '7': '#b933ad',
        'S': '#808183',
    }
    BASEURL = 'http://datamine.mta.info/mta_esi.php?key=%s&feed_id=%d'
    METADATA_PATH = 'metadata/'

    def __init__(self, apikey, postgres_user='subway',
                 postgres_password='subway', postgres_db='subway'):
        if apikey is None:
            # Helper: Attempt to read APIKEY from disk
            with open('./mta_key.txt', 'r') as fil:
                apikey = fil.read().strip()
        self.apikey = apikey
        self.shapes_clean = False
        self.last_trips_store = ''
        self.last_updates_store = ''
        self.shapes = pd.read_csv(
                os.path.join(NYCT_Tracker.METADATA_PATH, 'shapes.txt'))
        self.stops = pd.read_csv(
                os.path.join(NYCT_Tracker.METADATA_PATH, 'stops.txt'))
        self.engine = create_engine('postgresql://%s:%s@127.0.0.1:5432/%s' % (
            postgres_user, postgres_password, postgres_db), echo=False)

    def get_trips(self, line):
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(self.BASEURL % (
            self.apikey, self.LINE_ID[line]))
        feed.ParseFromString(response.content)
        return parse_feed(feed)

    def get_all_trips(self):
        alltrips = []
        allupdates = []
        otheroutput = []
        for line in self.LINE_ID:
            trips, updates, other = self.get_trips(line)
            alltrips.append(trips)
            allupdates.append(updates)
            otheroutput = otheroutput + other
            time.sleep(0.250)
        return pd.concat(alltrips), pd.concat(allupdates), otheroutput

    def get_stops(self, trimmed=True):
        ret = self.stops
        if trimmed:
            ret = self.stops[self.stops.location_type == 1]
            ret.index = pd.Int64Index(range(len(ret)))
            del ret['location_type']
            del ret['stop_url']
            del ret['zone_id']
            del ret['stop_desc']
            del ret['stop_code']
            del ret['parent_station']
        return ret

    def get_stop_by_name(self, stop):
        stop = stop[:3]
        ret = self.stops[self.stops.stop_id == stop].iloc[0]
        return ret

    def store_trips(self, trips):
        timestamp = trips.index[0].split('_')[-1]
        if self.last_trips_store == timestamp:
            raise RuntimeError("Timestamp %s already stored" % timestamp)
        trips.to_sql('trips', self.engine, if_exists='append')
        self.last_trips_store = timestamp

    def store_updates(self, updates):
        timestamp = updates.index[0].split('_')[-1]
        if self.last_updates_store == timestamp:
            raise RuntimeError("Timestamp %s already stored" % timestamp)
        updates.to_sql('updates', self.engine, if_exists='append')
        self.last_updates_store = timestamp

    def get_shapes(self):
        # TODO - this is horribly inefficient, and ugly. But maybe not used.
        if not self.shapes_clean:
            remove = []
            drop_idxes = pd.Int64Index([])
            routes = self.shapes.shape_id.unique()
            for i in range(len(routes)):
                route = routes[i]
                for other_route in self.shapes[
                        self.shapes.shape_id.str.startswith(
                            route[0])].shape_id.unique():
                    if other_route == route:
                        continue
                    if other_route in remove:
                        continue
                    latcommon = np.setdiff1d(
                        self.shapes[
                            self.shapes.shape_id == route].shape_pt_lat,
                        self.shapes[
                            self.shapes.shape_id == other_route].shape_pt_lat)
                    loncommon = np.setdiff1d(
                        self.shapes[
                            self.shapes.shape_id == route].shape_pt_lon,
                        self.shapes[
                            self.shapes.shape_id == other_route].shape_pt_lon)
                    if len(latcommon) == 0 and len(loncommon) == 0:
                        # print route+" is contained within "+other_route
                        remove.append(route)
                        drop_idxes = np.concatenate(
                            (drop_idxes,
                             self.shapes[self.shapes.shape_id == route].index))
                        break
            self.shapes = self.shapes.drop(drop_idxes)
            self.shapes_clean = True
        return self.shapes

if __name__ == '__main__':
    import time
    import traceback
    from datetime import datetime

    trk = NYCT_Tracker(None)
    while True:
        start = 0.0
        stop = 0.0
        try:
            start = time.time()
            trips, updates, other = trk.get_all_trips()
            trk.store_trips(trips)
            trk.store_updates(updates)
            stop = time.time()
            print("%s: Trips %d, Updates %d, Other %d, Duration %.3f" % (
                    datetime.now().strftime("%y%m%d_%H%M%S"),
                    len(trips),
                    len(updates),
                    len(other),
                    stop - start))
            time.sleep(30.0 - (stop-start))
        except KeyboardInterrupt:
            break
        except:
            traceback.print_exc()
            time.sleep(30.0)
            continue
