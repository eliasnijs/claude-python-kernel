"""
Python kernel server.

Runs as a standalone Unix socket server. Must be started explicitly before
Claude Code can use it. Persists across Claude Code sessions.

Usage:
  python kernel.py <name>   # start a named kernel
  python kernel.py          # start with default name "default"

Socket path: /tmp/python-kernel-<name>.sock
"""

import ast
import sys
import os
import socket
import json
import threading

SOCKET_DIR = "/tmp"
SOCKET_PREFIX = "python-kernel-"


def socket_path(name: str) -> str:
    return os.path.join(SOCKET_DIR, f"{SOCKET_PREFIX}{name}.sock")


kernel_ns: dict = {}


def run_script(code: str):
    ns = {**kernel_ns}
    tree = ast.parse(code, mode="exec")
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        *stmts, last_expr = tree.body
        if stmts:
            mod = ast.Module(body=stmts, type_ignores=[])
            ast.fix_missing_locations(mod)
            exec(compile(mod, "<script>", "exec"), ns)
        expr = ast.Expression(body=last_expr.value)
        ast.fix_missing_locations(expr)
        return eval(compile(expr, "<script>", "eval"), ns)
    else:
        exec(compile(tree, "<script>", "exec"), ns)
        return None


def kernel_exec(code: str) -> None:
    exec(compile(code, "<kernel>", "exec"), kernel_ns)


def handle(conn, name):
    buf = b""
    with conn:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    req = json.loads(line)
                    cmd = req.get("cmd")
                    code = req.get("code", "")
                    if cmd == "run_script":
                        result = run_script(code)
                        resp = {"ok": True, "result": repr(result) if result is not None else None}
                    elif cmd == "kernel_exec":
                        kernel_exec(code)
                        resp = {"ok": True, "result": None}
                    elif cmd == "vars":
                        resp = {"ok": True, "result": {
                            k: repr(v) for k, v in kernel_ns.items()
                            if not k.startswith("_")
                        }}
                    elif cmd == "die":
                        conn.sendall(json.dumps({"ok": True, "result": None}).encode() + b"\n")
                        os.remove(socket_path(name))
                        os._exit(0)
                    else:
                        resp = {"ok": False, "error": f"unknown cmd: {cmd}"}
                except Exception as e:
                    resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                conn.sendall(json.dumps(resp).encode() + b"\n")


def serve(name: str):
    path = socket_path(name)
    if os.path.exists(path):
        os.remove(path)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
        srv.bind(path)
        srv.listen()
        print(f"kernel '{name}' ready at {path}")
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=handle, args=(conn, name), daemon=True).start()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "default"
    serve(name)
