import logging
import config as server_config
from calsync import server
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

def main():
    caldav_client = server.CalDavClient(server_config.caldav)
    gcal_client = server.GoogleCalendarClient(server_config.gcal)
    synchronizer = server.EventSynchronizer(
        gcal_client, server_config.gcal["calendar_id"], caldav_client, server_config.caldav["calendar_url"]
    )
    import IPython
    IPython.embed()
    # synchronizer.sync()

if __name__ == "__main__":
    main()
