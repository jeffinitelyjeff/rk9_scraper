import argparse
from collections import defaultdict, Counter, namedtuple
import csv
import datetime
import logging
import os
import pprint
import sys

import inquirer

FILENAME = os.path.basename(__file__)

run_timestamp = datetime.datetime.now()

pp = pprint.PrettyPrinter(indent=2)

parser = argparse.ArgumentParser()
parser.add_argument('--dir', type=str, required=True)

args = parser.parse_args()

main_dir = os.path.abspath(args.dir or ".")
log_dir = os.path.join(main_dir, "logs")

try:
  os.mkdir(log_dir)
except FileExistsError:
  pass

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
    rows.sort(key=lambda x: x["Pairing Name"])
    for row in rows:
      writer.writerow(row)


# --- main ---

sub_decks = read_csv("submitted_decks.csv")
matches = read_csv("matches.csv")
try:
  games = read_csv("games.csv")
except FileNotFoundError:
  games = []
try:
  rankings = read_csv("rankings.csv")
except FileNotFoundError:
  rankings = []

ranking_by_pid = {r["player_id"]: int(r["ranking"]) for r in rankings}
ranking_by_discord = {r["discord"]: int(r["ranking"]) for r in rankings}
num_players = len(rankings)

# this would seem like the logical solution, but the whole reason to start
# using pid is that ranking names didn't match pairing names
# record_name_by_pid = {r["player_id"]: r["name"] for r in rankings}
record_name_by_pid = {}

try:
  overrides = read_csv("overrides.csv")
  override_dict = {}
  for row in overrides:
    record_name = row["Pairing Name"].strip().lower()
    submitted_name = row["Form Name"].strip().lower()
    override_dict[record_name] = submitted_name
except FileNotFoundError:
  override_dict = {}

try:
  ignore_names = read_csv("ignored_names.csv")
  ignored_names = set(
      [row["Pairing Name"].strip().lower() for row in ignore_names])
except FileNotFoundError:
  ignored_names = set()

sub_player_counts = Counter()
sub_players_by_word = defaultdict(set)
for player in sub_decks:
  full_name = player["Player Name"].strip().lower()
  words = full_name.split()
  for word in words:
    sub_players_by_word[word].add(full_name)
  sub_player_counts[full_name] += 1

for sub_player, count in sub_player_counts.items():
  if count > 1 and sub_player not in ignored_names:
    log(f"FATAL error: multiple submissions for {sub_player}")
    sys.exit(1)

sub_players = set(sub_player_counts.keys())

PlayerRecord = namedtuple('PlayerRecord', ['name', 'ranking'])

record_players = set()
record_player_names = set()
for ranking in rankings:
  name = ranking["name"].strip().lower()
  rank = int(ranking["ranking"])
  record_players.add(PlayerRecord(name, rank))
  record_player_names.add(name)


def get_count_tags_from_sub_deck_row(row):
  tags = []
  i = 1
  while True:
    tag = row.get(f"Count Tag {i}")
    if not tag:
      break
    tags.append(tag)
    i += 1
  return tags


def deck_mapping():

  try:
    # this path is deprecated
    normalized_decks = read_csv("normalized_decks.csv")
    canon_decks_by_sub_deck = {}
    for deck in normalized_decks:
      submitted = deck["Submitted Deck Type"]
      canonical_name = deck["Canonical Deck Type"]
      canon_decks_by_sub_deck[submitted] = canonical_name
  except FileNotFoundError:
    canon_decks_by_sub_deck = {}

  deck_dict = {}
  mismatched_decks = set()

  for player in sub_decks:
    sub_player_name = player["Player Name"].strip().lower()
    sub_deck_1 = player["Deck Type"]
    sub_deck_2 = player["Deck Type 2"]

    sub_tags = get_count_tags_from_sub_deck_row(player)

    if canon_decks_by_sub_deck:
      canon_deck_1 = canon_decks_by_sub_deck.get(sub_deck_1)
      canon_deck_2 = canon_decks_by_sub_deck.get(sub_deck_2)
    else:
      canon_deck_1 = sub_deck_1
      canon_deck_2 = sub_deck_2

    if canon_deck_1 is None:
      log(f"deck not found: {sub_deck_1}")
      mismatched_decks.add(sub_deck_1)
    else:
      deck_labels = [canon_deck_1, canon_deck_2, *sub_tags]
      deck_dict[sub_player_name] = [l for l in deck_labels if l]

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

  share_word = set()
  words = player.split()
  for word in words:
    share_word.update(sub_players_by_word.get(word, set()))

  share_word = sorted(share_word)
  guesses = [
      f'* {g}' if g in record_player_names else f'- {g}' for g in share_word
  ]

  # record_first = player.split()[0]
  # record_last = player.split()[-1]

  # same_first = sub_players_by_first_name.get(record_first, set())
  # same_last = sub_players_by_last_name.get(record_last, set())
  # same_first_and_last = sorted(same_first.intersection(same_last))

  # if len(same_first_and_last) == 1:
  #   guess = same_first_and_last[0]
  #   if guess in record_players:
  #     # if someone else submitted a deck with the same name
  #     return None, [guess]
  #   else:
  #     return guess, []

  # same_first_or_last = sorted(same_first.union(same_last))

  # guesses = [f'{g} *' if g in record_players else g for g in same_first_or_last]

  if len(guesses) > 0:
    return None, guesses

  return None, []


