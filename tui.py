"""
TUI for inspecting running Python kernels.

  python tui.py

Navigation:
  j/k or arrow keys  move selection
  enter              select / drill in
  q / esc            go back / quit
  r                  refresh
"""

import curses
import glob
import json
import os
import socket

SOCKET_DIR = "/tmp"
SOCKET_PREFIX = "python-kernel-"

# Claude Code dark palette (256-color approximations)
# background: #1a1a1a  → color 234
# foreground: #e0e0e0  → color 254
# accent:     #AFD7FF  → color 153  (normal accent, light blue)
# active:     #87D787  → color 114  (active/connected, green)
# error:      #FF87AF  → color 211  (error/warning, pink-red)
# muted:      #6b6b6b  → color 242
# separator:  #333333  → color 236

C_BG      = 16
C_FG      = 254
C_ACCENT  = 153
C_ACTIVE  = 114
C_ERROR   = 211
C_MUTED   = 242
C_SEP     = 236

P_NORMAL  = 1
P_SEL     = 2
P_TITLE   = 3
P_HINT    = 4
P_SEP     = 5
P_MUTED   = 6
P_ACTIVE  = 7
P_ERROR   = 8


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(P_NORMAL, C_FG,     C_BG)
    curses.init_pair(P_SEL,    C_BG,     C_ACCENT)
    curses.init_pair(P_TITLE,  C_ACCENT, C_BG)
    curses.init_pair(P_HINT,   C_MUTED,  C_BG)
    curses.init_pair(P_SEP,    C_SEP,    C_BG)
    curses.init_pair(P_MUTED,  C_MUTED,  C_BG)
    curses.init_pair(P_ACTIVE, C_ACTIVE, C_BG)
    curses.init_pair(P_ERROR,  C_ERROR,  C_BG)


def socket_path(name: str) -> str:
    return os.path.join(SOCKET_DIR, f"{SOCKET_PREFIX}{name}.sock")


def list_kernels() -> list[str]:
    socks = glob.glob(os.path.join(SOCKET_DIR, f"{SOCKET_PREFIX}*.sock"))
    names = []
    for s in sorted(socks):
        name = os.path.basename(s)[len(SOCKET_PREFIX):-len(".sock")]
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
                c.connect(s)
            names.append(name)
        except OSError:
            pass
    return names


def kernel_vars(name: str) -> dict[str, str] | str:
    path = socket_path(name)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(path)
            s.sendall(json.dumps({"cmd": "vars", "code": ""}).encode() + b"\n")
            data = json.loads(s.makefile("rb").readline())
        if data["ok"]:
            return data["result"]
        return data["error"]
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def fill_bg(win):
    h, w = win.getmaxyx()
    for y in range(h):
        try:
            win.addstr(y, 0, " " * (w - 1), curses.color_pair(P_NORMAL))
        except curses.error:
            pass


def draw_hint_bar(win, text: str):
    h, w = win.getmaxyx()
    bar = text[:w-1].ljust(w - 1)
    try:
        win.addstr(h - 1, 0, bar, curses.color_pair(P_HINT))
    except curses.error:
        pass


def draw_list(win, items: list[str], sel: int, title: str):
    win.erase()
    fill_bg(win)
    h, w = win.getmaxyx()

    win.addstr(0, 1, title[:w-2], curses.color_pair(P_TITLE) | curses.A_BOLD)
    sep = "─" * (w - 1)
    try:
        win.addstr(1, 0, sep, curses.color_pair(P_SEP))
    except curses.error:
        pass

    for i, item in enumerate(items):
        y = i + 2
        if y >= h - 1:
            break
        if i == sel:
            line = f" ▶ {item} ".ljust(w - 1)
            win.addstr(y, 0, line[:w-1], curses.color_pair(P_SEL) | curses.A_BOLD)
        else:
            win.addstr(y, 0, "   ", curses.color_pair(P_NORMAL))
            win.addstr(y, 3, item[:w-4], curses.color_pair(P_ACTIVE))

    if not items:
        win.addstr(2, 2, "(no kernels running)", curses.color_pair(P_ERROR))

    draw_hint_bar(win, "  q quit    ↑↓ / jk move    enter select    r refresh")
    win.refresh()


