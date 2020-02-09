import logging
import caldav
from . import resource

log = logging.getLogger(__name__)

class EventSynchronizer(object):

    gcal_client = None
    gcal_calendar_id = ""
    caldav_client = None
    caldav_calendar_url = ""

    def __init__(self, gcal_client, gcal_calendar_id, caldav_client, caldav_calendar_url):
        self.gcal_client = gcal_client
        self.gcal_calendar_id = gcal_calendar_id
        self.caldav_client = caldav_client
        self.caldav_calendar_url = caldav_calendar_url

    def sync_once(self, events, ical_calender):
        event = resource.EventResource.init_from_gcal(next(events))
        try:
            log.debug("processing event %r", event)
            uid = event.get("iCalUID", "") or "{}@google.com".format(event.get("id", ""))
            found_ical_event = ical_calender.event_by_uid(uid)
            if event["status"] != "cancelled":
                log.debug("updating event with UID %r", uid)
                found_ical_event.data = event.get_ical()
                found_ical_event.save()
            else:
                log.debug("deleting event with UID %r", uid)
                found_ical_event.delete()
        except caldav.error.NotFoundError:
            if event["status"] == "cancelled":
                log.debug("event with UID %r not found, maybe it is removed, skipping", uid)
                return
            log.debug("creating event with UID %r", uid)
            ical_calender.add_event(event.get_ical())
        except Exception as e:
            log.error("unexpected error %r", e)
            raise e

    def sync(self):
        events = self.gcal_client.get_sync_events(self.gcal_calendar_id)
        ical_calender = self.caldav_client.get_calendar_by_url(self.caldav_calendar_url)
        try:
            while True:
                self.sync_once(events, ical_calender)
        except StopIteration:
            log.info("finished syncing")
            self.gcal_client.save_sync_token()
        except Exception as e:
            log.exception("cannot sync due to %r", e)