def player_mapping():
  dict = override_dict.copy()
  mismatched_players = {}

  reject_following = False
  for rec_player in sorted(x.name for x in record_players):
    rec_name = rec_player.name
    rec_rank = rec_player.ranking

    if not rec_name:
      continue

    if rec_name in ignored_names:
      continue

    if rec_name in override_dict:
      continue

    sub_name, guesses = sub_name_for_record_player(rec_name)
    if sub_name is not None:
      dict[rec_name] = sub_name
    elif guesses:
      if reject_following:
        mismatched_players[rec_name] = rec_rank
        continue

      reject = u"✗ None of these"
      reject_all = u"✗ None of these (for all remaining players)"
      question = inquirer.List(
          'chosen_guess',
          message=f"vv FORM NAMES vv --- PAIRING NAME: =>[ {rec_name} ]<=",
          choices=guesses + [reject, reject_all],
          carousel=True,
      )
      answers = inquirer.prompt([question])
      answer = answers["chosen_guess"].strip("*- ")
      if answer == reject:
        log(f"player not found: {rec_name}")
        mismatched_players[rec_name] = rec_rank
      elif answer == reject_all:
        reject_following = True
        mismatched_players[rec_name] = rec_rank
      else:
        dict[rec_name] = answer
        override_dict[rec_name] = answer
    else:
      log(f"player not found: {rec_name}")
      mismatched_players[rec_name] = rec_rank

  mismatched_path = os.path.join(main_dir, "mismatched_players.csv")
  if len(mismatched_players) > 0:
    with open(mismatched_path, "w") as f:
      writer = csv.writer(f)
      writer.writerow(["form name", "ranking"])
      for name, rank in sorted(mismatched_players.items()):
        writer.writerow([name, rank])
  else:
    try:
      os.remove(mismatched_path)
    except FileNotFoundError:
      pass

  return dict, len(mismatched_players)


decks_for_sub_player, num_bad_decks = deck_mapping()
sub_player_for_record_player, num_bad_players = player_mapping()


def write_deck_rankings():
  broken_rankings = 0
  ignored_rankings = 0

  if len(rankings) == 0:
    return broken_rankings, ignored_rankings

  output_path = os.path.join(main_dir, f"deck_rankings.csv")
  with open(output_path, "w") as f:
    writer = csv.writer(f)
    writer.writerow(
        ["ranking", "deck", "pairing name", "form name", "pid", "discord"])

    for ranking_row in rankings:
      ranking = int(ranking_row["ranking"])
      ranking_name = ranking_row["name"].strip().lower()
      pid = ranking_row["player_id"]
      discord = ranking_row["discord"]

      if pid:
        try:
          record_name = record_name_by_pid[pid]
        except KeyError:
          log(f"ranking for {ranking_name} ignored b/c they have no records")
          continue
      else:
        record_name = ranking_name

      sub_name = sub_player_for_record_player.get(record_name)

      if sub_name is None:
        log(f"broken ranking: {record_name}", print_dest=None)
        broken_rankings += 1
        continue

      decks = decks_for_sub_player[sub_name]

      for deck in decks:
        writer.writerow([ranking, deck, record_name, sub_name, pid, discord])

  return broken_rankings, ignored_rankings


