import logging
import config as server_config
from calsync import server, clients
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)

def main():
    caldav_client = clients.CalDavClient(server_config.caldav)
    gcal_client = clients.GoogleCalendarClient(server_config.gcal)
    synchronizer = server.EventSynchronizer(
        gcal_client, server_config.gcal["calendar_id"], caldav_client, server_config.caldav["calendar_url"]
    )
    synchronizer.sync()

if __name__ == "__main__":
    main()
