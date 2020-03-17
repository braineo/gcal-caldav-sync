import os
import caldav
import pickle
import logging
import json
import arrow
import googleapiclient.discovery
import google_auth_oauthlib.flow
import google.auth.transport.requests

from . import resource

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

    def get_events(self, calendar_url, time_min):
        calendar = self.get_calendar_by_url(calendar_url)
        if not calendar:
            return []
        # only search for future events
        caldav_events = calendar.date_search(time_min)
        convertor = resource.CalDavIcsConvertor(caldav_events)
        return convertor.get_resource_events()

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

    def flatten_event_response(self, calendar_id, events):
        """Get all events items from paginated api response

        :param calendar_id: google calendar id
        :param events: initial reponse of event.list
        :returns: all events
        :rtype: list

        """
        all_events = []
        next_page_token = None
        while True:
            for event in events.get("items", []):
                event['timeZone'] = events['timeZone']
                all_events.append(resource.EventResource.init_from_gcal(event))
            events = (
                self._service.events()
                .list(maxResults=2500, calendarId=calendar_id, pageToken=next_page_token)
                .execute()
            )
            next_page_token = events.get("nextPageToken", None)

            if not next_page_token:
                self._sync_token[calendar_id] = events.get("nextSyncToken", None)
                break
        return all_events

    def get_sync_events(self, calendar_id):
        sync_token = self._sync_token.get(calendar_id, None)
        # will be a full sync if sync_token is None
        events = self._service.events().list(maxResults=2500, calendarId=calendar_id, syncToken=sync_token).execute()

        return self.flatten_event_response(calendar_id, events)

    def save_sync_token(self):
        with open(self._config["sync_token_path"], "w") as f:
            json.dump(self._sync_token, f)

    def get_events(self, calendar_id, time_min):
        """get all events based on updated_min

        :param calendar_id: calendarId: string, Calendar identifier. To retrieve calendar IDs call the calendarList.list method. If you want to access the primary calendar of the currently logged in user, use the "primary" keyword.
        :param time_min: arrow object. Google api takes string, Lower bound (exclusive) for an event's end time to filter by. Must be an RFC3339 timestamp with mandatory time zone offset, for example, 2011-06-03T10:00:00-07:00, 2011-06-03T10:00:00Z
        :returns: 
        :rtype: 

        """
        all_events = []
        events = self._service.events().list(maxResults=2500, calendarId=calendar_id, timeMin=time_min.isoformat()).execute()
        for event in events.get("items", []):
            event['timeZone'] = events['timeZone']
            all_events.append(resource.EventResource.init_from_gcal(event))
        return all_events
