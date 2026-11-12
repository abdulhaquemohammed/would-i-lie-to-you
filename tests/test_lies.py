"""Unit tests for M4-M7 lie handling. TC06, TC08, TC21, TC22, TC23, TC24."""
import random

from config import Config
from tests.fake_ai import SAMPLE_LIES, FakeAI
from wilty.ai_prompt import is_clean, parse_lies
from wilty.lie_bank import MIN_BANK_SIZE, LieBank
from wilty.lie_history import LieHistory, is_near_duplicate
from wilty.lie_provider import LieProvider


def test_tc06_lie_bank_valid():
    bank = LieBank(Config.LIE_BANK_PATH)
    assert len(bank) >= MIN_BANK_SIZE
    assert all(lie.strip() for lie in bank.lies)
    assert len(set(bank.lies)) == len(bank.lies)
    for i, a in enumerate(bank.lies):
        for b in bank.lies[i + 1:]:
            assert not is_near_duplicate(a, b), (a, b)
        assert is_clean(a)


def test_tc21_ten_offline_games_no_repeats(tmp_path):
    history = LieHistory(tmp_path / "h.json", window_games=10)
    bank = LieBank(Config.LIE_BANK_PATH, rng=random.Random(3))
    provider = LieProvider(bank, history)
    played = []
    for g in range(10):
        history.start_game(f"g{g}")
        for _ in range(6):
            lie = provider.next_lie().text
            history.record_lie(f"g{g}", lie)
            played.append(lie)
    assert len(played) == 60
    assert len(set(played)) == 60


def test_tc23_near_duplicate_detected(tmp_path):
    history = LieHistory(tmp_path / "h.json")
    history.start_game("g0")
    history.record_lie("g0", SAMPLE_LIES[0])
    reworded = SAMPLE_LIES[0].replace("camel", "camels")
    assert history.is_duplicate(reworded)
    assert not history.is_duplicate(SAMPLE_LIES[1])


def test_tc22_ai_repeat_is_rejected(tmp_path):
    history = LieHistory(tmp_path / "h.json")
    history.start_game("old")
    history.record_lie("old", SAMPLE_LIES[0])
    history.start_game("new")
    fake = FakeAI(batches=[[SAMPLE_LIES[0], SAMPLE_LIES[1]], [SAMPLE_LIES[2]]])
    bank = LieBank(Config.LIE_BANK_PATH)
    provider = LieProvider(bank, history, fake)
    provider.prepare(2, [])
    assert provider.queue == [SAMPLE_LIES[1], SAMPLE_LIES[2]]
    assert fake.calls == 2


def test_tc08_offensive_lie_rejected(tmp_path):
    history = LieHistory(tmp_path / "h.json")
    history.start_game("g")
    bad = "I once got so drunk I forgot my own name and woke up naked."
    fake = FakeAI(batches=[[bad, SAMPLE_LIES[3]], [SAMPLE_LIES[4]]])
    provider = LieProvider(LieBank(Config.LIE_BANK_PATH), history, fake)
    provider.prepare(2, [])
    assert bad not in provider.queue
    assert provider.queue == [SAMPLE_LIES[3], SAMPLE_LIES[4]]


def test_tc24_bank_used_fully_before_repeat(tmp_path):
    history = LieHistory(tmp_path / "h.json", window_games=10)
    bank = LieBank(Config.LIE_BANK_PATH, rng=random.Random(9))
    picks = []
    for g in range(len(bank)):
        history.start_game(f"g{g}")
        lie = bank.pick(history)
        history.record_lie(f"g{g}", lie)
        picks.append(lie)
    assert len(set(picks)) == len(bank)  # every entry once before any repeat


def test_parse_lies_handles_extra_text():
    assert parse_lies('Here you go:\n["one lie", "two lie"]') == ["one lie", "two lie"]


def test_parse_lies_accepts_object_from_local_models():
    assert parse_lies('{"lies": ["one", "two"]}') == ["one", "two"]


def test_local_client_reports_ollama_not_running():
    import pytest
    from wilty.local_client import LocalClient, LocalModelError
    client = LocalClient("http://127.0.0.1:9", "llama3.2:3b", timeout=2)
    with pytest.raises(LocalModelError, match="not running"):
        client.generate_lies(3, [], [])
