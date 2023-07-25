import argparse
from collections import defaultdict, Counter
import csv
import datetime
import logging
import os
import pprint
import sys

import nicknames

FILENAME = os.path.basename(__file__)

run_timestamp = datetime.datetime.now()

pp = pprint.PrettyPrinter(indent=2)

parser = argparse.ArgumentParser()
parser.add_argument('--dir', type=str, required=True)

args = parser.parse_args()

main_dir = os.path.abspath(args.dir or ".")
log_name = f"{FILENAME}-{run_timestamp:%Y%m%d}.log"
log_path = os.path.join(main_dir, log_name)

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


def read_csv(fname):
  path = os.path.join(main_dir, fname)
  with open(path, newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    return list(reader)


# --- main ---

sub_decks = read_csv("submitted_decks.csv")
normalized_decks = read_csv("normalized_decks.csv")
matches = read_csv("matches.csv")
games = read_csv("games.csv")

try:
  ignore_names = read_csv("ignored_names.csv")
  ignored_names = set(
      [row["Record Name"].strip().lower() for row in ignore_names])
except FileNotFoundError:
  ignored_names = set()

sub_player_counts = Counter()
sub_players_by_first_name = defaultdict(set)
sub_players_by_last_name = defaultdict(set)
for player in sub_decks:
  full_name = player["Player Name"].strip().lower()
  first_name = full_name.split()[0]
  last_name = full_name.split()[-1]
  sub_player_counts[full_name] += 1
  sub_players_by_first_name[first_name].add(full_name)
  sub_players_by_last_name[last_name].add(full_name)

for sub_player, count in sub_player_counts.items():
  if count > 1 and sub_player not in ignored_names:
    log(f"FATAL error: multiple submissions for {sub_player}")
    sys.exit(1)

sub_players = set(sub_player_counts.keys())

record_players = set()
for match in matches:
  record_players.add(match["winner"].strip().lower())
  record_players.add(match["loser"].strip().lower())


def deck_mapping():
  canon_decks_by_sub = {}

  for deck in normalized_decks:
    submitted = deck["Submitted Deck Type"]
    canonical_name = deck["Canonical Deck Type"]
    canon_decks_by_sub[submitted] = canonical_name

  deck_dict = {}
  mismatched_decks = set()

  for player in sub_decks:
    sub_player_name = player["Player Name"].strip().lower()
    sub_deck = player["Deck Type"]
    canon_deck = canon_decks_by_sub.get(sub_deck)
    if canon_deck is None:
      log(f"deck not found: {sub_deck}")
      mismatched_decks.add(sub_deck)
    else:
      deck_dict[sub_player_name] = canon_deck

  if len(mismatched_decks) > 0:
    output_path = os.path.join(main_dir, "mismatched_decks.txt")
    with open(output_path, "w") as f:
      f.write("\n".join(sorted(mismatched_decks)))

  return deck_dict, len(mismatched_decks)


def sub_name_for_record_player(player):
  if not player:
    return None, []

  if player in sub_players:
    return player, []

  record_first = player.split()[0]
  record_last = player.split()[-1]

  same_first = sub_players_by_first_name.get(record_first, set())
  same_last = sub_players_by_last_name.get(record_last, set())
  same_first_and_last = sorted(same_first.intersection(same_last))

  if len(same_first_and_last) == 1:
    guess = same_first_and_last[0]
    if guess in record_players:
      # if someone else submitted a deck with the same name
      return None, [guess]
    else:
      return guess, []

  same_first_or_last = sorted(same_first.union(same_last))

  if len(same_first_or_last) > 0:
    return None, same_first_or_last

  # FIXME: let user pick a guess
  return None, []


def player_mapping():
  dict = {}
  mismatched_players = set()

  for player in sorted(record_players):
    sub_name, guesses = sub_name_for_record_player(player)
    if sub_name is not None:
      dict[player] = sub_name
    else:
      guesses_f = f"(guesses: {', '.join(guesses)})" if len(guesses) > 0 else ""
      log(f"player not found: {player} {guesses_f}")
      mismatched_players.add(player)

  if len(mismatched_players) > 0:
    output_path = os.path.join(main_dir, "mismatched_players.txt")
    with open(output_path, "w") as f:
      f.write("\n".join(sorted(mismatched_players)))

  return dict, len(mismatched_players)


deck_for_sub_player, num_bad_decks = deck_mapping()
sub_player_for_record_player, num_bad_players = player_mapping()


def write_deck_records(record_type, records):
  broken_records = 0
  ignored_records = 0

  output_path = os.path.join(main_dir, f"deck_{record_type}.csv")
  with open(output_path, "w") as f:
    writer = csv.writer(f)
    writer.writerow(
        ["round", "table", "winner", "loser", "winner_deck", "loser_deck"])
    for record in records:
      round = record["round"]
      table = record["table"]
      winner = record["winner"].strip().lower()
      loser = record["loser"].strip().lower()

      if winner in ignored_names or loser in ignored_names:
        ignored_records += 1
        continue

      submitted_winner = sub_player_for_record_player.get(winner)
      submitted_loser = sub_player_for_record_player.get(loser)

      if submitted_winner is None or submitted_loser is None:
        broken_records += 1
        continue

      winner_deck = deck_for_sub_player[submitted_winner]
      loser_deck = deck_for_sub_player[submitted_loser]

      writer.writerow([round, table, winner, loser, winner_deck, loser_deck])

  return broken_records, ignored_records


broken_matches, ignored_matches = write_deck_records("matches", matches)
broken_games, ignored_games = write_deck_records("games", games)

log(f"mismatched decks: {num_bad_decks} (of {len(sub_decks)})")
log(f"mismatched players: {num_bad_players} (of {len(sub_decks)})")
log(f"broken matches: {broken_matches} (of {len(matches)})")
log(f"broken games: {broken_games} (of {len(games)})")
log(f"ignored matches: {ignored_matches} (of {len(matches)})")
log(f"ignored games: {ignored_games} (of {len(games)})")