import argparse
import csv
import datetime
import logging
import os
import pprint
import re
import sys

FILENAME = os.path.basename(__file__)

run_timestamp = datetime.datetime.now()

pp = pprint.PrettyPrinter(indent=2)

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=str, default="output")
parser.add_argument('--input', type=str, required=True)

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


def get_round_matches(txt_f, round):
  matches = []
  table = None
  winner = None
  loser = None
  pending_name = None

  ignore_list = ['TABLE']

  for line in txt_f:
    line = line.strip()

    if table and winner and loser:
      match = Match(winner, loser, table, round)
      matches.append(match)
      table = None
      winner = None
      loser = None

    if not line.strip():
      log(f"skip << {line}", print_dest=None)
      continue

    if line in ignore_list:
      log(f"ignore << {line}", print_dest=None)
      continue

    if line.isdigit():
      log(f"table << {line}", print_dest=None)
      table = line
      continue

    if line == "Win: 1":
      log(f"winner << {line}", print_dest=None)
      winner = pending_name
      continue

    if line == "Loss: 0":
      log(f"loser << {line}", print_dest=None)
      loser = pending_name
      continue

    log(f"pending_name << {line}", print_dest=None)
    pending_name = line

  return matches


def main():
  txt_dir = os.path.abspath(args.input)
  input_name = os.path.basename(txt_dir)
  if not os.path.isdir(txt_dir):
    log(f"input directory {txt_dir} does not exist")
    sys.exit(1)

  txt_files = [f for f in os.listdir(txt_dir) if f.endswith(".txt")]
  if not txt_files:
    log(f"no txt files found in {txt_dir}")
    sys.exit(1)

  all_matches = []

  for txt_file in sorted(txt_files):
    log(f"parsing {txt_file}...")
    round = re.match(r"round_(\d+).txt", txt_file).group(1)
    txt_path = os.path.join(txt_dir, txt_file)
    with open(txt_path, 'r') as f:
      round_matches = get_round_matches(f, round)
      if not round_matches:
        log(f"no matches found in {txt_file}")
        sys.exit(1)
      log(f"found {len(round_matches)} matches")
      all_matches.extend(round_matches)

  log(f"TOTAL: found {len(all_matches)} matches")

  output_path = os.path.join(args.output, f"{input_name}_matches.csv")
  with open(output_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["round", "table", "winner", "loser"])
    for match in all_matches:
      writer.writerow([match.round, match.table, match.winner, match.loser])

  log(f"output written to {output_path}")


if __name__ == "__main__":
  main()
