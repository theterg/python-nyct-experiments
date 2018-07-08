import pandas as pd
# GTFS protobuf wrapper was generated using protoc and https://developers.google.com/transit/gtfs-realtime/gtfs-realtime.proto
# The NYCT extensions to GTFS are also compiled from this protobuf: http://datamine.mta.info/sites/all/files/pdfs/nyct-subway.proto.txt
try:
    import gtfs_realtime_pb2
    import nyct_subway_pb2
except ImportError:
    from . import gtfs_realtime_pb2
    from . import nyct_subway_pb2
import requests
import os
import time
from sqlalchemy import create_engine
from .models import Trip, Update


def append_trip_info(trip):
    nyct_trip = trip.Extensions[nyct_subway_pb2.nyct_trip_descriptor]
    data = {}
    data['trip_id'] = trip.trip_id
    data['is_assigned'] = nyct_trip.is_assigned
    data['train_id'] = nyct_trip.train_id
    data['direction'] = nyct_trip.direction
    data['route_id'] = trip.route_id
    return data


def parse_feed(feed):
    unknown = []
    trips_raw = {}
    updates_raw = []
    feed_query_time = feed.header.timestamp
    for idx in range(len(feed.entity)):
        entity = feed.entity[idx]
        if entity.HasField("vehicle"):
            trip_id = entity.vehicle.trip.trip_id
            if trip_id not in trips_raw:
                trip = Trip(id="%s_%d" % (str(trip_id), feed_query_time),
                            route_id=entity.vehicle.trip.route_id,
                            trip_id=trip_id)
            else:
                trip = trips_raw[trip_id]
            nyct_trip = entity.vehicle.trip.Extensions[
                    nyct_subway_pb2.nyct_trip_descriptor]
            trip.is_assigned = nyct_trip.is_assigned
            trip.train_id = nyct_trip.train_id
            trip.direction = nyct_trip.direction
            trip.timestamp = entity.vehicle.timestamp
            trip.current_stop_sequence = entity.vehicle.current_stop_sequence
            trip.current_status = entity.vehicle.current_status
            trip.retrieval = feed_query_time
            trips_raw[trip_id] = trip
        elif entity.HasField("trip_update"):
            trip_id = entity.trip_update.trip.trip_id
            if trip_id not in trips_raw:
                trip = Trip(id="%s_%d" % (str(trip_id), feed_query_time),
                            route_id=entity.trip_update.trip.route_id,
                            trip_id=trip_id)
            else:
                trip = trips_raw[trip_id]
            for update in entity.trip_update.stop_time_update:
                new_update = Update(
                    id="%s_%s_%d" % (trip_id, update.stop_id, feed_query_time),
                    parent_trip=trip,
                    trip_id=entity.trip_update.trip.trip_id,
                    arrival=update.arrival.time,
                    departure=update.departure.time,
                    stop=update.stop_id,
                    schedule_relationship=update.schedule_relationship,
                )
                nyct_update = update.Extensions[
                        nyct_subway_pb2.nyct_stop_time_update]
                new_update.scheduled_track = nyct_update.scheduled_track
                new_update.actual_track = nyct_update.actual_track
                new_update.retrieval = feed_query_time
                updates_raw.append(new_update)
            upd = entity.trip_update
            trip.curr_stop = upd.stop_time_update[0].stop_id
            trip.curr_stop_time = upd.stop_time_update[0].departure.time
            if len(upd.stop_time_update) > 1:
                trip.next_stop = upd.stop_time_update[1].stop_id
                trip.next_stop_time = upd.stop_time_update[1].departure.time
            else:
                trip.next_stop = trip.curr_stop
                trip.next_stop_time = trip.curr_stop_time
            trip.retrieval = feed_query_time
            trips_raw[trip_id] = trip
        elif entity.HasField("alert"):
            for selector in entity.alert.informed_entity:
                trip_id = selector.trip.trip_id
                if trip_id in trips_raw:
                    trips_raw[trip_id].alert = True
                # Really not much else we know here, soooo
        else:
            unknown.append(entity.SerializeToString())
    # trips = pd.DataFrame(index=list(trips_raw.keys()),
    #                      data=list(trips_raw.values())).sort_values('curr_stop_time')
    # updates = pd.DataFrame(index=list(updates_raw.keys()),
    #                      data=list(updates_raw.values())).sort_values('departure')
    return list(trips_raw.values()), updates_raw, unknown


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
        # engine = create_engine('postgresql://%s:%s@127.0.0.1:5432/%s' % (
        #     postgres_user, postgres_password, postgres_db), echo=False)

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
            alltrips = alltrips + trips
            allupdates = allupdates + updates
            otheroutput = otheroutput + other
            time.sleep(0.250)
        return alltrips, allupdates, otheroutput

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
        for trip in trips:
            trips.save()
        # timestamp = trips.index[0].split('_')[-1]
        # if self.last_trips_store == timestamp:
        #     raise RuntimeError("Timestamp %s already stored" % timestamp)
        # trips.to_sql('trips', self.engine, if_exists='append')
        # self.last_trips_store = timestamp

    def store_updates(self, updates):
        for update in updates:
            update.save()
        # timestamp = updates.index[0].split('_')[-1]
        # if self.last_updates_store == timestamp:
        #     raise RuntimeError("Timestamp %s already stored" % timestamp)
        # updates.to_sql('updates', self.engine, if_exists='append')
        # self.last_updates_store = timestamp

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
