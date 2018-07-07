from django.core.management import BaseCommand
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


class Command(BaseCommand):
    help = "Send an updated to all connected clients, immediately"

    def handle(self, *args, **options):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.send)(
            "scraper",
            {
                'type': 'get_latest',
                'message': ''
            }
        )
