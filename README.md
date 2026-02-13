# Stockfish Local Analysis (Web)

Modern local chess analysis app with Stockfish, dark UI, evaluation bar, arrows, and humanization modes.

## Features

- Chessboard with legal move validation and promotion
- Stockfish analysis (`MultiPV`, best line + top lines)
- Evaluation bar + arrows + highlighted squares
- Humanization system (`Don't blunder`, `Natural mistakes`, `Chaotic`)
- Presets (`Coach`, `Blitz Human`, `Tournament Human`, `Engine Max`)
- Optional PC capture pipeline (`pc_capture/`) for Chess.com browser board -> FEN

## Tech Stack

- `HTML`, `CSS`, `Vanilla JS`
- `python-chess`, `Flask`
- `Stockfish` (UCI engine)

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Put Stockfish binary in one of these locations:

- `./stockfish/stockfish-windows-x86-64-avx2.exe`
- `./stockfish/stockfish.exe`
- `./stockfish.exe`

Or set:

```bash
set STOCKFISH_PATH=C:\path\to\stockfish.exe
```

3. Run server:

```bash
python app.py
```

4. Open:

- Local: `http://127.0.0.1:8000`
- LAN: `http://<your-pc-ip>:8000`

## Humanization

- Toggle `Humanization` in UI
- Set intensity with `Human level`
- Pick behavior mode:
  - `Don't blunder` (safe inaccuracies)
  - `Natural mistakes` (balanced)
  - `Chaotic` (high variance)

## Chess.com Capture (optional)

`pc_capture/` includes a Windows script to capture board screenshots and build FEN.

```bash
python pc_capture/chesscom_capture.py --calibrate --title "Chess.com"
python pc_capture/chesscom_capture.py --title "Chess.com" --post http://127.0.0.1:8000
```

## Repository Structure

- `index.html` - frontend UI
- `app.py` - backend API + Stockfish integration
- `imgs/` - piece set
- `pc_capture/` - Chess.com capture tooling

## License

MIT (recommended)
