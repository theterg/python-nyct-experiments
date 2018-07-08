from django.db import models


class Trip(models.Model):
    DIRECTION_CHOICES = (
            (-1, 'Unknown'),
            (1, 'North'),
            (3, 'South'),
    )
    STATUS_CHOICES = (
            (-1, 'Unknown'),
            (0, 'Incoming_At'),
            (1, 'Stopped_At'),
            (2, 'In_Transit_To'),
    )
    id = models.CharField(max_length=40, primary_key=True)
    alert = models.BooleanField(default=False)
    curr_stop = models.CharField(max_length=4)
    curr_stop_time = models.PositiveIntegerField(default=0)
    current_status = models.SmallIntegerField(default=-1,
                                              choices=STATUS_CHOICES)
    current_stop_sequence = models.SmallIntegerField(default=-1)
    direction = models.SmallIntegerField(default=-1,
                                         choices=DIRECTION_CHOICES)
    is_assigned = models.BooleanField(default=False)
    next_stop = models.CharField(max_length=4)
    next_stop_time = models.PositiveIntegerField(default=0)
    route_id = models.CharField(max_length=4)
    timestamp = models.PositiveIntegerField(default=0)
    train_id = models.CharField(max_length=20)
    trip_id = models.CharField(max_length=20)
    retrieval = models.PositiveIntegerField(default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'alert': self.alert,
            'curr_stop': self.curr_stop,
            'curr_stop_time': self.curr_stop_time,
            'current_status': self.current_status,
            'current_stop_sequence': self.current_stop_sequence,
            'direction': self.direction,
            'is_assigned': self.is_assigned,
            'next_stop': self.next_stop,
            'next_stop_time': self.next_stop_time,
            'route_id': self.route_id,
            'timestamp': self.timestamp,
            'train_id': self.train_id,
            'trip_id': self.trip_id,
            'retrieval': self.retrieval,
        }


class TrainStatus(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.SET_NULL, null=True)
    alert = models.BooleanField(default=False)
    nearest_stop = models.CharField(max_length=4)
    current_status = models.SmallIntegerField(default=-1,
                                              choices=Trip.STATUS_CHOICES)
    direction = models.SmallIntegerField(default=-1,
                                         choices=Trip.DIRECTION_CHOICES)
    at_station = models.BooleanField(default=True)
    progress = models.FloatField(default=0.0)
    timestamp = models.PositiveIntegerField(default=0)
    route_id = models.CharField(max_length=4)
    retrieval = models.PositiveIntegerField(default=0)
    lat = models.FloatField()
    lon = models.FloatField()
    stop_name = models.CharField(max_length=100)

    def to_dict(self):
        return {
            'trip': self.trip.id,
            'alert': self.alert,
            'nearest_stop': self.nearest_stop,
            'current_status': self.current_status,
            'direction': self.direction,
            'at_station': self.at_station,
            'progress': self.progress,
            'timestamp': self.timestamp,
            'route_id': self.route_id,
            'retrieval': self.retrieval,
            'lat': self.lat,
            'lon': self.lon,
            'stop_name': self.stop_name,
        }

    @classmethod
    def from_trip(cls, trip, tracker):
        if not trip.is_assigned:
            return None
        stop = None
        at_station = (trip.curr_stop_time == trip.timestamp)
        progress = 0.0
        if at_station:
            stopid = trip.curr_stop[:3]
            candidates = tracker.stops[tracker.stops.stop_id == stopid]
            if len(candidates) > 0:
                stop = candidates.iloc[0]
        else:
            # TODO - calculate the lat/lon of a trip in progress!
            # if we don't set stop here, we'll just return None
            pass
        if stop is None:
            return None
        return TrainStatus(
            trip=trip,
            alert=trip.alert,
            nearest_stop=trip.curr_stop,
            current_status=trip.current_status,
            direction=trip.direction,
            route_id=trip.route_id,
            at_station=at_station,
            progress=progress,
            retrieval=trip.retrieval,
            lat=stop.stop_lat,
            lon=stop.stop_lon,
            stop_name=stop.stop_name,
        )


class Update(models.Model):
    SCHEDULE_CHOICES = (
        (-1, 'Unknown'),
        (0, 'Scheduled'),
        (1, 'Added'),
        (2, 'Unscheduled'),
        (3, 'Cancelled')
    )
    id = models.CharField(max_length=40, primary_key=True)
    arrival = models.PositiveIntegerField(default=0)
    departure = models.PositiveIntegerField(default=0)
    schedule_relationship = models.SmallIntegerField(default=-1,
                                                     choices=SCHEDULE_CHOICES)
    actual_track = models.CharField(max_length=2)
    scheduled_track = models.CharField(max_length=2)
    stop = models.CharField(max_length=4)
    trip_id = models.CharField(max_length=20)
    parent_trip = models.ForeignKey(Trip, on_delete=models.SET_NULL, null=True)
    retrieval = models.PositiveIntegerField(default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'arrival': self.arrival,
            'departure': self.departure,
            'schedule_relationship': self.schedule_relationship,
            'actual_track': self.actual_track,
            'scheduled_track': self.scheduled_track,
            'stop': self.stop,
            'trip_id': self.trip_id,
            'retrieval': self.retrieval,
        }


class Failure(models.Model):
    content = models.BinaryField()
    elapsed = models.DurationField()
    headers = models.CharField(max_length=200)
    reason = models.CharField(max_length=100)
    status_code = models.SmallIntegerField(default=-1)
