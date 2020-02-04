import caldav
import os
import pickle
import ics
import googleapiclient.discovery
import google_auth_oauthlib.flow
import google.auth.transport.requests
import logging
import json
import arrow
import config as server_config

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class CalDavClient(caldav.DAVClient):
    _principal = None
    _calendars = None
    _last_sync_datetime = None
    _config = None

    def __init__(self, config):
        self._config = config
        super(CalDavClient, self).__init__(
            url=self._config["calendar_url"],
            username=self._config["username"],
            password=self._config["password"],
        )
        if os.path.exists(self._config["last_sync_datetime_path"]):
            with open(self._config["last_sync_datetime_path"]) as f:
                datetime_str = f.read().strip()
                if datetime_str:
                    self._last_sync_datetime = arrow.get(datetime_str)
        self._connect()

    def _connect(self):
        self._principal = self.principal()
        self._calendars = self._principal.calendars()

    def get_calendars(self):
        return self._calendars

    def get_calendar_by_url(self, calendar_url):
        for calendar in self._calendars:
            if calendar.canonical_url == calendar_url:
                return calendar
        log.error("cannot find calendar %r, avaiable calendars are %r", calendar_url, [c.canonical_url for c in self._calendars])


    def get_sync_events(self, calendar_url):
        calendar = self.get_calendar_by_url(calendar_url)
        if not calendar:
            return []
        # only search for future events
        caldav_events = calendar.date_search(arrow.now())
        convertor = CalDavIcsConvertor(caldav_events)
        return convertor.get_resource_events()

    def set_last_sync_datetime(self):
        self._last_sync_datetime = arrow.now().isoformat()
        with open(self._config["last_sync_datetime_path"], 'w') as f:
            f.write(self._last_sync_datetime.isoformat())


class GoogleCalendarClient(object):

    _credentials = None
    _service = None
    _sync_token = None  # cache for synchronization like sync token key
    _config = None
    SCOPES = ["https://www.googleapis.com/auth/calendar"]  # read/write access to Calendars

    def __init__(self, config):
        self._config = config
        if os.path.exists(self._config["sync_token_path"]):
            with open(self._config["sync_token_path"]) as f:
                self._sync_token = json.load(f)
        else:
            self._sync_token = {}
        if os.path.exists("token.pickle"):
            with open("token.pickle", "rb") as token:
                self._credentials = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not self._credentials or not self._credentials.valid:
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(google.auth.transport.requests.Request())
            else:
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    self._config["credentials_path"], GoogleCalendarClient.SCOPES
                )
                self._credentials = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("token.pickle", "wb") as token:
                pickle.dump(self._credentials, token)

        self._service = googleapiclient.discovery.build(
            "calendar", "v3", credentials=self._credentials, cache_discovery=False
        )

    def get_events(self, calendar_id, events):
        next_page_token = None
        while True:
            for event in events.get("items", []):
                yield event
            events = self._service.events().list(calendarId=calendar_id, pageToken=next_page_token).execute()
            next_page_token = events.get("nextPageToken", None)

            if not next_page_token:
                self._sync_token[calendar_id] = events.get("nextSyncToken", None)
                break

    def get_sync_events(self, calendar_id):
        sync_token = self._sync_token.get(calendar_id, None)
        # will be a full sync if sync_token is None
        events = self._service.events().list(calendarId=calendar_id, syncToken=sync_token).execute()

        return self.get_events(calendar_id, events)

    def save_sync_token(self):
        with open(self._config["sync_token_path"], "w") as f:
            json.dump(self._sync_token, f)


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
        event = EventResource(next(events))
        try:
            log.debug("processing event %r", event)
            uid = event.get("iCalUID", "") or "{}@google.com".format(event.get("id", ""))
            found_ical_event = ical_calender.event_by_uid(uid)
            if event["status"] != "cancelled":
                log.debug("updating event with UID %r", uid)
                found_ical_event.data = event.export_ical()
                found_ical_event.save()
            else:
                log.debug("deleting event with UID %r", uid)
                found_ical_event.delete()
        except caldav.error.NotFoundError:
            if event["status"] == "cancelled":
                log.debug("event with UID %r not found, maybe it is removed, skipping", uid)
                return
            log.debug("creating event with UID %r", uid)
            ical_calender.add_event(event.export_ical())
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


class CalDavIcsConvertor(object):
    _event_list = None

    def __init__(self, event_list):
        self._event_list = event_list

    def get_ics_events(self):
        canlendar_list = ics.Calendar.parse_multiple('\n'.join(caldav_event.data for caldav_event in self._event_list))
        events = set()
        for calendar in canlendar_list:
            events |= calendar.events
        return events

    def get_resource_events(self):
        events = self.get_ics_events()
        return [EventResource.init_from_ics(event) for event in events]

class EventResource(dict):

    @classmethod
    def init_from_ics(cls, ics_event):
        event = {
            "summary": ics_event.name,
            "start": ics_event.begin.isoformat() if ics_event.begin else None,
            "end": ics_event.begin.isoformat() if ics_event.end else None,
            'iCalUID': ics_event.uid,
            'description': ics_event.description,
            "created": ics_event.created.isoformat() if ics_event.created else None,
            "updated": ics_event.last_modified.isoformat() if ics_event.last_modified else None,
            "location": ics_event.location,
            "transparency": "transparent" if ics_event.transparent else "opaque",
            "status": ics_event.status,
            "organizer": {"email": ics_event.organizer.replace('mailto:', '')} if ics_event.organizer is not None else None,
        }
        return cls(event)

    def export_ical(self):
        ics_calendar = ics.Calendar()
        ics_event = ics.Event(
            name=self.get("summary", None),
            duration=None,
            uid=self.get("iCalUID", None),
            description=self.get("description", None),
            created=self.get("created", None),
            last_modified=self.get("updated", None),
            location=self.get("location", None),
            url=None,
            transparent=self.get("transparency", None) == "transparent",
            alarms=None,
            attendees=[
                ics.Attendee(attendee["email"]) for attendee in self.get("attendees", []) if attendee.get("email", None)
            ],
            categories=None,
            status=self.get("status", None),
            organizer=self.get("organizer", {}).get("email", None),
            geo=None,
            classification=None,
        )

        for gcal_key, ics_key in [("start", "begin"), ("end", "end")]:
            is_one_day_event = self.get(gcal_key, {}).get("dateTime", None) is None
            arror_time = (
                self.get(gcal_key, {}).get("dateTime", None)
                if not is_one_day_event
                else self.get(gcal_key, {}).get("date", None)
            )
            setattr(ics_event, ics_key, arror_time)
            if is_one_day_event:
                ics_event.make_all_day()
        ics_calendar.events.add(ics_event)
        return ics_calendar.__str__()


def main():
    caldav_client = CalDavClient(server_config.caldav)
    gcal_client = GoogleCalendarClient(server_config.gcal)
    synchronizer = EventSynchronizer(
        gcal_client, server_config.gcal["calendar_id"], caldav_client, server_config.caldav["calendar_url"]
    )
    synchronizer.sync()

if __name__ == "__main__":
    main()
