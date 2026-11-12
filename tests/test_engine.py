"""Unit tests for M3 game_engine. TC02, TC09, TC10, TC15, TC16, TC20."""
import random

import pytest

from wilty.game_engine import Game, GameStateError, GuessError, parse_guess
from wilty.models import Player, Statement, Team


def make_teams():
    return [
        Team("Team A", [Player(f"A{i}", [f"A{i} true one", f"A{i} true two"]) for i in range(3)]),
        Team("Team B", [Player(f"B{i}", [f"B{i} true one", f"B{i} true two"]) for i in range(3)]),
    ]


def make_game(seed=1, lie_counter=None):
    counter = lie_counter if lie_counter is not None else [0]

    def lie_source():
        counter[0] += 1
        return Statement(f"lie {counter[0]}", False, "bank")

    return Game(make_teams(), lie_source, 6, rng=random.Random(seed))


def play_round(game, guess_correct):
    rnd = game.start_round()
    right = "T" if rnd.statement.is_true else "L"
    wrong = "L" if right == "T" else "T"
    return game.submit_guess(right if guess_correct else wrong)


def test_tc02_six_rounds_alternate_and_everyone_speaks_once():
    game = make_game()
    speakers = []
    # A wins every round it guesses, B loses every guess -> scores not level
    for i in range(6):
        rnd = game.start_round()
        speakers.append((rnd.speaker_team, rnd.speaker_index))
        guess_correct = rnd.guessing_team == 0
        right = "T" if rnd.statement.is_true else "L"
        game.submit_guess(right if guess_correct else ("L" if right == "T" else "T"))
    assert [s[0] for s in speakers] == [0, 1, 0, 1, 0, 1]
    assert sorted(speakers) == [(t, p) for t in range(2) for p in range(3)]
    assert game.is_over()
    with pytest.raises(GameStateError):
        game.start_round()


def test_tc09_truth_rate_roughly_half_and_lie_count_varies():
    truths = 0
    lie_counts = set()
    rng = random.Random(42)
    for _ in range(1000):
        game = Game(make_teams(), lambda: Statement("x", False, "bank"), 6, rng=rng)
        lies = 0
        for _ in range(6):
            rnd = game.start_round()
            truths += rnd.statement.is_true
            lies += not rnd.statement.is_true
            game.submit_guess("T")
        lie_counts.add(lies)
    share = truths / 6000
    assert 0.45 <= share <= 0.55
    assert len(lie_counts) > 3  # not always 3 lies per game


def test_tc10_true_story_never_reused():
    for seed in range(50):
        game = make_game(seed)
        used = []
        while not game.is_over():
            rnd = game.start_round()
            if rnd.statement.is_true:
                used.append(rnd.statement.text)
            game.submit_guess("T")
        assert len(used) == len(set(used))


@pytest.mark.parametrize("raw,expected", [("t", "T"), ("T", "T"), ("l", "L"), ("L", "L"), (" t ", "T")])
def test_tc15_valid_guesses(raw, expected):
    assert parse_guess(raw) == expected


@pytest.mark.parametrize("raw", ["x", "", None, "TL", "1", "truth"])
def test_tc15_invalid_guesses(raw):
    with pytest.raises(GuessError):
        parse_guess(raw)


def test_tc15_invalid_guess_does_not_score():
    game = make_game()
    game.start_round()
    with pytest.raises(GuessError):
        game.submit_guess("x")
    assert [t.score for t in game.teams] == [0, 0]
    assert game.current is not None


def test_tc16_scoring():
    game = make_game()
    rnd = play_round(game, guess_correct=True)
    assert rnd.point_to == rnd.guessing_team
    assert game.teams[rnd.guessing_team].score == 1 and game.teams[rnd.speaker_team].score == 0

    rnd = play_round(game, guess_correct=False)
    assert rnd.point_to == rnd.speaker_team
    assert all(t.score >= 0 for t in game.teams)
    assert sum(t.score for t in game.teams) == 2


def test_tc20_sudden_death():
    game = make_game()
    # Make it 3-3: every guess correct -> each team gets a point when guessing (3 each)
    for _ in range(6):
        play_round(game, guess_correct=True)
    assert [t.score for t in game.teams] == [3, 3]
    assert not game.is_over()
    assert game.round_label() == "Sudden death"

    # Pair 1: both correct -> still level -> carries on
    r = play_round(game, True)
    assert r.sudden_death
    assert not game.is_over()  # mid pair
    play_round(game, True)
    assert not game.is_over()

    # Pair 2: Team A speaks first; B guesses wrong (A +1), then A guesses right (A +1)
    play_round(game, False)
    assert not game.is_over()
    play_round(game, True)
    assert game.is_over()
    assert game.winner() == 0
