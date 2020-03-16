# Two way (kind of) synchronizer for Google calendar and caldav server

Motivation for this small tool is, so hard to find a good graphical caldav client under linux. I've tried thunderbird, MineTime, Gnome Calendar, Korganizer etc. MineTime is a better one among those clients, which is a research project and essentially a electron app.

I thought maybe Google calendar support caldav and it turned out to be a missing feature. Then it comes to this side project.

What this program does is extermely simple --- try to do 2 ways synchronization between Google calendar and caldav. Because if someone else can send you event invitations that you are not the only source creating events. Otherwise 1 way synchronization is good enough.

Developed under Python 3.8.1

## Getting Started

### Prerequisite
* Enable calendar API access [here](https://developers.google.com/calendar/quickstart/python)
* Download your google calender API credentials [here](https://console.developers.google.com/apis/credentials) as `credentials.json`

### Settings
/home/binbin/Develop/sync-caldav-to-google/config/
* Put `credentials.json` in config folder
* Copy `__init__.template.py` as `__init__.py` in config folder and fill in information
* `pip install -r requirements.txt`

### Work flow
1. List all events from Google calendar, use sync token to remember where to pick up in next sync
2. Add, remove and update caldav events
3. List events from Google and caldav then compare 2 lists

### Known issues
* An event deleted on caldav will not be deleted on Google caldendar side since it is hard to tell what event is deleted on caldav server
