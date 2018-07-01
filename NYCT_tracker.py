import pandas as pd
import numpy as np
# GTFS protobuf wrapper was generated using protoc and https://developers.google.com/transit/gtfs-realtime/gtfs-realtime.proto
import gtfs_realtime_pb2
# The NYCT extensions to GTFS are also compiled from this protobuf: http://datamine.mta.info/sites/all/files/pdfs/nyct-subway.proto.txt
import nyct_subway_pb2
import requests
import copy
import os
from sqlalchemy import create_engine


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

    def __init__(self, apikey):
        if apikey is None:
            # Helper: Attempt to read APIKEY from disk
            with open('./mta_key.txt', 'r') as fil:
                apikey = fil.read().strip()
        self.apikey = apikey
        self.shapes_clean = False
        self.shapes = pd.read_csv(
                os.path.join(NYCT_Tracker.METADATA_PATH, 'shapes.txt'))

    def get_shapes(self):
        # TODO - this is horribly inefficient.
        if not self.shapes_clean:
            remove = []
            drop_idxes = pd.Int64Index([])
            routes = self.shapes.shape_id.unique()
            for i in range(len(routes)):
                route = routes[i]
                for other_route in self.shapes[
                        self.shapes.shape_id.str.startswith(route[0])].shape_id.unique():
                    if other_route == route:
                        continue
                    if other_route in remove:
                        continue
                    latcommon = np.setdiff1d(self.shapes[self.shapes.shape_id==route].shape_pt_lat,
                                             self.shapes[self.shapes.shape_id==other_route].shape_pt_lat)
                    loncommon = np.setdiff1d(self.shapes[self.shapes.shape_id==route].shape_pt_lon,
                                             self.shapes[self.shapes.shape_id==other_route].shape_pt_lon)
                    if len(latcommon) == 0 and len(loncommon) == 0:
                        # print route+" is contained within "+other_route
                        remove.append(route)
                        drop_idxes = np.concatenate((drop_idxes, self.shapes[self.shapes.shape_id==route].index))
                        break
            self.shapes = self.shapes.drop(drop_idxes)
            self.shapes_clean = True
        return self.shapes
