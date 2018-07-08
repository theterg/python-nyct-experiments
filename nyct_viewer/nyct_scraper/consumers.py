# chat/consumers.py
from channels.consumer import SyncConsumer
from asgiref.sync import async_to_sync
from . import NYCT_scraper
import logging
from .models import TrainStatus

logger = logging.getLogger(__name__)


class ScraperConsumer(SyncConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scraper = NYCT_scraper.NYCT_Scraper()
        self.scraper.subscribe(self.raw_update)
        self.current_trains = []

    def raw_update(self, trips, updates, other):
            async_to_sync(self.channel_layer.group_send)(
                    "realtime_stream",
                    {
                        'type': 'raw_data',
                        'data': [x.to_dict() for x in trips],
                    }
            )
            trains = []
            for trip in trips:
                trip.save()
                train = TrainStatus.from_trip(trip, self.scraper.trk)
                if train is not None:
                    trains.append(train)
            self.current_trains = trains
            async_to_sync(self.channel_layer.group_send)(
                    "realtime_stream",
                    {
                        'type': 'train_status',
                        'data': [x.to_dict() for x in trains],
                    }
            )
            for update in updates:
                update.save()

    def get_latest(self, event):
        data = []
        if self.scraper.latest_trips is not None:
            logger.debug("Retrieved %d trips, %d updates" % (
                        len(self.scraper.latest_trips),
                        len(self.scraper.latest_updates)))
            data = [x.to_dict() for x in self.scraper.latest_trips]
        if 'user' in event:
            # If this request to get latest came from a particular user,
            # ONLY reply back to that user
            target = event['user']
        else:
            # If this request came from the cloud, send it to everyone
            target = 'realtime_stream'
        async_to_sync(self.channel_layer.group_send)(
                target,
                {
                    'type': 'raw_data',
                    'data': data
                }
        )
        async_to_sync(self.channel_layer.group_send)(
                target,
                {
                    'type': 'train_status',
                    'data': [x.to_dict() for x in self.current_trains],
                }
        )
