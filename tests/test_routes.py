"""Integration tests for M8 routes with the local AI faked.
TC01, TC03, TC04, TC05, TC07, TC19, TC25, TC31, TC35, TC36."""
import json

import pytest

from app import create_app
from tests.fake_ai import SAMPLE_LIES, FakeAI

PLAYERS = {"team_a": "Dragons", "team_b": "Owls",
           "t0p0": "Ali", "t0p1": "Bea", "t0p2": "Cal", "t1p0": "Dee", "t1p1": "Eli", "t1p2": "Fay"}


def build(tmp_path, fake=None):
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "RANDOM_SEED": 7,
                      "LIE_HISTORY_PATH": tmp_path / "history.json"},
                     ai_factory=lambda config: fake if fake is not None else pytest.fail("AI should not be called"))
    return app, app.test_client()


def setup_game(client, **extra):
    data = dict(PLAYERS, **extra)
    assert client.post("/setup", data=data).status_code == 302
    for i in range(6):
        r = client.post("/stories", data={"story0": f"Player {i} true story about a red kite",
                                          "story1": f"Player {i} second story about a bakery"})
        assert r.status_code == 302


def game_of(app):
    return next(iter(app.extensions["wilty_games"].values()))


def play_to_end(app, client):
    while True:
        r = client.get("/round")
        if r.status_code == 302 and "/end" in r.headers["Location"]:
            break
        sess = game_of(app)
        rnd = sess.game.current
        client.post("/guess", data={"guess": "T" if rnd.statement.is_true else "L"})
        if sess.game.rounds_played > 30:
            pytest.fail("game never ended")
        client.post("/next")
        if sess.game.rounds_played >= 6 and not sess.game.is_over():
            client.get("/round")
            rnd = sess.game.current
            client.post("/guess", data={"guess": "L" if rnd.statement.is_true else "T"})
            client.post("/next")


def test_tc01_setup_validation(tmp_path):
    app, client = build(tmp_path, FakeAI())
    r = client.post("/setup", data=dict(PLAYERS, t0p2=""))
    assert r.status_code == 400 and b"3 named players" in r.data
    assert client.post("/setup", data=dict(PLAYERS, team_b="")).status_code == 400
    assert client.post("/setup", data=PLAYERS).status_code == 302


def test_setup_offers_only_local_ai_and_lie_bank(tmp_path):
    app, client = build(tmp_path, FakeAI())
    page = client.get("/").data
    assert b'value="local"' in page and b'value="offline"' in page
    assert b"Claude" not in page


def test_tc03_story_validation(tmp_path):
    app, client = build(tmp_path, FakeAI())
    client.post("/setup", data=PLAYERS)
    assert client.post("/stories", data={"story0": "only one", "story1": ""}).status_code == 400
    assert client.post("/stories", data={"story0": "same", "story1": "Same"}).status_code == 400
    assert client.post("/stories", data={"story0": "zebra secret", "story1": "walrus secret"}).status_code == 302
    page = client.get("/stories").data
    assert b"Bea" in page and b"zebra" not in page


def test_tc04_tc35_local_ai_lies_ready_before_round_one(tmp_path):
    fake = FakeAI(batches=[SAMPLE_LIES[:10]])
    app, client = build(tmp_path, fake)
    setup_game(client, lie_source="local")
    assert fake.calls == 1
    sess = game_of(app)
    assert len(sess.provider.queue) == 10
    client.get("/round")
    assert fake.calls == 1  # no AI call during rounds
    assert sess.provider.next_lie().source == "local"


def test_tc05_tc36_local_ai_not_running_falls_back_to_bank(tmp_path):
    app, client = build(tmp_path, FakeAI(error="Ollama is not running on this laptop."))
    setup_game(client, lie_source="local")
    page = client.get("/round").data
    assert b"Couldn&#39;t reach the local AI model" in page and b"built-in lie bank" in page


def test_tc07_lie_bank_mode_never_calls_ai(tmp_path):
    app, client = build(tmp_path, None)  # factory fails the test if called
    setup_game(client, lie_source="offline")
    assert b"Offline mode" in client.get("/round").data


def test_unknown_source_defaults_to_local(tmp_path):
    fake = FakeAI(batches=[SAMPLE_LIES[:10]])
    app, client = build(tmp_path, fake)
    setup_game(client, lie_source="claude")
    assert game_of(app).settings.lie_source == "local"


def test_tc19_end_and_play_again(tmp_path):
    app, client = build(tmp_path, FakeAI(batches=[SAMPLE_LIES[:10]]))
    setup_game(client)
    play_to_end(app, client)
    sess = game_of(app)
    assert sess.teams[sess.game.winner()].name.encode() in client.get("/end").data
    assert client.post("/reset").status_code == 302
    assert app.extensions["wilty_games"] == {}


def test_tc25_test_mode_shows_answer_and_keeps_history_clean(tmp_path):
    app, client = build(tmp_path, FakeAI(batches=[SAMPLE_LIES[:10]]))
    setup_game(client, test_mode="on")
    page = client.get("/round").data
    assert b"TEST GAME" in page and b"Test mode: this statement is" in page
    play_to_end(app, client)
    assert not (tmp_path / "history.json").exists()


def test_tc31_history_holds_lies_only(tmp_path):
    app, client = build(tmp_path, FakeAI(batches=[SAMPLE_LIES[:10]]))
    setup_game(client)
    play_to_end(app, client)
    text = (tmp_path / "history.json").read_text()
    for name in ["Ali", "Bea", "Dragons", "Owls", "red kite", "bakery"]:
        assert name not in text
    played = [r.statement.text for r in game_of(app).game.rounds if not r.statement.is_true]
    assert json.loads(text)["games"][-1]["lies"] == played


def test_guess_validation_on_page(tmp_path):
    app, client = build(tmp_path, FakeAI(batches=[SAMPLE_LIES[:10]]))
    setup_game(client)
    client.get("/round")
    r = client.post("/guess", data={"guess": "x"})
    assert r.status_code == 400 and b"Type T for truth" in r.data
    assert client.post("/guess", data={"guess": "t"}).status_code == 302
    page = client.get("/reveal").data
    assert b"Point to" in page and (b"TRUTH" in page or b"LIE" in page)
