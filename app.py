"""M8: Flask routes. Holds each game in server memory; the browser only keeps a game id."""
import random
import uuid
from dataclasses import dataclass, field

from flask import Flask, redirect, render_template, request, session, url_for

from config import Config
from wilty.local_client import LocalClient
from wilty.game_engine import Game, GameStateError, GuessError
from wilty.lie_bank import LieBank
from wilty.lie_history import LieHistory
from wilty.lie_provider import LieProvider
from wilty.models import LIE_SOURCES, Player, Settings, Team


@dataclass
class GameSession:
    id: str
    settings: Settings
    teams: list
    story_turn: int = 0  # which player is entering stories (0..5)
    game: Game = None
    provider: LieProvider = None
    history: LieHistory = None
    notice: str = None
    rng: random.Random = field(default_factory=random.Random)

    def players_in_order(self):
        return [(t, p) for t in self.teams for p in t.players]


def default_local_factory(config):
    return LocalClient(config["OLLAMA_URL"], config["OLLAMA_MODEL"], config["OLLAMA_TIMEOUT_SECONDS"])


def create_app(test_config=None, ai_factory=default_local_factory):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    games = {}
    app.extensions["wilty_games"] = games

    def current():
        game_id = session.get("game_id")
        return games.get(game_id) if game_id else None

    def make_rng():
        seed = app.config["RANDOM_SEED"]
        return random.Random(seed) if seed is not None else random.Random()

    # ---- setup -------------------------------------------------------------

    @app.get("/")
    def setup():
        return render_template("setup.html", form={}, error=None, n=app.config["PLAYERS_PER_TEAM"])

    @app.post("/setup")
    def create_game():
        n = app.config["PLAYERS_PER_TEAM"]
        form = request.form
        team_names = [form.get("team_a", "").strip(), form.get("team_b", "").strip()]
        player_names = [[form.get(f"t{t}p{i}", "").strip() for i in range(n)] for t in range(2)]

        error = None
        if not all(team_names):
            error = "Both teams need a name."
        elif team_names[0].lower() == team_names[1].lower():
            error = "The two teams need different names."
        elif not all(all(names) for names in player_names):
            error = f"Every team needs {n} named players."
        if error:
            return render_template("setup.html", form=form, error=error, n=n), 400

        source = form.get("lie_source", "local")
        if source not in LIE_SOURCES:
            source = "local"

        sess = GameSession(
            id=uuid.uuid4().hex,
            settings=Settings(lie_source=source, test_mode=bool(form.get("test_mode"))),
            teams=[Team(team_names[t], [Player(name) for name in player_names[t]]) for t in range(2)],
            rng=make_rng(),
        )
        games[sess.id] = sess
        session["game_id"] = sess.id
        return redirect(url_for("stories"))

    # ---- true stories (FR4) ------------------------------------------------

    @app.route("/stories", methods=["GET", "POST"])
    def stories():
        sess = current()
        if sess is None:
            return redirect(url_for("setup"))
        order = sess.players_in_order()
        if sess.story_turn >= len(order):
            return redirect(url_for("round_page"))
        team, player = order[sess.story_turn]

        if request.method == "POST":
            count = app.config["STORIES_PER_PLAYER"]
            entered = [request.form.get(f"story{i}", "").strip() for i in range(count)]
            if not all(entered):
                return render_template("story.html", team=team, player=player, error=f"Enter {count} true stories.",
                                       step=sess.story_turn + 1, total=len(order)), 400
            if len({s.lower() for s in entered}) != len(entered):
                return render_template("story.html", team=team, player=player, error="Your stories must be different.",
                                       step=sess.story_turn + 1, total=len(order)), 400
            player.stories = entered
            sess.story_turn += 1
            if sess.story_turn >= len(order):
                start_game(sess)
                return redirect(url_for("round_page"))
            return redirect(url_for("stories"))

        return render_template("story.html", team=team, player=player, error=None,
                               step=sess.story_turn + 1, total=len(order))

    def start_game(sess):
        test_mode = sess.settings.test_mode
        sess.history = LieHistory(app.config["LIE_HISTORY_PATH"], app.config["NO_REPEAT_GAMES"], persist=not test_mode)
        sess.history.start_game(sess.id)

        client = None
        source = sess.settings.lie_source
        if source == "offline":
            sess.notice = "Offline mode: lies come from the built-in lie bank."
        else:
            client = ai_factory(app.config)

        bank = LieBank(app.config["LIE_BANK_PATH"], rng=sess.rng)
        sess.provider = LieProvider(bank, sess.history, client)
        examples = [s for _, p in sess.players_in_order() for s in p.stories]
        sess.provider.prepare(app.config["REGULAR_ROUNDS"] + app.config["EXTRA_LIES"], examples)
        if sess.provider.status:
            sess.notice = sess.provider.status

        sess.game = Game(sess.teams, sess.provider.next_lie, app.config["REGULAR_ROUNDS"], rng=sess.rng)

    # ---- rounds ------------------------------------------------------------

    def round_context(sess, error=None, phase="privacy"):
        game = sess.game
        rnd = game.current
        return dict(
            game=game, rnd=rnd, teams=sess.teams, settings=sess.settings, notice=sess.notice,
            speaker=sess.teams[rnd.speaker_team].players[rnd.speaker_index],
            speaker_team=sess.teams[rnd.speaker_team], guessing_team=sess.teams[rnd.guessing_team],
            label=game.round_label(rnd.number), timer_seconds=app.config["TIMER_SECONDS"],
            error=error, phase=phase,
        )

    @app.get("/round")
    def round_page():
        sess = current()
        if sess is None or sess.game is None:
            return redirect(url_for("setup"))
        if sess.game.is_over():
            return redirect(url_for("end"))
        sess.game.start_round()
        return render_template("round.html", **round_context(sess))

    @app.post("/guess")
    def guess():
        sess = current()
        if sess is None or sess.game is None:
            return redirect(url_for("setup"))
        try:
            rnd = sess.game.submit_guess(request.form.get("guess"))
        except GuessError as exc:
            return render_template("round.html", **round_context(sess, error=str(exc), phase="guess")), 400
        except GameStateError:
            return redirect(url_for("round_page"))
        if not rnd.statement.is_true:
            sess.history.record_lie(sess.id, rnd.statement.text)
        return redirect(url_for("reveal"))

    @app.get("/reveal")
    def reveal():
        sess = current()
        if sess is None or sess.game is None or not sess.game.rounds:
            return redirect(url_for("setup"))
        rnd = sess.game.rounds[-1]
        return render_template(
            "reveal.html", rnd=rnd, teams=sess.teams, settings=sess.settings,
            speaker=sess.teams[rnd.speaker_team].players[rnd.speaker_index],
            label=sess.game.round_label(rnd.number), game_over=sess.game.is_over(),
        )

    @app.post("/next")
    def next_round():
        sess = current()
        if sess is None or sess.game is None:
            return redirect(url_for("setup"))
        return redirect(url_for("end" if sess.game.is_over() else "round_page"))

    @app.get("/end")
    def end():
        sess = current()
        if sess is None or sess.game is None or not sess.game.is_over():
            return redirect(url_for("setup"))
        return render_template("end.html", teams=sess.teams, winner=sess.teams[sess.game.winner()],
                               settings=sess.settings, rounds=sess.game.rounds)

    @app.post("/reset")
    def reset():
        game_id = session.pop("game_id", None)
        games.pop(game_id, None)  # drops names and true stories (NFR6)
        return redirect(url_for("setup"))

    return app


if __name__ == "__main__":
    # Port 5050 because macOS uses 5000 for AirPlay
    create_app().run(debug=True, port=5050)
