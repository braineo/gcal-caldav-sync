import caldav
import os
import pickle
import ics
import googleapiclient.discovery
import google_auth_oauthlib.flow
import google.auth.transport.requests
import logging

import config as server_config

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

    def get_calendar_by_url(self, calendar_url):
        for calendar in self._calendars:
            if calendar.canonical_url == calendar_url:
                return calendar
        log.error("cannot find calendar %r, avaiable calendars are %r", calendar_url, [c.name for c in self._calendars])


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
    caldav_calendar_url = ""

    def __init__(self, gcal_client, gcal_calendar_id, caldav_client, caldav_calendar_url):
        self.gcal_client = gcal_client
        self.gcal_calendar_id = gcal_calendar_id
        self.caldav_client = caldav_client
        self.caldav_calendar_url = caldav_calendar_url

    def sync_once(self, events, ical_calender):
        event = EventResource(next(events))
        try:
            found_ical_event = ical_calender.event_by_uid(event.get("iCalUID", ""))
            log.debug("updating event with UID %r", event.get("iCalUID", ""))
            found_ical_event.data = event.export_ical()
            found_ical_event.save()
        except caldav.error.NotFoundError:
            log.debug("creating event with UID %r", event.get("iCalUID", ""))
            ical_calender.add_event(event.export_ical())
        except Exception as e:
            log.error("unexpected error %r", e)

    def sync(self):
        events = self.gcal_client.get_events(self.gcal_calendar_id)
        ical_calender = self.caldav_client.get_calendar_by_url(self.caldav_calendar_url)
        try:
            while True:
                self.sync_once(events, ical_calender)
        except StopIteration:
            log.info("finished syncing")
        except Exception as e:
            log.error("cannot sync %r", e)


class EventResource(dict):
    def export_ical(self):
        ics_calendar = ics.Calendar()
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
        ics_calendar.events.add(ics_event)
        return ics_calendar.__str__()


def main():
    caldav_client = CalDavClient(
        server_config.caldav["calendar_url"],
        username=server_config.caldav["username"],
        password=server_config.caldav["password"],
    )
    gcal_client = GoogleCalendarClient("credentials.json")
    synchronizer = EventSynchronizer(
        gcal_client, server_config.gcal["calendar_id"], caldav_client, server_config.caldav["calendar_url"]
    )
    synchronizer.sync()

if __name__ == "__main__":
    main()
