import os

config_dir = os.path.dirname(os.path.abspath(__file__))

caldav = {
    "username": "username",
    "password": "password",
    "calendar_url": "https://url/to/Calendar/"
}

gcal = {
    "calendar_id": "calendar_id of google calender",
    "credentials_path": os.path.join(config_dir, "credentials.json"),
    "sync_token_path": os.path.join(config_dir, "sync_token.json"),
}
