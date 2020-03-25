import logging
import caldav
import arrow

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

    def sync_once(self, event, ical_calender):
        """Search event in ical, then do add, remove or update according to status

        :param event: EventResource
        :param ical_calender: caldav.Calendar

        """

        try:
            log.info("processing event %r", event)
            uid = event.get("iCalUID", "") or "{}@google.com".format(event.get("id", ""))
            found_ical_event = ical_calender.event_by_uid(uid)
            if event["status"] != "cancelled":
                log.info("updating event with UID %r", uid)
                found_ical_event.data = event.get_ical()
                found_ical_event.save()
            else:
                log.info("deleting event with UID %r", uid)
                found_ical_event.delete()
        except caldav.error.NotFoundError:
            if event["status"] == "cancelled":
                log.info("event with UID %r not found, maybe it is removed, skipping", uid)
                return
            log.info("creating event with UID %r", uid)
            ical_calender.add_event(event.get_ical())
        except caldav.error.AuthorizationError as e:
            log.info('cannot process event because authorization error %r', e)
        except Exception as e:
            log.error("unexpected error %r", e)
            raise e

    def sync(self):
        events = self.gcal_client.get_sync_events(self.gcal_calendar_id)
        ical_calender = self.caldav_client.get_calendar_by_url(self.caldav_calendar_url)

        # Sync updated event from Google calendar
        try:
            for event in events:
                self.sync_once(event, ical_calender)
            log.info("finished syncing")
            self.gcal_client.save_sync_token()
        except Exception as e:
            log.exception("cannot sync due to %r", e)

        # Compare caldav event and gcal event by UID and add/update events
        now = arrow.now()
        caldav_events = self.caldav_client.get_events(self.caldav_calendar_url, now)
        gcal_events = self.gcal_client.get_events(self.gcal_calendar_id, now)
        gcal_uid_event_map = {event['iCalUID']: event for event in gcal_events}
        for event in caldav_events:
            try:
                log.info('processing event %r', event)
                uid = event['iCalUID']
                if uid not in gcal_uid_event_map:
                    log.info('create event with UID %r', uid)
                    self.gcal_client.add_event(self.gcal_calendar_id, event)

                elif event['updated'] > gcal_uid_event_map[uid]['updated']:
                    log.info('updating event with UID %r', uid)
                    self.gcal_client.update_event(self.gcal_calendar_id, gcal_uid_event_map[uid]['id'], event)
            except Exception as e:
                log.exception('cannot process event %r', e)
