import argparse
import csv
import datetime
import logging
import os
import pprint
import sys

import bcp
import rk9

from util import Match, Game

FILENAME = os.path.basename(__file__)

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
  return Match(winner,
               loser,
               table,
               round,
               winner_wins,
               loser_wins,
               winner_pid=winner_pid,
               loser_pid=loser_pid)


def get_all_matches_bcp(client_id, event_id):
  match_data = []

  for round in range(1, 20):
    new_matches = bcp.get_all_match_data(client_id, event_id, round)
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
    matches = rk9.get_all_matches(args.tid)
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
    writer.writerow([
        "round", "table", "winner", "loser", "winner_pid", "loser_pid",
        "winner_discord", "loser_discord"
    ])
    for match in matches:
      writer.writerow([
          match.round, match.table, match.winner, match.loser, match.winner_pid,
          match.loser_pid, match.winner_discord, match.loser_discord
      ])

  log(f"output written to {match_path}")

  has_games = any([len(m.games) > 0 for m in matches])
  if has_games:
    game_path = os.path.join(args.output, f"{platform}_{args.tid}_games.csv")
    with open(game_path, 'w', newline='') as f:
      writer = csv.writer(f)
      writer.writerow([
          "round", "table", "winner", "loser", "winner_pid", "loser_pid",
          "winner_discord", "loser_discord"
      ])
      for match in matches:
        for game in match.games:
          writer.writerow([
              game.round, game.table, game.winner, game.loser, game.winner_pid,
              game.loser_pid, game.winner_discord, game.loser_discord
          ])

    log(f"output written to {game_path}")


if __name__ == "__main__":
  main()
