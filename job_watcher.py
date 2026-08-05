#!/usr/bin/env python3
"""
Cloud-ready personal motorsport job alert bot.

The bot monitors public employer career systems directly, filters finance, accounting, planning, strategy, and closely related roles,
stores seen jobs in SQLite, and sends push notifications.
It does not sign in to or scrape LinkedIn.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_USER_AGENT = (
    "PersonalJobAlertBot/2.0 "
    "(personal job-search notifier; public career pages; low request volume)"
)
SUPPORTED_SOURCE_TYPES = {
    "greenhouse",
    "lever",
    "recruitee",
    "pinpoint",
    "personio",
    "workday",
    "bamboohr",
    "adp_wfn",
    "oracle_hcm",
    "html",
    "link_page",
}


@dataclass(frozen=True)
class Job:
    source_name: str
    source_type: str
    external_id: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    posted_at: str = ""

    @property
    def fingerprint(self) -> str:
        raw = "|".join(
            [
                self.source_name.strip().casefold(),
                self.external_id.strip().casefold(),
                self.url.strip().casefold(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_jobs (
                fingerprint TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                external_id TEXT NOT NULL,
                first_seen_utc TEXT NOT NULL,
                last_seen_utc TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_state (
                source_name TEXT PRIMARY KEY,
                initialized_utc TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def source_initialized(self, source_name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM source_state WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        return row is not None

    def mark_source_initialized(self, source_name: str) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO source_state(source_name, initialized_utc)
            VALUES (?, ?)
            ON CONFLICT(source_name) DO NOTHING
            """,
            (source_name, now),
        )
        self.conn.commit()

    def has_seen(self, fingerprint: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_jobs WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return row is not None

    def record(self, job: Job) -> None:
        now = utc_now()
        payload = json.dumps(asdict(job), ensure_ascii=False)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO seen_jobs(
                fingerprint, source_name, external_id,
                first_seen_utc, last_seen_utc, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job.fingerprint,
                job.source_name,
                job.external_id,
                now,
                now,
                payload,
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = html.unescape(str(value))
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def contains_any(haystack: str, needles: Iterable[str]) -> bool:
    normalized_haystack = normalize(haystack)
    return any(normalize(term) in normalized_haystack for term in needles if term)


def matches_filters(job: Job, filters: dict[str, Any]) -> bool:
    title = job.title
    location = job.location
    searchable = " ".join([job.title, job.location, job.description])

    title_any = filters.get("title_any", [])
    title_all = filters.get("title_all", [])
    exclude_title_any = filters.get("exclude_title_any", [])
    location_any = filters.get("location_any", [])
    keyword_any = filters.get("keyword_any", [])
    exclude_keyword_any = filters.get("exclude_keyword_any", [])

    if title_any and not contains_any(title, title_any):
        return False
    if title_all and not all(normalize(term) in normalize(title) for term in title_all):
        return False
    if exclude_title_any and contains_any(title, exclude_title_any):
        return False
    if location_any and not contains_any(location, location_any):
        return False
    if keyword_any and not contains_any(searchable, keyword_any):
        return False
    if exclude_keyword_any and contains_any(searchable, exclude_keyword_any):
        return False
    return True


def build_session(config: dict[str, Any]) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {
            "User-Agent": config.get("user_agent", DEFAULT_USER_AGENT),
            "Accept": "application/json,text/html,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return session


def request_json(
    session: requests.Session,
    url: str,
    timeout: int,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    if method.upper() == "POST":
        response = session.post(url, json=payload or {}, headers=headers, timeout=timeout)
    else:
        response = session.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def pick(mapping: Any, *paths: str, default: Any = "") -> Any:
    """Return the first non-empty value from dotted dictionary paths."""
    if not isinstance(mapping, dict):
        return default
    for path in paths:
        value: Any = mapping
        found = True
        for part in path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                found = False
                break
        if found and value not in (None, "", [], {}):
            return value
    return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def dedupe_jobs(jobs: Iterable[Job]) -> list[Job]:
    result: list[Job] = []
    seen: set[tuple[str, str]] = set()
    for job in jobs:
        key = (normalize(job.external_id), normalize(job.url))
        if not job.title or not job.url or key in seen:
            continue
        seen.add(key)
        result.append(job)
    return result


def fetch_greenhouse(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    token = source["board_token"].strip()
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    payload = request_json(session, url, timeout)
    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        location = clean_text((item.get("location") or {}).get("name"))
        jobs.append(
            Job(
                source_name=source["name"],
                source_type="greenhouse",
                external_id=str(item.get("id", "")),
                title=clean_text(item.get("title")),
                company=source.get("company", source["name"]),
                location=location,
                url=str(item.get("absolute_url", "")).strip(),
                description=clean_text(item.get("content")),
                posted_at=str(item.get("updated_at", "")).strip(),
            )
        )
    return dedupe_jobs(jobs)


def fetch_lever(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    site = source["site"].strip()
    region = source.get("region", "global").strip().casefold()
    api_host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
    payload = request_json(
        session, f"https://{api_host}/v0/postings/{site}?mode=json", timeout
    )
    jobs: list[Job] = []
    for item in payload:
        categories = item.get("categories") or {}
        created_at = item.get("createdAt")
        posted_at = ""
        if isinstance(created_at, (int, float)):
            posted_at = datetime.fromtimestamp(
                created_at / 1000, tz=timezone.utc
            ).isoformat(timespec="seconds")
        jobs.append(
            Job(
                source_name=source["name"],
                source_type="lever",
                external_id=str(item.get("id", "")),
                title=clean_text(item.get("text")),
                company=source.get("company", source["name"]),
                location=clean_text(categories.get("location")),
                url=str(item.get("hostedUrl") or item.get("applyUrl") or "").strip(),
                description=" ".join(
                    filter(
                        None,
                        [
                            clean_text(item.get("descriptionPlain")),
                            clean_text(item.get("additionalPlain")),
                            clean_text(categories.get("team")),
                            clean_text(categories.get("department")),
                            clean_text(categories.get("commitment")),
                        ],
                    )
                ),
                posted_at=posted_at,
            )
        )
    return dedupe_jobs(jobs)


def fetch_recruitee(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    account = source["account"].strip()
    url = source.get("feed_url") or f"https://{account}.recruitee.com/api/offers/"
    payload = request_json(session, url, timeout)
    items = payload.get("offers", payload if isinstance(payload, list) else [])
    jobs: list[Job] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        location_value = pick(item, "location", "location.name", "city")
        if isinstance(location_value, dict):
            location_value = " ".join(
                clean_text(v)
                for v in [
                    location_value.get("city"),
                    location_value.get("state"),
                    location_value.get("country"),
                ]
                if v
            )
        link = clean_text(
            pick(item, "careers_url", "careersUrl", "url", "apply_url", "applyUrl")
        )
        slug = clean_text(pick(item, "slug", "id"))
        if not link and slug:
            link = f"https://{account}.recruitee.com/o/{slug}"
        jobs.append(
            Job(
                source_name=source["name"],
                source_type="recruitee",
                external_id=clean_text(pick(item, "id", "slug", default=stable_id(link))),
                title=clean_text(pick(item, "title", "name")),
                company=source.get("company", source["name"]),
                location=clean_text(location_value),
                url=link,
                description=" ".join(
                    filter(
                        None,
                        [
                            clean_text(pick(item, "description", "description_plain")),
                            clean_text(pick(item, "requirements")),
                            clean_text(pick(item, "department.name", "department")),
                            clean_text(pick(item, "employment_type", "employmentType")),
                        ],
                    )
                ),
                posted_at=clean_text(
                    pick(item, "published_at", "publishedAt", "created_at", "createdAt")
                ),
            )
        )
    return dedupe_jobs(jobs)


def fetch_pinpoint(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    subdomain = source["subdomain"].strip()
    url = source.get("feed_url") or f"https://{subdomain}.pinpointhq.com/postings.json"
    payload = request_json(session, url, timeout)
    if isinstance(payload, dict):
        items = pick(payload, "data", "postings", "jobs", default=[])
    else:
        items = payload
    jobs: list[Job] = []
    for item in as_list(items):
        if not isinstance(item, dict):
            continue
        link = clean_text(pick(item, "url", "job_url", "absolute_url", "apply_url"))
        if link and link.startswith("/"):
            link = urljoin(f"https://{subdomain}.pinpointhq.com/", link)
        location = pick(item, "location.name", "location", "location_name")
        if isinstance(location, dict):
            location = " ".join(clean_text(v) for v in location.values() if v)
        jobs.append(
            Job(
                source_name=source["name"],
                source_type="pinpoint",
                external_id=clean_text(pick(item, "id", "reference", default=stable_id(link))),
                title=clean_text(pick(item, "title", "name")),
                company=source.get("company", source["name"]),
                location=clean_text(location),
                url=link,
                description=" ".join(
                    filter(
                        None,
                        [
                            clean_text(pick(item, "description", "summary")),
                            clean_text(pick(item, "department.name", "department")),
                            clean_text(pick(item, "employment_type", "employmentType")),
                        ],
                    )
                ),
                posted_at=clean_text(
                    pick(item, "published_at", "publishedAt", "created_at", "createdAt")
                ),
            )
        )
    return dedupe_jobs(jobs)


def xml_text(element: ET.Element, name: str) -> str:
    child = element.find(name)
    return clean_text(child.text if child is not None else "")


def fetch_personio(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    account = source["account"].strip()
    domain = source.get("domain", "de").strip()
    language = source.get("language", "en").strip()
    feed_url = source.get("feed_url") or (
        f"https://{account}.jobs.personio.{domain}/xml?{urlencode({'language': language})}"
    )
    response = session.get(feed_url, timeout=timeout)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    jobs: list[Job] = []
    for position in root.findall(".//position"):
        external_id = xml_text(position, "id")
        title = xml_text(position, "name")
        office = xml_text(position, "office")
        descriptions = [
            clean_text(value.text)
            for value in position.findall(".//jobDescription/value")
            if value.text
        ]
        description_parts = [
            xml_text(position, "department"),
            xml_text(position, "recruitingCategory"),
            xml_text(position, "employmentType"),
            xml_text(position, "seniority"),
            *descriptions,
        ]
        hosted_base = source.get("hosted_base_url") or (
            f"https://{account}.jobs.personio.{domain}"
        )
        link = f"{hosted_base.rstrip('/')}/job/{external_id}?display={language}"
        jobs.append(
            Job(
                source_name=source["name"],
                source_type="personio",
                external_id=external_id or stable_id(link),
                title=title,
                company=source.get("company", source["name"]),
                location=office,
                url=link,
                description=" ".join(filter(None, description_parts)),
                posted_at=xml_text(position, "createdAt"),
            )
        )
    return dedupe_jobs(jobs)


def fetch_workday(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    host = source["host"].strip().rstrip("/")
    tenant = source["tenant"].strip()
    site = source["site"].strip()
    page_size = min(max(int(source.get("page_size", 20)), 1), 100)
    max_pages = min(max(int(source.get("max_pages", 25)), 1), 100)
    endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    careers_base = source.get("careers_base_url") or f"https://{host}/{site}"

    jobs: list[Job] = []
    offset = 0
    for _ in range(max_pages):
        payload = request_json(
            session,
            endpoint,
            timeout,
            method="POST",
            payload={
                "appliedFacets": source.get("applied_facets", {}),
                "limit": page_size,
                "offset": offset,
                "searchText": source.get("search_text", ""),
            },
            headers={"Content-Type": "application/json"},
        )
        postings = payload.get("jobPostings", []) if isinstance(payload, dict) else []
        if not postings:
            break
        for item in postings:
            path = clean_text(pick(item, "externalPath", "path"))
            link = urljoin(careers_base.rstrip("/") + "/", path.lstrip("/"))
            bullets = pick(item, "bulletFields", default=[])
            jobs.append(
                Job(
                    source_name=source["name"],
                    source_type="workday",
                    external_id=clean_text(
                        pick(item, "jobReqId", "externalPath", default=stable_id(link))
                    ),
                    title=clean_text(pick(item, "title", "jobTitle")),
                    company=source.get("company", source["name"]),
                    location=clean_text(
                        pick(item, "locationsText", "location", "primaryLocation")
                    ),
                    url=link,
                    description=" ".join(clean_text(x) for x in as_list(bullets) if x),
                    posted_at=clean_text(pick(item, "postedOn", "postedDate")),
                )
            )
        offset += len(postings)
        total = int(payload.get("total", offset)) if isinstance(payload, dict) else offset
        if offset >= total or len(postings) < page_size:
            break
    return dedupe_jobs(jobs)


def fetch_bamboohr(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    subdomain = source["subdomain"].strip()
    endpoint = source.get("feed_url") or f"https://{subdomain}.bamboohr.com/careers/list"
    response = session.get(endpoint, timeout=timeout)
    response.raise_for_status()
    jobs: list[Job] = []

    content_type = response.headers.get("content-type", "").casefold()
    if "json" in content_type or response.text.lstrip().startswith(("{", "[")):
        payload = response.json()
        items = pick(payload, "result", "jobs", "data", default=payload)
        for item in as_list(items):
            if not isinstance(item, dict):
                continue
            external_id = clean_text(pick(item, "id", "jobOpeningId", "jobId"))
            location = pick(item, "location", "location.city", "locationName")
            if isinstance(location, dict):
                location = ", ".join(
                    clean_text(v)
                    for v in [
                        location.get("city"),
                        location.get("state"),
                        location.get("country"),
                    ]
                    if v
                )
            link = clean_text(pick(item, "url", "jobUrl", "applyUrl"))
            if not link and external_id:
                link = f"https://{subdomain}.bamboohr.com/careers/{external_id}"
            jobs.append(
                Job(
                    source_name=source["name"],
                    source_type="bamboohr",
                    external_id=external_id or stable_id(link),
                    title=clean_text(
                        pick(item, "jobOpeningName", "title", "name", "jobTitle")
                    ),
                    company=source.get("company", source["name"]),
                    location=clean_text(location),
                    url=link,
                    description=" ".join(
                        filter(
                            None,
                            [
                                clean_text(pick(item, "description", "summary")),
                                clean_text(pick(item, "department", "departmentLabel")),
                                clean_text(pick(item, "employmentStatusLabel", "type")),
                            ],
                        )
                    ),
                    posted_at=clean_text(pick(item, "datePosted", "postedDate")),
                )
            )
    else:
        soup = BeautifulSoup(response.text, "html.parser")
        pattern = re.compile(r"/careers/(\d+)")
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href", ""))
            match = pattern.search(href)
            if not match:
                continue
            container = nearest_job_container(anchor)
            text = clean_text(container.get_text(" ", strip=True))
            title = clean_text(anchor.get_text(" ", strip=True)) or text
            link = urljoin(endpoint, href)
            jobs.append(
                Job(
                    source_name=source["name"],
                    source_type="bamboohr",
                    external_id=match.group(1),
                    title=title,
                    company=source.get("company", source["name"]),
                    location="",
                    url=link,
                    description=text,
                )
            )
    return dedupe_jobs(jobs)


def recursive_dicts(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from recursive_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from recursive_dicts(nested)


def fetch_adp_wfn(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    cid = source["cid"].strip()
    ccid = source["ccid"].strip()
    locale = source.get("locale", "en_US").strip()
    base = source.get("base_url", "https://workforcenow.adp.com/mascsr/default")
    endpoint = (
        f"{base.rstrip('/')}/careercenter/public/events/staffing/v1/job-requisitions?"
        + urlencode({"cid": cid, "ccId": ccid, "locale": locale, "lang": locale})
    )
    payload = request_json(session, endpoint, timeout)

    candidates: list[dict[str, Any]] = []
    for item in recursive_dicts(payload):
        title = pick(
            item,
            "requisitionTitle",
            "jobTitle",
            "title",
            "positionTitle",
            "name",
        )
        identifier = pick(
            item,
            "itemID",
            "requisitionID",
            "jobRequisitionID",
            "id",
            "requisitionNumber",
        )
        if title and identifier:
            candidates.append(item)

    jobs: list[Job] = []
    for item in candidates:
        external_id = clean_text(
            pick(
                item,
                "itemID",
                "requisitionID",
                "jobRequisitionID",
                "id",
                "requisitionNumber",
            )
        )
        title = clean_text(
            pick(item, "requisitionTitle", "jobTitle", "title", "positionTitle", "name")
        )
        location = clean_text(
            pick(
                item,
                "positionLocation.displayName",
                "location.displayName",
                "location.name",
                "workLocation",
                "location",
            )
        )
        detail_url = source.get("career_center_url") or (
            f"{base.rstrip('/')}/mdf/recruitment/recruitment.html?"
            + urlencode(
                {
                    "cid": cid,
                    "ccId": ccid,
                    "lang": locale,
                    "selectedMenuKey": "CareerCenter",
                }
            )
        )
        jobs.append(
            Job(
                source_name=source["name"],
                source_type="adp_wfn",
                external_id=external_id,
                title=title,
                company=source.get("company", source["name"]),
                location=location,
                url=detail_url,
                description=clean_text(item),
                posted_at=clean_text(
                    pick(item, "postedDate", "postingDate", "creationDate", "effectiveDate")
                ),
            )
        )
    return dedupe_jobs(jobs)



def fetch_oracle_hcm(
    source: dict[str, Any], session: requests.Session, timeout: int
) -> list[Job]:
    """Fetch public Oracle Recruiting Cloud career-site requisitions."""
    base_url = source["base_url"].strip().rstrip("/")
    site_number = source["site_number"].strip()
    language = source.get("language", "en").strip()
    page_size = min(max(int(source.get("page_size", 25)), 1), 100)
    max_pages = min(max(int(source.get("max_pages", 20)), 1), 100)
    endpoint = (
        f"{base_url}/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    careers_base = source.get("careers_base_url") or (
        f"{base_url}/{language}/sites/{site_number}"
    )

    jobs: list[Job] = []
    offset = 0
    for _ in range(max_pages):
        finder = (
            f"findReqs;siteNumber={site_number},limit={page_size},"
            f"offset={offset},sortBy=POSTING_DATES_DESC"
        )
        payload = request_json(
            session,
            endpoint + "?" + urlencode(
                {
                    "onlyData": "true",
                    "expand": "requisitionList",
                    "finder": finder,
                }
            ),
            timeout,
        )

        requisitions: list[dict[str, Any]] = []
        total = None
        for node in recursive_dicts(payload):
            possible = node.get("requisitionList")
            if isinstance(possible, list):
                requisitions.extend(
                    item for item in possible if isinstance(item, dict)
                )
            for key in ("TotalJobsCount", "totalJobsCount", "total"):
                if total is None and isinstance(node.get(key), (int, float, str)):
                    try:
                        total = int(node[key])
                    except (TypeError, ValueError):
                        pass

        # Some deployments return requisitions directly in items.
        if not requisitions and isinstance(payload, dict):
            for item in as_list(payload.get("items")):
                if isinstance(item, dict) and pick(
                    item, "Title", "ExternalTitle", "RequisitionTitle", "title"
                ):
                    requisitions.append(item)

        if not requisitions:
            break

        for item in requisitions:
            external_id = clean_text(
                pick(
                    item,
                    "Id",
                    "SearchId",
                    "RequisitionId",
                    "ExternalId",
                    "RequisitionNumber",
                    "id",
                )
            )
            title = clean_text(
                pick(
                    item,
                    "Title",
                    "ExternalTitle",
                    "RequisitionTitle",
                    "title",
                )
            )
            location = clean_text(
                pick(
                    item,
                    "PrimaryLocation",
                    "Location",
                    "locationsText",
                    "location",
                )
            )
            link = clean_text(
                pick(item, "ExternalURL", "JobURL", "jobUrl", "url")
            )
            if not link and external_id:
                link = f"{careers_base.rstrip('/')}/job/{external_id}"
            description = " ".join(
                filter(
                    None,
                    [
                        clean_text(pick(item, "ShortDescription", "Description")),
                        clean_text(pick(item, "JobFunction", "JobFamily")),
                        clean_text(pick(item, "Organization", "BusinessUnit")),
                        clean_text(pick(item, "JobType", "JobSchedule")),
                    ],
                )
            )
            jobs.append(
                Job(
                    source_name=source["name"],
                    source_type="oracle_hcm",
                    external_id=external_id or stable_id(link),
                    title=title,
                    company=source.get("company", source["name"]),
                    location=location,
                    url=link,
                    description=description,
                    posted_at=clean_text(
                        pick(item, "PostedDate", "PostingStartDate", "postedDate")
                    ),
                )
            )

        offset += len(requisitions)
        if len(requisitions) < page_size or (total is not None and offset >= total):
            break

    return dedupe_jobs(jobs)

def robots_allows(
    session: requests.Session,
    target_url: str,
    user_agent: str,
    timeout: int,
) -> bool:
    parsed = urlparse(target_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = session.get(robots_url, timeout=timeout)
        if response.status_code >= 400:
            return True
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(user_agent, target_url)
    except requests.RequestException:
        return True


def select_text(card: Tag, selector: str | None) -> str:
    if not selector:
        return ""
    node = card.select_one(selector)
    return clean_text(node.get_text(" ", strip=True)) if node else ""


def select_link(card: Tag, selector: str | None, base_url: str) -> str:
    if not selector:
        return ""
    node = card.select_one(selector)
    if not node:
        return ""
    href = node.get("href")
    return urljoin(base_url, str(href).strip()) if href else ""


def fetch_html(
    source: dict[str, Any],
    session: requests.Session,
    timeout: int,
    user_agent: str,
) -> list[Job]:
    url = source["url"].strip()
    if source.get("respect_robots", True) and not robots_allows(
        session, url, user_agent, timeout
    ):
        raise RuntimeError(f"robots.txt does not allow monitoring: {url}")
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    jobs: list[Job] = []
    for card in soup.select(source["card_selector"]):
        title = select_text(card, source["title_selector"])
        link = select_link(
            card, source.get("link_selector", source["title_selector"]), url
        )
        location = select_text(card, source.get("location_selector"))
        description = select_text(card, source.get("description_selector"))
        if title and link:
            jobs.append(
                Job(
                    source_name=source["name"],
                    source_type="html",
                    external_id=stable_id(link),
                    title=title,
                    company=source.get("company", source["name"]),
                    location=location,
                    url=link,
                    description=description,
                )
            )
    return dedupe_jobs(jobs)


def nearest_job_container(anchor: Tag) -> Tag:
    current: Tag | None = anchor
    for _ in range(7):
        if current is None:
            break
        if current.name in {"article", "li", "tr"}:
            return current
        classes = " ".join(current.get("class", [])) if isinstance(current, Tag) else ""
        if re.search(r"job|vacan|position|opening|result|card", classes, re.I):
            return current
        current = current.parent if isinstance(current.parent, Tag) else None
    return anchor.parent if isinstance(anchor.parent, Tag) else anchor


def fetch_link_page(
    source: dict[str, Any],
    session: requests.Session,
    timeout: int,
    user_agent: str,
) -> list[Job]:
    urls = as_list(source.get("urls") or source.get("url"))
    include_pattern = re.compile(source["include_url_regex"], re.I)
    exclude_pattern = (
        re.compile(source["exclude_url_regex"], re.I)
        if source.get("exclude_url_regex")
        else None
    )
    title_regex = re.compile(source["title_regex"], re.I) if source.get("title_regex") else None
    location_regex = (
        re.compile(source["location_regex"], re.I)
        if source.get("location_regex")
        else None
    )
    jobs: list[Job] = []

    for page_url_value in urls:
        page_url = str(page_url_value).strip()
        if source.get("respect_robots", True) and not robots_allows(
            session, page_url, user_agent, timeout
        ):
            raise RuntimeError(f"robots.txt does not allow monitoring: {page_url}")
        response = session.get(page_url, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.select("a[href]"):
            href = urljoin(page_url, str(anchor.get("href", "")).strip())
            if not include_pattern.search(href):
                continue
            if exclude_pattern and exclude_pattern.search(href):
                continue
            container = nearest_job_container(anchor)
            container_text = clean_text(container.get_text(" ", strip=True))
            anchor_text = clean_text(anchor.get_text(" ", strip=True))

            title = ""
            if source.get("title_selector"):
                title = select_text(container, source["title_selector"])
            if not title and title_regex:
                match = title_regex.search(container_text)
                if match:
                    title = clean_text(match.groupdict().get("title") or match.group(1))
            if not title:
                title = anchor_text
            if not title or normalize(title) in {
                "view details",
                "view job",
                "apply",
                "apply now",
                "learn more",
                "read more",
            }:
                heading = container.select_one("h1,h2,h3,h4,h5,[class*='title']")
                title = clean_text(heading.get_text(" ", strip=True)) if heading else container_text

            location = ""
            if source.get("location_selector"):
                location = select_text(container, source["location_selector"])
            if not location and location_regex:
                match = location_regex.search(container_text)
                if match:
                    location = clean_text(
                        match.groupdict().get("location") or match.group(1)
                    )

            jobs.append(
                Job(
                    source_name=source["name"],
                    source_type="link_page",
                    external_id=stable_id(href),
                    title=title[:500],
                    company=source.get("company", source["name"]),
                    location=location,
                    url=href,
                    description=container_text,
                )
            )
    return dedupe_jobs(jobs)


def fetch_source(
    source: dict[str, Any],
    session: requests.Session,
    timeout: int,
    user_agent: str,
) -> list[Job]:
    source_type = source["type"].strip().casefold()
    if source_type == "greenhouse":
        return fetch_greenhouse(source, session, timeout)
    if source_type == "lever":
        return fetch_lever(source, session, timeout)
    if source_type == "recruitee":
        return fetch_recruitee(source, session, timeout)
    if source_type == "pinpoint":
        return fetch_pinpoint(source, session, timeout)
    if source_type == "personio":
        return fetch_personio(source, session, timeout)
    if source_type == "workday":
        return fetch_workday(source, session, timeout)
    if source_type == "bamboohr":
        return fetch_bamboohr(source, session, timeout)
    if source_type == "adp_wfn":
        return fetch_adp_wfn(source, session, timeout)
    if source_type == "oracle_hcm":
        return fetch_oracle_hcm(source, session, timeout)
    if source_type == "html":
        return fetch_html(source, session, timeout, user_agent)
    if source_type == "link_page":
        return fetch_link_page(source, session, timeout, user_agent)
    raise ValueError(f"Unsupported source type: {source_type}")


def format_message(job: Job) -> str:
    parts = ["🏎️ NEW EXPERIENCE-MATCHED JOB", job.title, job.company]
    if job.location:
        parts.append(job.location)
    if job.posted_at:
        parts.append(f"Source timestamp: {job.posted_at}")
    parts.append(job.url)
    return "\n".join(parts)


def notify_console(job: Job) -> None:
    print("\n" + format_message(job) + "\n", flush=True)


def notify_discord(job: Job, session: requests.Session, timeout: int) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set")
    response = session.post(
        webhook,
        json={"content": format_message(job), "allowed_mentions": {"parse": []}},
        timeout=timeout,
    )
    response.raise_for_status()


def notify_ntfy(job: Job, session: requests.Session, timeout: int) -> None:
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    token = os.environ.get("NTFY_TOKEN", "").strip()
    if not topic:
        raise RuntimeError("NTFY_TOPIC is not set")
    headers = {
        "Title": f"New job: {job.title}"[:250],
        "Tags": "briefcase",
        "Click": job.url,
        "Priority": "high",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = session.post(
        f"{server}/{topic}",
        data=format_message(job).encode("utf-8"),
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()


def send_notifications(
    job: Job,
    channels: list[str],
    session: requests.Session,
    timeout: int,
) -> None:
    errors: list[str] = []
    for channel in channels:
        try:
            normalized = channel.strip().casefold()
            if normalized == "console":
                notify_console(job)
            elif normalized == "discord":
                notify_discord(job, session, timeout)
            elif normalized == "ntfy":
                notify_ntfy(job, session, timeout)
            else:
                raise ValueError(f"Unsupported notification channel: {channel}")
        except Exception as exc:
            errors.append(f"{channel}: {exc}")
            logging.exception("Notification channel failed: %s", channel)
    if errors and len(errors) == len(channels):
        raise RuntimeError("All notification channels failed: " + "; ".join(errors))


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("sources"), list) or not config["sources"]:
        raise ValueError("config.sources must contain at least one source")

    required_by_type = {
        "greenhouse": ["board_token"],
        "lever": ["site"],
        "recruitee": ["account"],
        "pinpoint": ["subdomain"],
        "personio": ["account"],
        "workday": ["host", "tenant", "site"],
        "bamboohr": ["subdomain"],
        "adp_wfn": ["cid", "ccid"],
        "oracle_hcm": ["base_url", "site_number"],
        "html": ["url", "card_selector", "title_selector"],
        "link_page": ["include_url_regex"],
    }

    source_names: set[str] = set()
    for source in config["sources"]:
        for field in ("name", "type"):
            if not source.get(field):
                raise ValueError(f"Every source requires '{field}'")
        if source["name"] in source_names:
            raise ValueError(f"Duplicate source name: {source['name']}")
        source_names.add(source["name"])

        source_type = source["type"].strip().casefold()
        if source_type not in SUPPORTED_SOURCE_TYPES:
            raise ValueError(f"Unsupported source type: {source_type}")
        for field in required_by_type[source_type]:
            if not source.get(field):
                raise ValueError(f"Source '{source['name']}' requires '{field}'")
        if source_type == "link_page" and not (source.get("url") or source.get("urls")):
            raise ValueError(f"Source '{source['name']}' requires 'url' or 'urls'")

    interval = int(config.get("poll_interval_seconds", 60))
    if interval < 60:
        raise ValueError("poll_interval_seconds must be at least 60")
    channels = config.get("notifications", {}).get("channels", ["console"])
    if not channels:
        raise ValueError("At least one notification channel is required")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    validate_config(config)
    return config


def run_cycle(
    config: dict[str, Any],
    store: StateStore,
    session: requests.Session,
    *,
    preview: bool = False,
) -> tuple[int, int, int]:
    timeout = int(config.get("request_timeout_seconds", 25))
    filters = config.get("filters", {})
    channels = config.get("notifications", {}).get("channels", ["console"])
    notify_existing = bool(config.get("notify_existing_on_first_run", False))
    user_agent = config.get("user_agent", DEFAULT_USER_AGENT)

    found = 0
    alerted = 0
    failures = 0
    for source in config["sources"]:
        if source.get("enabled", True) is False:
            logging.info("Skipping disabled source: %s", source["name"])
            continue
        source_name = source["name"]
        try:
            jobs = fetch_source(source, session, timeout, user_agent)
            source_filters = source.get("filters", {})
            matching_jobs = [
                job
                for job in jobs
                if matches_filters(job, source_filters)
                and matches_filters(job, filters)
            ]
            found += len(matching_jobs)
            logging.info(
                "%s: fetched %d jobs; %d matched",
                source_name,
                len(jobs),
                len(matching_jobs),
            )

            if preview:
                for job in matching_jobs:
                    notify_console(job)
                continue

            initialized = store.source_initialized(source_name)
            for job in matching_jobs:
                is_new = not store.has_seen(job.fingerprint)
                should_alert = is_new and (initialized or notify_existing)
                if should_alert:
                    send_notifications(job, channels, session, timeout)
                    alerted += 1
                store.record(job)
            store.mark_source_initialized(source_name)
        except Exception:
            failures += 1
            logging.exception("Source failed: %s", source_name)
    return found, alerted, failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor company career pages")
    parser.add_argument("--config", default="config.json", help="Config JSON path")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--preview", action="store_true", help="Print current matches; do not save")
    parser.add_argument("--validate", action="store_true", help="Validate config and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        config = load_config(config_path)
    except Exception as exc:
        logging.error("Invalid config: %s", exc)
        return 2
    if args.validate:
        print(f"Valid config: {config_path}")
        return 0

    state_path = Path(config.get("state_database", "job_alerts.sqlite3"))
    if not state_path.is_absolute():
        state_path = config_path.parent / state_path

    session = build_session(config)
    store = StateStore(state_path)
    interval = int(config.get("poll_interval_seconds", 60))
    try:
        while True:
            started = time.monotonic()
            found, alerted, failures = run_cycle(
                config, store, session, preview=args.preview
            )
            logging.info(
                "Cycle complete: %d current matches; %d new alerts; %d source failures",
                found,
                alerted,
                failures,
            )
            if args.once or args.preview:
                return 1 if failures == len([s for s in config["sources"] if s.get("enabled", True)]) else 0
            elapsed = time.monotonic() - started
            time.sleep(max(1, interval - elapsed))
    except KeyboardInterrupt:
        logging.info("Stopped by user")
        return 0
    finally:
        store.close()
        session.close()


if __name__ == "__main__":
    sys.exit(main())
