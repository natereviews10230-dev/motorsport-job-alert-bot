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
    build_ntfy_view_actions,
    notify_ntfy,
    notify_ntfy_summary,
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


def test_source_extra_title_any():
    global_filters = {"title_any": ["finance", "accounting"]}
    source = {"extra_title_any": ["merchandising", "licensing"]}
    merged = merge_source_title_filters(global_filters, source)
    job = Job(
        source_name="Stellantis - Auburn Hills",
        source_type="browser_link_page",
        external_id="1",
        title="Merchandising Manager",
        company="Stellantis",
        location="Auburn Hills, MI",
        url="https://careers.stellantis.com/job/1/example/",
    )
    assert matches_filters(job, merged)
    assert matches_filters(job, {"location_any": ["Auburn Hills"]})


def test_summary_marks_new_and_is_compact():
    old_job = Job("A", "link_page", "1", "Financial Analyst", "Team A", "UK", "https://x/1")
    new_job = Job("B", "link_page", "2", "Licensing Manager", "Stellantis", "Auburn Hills, MI", "https://x/2")
    body = format_current_jobs_summary([old_job, new_job], {new_job.fingerprint}, max_bytes=3800)
    assert "2 current matches • 1 new" in body
    assert "🆕 Licensing Manager" in body
    assert "• Financial Analyst" in body
    assert len(body.encode("utf-8")) <= 3800


def test_parse_rendered_stellantis_page():
    page = """<html><body><li class='job-result'>
    <a href='https://careers.stellantis.com/job/23579847/model-controller-auburn-hills-mi/'>Model Controller</a>
    <span>Headquarters & Technology Center - Auburn Hills, MI</span>
    </li></body></html>"""
    jobs = parse_link_page_html({
        "name": "Stellantis - Auburn Hills",
        "company": "Stellantis",
        "include_url_regex": r"careers\.stellantis\.com/job/\d+/",
        "location_regex": r"(?P<location>Auburn Hills(?:,?\s*MI)?)",
    }, "https://careers.stellantis.com/job-search-results/", page, source_type="browser_link_page")
    assert len(jobs) == 1
    assert jobs[0].title == "Model Controller"
    assert "Auburn Hills" in jobs[0].location


def test_new_only_summary_wording():
    job = Job("A", "link_page", "1", "Model Controller", "Stellantis", "Auburn Hills, MI", "https://x/1")
    body = format_jobs_summary([job], {job.fingerprint}, summary_kind="new", max_bytes=3800)
    assert "1 new job match" in body
    assert "🆕 Model Controller" in body
    assert "current matches" not in body


def test_stellantis_merchandising_extra_titles():
    global_filters = {"title_any": ["finance", "accounting"]}
    source = {"extra_title_any": ["licensing", "merchandising", "accessory product"]}
    merged = merge_source_title_filters(global_filters, source)
    job = Job(
        source_name="Stellantis - Auburn Hills",
        source_type="browser_link_page",
        external_id="2",
        title="Jeep Accessory Product Planner",
        company="Stellantis",
        location="Auburn Hills, MI",
        url="https://careers.stellantis.com/job/2/example/",
    )
    assert matches_filters(job, merged)
    assert matches_filters(job, {"location_any": ["Auburn Hills"]})


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
    test_source_extra_title_any()
    test_summary_marks_new_and_is_compact()
    test_parse_rendered_stellantis_page()
    test_new_only_summary_wording()
    test_stellantis_merchandising_extra_titles()
    print("All local tests passed.")


def test_commercial_financial_analyst_matches_auburn_hills():
    job = Job(
        source_name="Stellantis - Auburn Hills",
        source_type="browser_link_page",
        external_id="23599999",
        title="Commercial Financial Analyst",
        company="Stellantis",
        location="Auburn Hills, MI, US",
        url="https://careers.stellantis.com/job/23599999/commercial-financial-analyst-auburn-hills-mi/",
    )
    assert matches_filters(job, {"title_any": ["financial", "commercial analyst"]})
    assert matches_filters(job, {"location_any": ["Auburn Hills"]})


def test_buyer_matches_procurement_family():
    job = Job(
        source_name="Red Bull Racing & Technology",
        source_type="browser_link_page",
        external_id="123",
        title="Senior Buyer",
        company="Red Bull Racing & Red Bull Technology",
        location="Milton Keynes, UK",
        url="https://careers.redbullracing.com/en/sites/CX_2/job/123",
    )
    assert matches_filters(job, {"title_any": ["buyer", "procurement", "sourcing"]})


