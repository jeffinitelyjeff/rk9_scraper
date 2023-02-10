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
PAIRINGS_URL = "https://rk9.gg/pairings/{}"

run_timestamp = datetime.datetime.now()

pp = pprint.PrettyPrinter(indent=2)

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=str)
parser.add_argument('--overwrite', action='store_true')
parser.add_argument('--tid', type=str, required=True)

args = parser.parse_args()

log_dir = os.path.abspath(args.output or ".")
log_name = f"{FILENAME}-{run_timestamp:%Y%m%d}.log"
log_path = os.path.join(log_dir, log_name)

logging.basicConfig(format='[%(asctime)s] %(message)s',
                    filename=log_path, level=logging.DEBUG)
logger = logging.getLogger()


def log(msg, print_dest="stderr"):
  logger.info(msg)

  if print_dest == "stderr":
    print(msg, file=sys.stderr)

  if print_dest == "stdout":
    print(msg)


def scrape(data_url):
  log(f"scrape: {data_url}")
  response = requests.get(data_url)

  try:
    soup = bs4.BeautifulSoup(response.text, "html.parser")
    data = soup.find(id="P2")
  except AttributeError:
    return None

  return data


class Match:
  def __init__(self, winner, loser, table, round):
    self.winner = winner
    self.loser = loser
    self.table = table
    self.round = round

  def __repr__(self):
    return f"{self.winner} beat {self.loser} (round {self.round}, table {self.table})"
    # return f"Match(winner={self.winner}, loser={self.loser}, table={self.table}, round={self.round})"

  def is_valid_match(self):
    return self.winner and self.loser and self.table


def get_matches(data, round):
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


def get_all_matches(data):
  matches = []
  round = 1
  while True:
    round_matches = get_matches(data, round)
    if round_matches:
      log(f"found {len(round_matches)} matches for round {round}")
      matches.extend(round_matches)
      round += 1
    else:
      log(f"no matches found for round {round}")
      break

  return matches


def main():
  data = scrape(PAIRINGS_URL.format(args.tid))
  matches = get_all_matches(data)
  log(f"found {len(matches)} matches")

  output_path = os.path.join(args.output, f"{args.tid}_matches.csv")
  with open(output_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["round", "table", "winner", "loser"])
    for match in matches:
      writer.writerow([match.round, match.table, match.winner, match.loser])

  log(f"output written to {output_path}")


if __name__ == "__main__":
  main()
