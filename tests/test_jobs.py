import time

from dfxm_geo_mcp.jobs import JobRegistry


def test_job_succeeds_and_returns_result():
    reg = JobRegistry()
    jid = reg.submit(("k", 1), lambda report: 42)
    for _ in range(100):
        if reg.status(jid).state in ("succeeded", "failed"):
            break
        time.sleep(0.02)
    assert reg.status(jid).state == "succeeded"
    assert reg.result(jid) == 42


def test_dedup_returns_same_id_for_live_key():
    reg = JobRegistry()
    started = []

    def slow(report):
        started.append(1)
        time.sleep(0.2)
        return 1

    a = reg.submit(("dup",), slow)
    b = reg.submit(("dup",), slow)
    assert a == b


def test_failing_job_surfaces_error():
    reg = JobRegistry()

    def boom(report):
        raise RuntimeError("kaboom")

    jid = reg.submit(("e",), boom)
    for _ in range(100):
        if reg.status(jid).state in ("succeeded", "failed"):
            break
        time.sleep(0.02)
    assert reg.status(jid).state == "failed"
    assert "kaboom" in (reg.status(jid).error or "")
