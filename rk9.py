import datetime
import logging
import os
import re
import sys

import bs4
import requests

from util import Match, Player

run_timestamp = datetime.datetime.now()

# TODO: fix these paths -- since they're global, they get set once by bcp.py
# and then all the logs for other modules get written to bcp.py

FILENAME = os.path.basename(__file__)
FILEDIR = os.path.dirname(__file__)

RK9_PAIRINGS_URL = "https://rk9.gg/pairings/{}"

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


def get_all_matches(event_id):
  data = scrape(RK9_PAIRINGS_URL.format(event_id))
  matches = []
  round = 1
  while True:
    round_matches = get_round_matches(data, round)
    if round_matches:
      log(f"found {len(round_matches)} matches for round {round}")
      matches.extend(round_matches)
      round += 1
    else:
      log(f"no matches found for round {round}")
      break

  return matches


def scrape(data_url):
  log(f"scrape: {data_url}")
  response = requests.get(data_url)

  mb = len(response.content) / 1024 / 1024
  log(f"got {mb:.2f} MB response")

  try:
    soup = bs4.BeautifulSoup(response.text, "html.parser")
    data = soup.find(id="P2")
  except AttributeError:
    return None

  log(f"soup parsed html")

  return data


def get_round_matches(data, round):
  round_div = data.find(id=f"P2R{round}")
  if not round_div:
    return None

  matches = []
  match_divs = round_div.find_all("div", class_="match")
  for match_div in match_divs:
    winner = None
    loser = None
    table = None
    winner_discord = None
    loser_discord = None

    discord_re = re.compile(r'"(.*)" (.*)')

    try:
      winner = match_div.find("div", class_="winner").find(
          "span", class_="name").get_text(" ", strip=True)
      winner_discord_match = discord_re.match(winner)
      if winner_discord_match:
        winner_discord = winner_discord_match.group(1)
        winner = winner_discord_match.group(2)
    except AttributeError:
      log(f"failed to parse winner", print_dest=None)

    try:
      loser = match_div.find("div", class_="loser").find(
          "span", class_="name").get_text(" ", strip=True)
      loser_re_match = discord_re.match(loser)
      if loser_re_match:
        loser_discord = loser_re_match.group(1)
        loser = loser_re_match.group(2)
    except AttributeError:
      log(f"failed to parse loser", print_dest=None)

    try:
      table = match_div.find("span", class_="tablenumber").text
    except AttributeError:
      log(f"failed to parse table", print_dest=None)

    match = Match(winner,
                  loser,
                  table,
                  round,
                  winner_discord=winner_discord,
                  loser_discord=loser_discord)
    if match.is_valid_match():
      matches.append(match)
    else:
      log(f"missing data for match: {match}, {match_div}", print_dest=None)

  return matches


def get_rankings(event_id):
  data = scrape(RK9_PAIRINGS_URL.format(event_id))
  rankings_div = data.find(id="P2-standings")
  if not rankings_div:
    return None

  discord_re = re.compile(r'(\d+). "(.*)" (.*)')
  nodiscord_re = re.compile(r'(\d+). (.*)')
  rankings = []
  for row in rankings_div.stripped_strings:
    discord_match = discord_re.match(row)
    if discord_match:
      ranking, discord, name = discord_match.groups()
      player = Player(name, ranking, discord=discord)
      if player.is_valid():
        rankings.append(player)
        continue

    nodiscord_match = nodiscord_re.match(row)
    if nodiscord_match:
      ranking, name = nodiscord_match.groups()
      player = Player(name, ranking)
      if player.is_valid():
        rankings.append(player)
        continue

    log(f"failed to parse ranking row: {row}")

  return rankings
