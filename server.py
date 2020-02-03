import caldav
import datetime
import json
import os
import pickle
import googleapiclient.discovery
import google_auth_oauthlib.flow
import google.auth.transport.requests
from caldav.elements import dav, cdav
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
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(client_secrets_file_path, GoogleCalendarClient.SCOPES)
                self._credentials = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("token.pickle", "wb") as token:
                pickle.dump(self._credentials, token)

        self._service = googleapiclient.discovery.build("calendar", "v3", credentials=self._credentials, cache_discovery=False)


class EventSynchronizer(object):

    source_caldav = None
    source_calendar_name = ""
    target_caldav = None
    target_calendar_name = ""

    def __init__(self, source_caldav, source_calendar_name, target_caldav, target_calendar_name):
        self.source_caldav = source_caldav
        self.source_calendar_name = source_calendar_name
        self.target_caldav = target_caldav
        self.target_calendar_name = target_calendar_name

    def get_syncing_events(self):
        calendar = self.source_caldav.get_calendar(self.source_calendar_name)
        return calendar.date_search(start=datetime.datetime.today())

    def sync(self):
        pass


def main():
    if os.path.exists("caldav.json"):
        with open("caldav.json") as caldav_conf_file:
            caldav_conf = json.load(caldav_conf_file)
    caldav_calender_client = CalDavClient(
        caldav_conf["source_url"], username=caldav_conf["username"], password=caldav_conf["password"]
    )