def write_deck_records(record_type, records):
  broken_records = 0
  ignored_records = 0
  top_count = Counter()
  core_count = 0
  extra_count = 0

  output_path = os.path.join(main_dir, f"deck_{record_type}.csv")
  with open(output_path, "w") as f:
    writer = csv.writer(f)
    writer.writerow([
        "round", "table", "winner", "loser", "winner_deck", "loser_deck",
        "core_record", "top_10p", "top_20p", "top_30p", "top_40p", "top_50p"
    ])
    for record in records:
      round = record["round"]
      table = record["table"]
      record_winner = record["winner"].strip().lower()
      record_loser = record["loser"].strip().lower()
      winner_pid = record["winner_pid"]
      loser_pid = record["loser_pid"]
      winner_discord = record["winner_discord"]
      loser_discord = record["loser_discord"]

      record_name_by_pid[winner_pid] = record_winner
      record_name_by_pid[loser_pid] = record_loser

      if not record_loser:
        continue

      if record_winner in ignored_names or record_loser in ignored_names:
        ignored_records += 1
        continue

      max_rank = num_players + 1

      winner_rank = num_players + 1
      if winner_pid:
        winner_rank = ranking_by_pid.get(winner_pid, max_rank)
      elif winner_discord:
        winner_rank = ranking_by_discord.get(winner_discord, max_rank)

      loser_rank = num_players + 1
      if loser_pid:
        loser_rank = ranking_by_pid.get(loser_pid, max_rank)
      elif loser_discord:
        loser_rank = ranking_by_discord.get(loser_discord, max_rank)

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

      winner_decks = decks_for_sub_player[sub_winner]
      loser_decks = decks_for_sub_player[sub_loser]

      winner_core_deck = winner_decks[0]
      loser_core_deck = loser_decks[0]

      deck_pairs = []

      # winner, loser, is_core_record
      deck_pairs.append((winner_core_deck, loser_core_deck, True))

      for winner_deck in winner_decks:
        for loser_deck in loser_decks:
          if winner_deck == winner_core_deck and loser_deck == loser_core_deck:
            continue
          deck_pairs.append((winner_deck, loser_deck, False))

      for (winner_deck, loser_deck, is_core_record) in deck_pairs:
        if is_core_record:
          core_count += 1
        else:
          extra_count += 1

        writer.writerow([
            round,
            table,
            record_winner,
            record_loser,
            winner_deck,
            loser_deck,
            "y" if is_core_record else "",
            "y" if both_top_10p else "",
            "y" if both_top_20p else "",
            "y" if both_top_30p else "",
            "y" if both_top_40p else "",
            "y" if both_top_50p else "",
        ])

  return broken_records, ignored_records, top_count, core_count, extra_count


if override_dict:
  overrides = []
  for k, v in override_dict.items():
    overrides.append({"Pairing Name": k, "Form Name": v})
  write_csv("overrides.csv", overrides, ["Pairing Name", "Form Name"])

(broken_matches, ignored_matches, top_match_counter, core_matches,
 extra_matches) = write_deck_records("matches", matches)

(broken_rankings, ignored_rankings) = write_deck_rankings()

t10p_m = top_match_counter["10p"]
t20p_m = top_match_counter["20p"]
t30p_m = top_match_counter["30p"]
t40p_m = top_match_counter["40p"]
t50p_m = top_match_counter["50p"]

if len(games) > 0:
  (broken_games, ignored_games, top_game_counter, core_games,
   extra_games) = write_deck_records("games", games)

  t10p_g = top_game_counter["10p"]
  t20p_g = top_game_counter["20p"]
  t30p_g = top_game_counter["30p"]
  t40p_g = top_game_counter["40p"]
  t50p_g = top_game_counter["50p"]

log(f"")
log(f"ignored matches: {ignored_matches} (of {len(matches)})")
if len(games) > 0:
  log(f"ignored games: {ignored_games} (of {len(games)})")
log(f"")
log(f"mismatched decks: {num_bad_decks} (of {len(sub_decks)})")
log(f"mismatched players: {num_bad_players} (of {len(sub_decks)})")
log(f"")
log(f"broken matches: {broken_matches} (of {len(matches)})")
if len(games) > 0:
  log(f"broken games: {broken_games} (of {len(games)})")
log(f"")
log(f"top 10/20/30/40/50% matches: {t10p_m}/{t20p_m}/{t30p_m}/{t40p_m}/{t50p_m} (of {len(matches)})"
   )
if len(games) > 0:
  log(f"top 10/20/30/40/50% games: {t10p_g}/{t20p_g}/{t30p_g}/{t40p_g}/{t50p_g} (of {len(games)})"
     )
log(f"")
log(f"core matches: {core_matches}, extra matches: {extra_matches}")
if len(games) > 0:
  log(f"core games: {core_games}, extra games: {extra_games}")
log(f"")
log(f"broken rankings: {broken_rankings}")
log(f"ignored rankings: {ignored_rankings}")
log(f"total players: {len(rankings)}")
log(f"")