def test_detail_jsonld_enrichment():
    from job_watcher import enrich_job_from_detail_html
    base = Job(
        source_name="Stellantis - Auburn Hills",
        source_type="browser_link_page",
        external_id="23599999",
        title="Learn more",
        company="Stellantis",
        location="",
        url="https://careers.stellantis.com/job/23599999/commercial-financial-analyst-auburn-hills-mi/",
    )
    page = '''<html><head><script type="application/ld+json">{
      "@context":"https://schema.org","@type":"JobPosting",
      "title":"Commercial Financial Analyst",
      "datePosted":"2026-08-07",
      "description":"Commercial finance analysis",
      "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
        "addressLocality":"Auburn Hills","addressRegion":"MI","addressCountry":"US"}}
    }</script></head><body><h1>Commercial Financial Analyst</h1></body></html>'''
    enriched = enrich_job_from_detail_html(base, page, {
        "location_regex": r"(?P<location>Auburn Hills(?:,?\s*MI)?)"
    })
    assert enriched.title == "Commercial Financial Analyst"
    assert "Auburn Hills" in enriched.location
    assert "MI" in enriched.location


def _live_config():
    return json.loads((Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))


def test_v5_regression_titles_from_user_misses():
    cfg = _live_config()
    filters = cfg['filters']
    cases = [
        ('Business Performance Analyst', 'Red Bull Racing'),
        ('Finance Business Partner', 'Mercedes F1'),
        ('Accounts Payable Specialist', 'Williams F1'),
        ('Accounts Assistant', 'Aston Martin F1'),
        ('VCARB F1 Team - Buyer (Composite)', 'VCARB'),
        ('Internal Control Analyst', 'Ford'),
        ('Commercial Financial Analyst', 'Stellantis'),
    ]
    for idx, (title, company) in enumerate(cases, 1):
        job = Job(
            source_name=company,
            source_type='test',
            external_id=str(idx),
            title=title,
            company=company,
            location='Auburn Hills, MI' if company == 'Stellantis' else 'Test',
            url=f'https://example.com/{idx}',
        )
        assert matches_filters(job, filters), title


def test_finance_department_metadata_can_rescue_generic_title():
    cfg = _live_config()
    job = Job(
        source_name='Test',
        source_type='test',
        external_id='dept-1',
        title='Operations Assistant',
        company='Example',
        location='Silverstone',
        url='https://example.com/dept-1',
        description='Department: Finance Employment Type: Permanent',
    )
    assert matches_filters(job, cfg['filters'])


def test_ford_source_or_filter_accepts_internal_control_exception():
    cfg = _live_config()
    ford = next(s for s in cfg['sources'] if s['name'] == 'Ford Racing')
    job = Job(
        source_name='Ford Racing',
        source_type='oracle_hcm',
        external_id='66034',
        title='Internal Control Analyst',
        company='Ford',
        location='Dearborn, Michigan',
        url='https://www.careers.ford.com/job/dearborn/internal-control-analyst/48560/97252488272',
        description='Category: Finance; SOX controls and reporting',
    )
    assert matches_filters(job, ford['filters'])
    assert matches_filters(job, cfg['filters'])


def test_stellantis_sales_marketing_expansion_stays_auburn_hills_scoped():
    cfg = _live_config()
    stellantis = next(s for s in cfg['sources'] if s['name'] == 'Stellantis - Auburn Hills')
    merged = merge_source_title_filters(cfg['filters'], stellantis)
    good = Job(
        'Stellantis - Auburn Hills', 'browser_link_page', '1',
        'Sales Planning Analyst', 'Stellantis', 'Auburn Hills, MI', 'https://example.com/1'
    )
    bad_location = Job(
        'Stellantis - Auburn Hills', 'browser_link_page', '2',
        'Marketing Analyst', 'Stellantis', 'Detroit, MI', 'https://example.com/2'
    )
    assert matches_filters(good, merged)
    assert matches_filters(good, stellantis['filters'])
    assert matches_filters(bad_location, merged)
    assert not matches_filters(bad_location, stellantis['filters'])


def test_link_page_detail_enrichment_recovers_mercedes_title():
    listing = """<html><body><article class='job-card'>
    <a href='/careers/vacancies/783'>View Details</a></article></body></html>"""
    detail = """<html><head><title>Finance Business Partner - Mercedes-AMG PETRONAS F1 Team</title></head>
    <body><h1>Vacancies</h1><div>Finance team budgeting forecasting</div></body></html>"""
    session = FakeSession([
        FakeResponse(text=listing, content_type='text/html'),
        FakeResponse(text=detail, content_type='text/html'),
    ])
    jobs = fetch_link_page({
        'name': 'Mercedes',
        'url': 'https://example.com/careers/vacancies',
        'include_url_regex': r'/careers/vacancies/\d+',
        'respect_robots': False,
        'enrich_job_details': True,
        'prefer_page_title': True,
        'page_title_strip_regex': r'\s*-\s*Mercedes-AMG PETRONAS F1 Team.*$',
        'detail_description_from_page': True,
    }, session, 10, 'test')
    assert jobs[0].title == 'Finance Business Partner'


