# chat/routing.py
from . import consumers

scraper_channels = {
    "scraper": consumers.ScraperConsumer,
}
