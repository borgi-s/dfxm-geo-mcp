"""Regression test over the REAL subprocess stdio transport.

The rest of the suite drives the server via the in-memory ``fastmcp.Client(mcp)``,
which never spawns a process, never opens a JSON-RPC stdin pipe, and so never
exercised the path that hung in Claude Desktop: dfxm-geo's git-SHA provenance
shelled out to ``git`` without isolating stdin, so behind the stdin pipe the git
child's ``communicate()`` blocked forever and ``run_forward`` never returned.

This test launches the actual server process and speaks raw newline-delimited
JSON-RPC to it (initialize -> initialized -> tools/call run_forward), asserting
the tool returns promptly instead of hanging.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time

import pytest

from dfxm_geo_mcp import runtime


def _await_response(lines: queue.Queue, want_id: int, timeout: float) -> dict | None:
    """Drain the server's stdout queue until a JSON-RPC reply with ``want_id`` arrives.

    Notifications (no ``id``) and any non-JSON noise are skipped. Returns None on timeout.
    """
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            raw = lines.get(timeout=remaining)
        except queue.Empty:
            return None
        text = raw.decode(errors="replace").strip()
        if not text:
            continue
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == want_id:
            return msg


@pytest.mark.slow
def test_run_forward_over_real_stdio_transport_does_not_hang() -> None:
    # Warm the shared on-disk numba cache in-process first, so the spawned
    # server's first run_forward pays no cold-JIT cost and the timeout below
    # measures a hang, not a slow first compile.
    runtime.configure_numba_cache()
    runtime.point_kernel_lookup_at_cache()
    from dfxm_geo_mcp.ops.forward import run_forward

    run_forward("")

    proc = subprocess.Popen(
        [sys.executable, "-m", "dfxm_geo_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    lines: queue.Queue = queue.Queue()

    def _pump() -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            lines.put(raw)

    threading.Thread(target=_pump, daemon=True).start()

    def send(obj: dict) -> None:
        assert proc.stdin is not None
        proc.stdin.write((json.dumps(obj) + "\n").encode())
        proc.stdin.flush()

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            }
        )
        assert _await_response(lines, 0, 30) is not None, (
            "no initialize response — server failed to attach over stdio"
        )

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "run_forward", "arguments": {"toml_text": ""}},
            }
        )

        reply = _await_response(lines, 1, 60)
        assert reply is not None, (
            "run_forward hung over the real stdio transport (no response within 60s)"
        )
        assert "error" not in reply, f"run_forward errored over stdio: {reply.get('error')}"
        assert "result" in reply
    finally:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
