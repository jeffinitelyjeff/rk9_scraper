import argparse
import csv
import datetime
import logging
import os
import pprint
import sys

import battlefy
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
platform_group.add_argument('--battlefy', action='store_true')
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


def main():
  if args.rk9:
    platform = "rk9"
    matches = rk9.get_all_matches(args.tid)
  elif args.bcp:
    platform = "bcp"
    if not args.client_id:
      log("bcp client-id required")
      sys.exit(1)
    matches = bcp.get_all_matches(args.client_id, args.tid)
  elif args.battlefy:
    platform = "battlefy"
    matches = battlefy.get_all_matches(args.tid)
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
