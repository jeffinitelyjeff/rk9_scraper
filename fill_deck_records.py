import argparse
from collections import defaultdict, Counter
import csv
import datetime
import logging
import os
import pprint
import sys

import inquirer
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


def write_csv(fname, rows, fields):
  path = os.path.join(main_dir, fname)
  with open(path, 'w') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fields)
    writer.writeheader()
    rows.sort(key=lambda x: x["Record Name"])
    for row in rows:
      writer.writerow(row)


# --- main ---

sub_decks = read_csv("submitted_decks.csv")
normalized_decks = read_csv("normalized_decks.csv")
matches = read_csv("matches.csv")
games = read_csv("games.csv")
rankings = read_csv("rankings.csv")

ranking_by_pid = {r["player_id"]: int(r["ranking"]) for r in rankings}
num_players = len(rankings)

try:
  overrides = read_csv("overrides.csv")
  override_dict = {}
  for row in overrides:
    record_name = row["Record Name"].strip().lower()
    submitted_name = row["Submitted Name"].strip().lower()
    override_dict[record_name] = submitted_name
except FileNotFoundError:
  override_dict = {}

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

  return None, []


def player_mapping():
  dict = override_dict.copy()
  mismatched_players = set()

  for player in sorted(record_players):
    if not player:
      continue

    if player in ignored_names:
      continue

    if player in override_dict:
      continue

    sub_name, guesses = sub_name_for_record_player(player)
    if sub_name is not None:
      dict[player] = sub_name
    elif guesses:
      reject = u"✗ None of these"
      question = inquirer.List(
          'chosen_guess',
          message=f"Which of these is =>[{player}]<=?",
          choices=guesses + [reject],
          carousel=True,
      )
      answers = inquirer.prompt([question])
      answer = answers["chosen_guess"]
      if answer == reject:
        log(f"player not found: {player}")
        mismatched_players.add(player)
      else:
        dict[player] = answer
        override_dict[player] = answer
    else:
      log(f"player not found: {player}")
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
  top_count = Counter()

  output_path = os.path.join(main_dir, f"deck_{record_type}.csv")
  with open(output_path, "w") as f:
    writer = csv.writer(f)
    writer.writerow([
        "round", "table", "winner", "loser", "winner_deck", "loser_deck",
        "top_10p", "top_20p", "top_30p", "top_40p", "top_50p"
    ])
    for record in records:
      round = record["round"]
      table = record["table"]
      record_winner = record["winner"].strip().lower()
      record_loser = record["loser"].strip().lower()
      winner_pid = record["winner_pid"]
      loser_pid = record["loser_pid"]

      if not record_loser:
        continue

      if record_winner in ignored_names or record_loser in ignored_names:
        ignored_records += 1
        continue

      winner_rank = ranking_by_pid.get(winner_pid, num_players + 1)
      loser_rank = ranking_by_pid.get(loser_pid, num_players + 1)

      winner_top_10p = winner_rank <= num_players * 0.1
      loser_top_10p = loser_rank <= num_players * 0.1
      both_top_10p = winner_top_10p and loser_top_10p
      if both_top_10p:
        top_count["10p"] += 1

      winner_top_20p = winner_rank <= num_players * 0.2
      loser_top_20p = loser_rank <= num_players * 0.2
      both_top_20p = winner_top_20p and loser_top_20p
      if both_top_20p:
        top_count["20p"] += 1

      winner_top_30p = winner_rank <= num_players * 0.3
      loser_top_30p = loser_rank <= num_players * 0.3
      both_top_30p = winner_top_30p and loser_top_30p
      if both_top_30p:
        top_count["30p"] += 1

      winner_top_40p = winner_rank <= num_players * 0.4
      loser_top_40p = loser_rank <= num_players * 0.4
      both_top_40p = winner_top_40p and loser_top_40p
      if both_top_40p:
        top_count["40p"] += 1

      winner_top_50p = winner_rank <= num_players * 0.5
      loser_top_50p = loser_rank <= num_players * 0.5
      both_top_50p = winner_top_50p and loser_top_50p
      if both_top_50p:
        top_count["50p"] += 1

      sub_winner = sub_player_for_record_player.get(record_winner)
      sub_loser = sub_player_for_record_player.get(record_loser)

      if sub_winner is None or sub_loser is None:
        log(f"broken {record_type} record: {record}", print_dest=None)
        broken_records += 1
        continue

      winner_deck = deck_for_sub_player[sub_winner]
      loser_deck = deck_for_sub_player[sub_loser]

      writer.writerow([
          round,
          table,
          record_winner,
          record_loser,
          winner_deck,
          loser_deck,
          "y" if both_top_10p else "",
          "y" if both_top_20p else "",
          "y" if both_top_30p else "",
          "y" if both_top_40p else "",
          "y" if both_top_50p else "",
      ])

  return broken_records, ignored_records, top_count


if override_dict:
  overrides = []
  for k, v in override_dict.items():
    overrides.append({"Record Name": k, "Submitted Name": v})
  write_csv("overrides.csv", overrides, ["Record Name", "Submitted Name"])

broken_matches, ignored_matches, top_match_counter = write_deck_records(
    "matches", matches)
broken_games, ignored_games, top_game_counter = write_deck_records(
    "games", games)

t10p_m = top_match_counter["10p"]
t20p_m = top_match_counter["20p"]
t30p_m = top_match_counter["30p"]
t40p_m = top_match_counter["40p"]
t50p_m = top_match_counter["50p"]
t10p_g = top_game_counter["10p"]
t20p_g = top_game_counter["20p"]
t30p_g = top_game_counter["30p"]
t40p_g = top_game_counter["40p"]
t50p_g = top_game_counter["50p"]

log(f"")
log(f"ignored matches: {ignored_matches} (of {len(matches)})")
log(f"ignored games: {ignored_games} (of {len(games)})")
log(f"")
log(f"mismatched decks: {num_bad_decks} (of {len(sub_decks)})")
log(f"mismatched players: {num_bad_players} (of {len(sub_decks)})")
log(f"")
log(f"broken matches: {broken_matches} (of {len(matches)})")
log(f"broken games: {broken_games} (of {len(games)})")
log(f"")
log(f"top 10/20/30/40/50% matches: {t10p_m}/{t20p_m}/{t30p_m}/{t40p_m}/{t50p_m} (of {len(matches)})"
   )
log(f"top 10/20/30/40/50% games: {t10p_g}/{t20p_g}/{t30p_g}/{t40p_g}/{t50p_g} (of {len(games)})"
   )
log(f"")
