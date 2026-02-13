import atexit
import math
import os
import random
import threading
from glob import glob

import chess
import chess.engine
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ENGINE = "stockfish.exe" if os.name == "nt" else "stockfish"


def resolve_engine_path():
    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    candidates = [
        os.path.join(BASE_DIR, "stockfish", "stockfish-windows-x86-64-avx2.exe"),
        os.path.join(BASE_DIR, "stockfish", DEFAULT_ENGINE),
        os.path.join(BASE_DIR, DEFAULT_ENGINE),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    exe_candidates = glob(os.path.join(BASE_DIR, "stockfish", "*.exe"))
    if exe_candidates:
        return exe_candidates[0]

    return env_path or candidates[0]


ENGINE_PATH = resolve_engine_path()

app = Flask(__name__, static_folder="static", static_url_path="/static")

engine_lock = threading.Lock()
engine = None
last_options = {}


def get_engine():
    global engine
    if not os.path.isfile(ENGINE_PATH):
        raise FileNotFoundError(f"Stockfish not found: {ENGINE_PATH}")
    if engine is None:
        engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
    return engine


def configure_engine(options):
    global last_options
    if options == last_options:
        return
    engine_instance = get_engine()
    try:
        engine_instance.configure(options)
        last_options = dict(options)
    except chess.engine.EngineError:
        pass


def serialize_score(score):
    if score is None:
        return {"type": "cp", "value": 0}
    if score.is_mate():
        mate = score.pov(chess.WHITE).mate()
        if mate is None:
            return {"type": "cp", "value": 0}
        return {"type": "mate", "value": mate}
    return {"type": "cp", "value": score.pov(chess.WHITE).score(mate_score=100000)}


def score_to_cp(score):
    if score["type"] == "mate":
        return 120000 if score["value"] > 0 else -120000
    return int(score["value"])


def choose_humanized_best(lines, turn, human_level, human_mode):
    if not lines:
        return None
    if human_level <= 0:
        return lines[0]["pv"][0] if lines[0]["pv"] else None

    scored = []
    for line in lines:
        if not line["pv"]:
            continue
        cp = score_to_cp(line["score"])
        turn_cp = cp if turn == chess.WHITE else -cp
        scored.append((line, turn_cp))

    if not scored:
        return None

    scored.sort(key=lambda item: item[1], reverse=True)
    best_turn_cp = scored[0][1]

    mode = (human_mode or "natural").lower()
    if mode == "dont_blunder":
        max_drop = 12 + int(human_level * 3.8)
        temperature = 10 + int(human_level * 2.8)
        safe_margin = 40
    elif mode == "chaotic":
        max_drop = 50 + int(human_level * 9.0)
        temperature = 25 + int(human_level * 7.5)
        safe_margin = -140
    else:
        max_drop = 25 + int(human_level * 7.5)
        temperature = 18 + int(human_level * 6.0)
        safe_margin = -40
    filtered = [(line, score) for line, score in scored if (best_turn_cp - score) <= max_drop]
    if not filtered:
        filtered = scored[:1]

    if best_turn_cp > 220:
        safer = [(line, score) for line, score in filtered if score > safe_margin]
        if safer:
            filtered = safer
    weights = []
    for _, score in filtered:
        loss = max(0, best_turn_cp - score)
        weights.append(math.exp(-loss / max(1, temperature)))

    pick = random.choices(filtered, weights=weights, k=1)[0][0]
    return pick["pv"][0] if pick["pv"] else None


@app.route("/")
def root():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/imgs/<path:filename>")
def imgs(filename):
    return send_from_directory(os.path.join(BASE_DIR, "imgs"), filename)


@app.route("/api/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(silent=True) or {}
    fen = payload.get("fen")
    depth = max(1, min(int(payload.get("depth", 16)), 24))
    multipv = max(1, min(int(payload.get("multipv", 3)), 10))
    skill = payload.get("skill")
    limit_strength = bool(payload.get("limitStrength", False))
    elo = payload.get("elo")
    style = payload.get("style", "normal")
    humanization = bool(payload.get("humanization", False))
    human_level = max(0, min(int(payload.get("humanLevel", 35)), 100))
    human_mode = str(payload.get("humanMode", "natural"))

    try:
        board = chess.Board(fen) if fen else chess.Board()
    except ValueError:
        return jsonify({"error": "Invalid FEN"}), 400

    try:
        engine_instance = get_engine()
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500

    with engine_lock:
        options = {}
        if skill is not None:
            options["Skill Level"] = max(0, min(int(skill), 20))
        options["UCI_LimitStrength"] = limit_strength
        if limit_strength and elo is not None:
            options["UCI_Elo"] = max(800, min(int(elo), 2850))
        style_map = {
            "passive": -20,
            "normal": 0,
            "aggressive": 20,
        }
        options["Contempt"] = style_map.get(style, 0)
        configure_engine(options)
        info = engine_instance.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)

    if not isinstance(info, list):
        info = [info]

    lines = []
    for line in info:
        pv_moves = [move.uci() for move in line.get("pv", [])]
        lines.append(
            {
                "score": serialize_score(line.get("score")),
                "pv": pv_moves,
            }
        )

    engine_best = lines[0]["pv"][0] if lines and lines[0]["pv"] else None
    best = (
        choose_humanized_best(lines, board.turn, human_level, human_mode)
        if humanization
        else engine_best
    )
    return jsonify(
        {
            "best": best,
            "engineBest": engine_best,
            "lines": lines,
            "humanizationUsed": humanization,
            "humanLevel": human_level,
            "humanMode": human_mode,
        }
    )


@atexit.register
def close_engine():
    global engine
    if engine is not None:
        try:
            engine.quit()
        except Exception:
            pass
        engine = None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
