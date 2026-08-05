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
    fetch_workday,
    matches_filters,
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
            "slug": "finance-analyst",
            "careers_url": "https://mclaren.recruitee.com/o/finance-analyst",
            "location": {"city": "Woking", "country": "UK"},
            "department": "Finance"
        }]})
    ])
    jobs = fetch_recruitee({"name": "McLaren", "account": "mclaren"}, session, 10)
    assert jobs[0].title == "Finance Analyst"
    assert "Woking" in jobs[0].location


def test_pinpoint():
    session = FakeSession([
        FakeResponse({"data": [{
            "id": "118475",
            "title": "Management Accountant",
            "url": "https://astonmartinf1.pinpointhq.com/en/postings/abc",
            "location": {"id": "1", "name": "Silverstone"},
            "department": {"id": "2", "name": "Finance"},
            "description": "Month-end accounting"
        }]})
    ])
    jobs = fetch_pinpoint({"name": "Aston", "subdomain": "astonmartinf1"}, session, 10)
    assert jobs[0].location == "Silverstone"
    assert jobs[0].title == "Management Accountant"


def test_personio():
    xml = """<workzag-jobs><position><id>2687441</id><name>Cost Cap Analyst</name>
    <office>Hinwil</office><department>Cost Cap</department><createdAt>2026-07-01</createdAt>
    <jobDescriptions><jobDescription><value><![CDATA[Finance compliance]]></value></jobDescription></jobDescriptions>
    </position></workzag-jobs>"""
    session = FakeSession([FakeResponse(text=xml, content_type="application/xml")])
    jobs = fetch_personio({"name": "Audi", "account": "audif1", "domain": "de"}, session, 10)
    assert jobs[0].external_id == "2687441"
    assert "Cost Cap" in jobs[0].title


def test_workday():
    session = FakeSession([
        FakeResponse({
            "total": 1,
            "jobPostings": [{
                "title": "Financial Controller",
                "externalPath": "/job/Enstone/Financial-Controller_R123",
                "locationsText": "Enstone",
                "postedOn": "Posted Today"
            }]
        })
    ])
    jobs = fetch_workday({
        "name": "Alpine", "host": "example.myworkdayjobs.com",
        "tenant": "tenant", "site": "careers", "max_pages": 1
    }, session, 10)
    assert jobs[0].title == "Financial Controller"
    assert "/careers/job/" in jobs[0].url


def test_bamboohr():
    session = FakeSession([
        FakeResponse({"result": [{
            "id": 44,
            "jobOpeningName": "Senior Accountant",
            "location": {"city": "Kannapolis", "state": "NC"},
            "departmentLabel": "Accounting"
        }]})
    ])
    jobs = fetch_bamboohr({"name": "Haas", "subdomain": "haasf1team"}, session, 10)
    assert jobs[0].title == "Senior Accountant"
    assert jobs[0].url.endswith("/44")


def test_adp():
    session = FakeSession([
        FakeResponse({"jobRequisitions": [{
            "itemID": "A-42",
            "requisitionTitle": "Accounting Manager",
            "positionLocation": {"displayName": "Indianapolis, IN"},
            "postedDate": "2026-08-01"
        }]})
    ])
    jobs = fetch_adp_wfn({
        "name": "Andretti", "cid": "cid", "ccid": "ccid"
    }, session, 10)
    assert jobs[0].title == "Accounting Manager"
    assert jobs[0].location == "Indianapolis, IN"



def test_oracle_hcm():
    session = FakeSession([
        FakeResponse({
            "items": [{
                "TotalJobsCount": 1,
                "requisitionList": [{
                    "Id": "10123",
                    "Title": "Finance Business Partner",
                    "PrimaryLocation": "Milton Keynes, UK",
                    "PostedDate": "2026-08-02",
                    "JobFunction": "Finance"
                }]
            }]
        })
    ])
    jobs = fetch_oracle_hcm({
        "name": "Red Bull Racing",
        "base_url": "https://careers.example.com",
        "site_number": "CX_2",
        "careers_base_url": "https://careers.example.com/en/sites/CX_2",
        "max_pages": 1
    }, session, 10)
    assert jobs[0].title == "Finance Business Partner"
    assert jobs[0].url.endswith("/job/10123")


def test_link_page():
    page = """<html><body><article class='job-card'><h3>Finance Business Partner</h3>
    <span class='location'>Brackley</span><a href='/careers/vacancies/783'>View Details</a>
    </article></body></html>"""
    session = FakeSession([FakeResponse(text=page, content_type="text/html")])
    jobs = fetch_link_page({
        "name": "Mercedes", "url": "https://example.com/careers/vacancies",
        "include_url_regex": r"/careers/vacancies/\d+", "respect_robots": False
    }, session, 10, "test")
    assert jobs[0].title == "Finance Business Partner"


if __name__ == "__main__":
    test_filters()
    test_state_store()
    test_recruitee()
    test_pinpoint()
    test_personio()
    test_workday()
    test_bamboohr()
    test_adp()
    test_oracle_hcm()
    test_link_page()
    print("All local tests passed.")
