import os

caldav = {
    "username": "username",
    "password": "password",
    "calendar_url": "https://url/to/Calendar/"
}

gcal = {
    "calendar_id": "calendar_id of google calender",
    "credentials_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json"),
}
