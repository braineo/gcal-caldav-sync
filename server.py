import caldav
import datetime
import json
import os
import pickle
import ics
import googleapiclient.discovery
import google_auth_oauthlib.flow
import google.auth.transport.requests
import logging

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class CalDavClient(caldav.DAVClient):
    _principal = None
    _calendars = None

    def __init__(self, url, proxy=None, username=None, password=None, auth=None, ssl_verify_cert=True):
        super(CalDavClient, self).__init__(url, proxy, username, password, auth, ssl_verify_cert)
        self._connect()

    def _connect(self):
        self._principal = self.principal()
        self._calendars = self._principal.calendars()

    def get_calendars(self):
        return self._calendars

    def get_calendar(self, calendar_name):
        for calendar in self._calendars:
            if calendar.name == calendar_name:
                return calendar
        log.error(
            "cannot find calendar %r, avaiable calendars are %r", calendar_name, [c.name for c in self._calendars]
        )


class GoogleCalendarClient(object):

    _credentials = None
    _service = None
    SCOPES = ["https://www.googleapis.com/auth/calendar"]  # read/write access to Calendars

    def __init__(self, client_secrets_file_path):
        if os.path.exists("token.pickle"):
            with open("token.pickle", "rb") as token:
                self._credentials = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not self._credentials or not self._credentials.valid:
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(google.auth.transport.requests.Request())
            else:
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    client_secrets_file_path, GoogleCalendarClient.SCOPES
                )
                self._credentials = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("token.pickle", "wb") as token:
                pickle.dump(self._credentials, token)

        self._service = googleapiclient.discovery.build(
            "calendar", "v3", credentials=self._credentials, cache_discovery=False
        )

    def get_events(self, calendar_name):
        page_token = None
        events = self._service.events().list(calendarId=calendar_name, pageToken=page_token).execute()
        while True:
            for event in events["items"]:
                yield event
            page_token = events.get("nextPageToken")
            if not page_token:
                break


class EventSynchronizer(object):

    gcal_client = None
    gcal_calendar_id = ""
    caldav_client = None
    caldav_calendar_name = ""

    def __init__(self, gcal_client, gcal_calendar_id, caldav_client, caldav_calendar_name):
        self.gcal_client = gcal_client
        self.gcal_calendar_id = gcal_calendar_id
        self.caldav_client = caldav_client
        self.caldav_calendar_name = caldav_calendar_name

    def sync_once(self, events, ical_calender):
        event = EventResource(next(events))
        ical_event = event.export_ical()
        try:
            ical_event = ical_calender.event_by_uid(event.get("iCalUID", ""))
            log.debug("updating event with UID %r", event.get("iCalUID", ""))
            ical_event.data = event.export_ical()
            ical_event.save()
        except caldav.error.NotFoundError:
            log.debug("creating event with UID %r", event.get("iCalUID", ""))
            ical_calender.add_event(ical_event)
        except Exception as e:
            log.error("unexpected error %r", e)

    def sync(self):
        events = self.gcal_client.get_events(self.gcal_calendar_id)
        ical_calender = self.caldav_client.get_calendar(self.caldav_calendar_name)
        try:
            while True:
                self.sync_once(self, events, ical_calender)
        except StopIteration:
            log.info("finished syncing")
        except Exception:
            log.error("cannot sync")


class EventResource(dict):
    def export_ical(self):
        ics_event = ics.Event(
            name=self["summary"],
            begin=self.get("start", {}).get("dateTime", None),
            end=self.get("end", {}).get("dateTime", None),
            duration=None,
            uid=self.get("iCalUID", None),
            description=self.get("description", None),
            created=self.get("created", None),
            last_modified=self.get("updated", None),
            location=self.get("location", None),
            url=None,
            transparent=self.get("transparency", None),
            alarms=None,
            attendees=None,
            categories=None,
            status=None,
            organizer=self.get("organizer", {}).get("email", None),
            geo=None,
            classification=None,
        )

        return ics_event.__str__()


def main():
    if os.path.exists("caldav.json"):
        with open("caldav.json") as caldav_conf_file:
            caldav_conf = json.load(caldav_conf_file)
    caldav_calender_client = CalDavClient(
        caldav_conf["source_url"], username=caldav_conf["username"], password=caldav_conf["password"]
    )