def test_redbull_preview_link_pattern_accepts_known_posting_shape():
    cfg = _live_config()
    rbr = next(s for s in cfg['sources'] if s['name'] == 'Red Bull Racing & Technology')
    page = """<html><body><article class='job-card'><h3>Business Performance Analyst</h3>
    <a href='https://careers.redbullracing.com/en/sites/CX_2/jobs/preview/10134'>Apply Now</a>
    </article></body></html>"""
    jobs = parse_link_page_html(rbr, rbr['url'], page, source_type='browser_link_page')
    assert len(jobs) == 1
    assert 'Business Performance Analyst' in jobs[0].title


class CaptureSession:
    def __init__(self):
        self.posts = []

    def post(self, *args, **kwargs):
        self.posts.append((args, kwargs))
        return FakeResponse({"id": "test"})


def test_ntfy_single_job_apply_now_action(monkeypatch=None):
    job = Job(
        'Mercedes', 'link_page', '783', 'Finance Business Partner',
        'Mercedes-AMG PETRONAS F1 Team', 'Brackley, UK',
        'https://www.mercedesamgf1.com/careers/vacancies/783'
    )
    actions = build_ntfy_view_actions([job])
    assert actions == 'view, Apply Now, https://www.mercedesamgf1.com/careers/vacancies/783'


def test_ntfy_multiple_jobs_get_up_to_three_apply_actions():
    jobs = [
        Job('A', 'test', '1', 'Finance Business Partner', 'Team A', 'UK', 'https://example.com/1'),
        Job('B', 'test', '2', 'Accounts Payable Specialist', 'Team B', 'UK', 'https://example.com/2'),
        Job('C', 'test', '3', 'Business Performance Analyst', 'Team C', 'UK', 'https://example.com/3'),
        Job('D', 'test', '4', 'Internal Control Analyst', 'Team D', 'US', 'https://example.com/4'),
    ]
    actions = build_ntfy_view_actions(jobs)
    assert actions.count('view, ') == 3
    assert 'https://example.com/1' in actions
    assert 'https://example.com/2' in actions
    assert 'https://example.com/3' in actions
    assert 'https://example.com/4' not in actions


def test_ntfy_action_header_encodes_separator_characters():
    job = Job(
        'A', 'test', '1', 'Finance, Strategy; Analyst', 'Team', 'UK',
        'https://example.com/apply?x=1,2;y=3'
    )
    actions = build_ntfy_view_actions([job])
    assert 'Apply Now' in actions
    assert '%2C' in actions
    assert '%3B' in actions


def test_notify_ntfy_sends_apply_button(monkeypatch):
    monkeypatch.setenv('NTFY_TOPIC', 'test-topic')
    monkeypatch.setenv('NTFY_SERVER', 'https://ntfy.sh')
    job = Job('A', 'test', '1', 'Finance Analyst', 'Team', 'UK', 'https://example.com/apply/1')
    session = CaptureSession()
    notify_ntfy(job, session, 10)
    headers = session.posts[0][1]['headers']
    assert headers['Actions'] == 'view, Apply Now, https://example.com/apply/1'
    assert headers['Click'] == job.url


def test_notify_ntfy_summary_sends_apply_buttons(monkeypatch):
    monkeypatch.setenv('NTFY_TOPIC', 'test-topic')
    monkeypatch.setenv('NTFY_SERVER', 'https://ntfy.sh')
    jobs = [
        Job('A', 'test', '1', 'Finance Analyst', 'Team A', 'UK', 'https://example.com/apply/1'),
        Job('B', 'test', '2', 'Accounts Assistant', 'Team B', 'UK', 'https://example.com/apply/2'),
    ]
    session = CaptureSession()
    notify_ntfy_summary(jobs, {j.fingerprint for j in jobs}, session, 10, summary_kind='new')
    headers = session.posts[0][1]['headers']
    assert headers['Actions'].count('view, ') == 2
    assert 'https://example.com/apply/1' in headers['Actions']
    assert 'https://example.com/apply/2' in headers['Actions']
