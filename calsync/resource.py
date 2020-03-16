import ics
import copy
import arrow


class CalDavIcsConvertor(object):

    def __init__(self, event_list):
        self._event_list = event_list

    def get_ics_events(self):
        canlendar_list = ics.Calendar.parse_multiple("\n".join(caldav_event.data for caldav_event in self._event_list))
        events = set()
        for calendar in canlendar_list:
            events |= calendar.events
        return events

    def get_resource_events(self, min_modify_time=None):
        events = self.get_ics_events()
        if min_modify_time:
            return [EventResource.init_from_ics(event) for event in events if event.last_modified >= min_modify_time]
        return [EventResource.init_from_ics(event) for event in events]


class EventResource(dict):
    @classmethod
    def init_from_gcal(cls, gcal_event):

        for key in ["created", "updated"]:
            if key in gcal_event:
                gcal_event[key] = arrow.get(gcal_event[key])

        is_all_day_event = False
        for key in ["start", "end"]:
            is_all_day_event = is_all_day_event or gcal_event.get(key, {}).get("dateTime", None) is None
            arror_time = (
                arrow.get(gcal_event.get(key, {}).get("dateTime", None))
                if not is_all_day_event
                else arrow.get(
                    "{date} {timeZone}".format(
                        date=gcal_event.get(key, {}).get("date", None), timeZone=gcal_event.get("timeZone")
                    ),
                    "YYYY-MM-DD ZZZ",
                )
            )
            gcal_event[key] = arror_time

        gcal_event["all_day_event"] = is_all_day_event

        return cls(gcal_event)

    @classmethod
    def init_from_ics(cls, ics_event):
        event = {
            "summary": ics_event.name,
            "start": ics_event.begin,
            "end": ics_event.end,
            "iCalUID": ics_event.uid,
            "description": ics_event.description,
            "created": ics_event.created,
            "updated": ics_event.last_modified,
            "location": ics_event.location,
            "transparency": "transparent" if ics_event.transparent else "opaque",
            "status": ics_event.status,
            "all_day_event": ics_event.all_day,
            "organizer": {"email": ics_event.organizer.replace("mailto:", "")}
            if ics_event.organizer is not None
            else None,
        }

        return cls(event)

    def get_ical(self):
        ics_calendar = ics.Calendar()
        ics_event = ics.Event(
            name=self.get("summary", None),
            duration=None,
            uid=self.get("iCalUID", None),
            description=self.get("description", None),
            begin=self.get("start", None),
            end=self.get("end", None),
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

        if self["all_day_event"]:
            ics_event.make_all_day()
        ics_calendar.events.add(ics_event)
        return ics_calendar.__str__()

    def get_gcal(self):
        # reverse process of init
        gcal_event = copy.deepcopy(self)
        for key in ["created", "updated"]:
            if key in self:
                gcal_event[key] = gcal_event[key].isoformat()

        is_all_day_event = gcal_event["all_day_event"]
        for key in ["start", "end"]:
            serialized_time = {}
            if is_all_day_event:
                serialized_time["date"] = gcal_event[key].date().isoformat()
            else:
                serialized_time["dateTime"] = gcal_event[key].isoformat()
            gcal_event[key] = serialized_time

        return gcal_event
