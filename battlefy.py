import datetime
import logging
import os
import sys

import requests

from util import Match, Player

run_timestamp = datetime.datetime.now()

FILENAME = os.path.basename(__file__)
FILEDIR = os.path.dirname(__file__)

BATTLEFY_RANKINGS_URL = "https://dtmwra1jsgyb0.cloudfront.net/stages/{event_id}/latest-round-standings"
BATTLEFY_PAIRINGS_URL = "https://dtmwra1jsgyb0.cloudfront.net/stages/{event_id}/matches"

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


def get_all_rankings_data(event_id):
  response = requests.get(BATTLEFY_RANKINGS_URL.format(event_id=event_id))
  data = response.json()

  return data


def get_all_match_data(event_id, round):
  params = {"roundNumber": round}

  response = requests.get(BATTLEFY_PAIRINGS_URL.format(event_id=event_id),
                          params=params)
  data = response.json()
  return data


def player_for_player_data(player_data, ranking):
  name = player_data["team"]["name"]
  placement = ranking
  player_id = player_data["_id"]
  return Player(name, placement, player_id=player_id)


def get_rankings(eventID):
  players_data = get_all_rankings_data(eventID)

  dnf_player_data = []
  ranked_player_data = []

  for player_data in players_data:
    if player_data.get("disqualified", False):
      dnf_player_data.append(player_data)
    else:
      ranked_player_data.append(player_data)

  players = [
      player_for_player_data(p_data, i + 1)
      for i, p_data in enumerate(ranked_player_data)
  ]
  dnf_players = [
      player_for_player_data(p_data,
                             len(players) + 1) for p_data in dnf_player_data
  ]
  players.extend(dnf_players)

  return [p for p in players if p and p.is_valid()]


def match_for_match_data(match_data, prior_rounds_match_count):
  table = match_data["matchNumber"] - prior_rounds_match_count
  round = match_data["roundNumber"]

  isBye = match_data['isBye']
  p1Name = match_data["top"].get("team", {}).get("name")
  p2Name = match_data["bottom"].get("team", {}).get("name")

  if isBye:
    return None
  elif not p1Name or not p2Name:
    log(f"missing player name: {match_data}", print_dest=None)
    return None

  p1Win = match_data["top"].get("winner", False)
  p2Win = match_data["bottom"].get("winner", False)

  if p1Win:
    winner = p1Name
    loser = p2Name
    winner_wins = match_data["top"]["score"]
    loser_wins = match_data["bottom"]["score"]
    winner_pid = match_data["top"]["teamID"]
    loser_pid = match_data["bottom"]["teamID"]
  elif p2Win:
    winner = p2Name
    loser = p1Name
    winner_wins = match_data["bottom"]["score"]
    loser_wins = match_data["top"]["score"]
    winner_pid = match_data["bottom"]["teamID"]
    loser_pid = match_data["top"]["teamID"]
  else:
    return None

  return Match(winner,
               loser,
               table,
               round,
               winner_wins,
               loser_wins,
               winner_pid=winner_pid,
               loser_pid=loser_pid)


def get_all_matches(event_id):
  matches = []
  prior_rounds_match_count = 0

  for round in range(1, 20):
    new_match_data = get_all_match_data(event_id, round)
    if new_match_data:
      matches.extend([
          match_for_match_data(match, prior_rounds_match_count)
          for match in new_match_data
      ])
      prior_rounds_match_count += len(new_match_data)
    else:
      break

  log(f"done scraping")

  return [m for m in matches if m and m.is_valid_match()]
