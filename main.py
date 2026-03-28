"""
MCP server exposing a Python kernel to Claude Code.
The kernel must be started separately with: python kernel.py <name>
"""

import sys
import json
import socket
import os
import subprocess
import time
import glob

SOCKET_DIR = "/tmp"
SOCKET_PREFIX = "python-kernel-"
KERNEL_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kernel.py")

TOOLS = [
    {
        "name": "list_python_kernels",
        "description": "List all currently running Python kernels by name.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "connect_python_kernel",
        "description": (
            "Connect to an already-running Python kernel by name. "
            "Use this at the start of a session to attach to a kernel started previously."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the kernel to connect to"}
            },
            "required": ["name"],
        },
    },
    {
        "name": "kill_python_kernel",
        "description": "Shut down a running Python kernel and remove its socket.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the kernel to kill"}
            },
            "required": ["name"],
        },
    },
    {
        "name": "spawn_python_kernel",
        "description": (
            "Start a named Python kernel. Must be called before run_script or kernel_exec. "
            "The kernel persists across Claude Code sessions until the machine reboots."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for this kernel (e.g. 'default', 'project-x')"
                },
                "python": {
                    "type": "string",
                    "description": "Absolute path to the Python executable (e.g. .venv/bin/python, /usr/bin/python3)"
                },
            },
            "required": ["name", "python"],
        },
    },
    {
        "name": "run_script",
        "description": (
            "Execute Python code with read access to kernel variables. "
            "The last expression is returned. "
            "Variables assigned here do NOT persist in the kernel. "
            "Use this for all code execution by default."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Kernel name"},
                "code": {"type": "string", "description": "Python code to execute"},
            },
            "required": ["name", "code"],
        },
    },
    {
        "name": "kernel_exec",
        "description": (
            "Execute Python code directly in the kernel namespace. "
            "Only use this when the user explicitly asks to store something in the kernel. "
            "For all other code execution use run_script instead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Kernel name"},
                "code": {"type": "string", "description": "Python code to execute"},
            },
            "required": ["name", "code"],
        },
    },
]


def socket_path(name: str) -> str:
    return os.path.join(SOCKET_DIR, f"{SOCKET_PREFIX}{name}.sock")


def kernel_call(name: str, cmd: str, code: str = "") -> tuple[str, bool]:
    path = socket_path(name)
    if not os.path.exists(path):
        return f"kernel '{name}' is not running", True
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(path)
            s.sendall(json.dumps({"cmd": cmd, "code": code}).encode() + b"\n")
            f = s.makefile("rb")
            data = json.loads(f.readline())
        if data["ok"]:
            return data["result"] or "(done)", False
        else:
            return data["error"], True
    except Exception as e:
        return f"{type(e).__name__}: {e}", True


def list_kernels() -> tuple[str, bool]:
    import glob
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
    return (", ".join(names) if names else "(none)"), False


def kernel_vars_text(name: str) -> str:
    path = socket_path(name)
    if not os.path.exists(path):
        return ""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(path)
            s.sendall(json.dumps({"cmd": "vars", "code": ""}).encode() + b"\n")
            data = json.loads(s.makefile("rb").readline())
        if not data.get("ok"):
            return ""
        variables = data.get("result", {})
        if not variables:
            return "\nvariables: (none)"
        lines = "\n".join(f"  {k} = {v}" for k, v in variables.items())
        return f"\nvariables:\n{lines}"
    except Exception:
        return ""


def connect_kernel(name: str) -> tuple[str, bool]:
    path = socket_path(name)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(path)
        return f"connected to kernel '{name}'" + kernel_vars_text(name), False
    except OSError:
        return f"kernel '{name}' is not running", True


def spawn_kernel(name: str, python: str) -> tuple[str, bool]:
    path = socket_path(name)
    if os.path.exists(path):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(path)
            return f"kernel '{name}' already running" + kernel_vars_text(name), False
        except OSError:
            os.remove(path)

    try:
        subprocess.Popen(
            [python, KERNEL_SCRIPT, name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        return f"python executable not found: {python}", True

    for _ in range(20):
        time.sleep(0.1)
        if os.path.exists(path):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.connect(path)
                return f"kernel '{name}' started" + kernel_vars_text(name), False
            except OSError:
                continue

    return "kernel did not start in time", True


def respond(id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id, "result": result}) + "\n")
    sys.stdout.flush()


def error(id, code, message):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()


def handle(req):
    id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    if method == "initialize":
        respond(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "python-kernel", "version": "1.0.0"},
        })
    elif method == "tools/list":
        respond(id, {"tools": TOOLS})
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        kernel_name = args.get("name", "default")
        if name == "kill_python_kernel":
            result, is_error = kernel_call(kernel_name, "die")
            if is_error and "ConnectionReset" in result or "BrokenPipe" in result:
                result, is_error = f"kernel '{kernel_name}' killed", False
        elif name == "list_python_kernels":
            result, is_error = list_kernels()
        elif name == "connect_python_kernel":
            result, is_error = connect_kernel(kernel_name)
        elif name == "spawn_python_kernel":
            result, is_error = spawn_kernel(kernel_name, args.get("python", sys.executable))
        else:
            result, is_error = kernel_call(kernel_name, name, args.get("code", ""))
        respond(id, {"content": [{"type": "text", "text": str(result)}], "isError": is_error})
    elif method == "notifications/initialized":
        pass
    elif id is not None:
        error(id, -32601, f"method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(req)


if __name__ == "__main__":
    main()
