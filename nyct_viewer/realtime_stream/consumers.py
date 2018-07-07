# chat/consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import async_to_sync
import logging
import json
import uuid


logger = logging.getLogger(__name__)


class RealtimeStreamConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def connect(self):
        self.group_name = str(uuid.uuid4())
        await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
        )
        await self.channel_layer.group_add(
                "realtime_stream",
                self.channel_name
        )
        await self.accept()
        await self.channel_layer.send(
            "scraper",
            {
                'type': 'get_latest',
                'user': self.group_name,
            }
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
                "realtime_stream",
                self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        # Any websocket messages sent BACK from client to server
        # are a request of some kind, should be rare if not used at all
        await self.channel_layer.group_send(
                "realtime_stream",
                {
                    'type': 'data_request',
                    'request': text_data_json,
                }
        )

    async def raw_data(self, event):
        await self.send(text_data=json.dumps(event))

    async def data_request(self, event):
        # Websocket clients (web clients) do not need to respond
        # to other data requests.
        pass
