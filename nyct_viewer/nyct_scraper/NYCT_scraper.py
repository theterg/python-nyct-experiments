import logging
import threading
import schedule
import atexit
import pandas as pd
try:
    from NYCT_tracker import NYCT_Tracker
except ImportError:
    from .NYCT_tracker import NYCT_Tracker

logger = logging.getLogger(__name__)


class NYCT_Scraper(object):
    ''' Simplistic singleton wrapper:
    We only want one instance of the scraper to ever be running at once
    Because we want to be nice to the MTA and avoid accidentally hitting
    the endpoint too often '''
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        cls._lock.acquire()
        if cls._instance is None:
            i = _NYCT_Scraper.__new__(_NYCT_Scraper)
            i.__init__()    # Weirdly __init__ isn't automatically called
            cls._instance = i
        else:
            i = cls._instance
        cls._lock.release()
        return i


class _NYCT_Scraper(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = False
        self.running = False
        self.latest_trips = pd.DataFrame()
        self.latest_updates = pd.DataFrame()
        self.subscribers = []
        self.exit = threading.Event()
        self.trk = NYCT_Tracker(None)
        atexit.register(self.stop)
        schedule.every(30).seconds.do(self._trip_update)
        self.restart()

    def subscribe(self, func):
        if func not in self.subscribers:
            self.subscribers.append(func)

    def unsubscribe(self, func):
        if func in self.subscribers:
            self.subscribers.remove(self.subscribers.index(func))

    def restart(self):
        # Threads don't normally allow restarting
        # So we need to re-instantiate our Thread instance
        # then we can re-start the thread
        threading.Thread.__init__(self)
        self.daemon = True
        self.running = False
        self.start()

    def stop(self):
        self.running = False
        self.exit.set()
        self.join()

    def run(self):
        self.running = True
        try:
            # Manually kick off a trip update
            self._trip_update()
        except:
            logger.exception("")
        while self.running:
            try:
                schedule.run_pending()
                delay = schedule.idle_seconds()
                # Enforce a minimum delay to avoid thrashing
                if delay < 1.0:
                    self.exit.wait(1.0)
                else:
                    self.exit.wait(delay)
            except KeyboardInterrupt:
                break
            except:
                logger.exception("")
                self.exit.wait(1.0)
                continue

    def _trip_update(self):
        trips, updates, other = self.trk.get_all_trips()
        logger.debug("Got %d trips, %d updates, %d other",
                     len(trips), len(updates), len(other))
        self.latest_trips = trips
        self.latest_updates = updates
        for func in self.subscribers:
            if hasattr(func, '__call__'):
                # Squash the heck out of interrupts:
                # We don't want one callback func to screw it up for others
                try:
                    func(trips, updates, other)
                except KeyboardInterrupt:
                    break
                except:
                    logger.exception("")
