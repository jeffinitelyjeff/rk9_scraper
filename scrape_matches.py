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
RK9_PAIRINGS_URL = "https://rk9.gg/pairings/{}"
BCP_PAIRINGS_URL = "https://prod-api.bestcoastpairings.com/pairings"

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


def scrape_rk9(data_url):
  log(f"scrape: {data_url}")
  response = requests.get(data_url)

  try:
    soup = bs4.BeautifulSoup(response.text, "html.parser")
    data = soup.find(id="P2")
  except AttributeError:
    return None

  return data


class Match:

  def __init__(self,
               winner,
               loser,
               table,
               round,
               winner_wins=0,
               loser_wins=0,
               winner_pid=None,
               loser_pid=None):
    self.winner = winner
    self.loser = loser
    self.table = table
    self.round = round
    self.winner_pid = winner_pid
    self.loser_pid = loser_pid
    self.games = self.make_games(winner_wins, loser_wins)

  def __repr__(self):
    return f"{self.winner} beat {self.loser} (round {self.round}, table {self.table})"
    # return f"Match(winner={self.winner}, loser={self.loser}, table={self.table}, round={self.round})"

  def is_valid_match(self):
    return self.winner and self.loser and self.table

  def make_games(self, winner_wins, loser_wins):
    l = []

    if winner_wins == '':
      winner_wins = 0

    if loser_wins == '':
      loser_wins = 0

    for i in range(int(winner_wins) or 0):
      l.append(
          Game(self.winner, self.loser, self.table, self.round, self.winner_pid,
               self.loser_pid))

    for i in range(int(loser_wins) or 0):
      l.append(
          Game(self.loser, self.winner, self.table, self.round, self.loser_pid,
               self.winner_pid))

    return l


class Game:

  def __init__(self,
               winner,
               loser,
               table,
               round,
               winner_pid=None,
               loser_pid=None):
    self.winner = winner
    self.loser = loser
    self.table = table
    self.round = round
    self.winner_pid = winner_pid
    self.loser_pid = loser_pid

  def __repr__(self):
    return f"{self.winner} beat {self.loser} (round {self.round}, table {self.table}, game {self.match_game})"


def get_matches_rk9(data, round):
  round_div = data.find(id=f"P2R{round}")
  if not round_div:
    return None

  matches = []
  match_divs = round_div.find_all("div", class_="match")
  for match_div in match_divs:
    winner, loser, table = None, None, None

    try:
      winner = match_div.find("div", class_="winner").find(
          "span", class_="name").get_text(" ", strip=True)
    except AttributeError:
      log(f"failed to parse winner", print_dest=None)

    try:
      loser = match_div.find("div", class_="loser").find(
          "span", class_="name").get_text(" ", strip=True)
    except AttributeError:
      log(f"failed to parse loser", print_dest=None)

    try:
      table = match_div.find("span", class_="tablenumber").text
    except AttributeError:
      log(f"failed to parse table", print_dest=None)

    match = Match(winner, loser, table, round)
    if match.is_valid_match():
      matches.append(match)
    else:
      log(f"missing data for match: {match}, {match_div}", print_dest=None)

  return matches


def get_all_matches_rk9(tid):
  data = scrape_rk9(RK9_PAIRINGS_URL.format(tid))
  matches = []
  round = 1
  while True:
    round_matches = get_matches_rk9(data, round)
    if round_matches:
      log(f"found {len(round_matches)} matches for round {round}")
      matches.extend(round_matches)
      round += 1
    else:
      log(f"no matches found for round {round}")
      break

  return matches


def get_bcp_data(client_id, tid, round, nextKey):
  params = {
      "eventId": tid,
      "round": round,
      "limit": 100,
      "pairingType": "Pairing"
  }
  headers = {
      "client-id": client_id,
      "User-Agent": "RapidAPI/4.2.0 (Macintosh; OS X/12.4.0) GCDHTTPRequest"
  }
  if nextKey:
    params["nextKey"] = nextKey

  response = requests.get(BCP_PAIRINGS_URL, params=params, headers=headers)
  data = response.json()

  return data


def get_round_match_data_bcp(client_id, tid, round):
  log(f"scraping round {round}")
  part = 1
  data = get_bcp_data(client_id, tid, round, None)
  matches = data.get("data", [])
  nextKey = data.get("nextKey")
  if not matches or not nextKey:
    return []

  while isinstance(nextKey, str):
    part += 1
    log(f"scraping round {round} (part {part})")
    data = get_bcp_data(client_id, tid, round, nextKey)
    matches.extend(data["data"])
    nextKey = data["nextKey"]

  log(f"found {len(matches)} matches for round {round}")
  matches.sort(key=lambda m: m["table"])
  return matches


def match_for_bcp_match_data(match_data):
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
  return Match(winner, loser, table, round, winner_wins, loser_wins, winner_pid,
               loser_pid)


def get_all_matches_bcp(client_id, tid):
  match_data = []

  for round in range(1, 20):
    new_matches = get_round_match_data_bcp(client_id, tid, round)
    if new_matches:
      match_data.extend(new_matches)
    else:
      break

  log(f"done scraping")

  matches = [match_for_bcp_match_data(match) for match in match_data]
  return [m for m in matches if m and m.is_valid_match()]


def main():
  platform = "rk9" if args.rk9 else "bcp"

  if args.rk9:
    matches = get_all_matches_rk9(args.tid)
  elif args.bcp:
    if not args.client_id:
      log("bcp client-id required")
      sys.exit(1)
    matches = get_all_matches_bcp(args.client_id, args.tid)
  else:
    log("invalid platform")
    sys.exit(1)

  games = sum([len(m.games) for m in matches])
  log(f"found {len(matches)} matches ({games} games)")

  match_path = os.path.join(args.output, f"{platform}_{args.tid}_matches.csv")
  with open(match_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(
        ["round", "table", "winner", "loser", "winner_pid", "loser_pid"])
    for match in matches:
      writer.writerow([
          match.round, match.table, match.winner, match.loser, match.winner_pid,
          match.loser_pid
      ])

  log(f"output written to {match_path}")

  game_path = os.path.join(args.output, f"{platform}_{args.tid}_games.csv")
  with open(game_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(
        ["round", "table", "winner", "loser", "winner_pid", "loser_pid"])
    for match in matches:
      for game in match.games:
        writer.writerow([
            game.round, game.table, game.winner, game.loser, game.winner_pid,
            game.loser_pid
        ])

  log(f"output written to {game_path}")


if __name__ == "__main__":
  main()