def draw_vars(win, name: str, variables: dict[str, str] | str, sel: int):
    win.erase()
    fill_bg(win)
    h, w = win.getmaxyx()

    win.addstr(0, 1, "kernel: ", curses.color_pair(P_TITLE) | curses.A_BOLD)
    win.addstr(0, 9, name[:w-10], curses.color_pair(P_ACTIVE) | curses.A_BOLD)
    sep = "─" * (w - 1)
    try:
        win.addstr(1, 0, sep, curses.color_pair(P_SEP))
    except curses.error:
        pass

    if isinstance(variables, str):
        win.addstr(2, 2, variables[:w-3], curses.color_pair(P_ERROR))
    elif not variables:
        win.addstr(2, 2, "(empty namespace)", curses.color_pair(P_MUTED))
    else:
        items = list(variables.items())
        for i, (k, v) in enumerate(items):
            y = i + 2
            if y >= h - 1:
                break
            if i == sel:
                line = f" ▶ {k}  =  {v} ".ljust(w - 1)
                win.addstr(y, 0, line[:w-1], curses.color_pair(P_SEL) | curses.A_BOLD)
            else:
                # key in blue accent, = in muted, value in normal white
                key_str = f"   {k}"
                eq_str  = "  =  "
                val_str = v
                x = 0
                win.addstr(y, x, key_str[:w-1], curses.color_pair(P_TITLE))
                x += len(key_str)
                if x < w - 1:
                    win.addstr(y, x, eq_str[:w-1-x], curses.color_pair(P_MUTED))
                    x += len(eq_str)
                if x < w - 1:
                    win.addstr(y, x, val_str[:w-1-x], curses.color_pair(P_NORMAL))

    draw_hint_bar(win, "  q / esc back    ↑↓ / jk move    r refresh")
    win.refresh()


def run(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    init_colors()

    sel = 0
    view = "kernels"
    current_kernel = ""
    current_vars: dict[str, str] | str = {}
    var_sel = 0

    kernels = list_kernels()

    while True:
        if view == "kernels":
            sel = min(sel, max(0, len(kernels) - 1))
            draw_list(stdscr, kernels, sel, "Python Kernels")
            key = stdscr.getch()
            if key in (ord("q"), 27):
                break
            elif key in (curses.KEY_UP, ord("k")) and sel > 0:
                sel -= 1
            elif key in (curses.KEY_DOWN, ord("j")) and sel < len(kernels) - 1:
                sel += 1
            elif key in (curses.KEY_ENTER, 10, 13) and kernels:
                current_kernel = kernels[sel]
                current_vars = kernel_vars(current_kernel)
                var_sel = 0
                view = "vars"
            elif key == ord("r"):
                kernels = list_kernels()
                sel = 0

        elif view == "vars":
            items = list(current_vars.items()) if isinstance(current_vars, dict) else []
            n = len(items)
            var_sel = min(var_sel, max(0, n - 1))
            draw_vars(stdscr, current_kernel, current_vars, var_sel)
            ch = stdscr.getch()
            if ch in (ord("q"), 27):
                view = "kernels"
                kernels = list_kernels()
            elif ch in (curses.KEY_UP, ord("k")) and var_sel > 0:
                var_sel -= 1
            elif ch in (curses.KEY_DOWN, ord("j")) and var_sel < n - 1:
                var_sel += 1
            elif ch == ord("r"):
                current_vars = kernel_vars(current_kernel)
                var_sel = 0


def main():
    curses.wrapper(run)


if __name__ == "__main__":
    main()
