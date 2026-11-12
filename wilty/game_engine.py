"""M3: pure game logic. No Flask, no internet, so it can be unit tested on its own."""
import random

from .models import LIE, TRUTH, Round, Statement


class GuessError(ValueError):
    """Raised when a guess is not T or L."""


class GameStateError(RuntimeError):
    """Raised when an action happens at the wrong time (e.g. guessing with no round running)."""


def parse_guess(raw):
    """FR12: accept only T or L, any case. Returns "T" or "L"."""
    guess = (raw or "").strip().upper()
    if guess not in (TRUTH, LIE):
        raise GuessError("Type T for truth or L for lie.")
    return guess


class Game:
    """
    Turn order: Team A speaks in odd rounds, Team B in even rounds, and each team
    rotates through its players, so in 6 rounds every player speaks exactly once.

    lie_source is a function with no arguments that returns a lie Statement.
    """

    def __init__(self, teams, lie_source, regular_rounds=6, rng=None):
        if len(teams) != 2:
            raise ValueError("A game needs exactly 2 teams.")
        self.teams = teams
        self.lie_source = lie_source
        self.regular_rounds = regular_rounds
        self.rng = rng or random.Random()
        self.rounds = []  # finished rounds
        self.current = None  # round being played
        self._turns = [0, 0]  # times each team has spoken

    # ---- state -------------------------------------------------------------

    @property
    def rounds_played(self):
        return len(self.rounds)

    @property
    def in_sudden_death(self):
        return self.rounds_played >= self.regular_rounds

    def is_over(self):
        """
        Over after the regular rounds if scores differ. In sudden death (FR22) each team
        gets one more round per pair, and the game ends after any pair that leaves a team ahead.
        """
        played = self.rounds_played
        if self.current is not None or played < self.regular_rounds:
            return False
        if (played - self.regular_rounds) % 2 == 1:
            return False  # mid-way through a sudden-death pair
        return self.teams[0].score != self.teams[1].score

    def winner(self):
        if not self.is_over():
            return None
        return 0 if self.teams[0].score > self.teams[1].score else 1

    def round_label(self, number=None):
        number = number or (self.rounds_played + 1)
        if number > self.regular_rounds:
            return "Sudden death"
        return f"Round {number} of {self.regular_rounds}"

    # ---- actions -----------------------------------------------------------

    def next_speaker(self):
        team_index = self.rounds_played % 2
        team = self.teams[team_index]
        player_index = self._turns[team_index] % len(team.players)
        return team_index, player_index

    def start_round(self):
        """FR7: each round is an independent coin flip between a true story and a lie."""
        if self.current is not None:
            return self.current
        if self.is_over():
            raise GameStateError("The game is over.")

        team_index, player_index = self.next_speaker()
        player = self.teams[team_index].players[player_index]
        unused = player.unused_story_indexes()

        if unused and self.rng.random() < 0.5:
            story_index = self.rng.choice(unused)
            player.used_stories.add(story_index)  # a true story is never reused
            statement = Statement(player.stories[story_index], True, "player")
        else:
            # Coin said lie, or the player has no true stories left
            statement = self.lie_source()

        self._turns[team_index] += 1
        number = self.rounds_played + 1
        self.current = Round(
            number=number,
            speaker_team=team_index,
            speaker_index=player_index,
            statement=statement,
            sudden_death=number > self.regular_rounds,
        )
        return self.current

    def submit_guess(self, raw_guess):
        """FR13: correct guess = point to the guessing team; wrong guess = point to the speaker's team."""
        if self.current is None:
            raise GameStateError("No round is running.")
        guess = parse_guess(raw_guess)

        rnd = self.current
        rnd.guess = guess
        rnd.correct = (guess == TRUTH) == rnd.statement.is_true
        rnd.point_to = rnd.guessing_team if rnd.correct else rnd.speaker_team
        self.teams[rnd.point_to].score += 1

        self.rounds.append(rnd)
        self.current = None
        return rnd
