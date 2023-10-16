class Match:

  def __init__(self,
               winner,
               loser,
               table,
               round,
               winner_wins=0,
               loser_wins=0,
               winner_pid=None,
               loser_pid=None,
               winner_discord=None,
               loser_discord=None):
    self.winner = winner
    self.loser = loser
    self.table = table
    self.round = round
    self.winner_pid = winner_pid
    self.loser_pid = loser_pid
    self.winner_discord = winner_discord
    self.loser_discord = loser_discord
    self.games = self.make_games(winner_wins, loser_wins)

  def __repr__(self):
    return f"{self.winner} beat {self.loser} (round {self.round}, table {self.table})"
    # return f"Match(winner={self.winner}, loser={self.loser}, table={self.table}, round={self.round})"

  def is_valid_match(self):
    return self.winner and self.loser and self.table and self.round

  def make_games(self, winner_wins, loser_wins):
    l = []

    if winner_wins == '':
      winner_wins = 0

    if loser_wins == '':
      loser_wins = 0

    for i in range(int(winner_wins) or 0):
      l.append(
          Game(self.winner, self.loser, self.table, self.round, self.winner_pid,
               self.loser_pid))

    for i in range(int(loser_wins) or 0):
      l.append(
          Game(self.loser, self.winner, self.table, self.round, self.loser_pid,
               self.winner_pid))

    return l


class Game:

  def __init__(self,
               winner,
               loser,
               table,
               round,
               winner_pid=None,
               loser_pid=None,
               winner_discord=None,
               loser_discord=None):
    self.winner = winner
    self.loser = loser
    self.table = table
    self.round = round
    self.winner_pid = winner_pid
    self.loser_pid = loser_pid
    self.winner_discord = winner_discord
    self.loser_discord = loser_discord

  def __repr__(self):
    return f"{self.winner} beat {self.loser} (round {self.round}, table {self.table}, game {self.match_game})"


class Player:

  def __init__(self, name, ranking, player_id=None, discord=None):
    self.name = name
    self.ranking = ranking
    self.player_id = player_id
    self.discord = discord

  def __repr__(self):
    return f"{self.name} placement: {self.ranking}"

  def is_valid(self):
    return self.name and self.ranking
