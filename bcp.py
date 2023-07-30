import datetime
import logging
import os
import sys

import requests

run_timestamp = datetime.datetime.now()

FILENAME = os.path.basename(__file__)
FILEDIR = os.path.dirname(__file__)

BCP_RANKINGS_URL = "https://prod-api.bestcoastpairings.com/players"

log_dir = os.path.join(FILEDIR, "logs")
log_name = f"{FILENAME}-{run_timestamp:%Y%m%d}.log"
log_path = os.path.join(log_dir, log_name)

logging.basicConfig(format='[%(asctime)s] %(message)s',
                    filename=log_path,
                    level=logging.DEBUG)
logger = logging.getLogger()


def log(msg, print_dest="stderr"):
  logger.info(msg)

  if print_dest == "stderr":
    print(msg, file=sys.stderr)

  if print_dest == "stdout":
    print(msg)


def get_rankings_data(client_id, eventID, limit, nextKey):
  params = {
      "eventId": eventID,
      "limit": limit,
      "placings": True,
  }
  headers = {
      "client-id": client_id,
      "User-Agent": "RapidAPI/4.2.0 (Macintosh; OS X/12.4.0) GCDHTTPRequest"
  }
  if nextKey:
    params["nextKey"] = nextKey

  response = requests.get(BCP_RANKINGS_URL, params=params, headers=headers)
  data = response.json()

  return data


def get_all_rankings_data(client_id, eventID):
  log(f"scraping rankings")
  part = 1
  limit = 100
  nextKey = None
  data = get_rankings_data(client_id, eventID, limit, None)
  items = data.get("data", [])
  players = items.copy()
  if not players:
    return []
  elif len(players) >= limit:
    nextKey = data.get("nextKey")

  while isinstance(nextKey, str) and len(items) > 0:
    part += 1
    log(f"scraping rankings (part {part})")
    data = get_rankings_data(client_id, eventID, 100, nextKey)
    new_items = data.get("data", [])

    if len(new_items) == len(items) and new_items == items:
      raise Exception("infinite loop detected")

    log(f"found {len(new_items)} rankings")
    items = new_items
    players.extend(items)
    if len(items) >= limit:
      nextKey = data["nextKey"]
    else:
      nextKey = None

  log(f"found {len(players)} rankings")
  players.sort(key=lambda p: p["placing"])
  return players
