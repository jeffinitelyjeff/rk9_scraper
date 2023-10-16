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


# results of scrape_matches.py
GameRecord = namedtuple('GameRecord', [
    'round', 'table', 'winner', 'loser', 'winner_pid', 'loser_pid',
    'winner_discord', 'loser_discord'
])

# results of scrape_rankings.py
RankingRecord = namedtuple('RankingRecord',
                           ['ranking', 'name', 'player_id', 'discord'],
                           defaults=(None,) * 4)

# export from players google sheet
DeckSubmission = namedtuple('DeckSubmission',
                            ['player_name', 'deck_types', 'tag_counts'])

# artifacts of this script
NameMapping = namedtuple(
    'NameMapping',
    ['ranking', 'pairing_record_name', 'form_submitted_name', 'deck_type'],
    defaults=(None,) * 4)
IgnoredName = namedtuple('IgnoredName', ['ranking', 'pairing_record_name'])


def read_csv(fname, tuple_type):
  path = os.path.join(main_dir, fname)
  with open(path, newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    if tuple_type:
      return [tuple_type(**row) for row in reader]
    else:
      return list(reader)


def get_indexed_fields(d, field_name):
  l = []
  i = 1

  while True:
    if i == 1:
      field = d.get(field_name) or d.get(f"{field_name}_{i}")
    else:
      field = d.get(f"{field_name}_{i}")

    if field:
      l.append(field)
    else:
      break

    i += 1

  return l


def read_deck_submissions_csv(fname):
  path = os.path.join(main_dir, fname)
  with open(path, newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    l = []
    for row in reader:
      deck_types = get_indexed_fields(row, "deck_type")
      tag_counts = get_indexed_fields(row, "tag_count")
      l.append(DeckSubmission(row["player_name"], deck_types, tag_counts))
  return l


def write_csv(fname, rows, tuple_type):
  path = os.path.join(main_dir, fname)
  with open(path, 'w') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=tuple_type._fields)
    writer.writeheader()
    for row in rows:
      writer.writerow(row._asdict())
      # FIXME: will this actually work?


# --- main ---

sub_decks = read_deck_submissions_csv("submitted_decks.csv")

matches = read_csv("matches.csv", GameRecord)

try:
  games = read_csv("games.csv", GameRecord)
except FileNotFoundError:
  games = []

try:
  rankings = read_csv("rankings.csv", RankingRecord)
except FileNotFoundError:
  rankings = []

ranking_by_pid = {r.player_id: int(r.ranking) for r in rankings}
ranking_by_discord = {r.discord: int(r.ranking) for r in rankings}
num_players = len(rankings)

# this would seem like the logical solution, but the whole reason to start
# using pid is that ranking names didn't match pairing names
# record_name_by_pid = {r["player_id"]: r["name"] for r in rankings}
record_name_by_pid = {}

try:
  overrides = read_csv("overrides.csv", NameMapping)
  override_dict = {int(o.ranking): o for o in overrides}
except FileNotFoundError:
  override_dict = {}

try:
  rows = read_csv("ignored_names.csv", IgnoredName)
  ignored_names = set(r.pairing_record_name.strip().lower() for r in rows)
except FileNotFoundError:
  ignored_names = set()

sub_player_counts = Counter()
sub_players_by_word = defaultdict(set)
for submission in sub_decks:
  full_name = submission.player_name
  words = full_name.split()
  for word in words:
    sub_players_by_word[word].add(full_name)
  sub_player_counts[full_name] += 1

for sub_player, count in sub_player_counts.items():
  if count > 1 and sub_player not in ignored_names:
    log(f"FATAL error: multiple submissions for {sub_player}")
    sys.exit(1)

sub_players = set(sub_player_counts.keys())

record_players = set()
record_player_names = set()
for ranking in rankings:
  name = ranking.name.strip().lower()
  rank = int(ranking.ranking)
  record_players.add(RankingRecord(ranking=rank, name=name))
  record_player_names.add(name)


def make_deck_mapping():

  deck_dict = {}

  for submission in sub_decks:
    sub_player_name = submission.player_name.strip().lower()
    deck_labels = submission.deck_types + submission.tag_counts
    deck_dict[sub_player_name] = [l for l in deck_labels if l]

  return deck_dict


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

  if len(guesses) > 0:
    return None, guesses

  return None, []


def make_player_mapping():
  dict = override_dict.copy()
  mismatched_players = {}

  reject_following = False
  for rec_player in sorted(record_players, key=lambda x: x.name):
    rec_name = rec_player.name
    rec_rank = rec_player.ranking

    empty_mapping = NameMapping(rec_rank, rec_name, '')

    if not rec_name:
      continue

    if rec_name in ignored_names:
      continue

    override_mapping = override_dict.get(rec_rank)
    if override_mapping and (override_mapping.form_submitted_name or
                             override_mapping.deck_type):
      continue

    sub_name, guesses = sub_name_for_record_player(rec_name)
    if sub_name is not None:
      dict[rec_rank] = NameMapping(rec_rank, rec_name, sub_name)
    elif guesses:
      if reject_following:
        mismatched_players[rec_rank] = empty_mapping
        continue

      reject = u"✗ None of these"
      reject_all = u"✗ None of these (all remaining)"
      question = inquirer.List(
          'chosen_guess',
          message=f"Submitted Form Name",
          choices=guesses + [reject, reject_all],
          carousel=True,
      )
      print(f"\n\nPairing Record Name: =>[ {rec_name} ]<= (Rank {rec_rank})\n")
      answers = inquirer.prompt([question])
      answer = answers["chosen_guess"].strip('*- ')
      if answer == reject:
        log(f"player not found: {rec_name}")
        mismatched_players[rec_rank] = empty_mapping
      elif answer == reject_all:
        reject_following = True
        mismatched_players[rec_name] = empty_mapping
      else:
        mapping = NameMapping(rec_rank, rec_name, answer)
        dict[rec_rank] = mapping
        override_dict[rec_rank] = mapping
    else:
      log(f"player not found: {rec_name}")
      mismatched_players[rec_rank] = empty_mapping

  mismatched_path = os.path.join(main_dir, "mismatched_players.csv")
  if len(mismatched_players) > 0:
    write_csv(mismatched_path, mismatched_players.values(), NameMapping)
  else:
    try:
      os.remove(mismatched_path)
    except FileNotFoundError:
      pass

  return dict, len(mismatched_players)


decks_by_sub_player = make_deck_mapping()
player_mapping_by_rank, num_bad_players = make_player_mapping()


# returns: list of deck types, form_submitted_name
def get_deck_types_for_rank(ranking):
  mapping = player_mapping_by_rank.get(ranking)

  if not mapping:
    log(f"broken ranking: no mapping for {ranking}")
    return [], None

  if mapping.deck_type:
    return [mapping.deck_type], None

  sub_name = mapping.form_submitted_name

  if not sub_name:
    log(f"broken ranking: {mapping.pairing_record_name}")
    return [], None

  return decks_by_sub_player[sub_name], sub_name


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
      ranking = int(ranking_row.ranking)
      ranking_name = ranking_row.name.strip().lower()
      pid = ranking_row.player_id
      discord = ranking_row.discord

      if pid:
        try:
          record_name = record_name_by_pid[pid]
        except KeyError:
          log(f"ranking for {ranking_name} ignored b/c they have no records")
          continue
      else:
        record_name = ranking_name

      deck_types, sub_name = get_deck_types_for_rank(ranking)
      if len(deck_types) == 0:
        broken_rankings += 1
        continue
      for deck in deck_types:
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
      round = record.round
      table = record.table
      record_winner = record.winner.strip().lower()
      record_loser = record.loser.strip().lower()
      winner_pid = record.winner_pid
      loser_pid = record.loser_pid
      winner_discord = record.winner_discord
      loser_discord = record.loser_discord

      record_name_by_pid[winner_pid] = record_winner
      record_name_by_pid[loser_pid] = record_loser

      if not record_loser:
        continue

      if record_winner in ignored_names or record_loser in ignored_names:
        ignored_records += 1
        continue

      max_rank = num_players + 1

      if winner_pid:
        winner_rank = ranking_by_pid.get(winner_pid, max_rank)
      elif winner_discord:
        winner_rank = ranking_by_discord.get(winner_discord, max_rank)
      else:
        winner_rank = num_players + 1

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

      winner_decks, sub_winner = get_deck_types_for_rank(winner_rank)
      loser_decks, sub_loser = get_deck_types_for_rank(loser_rank)

      if len(winner_decks) == 0 or len(loser_decks) == 0:
        log(f"broken {record_type} record: {record}", print_dest=None)
        broken_records += 1
        continue

      winner_core_deck = winner_decks[0]
      loser_core_deck = loser_decks[0]

      # winner, loser, is_core_record
      deck_pairs = []

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
  try:
    mismatched_players = read_csv("mismatched_players.csv", NameMapping)
  except FileNotFoundError:
    mismatched_players = []

  items = sorted(override_dict.values(),
                 key=lambda x: x.ranking) + mismatched_players
  write_csv("overrides.csv", items, NameMapping)

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
