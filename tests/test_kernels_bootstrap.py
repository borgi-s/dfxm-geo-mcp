"""Bootstrap runs the chatty MC kernel build in a CHILD PROCESS.

generate_kernel prints ~50s of chatter to stdout. start_bootstrap runs bootstrap
in a JobRegistry background thread concurrently with the stdio server, so that
chatter would corrupt the JSON-RPC channel on the real stdout. A process-global
redirect from that concurrent thread is unsafe (it would also swallow the
server's own writes — the Bug-A failure mode), so the build is isolated in a
subprocess whose stdout is discarded and whose stdin is pinned to DEVNULL.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dfxm_geo_mcp import kernels, runtime


def test_run_kernel_worker_discards_child_stdout(tmp_path, monkeypatch, capfd):
    # A stub "kernel build" that floods stdout (would corrupt JSON-RPC if leaked)
    # and writes the npz. Driven through the REAL subprocess plumbing.
    stub = tmp_path / "chatty_stub.py"
    stub.write_text(
        "import json, sys\n"
        "spec = json.loads(sys.argv[1])\n"
        "print('CHATTY ' * 2000)\n"
        "sys.stderr.write('a warning\\n')\n"
        "open(spec['output_path'], 'wb').write(b'x')\n",
        encoding="utf-8",
    )
    out = tmp_path / "k.npz"
    monkeypatch.setattr(kernels, "_WORKER_CMD", [sys.executable, str(stub)])

    kernels._run_kernel_worker({"output_path": str(out)})

    assert out.exists()
    captured = capfd.readouterr()
    assert "CHATTY" not in captured.out  # child stdout never reached our fd 1


def test_run_kernel_worker_raises_with_stderr_tail_on_failure(tmp_path, monkeypatch):
    stub = tmp_path / "boom_stub.py"
    stub.write_text(
        "import sys\n"
        "sys.stderr.write('boom-traceback-marker\\n')\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kernels, "_WORKER_CMD", [sys.executable, str(stub)])

    with pytest.raises(RuntimeError, match="boom-traceback-marker"):
        kernels._run_kernel_worker({"output_path": str(tmp_path / "x.npz")})


def test_bootstrap_reports_progress_and_returns_written_path(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    (tmp_path / "kernels").mkdir()

    seen = {}

    def fake_seam(spec: dict) -> None:
        seen["spec"] = spec
        Path(spec["output_path"]).write_bytes(b"kernel")

    monkeypatch.setattr(kernels, "_run_kernel_worker", fake_seam)

    reports: list[tuple[float, str]] = []
    path = kernels.bootstrap(
        (1, 2, 3), 17.0, mount_toml=None, report=lambda p, m: reports.append((p, m))
    )

    assert Path(path).name.startswith("Resq_i_h1_k2_l3_17keV_")
    assert Path(path).exists()
    assert seen["spec"]["hkl"] == [1, 2, 3]
    assert seen["spec"]["keV"] == 17.0
    assert reports[0][0] == 0.0
    assert reports[-1][0] == 1.0
    assert capfd.readouterr().out == ""  # bootstrap itself leaks nothing to stdout


def test_bootstrap_raises_if_worker_wrote_no_kernel(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    (tmp_path / "kernels").mkdir()
    monkeypatch.setattr(kernels, "_run_kernel_worker", lambda spec: None)  # writes nothing

    with pytest.raises(RuntimeError, match="not written"):
        kernels.bootstrap((1, 1, 1), 17.0, mount_toml=None, report=lambda p, m: None)


def test_kernel_worker_run_invokes_generate_kernel_with_resolved_mount(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    out = tmp_path / "k.npz"
    seen = {}

    def fake_generate_kernel(*, date, output_path, hkl, keV, mount):
        seen.update(date=date, hkl=hkl, keV=keV, mount=mount)
        Path(output_path).write_bytes(b"npz")
        return Path(output_path)

    monkeypatch.setattr(
        "dfxm_geo.reciprocal_space.kernel.generate_kernel", fake_generate_kernel
    )

    from dfxm_geo_mcp import _kernel_worker

    result = _kernel_worker.run(
        {
            "hkl": [1, 2, 3],
            "keV": 17.0,
            "mount_toml": None,
            "output_path": str(out),
            "date": "20260101_0000",
        }
    )

    assert result == out
    assert out.read_bytes() == b"npz"
    assert seen["hkl"] == (1, 2, 3)
    assert seen["keV"] == 17.0
    assert seen["date"] == "20260101_0000"
    assert seen["mount"] is not None  # default Al mount resolved for mount_toml=None
