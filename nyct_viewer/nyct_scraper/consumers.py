# chat/consumers.py
from channels.consumer import SyncConsumer
from asgiref.sync import async_to_sync
from . import NYCT_scraper
import logging
import json

logger = logging.getLogger(__name__)


class ScraperConsumer(SyncConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scraper = NYCT_scraper.NYCT_Scraper()

    def get_latest(self, event):
        data = []
        if self.scraper.latest_trips is not None:
            logger.debug("Retrieved %d trips, %d updates" % (
                        len(self.scraper.latest_trips),
                        len(self.scraper.latest_updates)))
            data = json.loads(self.scraper.latest_trips.to_json(
                orient='records'))
        if 'user' in event:
            # If this request to get latest came from a particular user,
            # ONLY reply back to that user
            async_to_sync(self.channel_layer.group_send)(
                    event['user'],
                    {
                        'type': 'raw_data',
                        'data': data
                    }
            )
        else:
            # If this request came from the cloud, send it to everyone
            async_to_sync(self.channel_layer.group_send)(
                    'realtime_stream',
                    {
                        'type': 'raw_data',
                        'data': data
                    }
            )
