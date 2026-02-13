# Chess.com Capture (Windows)

This tool captures the Chess.com window, detects the board region, and produces a FEN
by matching piece templates.

## Setup

1) Install deps:
```
pip install -r pc_capture/requirements.txt
```

2) Add piece templates into `pc_capture/templates/`:
```
wK.png wQ.png wR.png wB.png wN.png wP.png
bK.png bQ.png bR.png bB.png bN.png bP.png
```

3) Calibrate the board rectangle:
```
python pc_capture/chesscom_capture.py --calibrate --title "Chess.com"
```
Click top-left corner of the board, then bottom-right corner.

4) Capture and print FEN (auto every 5s):
```
python pc_capture/chesscom_capture.py --title "Chess.com"
```

5) Capture once:
```
python pc_capture/chesscom_capture.py --title "Chess.com" --once
```

6) Debug images:
```
python pc_capture/chesscom_capture.py --debug-dir pc_capture/debug
```
This saves `window.png`, `board.png`, and all 64 squares for template tuning.

## Options

- Auto-detects side (white/bottom) by default.
- `--no-auto-side` to disable, then `--flip` to force black-bottom.
- `--threshold 0.25` to adjust template sensitivity (edge-based).
- `--interval 5` capture interval seconds.
- `--post http://192.168.0.10:8000` to call your analysis server.
