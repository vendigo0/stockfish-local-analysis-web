import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, Tuple

import cv2
import mss
import numpy as np
import requests
import win32gui


CALIBRATION_PATH = os.path.join(os.path.dirname(__file__), "calibration.json")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


@dataclass
class Calibration:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def find_window_rect(title_substring: str) -> Tuple[int, int, int, int]:
    matches = []

    def enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title_substring.lower() in title.lower():
            matches.append((hwnd, title))

    win32gui.EnumWindows(enum_handler, None)
    if not matches:
        raise RuntimeError(f"Window not found: {title_substring}")

    hwnd, title = matches[0]
    rect = win32gui.GetWindowRect(hwnd)
    return rect


def grab_window(rect: Tuple[int, int, int, int]) -> np.ndarray:
    left, top, right, bottom = rect
    with mss.mss() as sct:
        region = {"left": left, "top": top, "width": right - left, "height": bottom - top}
        image = np.array(sct.grab(region))
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)


def save_calibration(calibration: Calibration) -> None:
    with open(CALIBRATION_PATH, "w", encoding="utf-8") as f:
        json.dump(calibration.__dict__, f, indent=2)


def load_calibration() -> Calibration:
    if not os.path.exists(CALIBRATION_PATH):
        raise RuntimeError("Calibration not found. Run with --calibrate first.")
    with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Calibration(**data)


def calibrate_board(image: np.ndarray) -> Calibration:
    points = []

    def click(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))

    cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Calibration", click)
    while len(points) < 2:
        preview = image.copy()
        for pt in points:
            cv2.circle(preview, pt, 6, (0, 255, 0), -1)
        cv2.imshow("Calibration", preview)
        if cv2.waitKey(10) & 0xFF == 27:
            break
    cv2.destroyAllWindows()

    if len(points) < 2:
        raise RuntimeError("Calibration cancelled.")

    (x1, y1), (x2, y2) = points[:2]
    left, right = sorted([x1, x2])
    top, bottom = sorted([y1, y2])
    return Calibration(left=left, top=top, right=right, bottom=bottom)


def load_templates(square_size: int) -> Dict[str, np.ndarray]:
    pieces = {}
    for name in os.listdir(TEMPLATES_DIR):
        if not name.lower().endswith(".png"):
            continue
        path = os.path.join(TEMPLATES_DIR, name)
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        resized = cv2.resize(img, (square_size, square_size), interpolation=cv2.INTER_AREA)
        edges = cv2.Canny(resized, 40, 120)
        key = os.path.splitext(name)[0]
        pieces[key] = edges
    if not pieces:
        raise RuntimeError("No templates found in pc_capture/templates.")
    return pieces


def match_piece(square: np.ndarray, templates: Dict[str, np.ndarray], threshold: float) -> str:
    square_gray = cv2.cvtColor(square, cv2.COLOR_BGR2GRAY)
    square_gray = cv2.GaussianBlur(square_gray, (3, 3), 0)
    square_edges = cv2.Canny(square_gray, 40, 120)
    edge_density = float(np.count_nonzero(square_edges)) / float(square_edges.size)
    if edge_density < 0.02:
        return ""
    best_score = -1.0
    best_piece = ""
    for name, tpl in templates.items():
        res = cv2.matchTemplate(square_edges, tpl, cv2.TM_CCOEFF_NORMED)
        score = float(res.max())
        if score > best_score:
            best_score = score
            best_piece = name
    if best_score < threshold:
        return ""
    return best_piece


def build_fen(pieces_grid) -> str:
    fen_rows = []
    for row in pieces_grid:
        empty = 0
        fen_row = ""
        for piece in row:
            if not piece:
                empty += 1
                continue
            if empty:
                fen_row += str(empty)
                empty = 0
            fen_row += piece
        if empty:
            fen_row += str(empty)
        fen_rows.append(fen_row)
    return "/".join(fen_rows) + " w - - 0 1"


def piece_to_fen(name: str) -> str:
    if not name:
        return ""
    color = name[0]
    piece = name[1].lower()
    return piece.upper() if color == "w" else piece


def guess_orientation(grid) -> bool:
    bottom = grid[6:]  # ranks 2-1
    top = grid[:2]  # ranks 8-7
    bottom_white = sum(1 for row in bottom for p in row if p and p.isupper())
    top_white = sum(1 for row in top for p in row if p and p.isupper())
    return top_white > bottom_white


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="Chess.com", help="Window title substring")
    parser.add_argument("--calibrate", action="store_true", help="Calibrate board area")
    parser.add_argument("--flip", action="store_true", help="Force flip (black at bottom)")
    parser.add_argument("--auto-side", action="store_true", help="Auto-detect side", default=True)
    parser.add_argument("--no-auto-side", action="store_true", help="Disable auto-detect side")
    parser.add_argument("--threshold", type=float, default=0.25, help="Template match threshold")
    parser.add_argument("--post", default="", help="Post FEN to analysis server")
    parser.add_argument("--interval", type=int, default=5, help="Capture interval seconds")
    parser.add_argument("--once", action="store_true", help="Capture once and exit")
    parser.add_argument("--debug-dir", default="", help="Save debug images to this folder")
    args = parser.parse_args()
    if args.no_auto_side:
        args.auto_side = False
    debug_dir = args.debug_dir.strip()
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)

    while True:
        rect = find_window_rect(args.title)
        window_img = grab_window(rect)

        if args.calibrate:
            calibration = calibrate_board(window_img)
            save_calibration(calibration)
            print("Saved calibration:", calibration)
            return

        calibration = load_calibration()
        board_img = window_img[
            calibration.top : calibration.bottom, calibration.left : calibration.right
        ]
        square_size = int(min(calibration.width, calibration.height) / 8)
        templates = load_templates(square_size)

        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, "window.png"), window_img)
            cv2.imwrite(os.path.join(debug_dir, "board.png"), board_img)

        grid = []
        for rank in range(8):
            row = []
            for file in range(8):
                x1 = file * square_size
                y1 = rank * square_size
                square = board_img[y1 : y1 + square_size, x1 : x1 + square_size]
                name = match_piece(square, templates, args.threshold)
                row.append(piece_to_fen(name))
                if debug_dir:
                    cv2.imwrite(
                        os.path.join(debug_dir, f"square_{rank}_{file}.png"), square
                    )
            grid.append(row)

        if args.auto_side:
            should_flip = guess_orientation(grid)
        else:
            should_flip = args.flip

        if should_flip:
            grid = [list(reversed(r)) for r in reversed(grid)]

        fen = build_fen(grid)
        print("FEN:", fen)
        if fen.startswith("8/8/8/8/8/8/8/8"):
            print("Warning: board appears empty. Check templates/threshold/calibration.")

        if args.post:
            try:
                resp = requests.post(
                    f"{args.post.rstrip('/')}/api/analyze",
                    json={"fen": fen, "depth": 16, "multipv": 3},
                    timeout=10,
                )
                print("Server response:", resp.text)
            except Exception as exc:
                print("Server error:", exc)

        if args.once:
            break

        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Error:", exc)
        sys.exit(1)
