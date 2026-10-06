import sys
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from artist_enrichment_pilot import read_json, write_json
from artist_enrichment_worker import (
    CodexAudit,
    EnrichmentWorker,
    codex_command,
    subscription_environment,
)
from artist_pilot_server import ReviewStore


@pytest.fixture
def worker(tmp_path):
    write_json(
        tmp_path / "artists.json",
        [{"artist_id": "a", "display_name": "Test", "representative_titles": ["Song"]}],
    )
    write_json(tmp_path / "observations.json", [])
    write_json(tmp_path / "musicbrainz.json", {"artists": {}, "runs": []})
    audit = Mock()
    audit.run.return_value = (
        [
            {
                "artist_id": "a",
                "roles": [],
                "bass_related": None,
                "interest_proposal": "uncertain",
                "identity_status": "unresolved",
                "links": [],
                "sources": [],
                "reason": "Unknown",
                "issues": [],
            }
        ],
        {"input_tokens": 10},
    )
    client = Mock(requests=1, cache_hits=0)
    client.get.return_value = {"artists": []}
    return EnrichmentWorker(ReviewStore(tmp_path), audit, client)


def wait(worker):
    worker.thread.join(3)
    assert not worker.thread.is_alive()


def test_idle_does_not_call_any_provider(worker):
    assert worker.snapshot()["status"] == "idle"
    worker.audit.preflight.assert_not_called()
    worker.client.get.assert_not_called()


def test_explicit_start_publishes_without_validating(worker):
    worker.action({"action": "start"})
    wait(worker)
    assert worker.snapshot()["counts"]["ready"] == 1
    assert worker.snapshot()["usage"]["input_tokens"] == 10
    assert worker.store.reviews() == {}
    assert read_json(worker.store.directory / "observations.json")[0]["artist_id"] == "a"
    assert "path" not in str(worker.audit.run.call_args.args[0])


def test_invalid_audit_does_not_publish_and_retry_uses_mb_checkpoint(worker):
    worker.audit.run.return_value = ([], {})
    worker.action({"action": "start"})
    wait(worker)
    assert worker.snapshot()["status"] == "paused"
    assert worker.snapshot()["counts"]["error"] == 1
    assert read_json(worker.store.directory / "observations.json") == []
    worker.action({"action": "retry"})
    wait(worker)
    assert worker.client.get.call_count == 1


def test_subscription_failure_does_not_lookup_or_audit(worker):
    worker.audit.preflight.side_effect = RuntimeError("ChatGPT required")
    worker.action({"action": "start"})
    wait(worker)
    worker.client.get.assert_not_called()
    worker.audit.run.assert_not_called()
    assert worker.snapshot()["counts"]["queued"] == 1


def test_validation_during_audit_wins(worker):
    def audit(*args):
        worker.store.save_page(
            {"a": {"decision": "exclude", "roles": ["MC"], "bass_related": False}}
        )
        return worker.audit.run.return_value

    worker.audit.run.side_effect = audit
    worker.action({"action": "start"})
    wait(worker)
    assert worker.store.reviews()["a"]["tags"] == ["idgaf"]
    assert read_json(worker.store.directory / "observations.json") == []
    assert worker.snapshot()["counts"]["validated"] == 1


def test_pause_finishes_current_batch(worker):
    entered, release = threading.Event(), threading.Event()
    result = worker.audit.run.return_value

    def audit(*args):
        entered.set()
        assert release.wait(2)
        return result

    worker.audit.run.side_effect = audit
    worker.action({"action": "start"})
    assert entered.wait(2)
    worker.action({"action": "pause"})
    release.set()
    wait(worker)
    assert worker.snapshot()["status"] == "paused"
    assert worker.snapshot()["counts"]["ready"] == 1


def test_api_credentials_removed_and_command_fixed(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "private")
    monkeypatch.setenv("CODEX_API_KEY", "private")
    assert "OPENAI_API_KEY" not in subscription_environment()
    assert "CODEX_API_KEY" not in subscription_environment()
    command = codex_command("codex.exe", tmp_path)
    assert command[command.index("-m") + 1] == "gpt-6-luna"
    assert 'model_reasoning_effort="low"' in command
    assert 'forced_login_method="chatgpt"' in command
    assert "read-only" in command


def test_api_login_rejected(monkeypatch):
    run = Mock(return_value=Mock(returncode=0, stdout="Logged in using an API key", stderr=""))
    monkeypatch.setattr("artist_enrichment_worker.subprocess.run", run)
    with pytest.raises(RuntimeError, match="API refusée"):
        CodexAudit("codex.exe").preflight()


def test_stop_discards_inflight_output_and_restart_stays_idle(worker):
    entered, release = threading.Event(), threading.Event()
    result = worker.audit.run.return_value

    def audit(*args):
        entered.set()
        assert release.wait(2)
        return result

    worker.audit.run.side_effect = audit
    worker.action({"action": "start"})
    assert entered.wait(2)
    worker.action({"action": "stop"})
    release.set()
    wait(worker)
    assert worker.snapshot()["counts"]["queued"] == 1
    assert read_json(worker.store.directory / "observations.json") == []
    restarted = EnrichmentWorker(worker.store, Mock(), Mock())
    assert restarted.snapshot()["status"] == "idle"
    restarted.audit.preflight.assert_not_called()


def test_unsourced_profiles_are_rejected(worker):
    row = worker.audit.run.return_value[0][0]
    row["links"] = [
        {
            "url": "https://soundcloud.com/example",
            "label": "SoundCloud",
            "evidence_url": "https://example.com",
        }
    ]
    worker.action({"action": "start"})
    wait(worker)
    assert worker.snapshot()["counts"]["error"] == 1
    assert read_json(worker.store.directory / "observations.json") == []


def test_codex_process_protocol_without_inference(monkeypatch, tmp_path, worker):
    script = tmp_path / "fake_codex.py"
    script.write_text(
        "import json, pathlib, sys\n"
        "sys.stdin.read()\n"
        "pathlib.Path(sys.argv[1], 'result.json').write_text(sys.argv[2])\n"
        "print(json.dumps({'type':'turn.completed','usage':{'output_tokens':7}}))\n",
        encoding="utf-8",
    )
    import json

    result = json.dumps({"observations": worker.audit.run.return_value[0]})
    monkeypatch.setattr(
        "artist_enrichment_worker.codex_command",
        lambda executable, directory: [sys.executable, str(script), str(directory), result],
    )
    rows, usage = CodexAudit("unused").run([], threading.Event(), Mock())
    assert rows[0]["artist_id"] == "a"
    assert usage == {"output_tokens": 7}


def test_second_worker_cannot_start_same_collection(worker):
    worker.acquire_execution_lock()
    other = EnrichmentWorker(worker.store, Mock(), worker.client)
    try:
        with pytest.raises(ValueError, match="autre worker"):
            other.action({"action": "start"})
        other.audit.preflight.assert_not_called()
    finally:
        worker.execution_lock.close()
        worker.execution_lock = None


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "launch"},
        {"action": "start", "batch_size": 0},
        {"action": "start", "batch_size": True},
    ],
)
def test_invalid_controls(worker, payload):
    with pytest.raises(ValueError):
        worker.action(payload)
