import json
import tempfile
from pathlib import Path

from job_watcher import (
    Job,
    StateStore,
    fetch_adp_wfn,
    fetch_bamboohr,
    fetch_link_page,
    fetch_oracle_hcm,
    fetch_personio,
    fetch_pinpoint,
    fetch_recruitee,
    fetch_smartrecruiters,
    fetch_workable,
    fetch_workday,
    matches_filters,
    build_ntfy_view_actions,
    notify_ntfy,
    notify_ntfy_summary,
    write_current_matches_report,
    format_current_jobs_summary,
    format_jobs_summary,
    merge_source_title_filters,
    parse_link_page_html,
)


class FakeResponse:
    def __init__(self, payload=None, text="", content_type="application/json"):
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")
        self.content = self.text.encode("utf-8")
        self.headers = {"content-type": content_type}
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, *args, **kwargs):
        return self.responses.pop(0)

    def post(self, *args, **kwargs):
        return self.responses.pop(0)


def test_filters():
    job = Job(
        source_name="Test",
        source_type="greenhouse",
        external_id="123",
        title="Cost Cap Analyst",
        company="Example",
        location="Hinwil, Switzerland",
        url="https://example.com/job/123",
        description="Finance and FIA financial regulations",
    )
    assert matches_filters(job, {"title_any": ["finance", "cost cap"]})
    assert not matches_filters(job, {"title_any": ["accountant"]})


def test_state_store():
    with tempfile.TemporaryDirectory() as temp:
        store = StateStore(Path(temp) / "state.sqlite3")
        job = Job(
            source_name="Test",
            source_type="lever",
            external_id="abc",
            title="Controller",
            company="Example",
            location="Detroit",
            url="https://example.com/jobs/abc",
        )
        assert not store.has_seen(job.fingerprint)
        store.record(job)
        assert store.has_seen(job.fingerprint)
        assert not store.source_initialized("Test")
        store.mark_source_initialized("Test")
        assert store.source_initialized("Test")
        store.close()


def test_recruitee():
    session = FakeSession([
        FakeResponse({"offers": [{
            "id": 7,
            "title": "Finance Analyst",
