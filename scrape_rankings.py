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

FILENAME = os.path.basename(__file__)
FILEDIR = os.path.dirname(__file__)

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


def main():
  args = parser.parse_args()

  if args.rk9:
    platform = "rk9"
    players = rk9.get_rankings(args.tid)
  elif args.bcp:
    platform = "bcp"
    if not args.client_id:
      log("bcp client-id required")
      sys.exit(1)
    players = bcp.get_rankings(args.client_id, args.tid)
  elif args.battlefy:
    platform = "battlefy"
    players = battlefy.get_rankings(args.tid)
  else:
    log("invalid platform")
    sys.exit(1)

  players_path = os.path.join(args.output,
                              f"{platform}_{args.tid}_rankings.csv")
  with open(players_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["ranking", "name", "player_id", "discord"])
    for player in players:
      writer.writerow(
          [player.ranking, player.name, player.player_id, player.discord])

  log(f"output written to {players_path}")


if __name__ == "__main__":
  main()
