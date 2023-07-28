import argparse
import csv
import datetime
import logging
import os
import pprint
import sys

import bs4
import requests

FILENAME = os.path.basename(__file__)
BCP_RANKINGS_URL = "https://prod-api.bestcoastpairings.com/players"

run_timestamp = datetime.datetime.now()

pp = pprint.PrettyPrinter(indent=2)

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=str)
parser.add_argument('--overwrite', action='store_true')
parser.add_argument('--tid', type=str, required=True)
platform_group = parser.add_mutually_exclusive_group(required=True)
platform_group.add_argument('--rk9', action='store_true')
platform_group.add_argument('--bcp', action='store_true')
parser.add_argument('--client-id', type=str)
parser.add_argument('--games', action='store_true')

args = parser.parse_args()

log_dir = os.path.abspath(args.output or ".")
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


class Player:

  def __init__(self, name, ranking, player_id):
    self.name = name
    self.ranking = ranking
    self.player_id = player_id

  def __repr__(self):
    return f"{self.name} placement: {self.ranking}"

  def is_valid(self):
    return self.name and self.ranking and self.player_id


def get_bcp_rankings_data(client_id, eventID, limit, nextKey):
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


def get_all_bcp_rankings_data(client_id, eventID):
  log(f"scraping rankings")
  part = 1
  limit = 100
  nextKey = None
  data = get_bcp_rankings_data(client_id, eventID, limit, None)
  items = data.get("data", [])
  players = items.copy()
  if not players:
    return []
  elif len(players) >= limit:
    nextKey = data.get("nextKey")

  while isinstance(nextKey, str) and len(items) > 0:
    part += 1
    log(f"scraping rankings (part {part})")
    data = get_bcp_rankings_data(client_id, eventID, 100, nextKey)
    items = data.get("data", [])
    players.extend(items)
    if len(items) >= limit:
      nextKey = data["nextKey"]

  log(f"found {len(players)} rankings")
  players.sort(key=lambda p: p["placing"])
  return players


def player_for_bcp_player_data(player_data):
  first_name = player_data["firstName"]
  last_name = player_data["lastName"]
  name = f"{first_name} {last_name}"
  placement = player_data["placing"]
  player_id = player_data["id"]
  player = Player(name, placement, player_id)
  if player.is_valid():
    return player
  else:
    return None


def get_all_bcp_rankings(client_id, eventID):
  players_data = get_all_bcp_rankings_data(client_id, eventID)
  players = [player_for_bcp_player_data(p_data) for p_data in players_data]
  return [p for p in players if p]


def main():
  platform = "rk9" if args.rk9 else "bcp"

  if args.rk9:
    raise NotImplementedError
  elif args.bcp:
    if not args.client_id:
      log("bcp client-id required")
      sys.exit(1)
    players = get_all_bcp_rankings(args.client_id, args.tid)
  else:
    log("invalid platform")
    sys.exit(1)

  players_path = os.path.join(args.output,
                              f"{platform}_{args.tid}_rankings.csv")
  with open(players_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["ranking", "name", "player_id"])
    for player in players:
      writer.writerow([player.ranking, player.name, player.player_id])

  log(f"output written to {players_path}")


if __name__ == "__main__":
  main()
