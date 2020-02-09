import os
import caldav
import pickle
import logging
import googleapiclient.discovery
import google_auth_oauthlib.flow
import google.auth.transport.requests

log = logging.getLogger(__name__)

class CalDavClient(caldav.DAVClient):
    _principal = None
    _calendars = None
    _last_sync_datetime = None
    _config = None

    def __init__(self, config):
        self._config = config
        super(CalDavClient, self).__init__(
            url=self._config["calendar_url"], username=self._config["username"], password=self._config["password"],
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
        log.error(
            "cannot find calendar %r, avaiable calendars are %r",
            calendar_url,
            [c.canonical_url for c in self._calendars],
        )

    def get_sync_events(self, calendar_url):
        calendar = self.get_calendar_by_url(calendar_url)
        if not calendar:
            return []
        # only search for future events
        caldav_events = calendar.date_search(arrow.now())
        convertor = CalDavIcsConvertor(caldav_events)
        return convertor.get_resource_events(self._last_sync_datetime)

    def set_last_sync_datetime(self):
        self._last_sync_datetime = arrow.now().isoformat()
        with open(self._config["last_sync_datetime_path"], "w") as f:
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
