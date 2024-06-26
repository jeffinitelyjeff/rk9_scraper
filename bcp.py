import datetime
import logging
import os
import sys

import requests

from util import Match, Player

run_timestamp = datetime.datetime.now()

FILENAME = os.path.basename(__file__)
FILEDIR = os.path.dirname(__file__)

BCP_RANKINGS_URL = "https://prod-api.bestcoastpairings.com/players"
BCP_PAIRINGS_URL = "https://prod-api.bestcoastpairings.com/pairings"

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


def get_rankings_data(client_id, event_id, limit, next_key):
  params = {
      "eventId": event_id,
      "limit": limit,
      "placings": True,
  }
  headers = {
      "client-id": client_id,
      "User-Agent": "RapidAPI/4.2.0 (Macintosh; OS X/12.4.0) GCDHTTPRequest"
  }
  if next_key:
    params["nextKey"] = next_key

  response = requests.get(BCP_RANKINGS_URL, params=params, headers=headers)
  data = response.json()

  return data


def get_match_data(client_id, event_id, round, limit, next_key):
  params = {
      "eventId": event_id,
      "round": round,
      "limit": limit,
      "pairingType": "Pairing"
  }
  headers = {
      "client-id": client_id,
      "User-Agent": "RapidAPI/4.2.0 (Macintosh; OS X/12.4.0) GCDHTTPRequest"
  }
  if next_key:
    params["nextKey"] = next_key

  response = requests.get(BCP_PAIRINGS_URL, params=params, headers=headers)
  data = response.json()

  return data


def get_data(type, client_id, event_id, limit, round=None, next_key=None):
  if type == "rankings":
    return get_rankings_data(client_id=client_id,
                             event_id=event_id,
                             limit=limit,
                             next_key=next_key)
  elif type == "matches":
    return get_match_data(client_id=client_id,
                          event_id=event_id,
                          round=round,
                          limit=limit,
                          next_key=next_key)
  else:
    raise Exception(f"unknown type: {type}")


def get_paginated_data(type, client_id, event_id, round=None):
  """
  Valid types: 
    - "rankings"
    - "matches"
  """

  if round:
    log(f"=== scraping {type} for round {round}")
  else:
    log(f"=== scraping {type}")

  part = 1
  limit = 100
  next_key = None
  last_items = []

  log(f"  - scraping pt1...")
  data = get_data(type, client_id, event_id, limit, round=round)

  items = data.get("data", [])
  log(f"  > found {len(items)} {type}")

  if not items:
    return []

  if len(items) >= limit:
    next_key = data.get("nextKey")

  while isinstance(next_key, str):
    part += 1

    log(f"  - scraping pt{part}...")
    data = get_data(type,
                    client_id,
                    event_id,
                    limit,
                    round=round,
                    next_key=next_key)

    new_items = data.get("data", [])
    log(f"  > found {len(new_items)} {type}")

    if not new_items:
      break

    if len(new_items) == len(last_items) and new_items == last_items:
      raise Exception("infinite loop detected")

    items.extend(new_items)

    if len(new_items) >= limit:
      new_next_key = data.get("nextKey")
      if new_next_key == next_key:
        raise Exception("infinite loop detected")
      else:
        next_key = new_next_key
    else:
      next_key = None

    last_items = new_items

  if round:
    log(f"--- found {len(items)} {type} for round {round}")
  else:
    log(f"--- found {len(items)} {type}")

  if type == "rankings":
    items.sort(key=lambda p: p["placing"])
  elif type == "matches":
    items.sort(key=lambda m: m["table"])
  else:
    raise Exception(f"unknown type: {type}")

  return items


def get_all_rankings_data(client_id, eventID):
  return get_paginated_data("rankings", client_id, eventID)


def get_all_match_data(client_id, eventID, round):
  return get_paginated_data("matches", client_id, eventID, round=round)


def player_for_player_data(player_data):
  first_name = player_data["firstName"]
  last_name = player_data["lastName"]
  name = f"{first_name} {last_name}"
  placement = player_data["placing"]
  player_id = player_data["id"]
  player = Player(name, placement, player_id=player_id)
  if player.is_valid():
    return player
  else:
    return None


def get_rankings(client_id, eventID):
  players_data = get_all_rankings_data(client_id, eventID)
  players = [player_for_player_data(p_data) for p_data in players_data]
  return [p for p in players if p]


def match_for_match_data(match_data):
  table = match_data["table"]
  round = match_data["round"]
  metadata = match_data.get("metaData")
  if not metadata:
    log(f"no metadata for match: {match_data}")
    return None
  p1Name = "{} {}".format(metadata["p1-firstName"], metadata["p1-lastName"])
  p2Name = "{} {}".format(metadata["p2-firstName"], metadata["p2-lastName"])
  p1Win = int(metadata["p1-marginOfVictory"]) > 0
  if p1Win:
    winner = p1Name
    loser = p2Name
    winner_wins = metadata["p1-gamePoints"]
    loser_wins = metadata["p2-gamePoints"]
    winner_pid = match_data.get("player1Id")
    loser_pid = match_data.get("player2Id")
  else:
    winner = p2Name
    loser = p1Name
    winner_wins = metadata["p2-gamePoints"]
    loser_wins = metadata["p1-gamePoints"]
    winner_pid = match_data.get("player2Id")
    loser_pid = match_data.get("player1Id")
  return Match(winner,
               loser,
               table,
               round,
               winner_wins,
               loser_wins,
               winner_pid=winner_pid,
               loser_pid=loser_pid)


def get_all_matches(client_id, event_id):
  match_data = []

  for round in range(1, 20):
    new_matches = get_all_match_data(client_id, event_id, round)
    if new_matches:
      match_data.extend(new_matches)
    else:
      break

  log(f"done scraping")

  matches = [match_for_match_data(match) for match in match_data]
  return [m for m in matches if m and m.is_valid_match()]
