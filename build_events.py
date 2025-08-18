#!/usr/bin/env python3
# build_events.py — Aggregates events into events.json for events.html

import json
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Optional libs (already in your requirements)
import feedparser
from icalendar import Calendar

# ---------- HTTP ----------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "LocalEventsAggregator/1.1 (+congressional office) PythonRequests"
})
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN = 0.25  # be polite to host sites

def fetch(url):
    r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r

# ---------- Sources (your 6) ----------
GNFCC_LIST      = "https://gzdev.gnfcc.com/chamber-events"
CHEROKEE_LIST   = "https://cherokeechamber.com/programs-events/chamber-calendar/"
DAWSON_LIST     = "https://business.dawsonchamber.org/events/calendar"
DLC_LIST        = "https://members.dlcchamber.org/events"
GHCC_LIST       = "https://members.ghcc.com/events"
FOCO_LIST       = "https://web.focochamber.org/events?oe=true"

LIST_SOURCES = [
    (GNFCC_LIST,    "GNFCC Chamber"),
    (CHEROKEE_LIST, "Cherokee Chamber"),
    (DAWSON_LIST,   "Dawson Chamber"),
    (DLC_LIST,      "DLC Chamber"),
    (GHCC_LIST,     "GHCC"),
    (FOCO_LIST,     "Forsyth County Chamber"),
]

# ---------- Generic helpers ----------
def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def to_iso(dt):
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt

def try_parse_date(s):
    if not s:
        return None
    s = s.strip()
    # ISO-ish quick path
    try:
        # normalize "YYYY-MM-DD HH:MM:SS" → "YYYY-MM-DDTHH:MM:SS"
        if " " in s and "T" not in s and re.match(r"\d{4}-\d{2}-\d{2}\s", s):
            s2 = s.replace(" ", "T", 1)
        else:
            s2 = s
        return datetime.fromisoformat(s2.replace("Z", "+00:00"))
    except Exception:
        pass
    # Common US formats
    fmts = [
        "%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y", "%m/%d/%y", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p",
        "%b %d, %Y", "%b %d, %Y %I:%M %p", "%B %d, %Y", "%B %d, %Y %I:%M %p",
        "%Y%m%dT%H%M%S", "%Y%m%d"
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None

def normalize_event(title, start=None, end=None, all_day=False, location="", url="", source="", description=""):
    return {
        "title": clean_text(title) or "(Untitled)",
        "start": to_iso(start) if start else None,
        "end": to_iso(end) if end else None,
        "allDay": bool(all_day),
        "location": clean_text(location),
        "url": url,
        "source": source,
        "description": clean_text(description),
    }

# ---------- JSON-LD extraction ----------
def jsonld_event_times(soup):
    """
    Try to pull start/end via schema.org/Event JSON-LD.
    Returns (start_dt, end_dt) or (None, None).
    """
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue

        def scan(obj):
            if not isinstance(obj, dict):
                return None, None
            # @graph container
            if "@graph" in obj and isinstance(obj["@graph"], list):
                for g in obj["@graph"]:
                    st, en = scan(g)
                    if st:
                        return st, en
            # Direct Event
            types = obj.get("@type")
            if (isinstance(types, str) and types.lower() == "event") or \
               (isinstance(types, list) and any(t.lower() == "event" for t in types if isinstance(t, str))):
                s = obj.get("startDate"); e = obj.get("endDate")
                sd = try_parse_date(s) if s else None
                ed = try_parse_date(e) if e else None
                if sd:
                    return sd, ed
            return None, None

        # List or single
        if isinstance(data, list):
            for item in data:
                sd, ed = scan(item)
                if sd:
                    return sd, ed
        elif isinstance(data, dict):
            sd, ed = scan(data)
            if sd:
                return sd, ed
    return None, None

# ---------- Detail page parser ----------
DATE_PATTERNS = [
    # "Thursday, August 14, 2025 (5:30 PM - 7:00 PM)"
    re.compile(r"([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})\s*\(([^)]+)\)"),
    # "Thursday, August 14, 2025 5:30 PM - 7:00 PM" (no parentheses)
    re.compile(r"([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})\s+(\d{1,2}:\d{2}\s*(?:AM|PM))(?:\s*[-–]\s*(\d{1,2}:\d{2}\s*(?:AM|PM)))?", re.I),
    # "August 14, 2025 at 5:30 PM"
    re.compile(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})\s+(?:at|@)\s+(\d{1,2}:\d{2}\s*(?:AM|PM))", re.I),
]

def parse_address_fallback(text):
    # very light address-y fallback
    m = re.search(r"\d{2,5}\s+[A-Za-z][A-Za-z0-9 .,'&-]{3,}\s+(?:Ave|Ave\.|St|St\.|Rd|Rd\.|Blvd|Blvd\.|Dr|Dr\.|Hwy|Pkwy|Way|Lane|Ln|Ct|Cir|Trail|Trl)\b.*?(?:\n|,|$)", text, re.I)
    return clean_text(m.group(0))[:200] if m else ""

def parse_detail_page(url, source_label):
    try:
        dr = fetch(url)
    except Exception as e:
        print(f"[detail] fetch error {url}: {e}", file=sys.stderr)
        return None

    dsoup = BeautifulSoup(dr.text, "html.parser")

    # Title (prefer h1/h2)
    title = "(Untitled)"
    h = dsoup.find(["h1","h2"], string=True)
    if h:
        title = clean_text(h.get_text())

    # Start/End: JSON-LD first
    start, end = jsonld_event_times(dsoup)

    # Text fallback patterns
    if not start:
        text = dsoup.get_text("\n", strip=True)
        # Pattern 1
        m = DATE_PATTERNS[0].search(text)
        if m:
            date_str, times = m.group(1), m.group(2)
            tm = re.findall(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", times, re.I)
            if tm:
                start = try_parse_date(f"{date_str} {tm[0]}")
                if len(tm) > 1:
                    end = try_parse_date(f"{date_str} {tm[1]}")
            else:
                start = try_parse_date(date_str)
        # Pattern 2
        if not start:
            m2 = DATE_PATTERNS[1].search(text)
            if m2:
                date_str = m2.group(1)
                t1 = m2.group(2)
                t2 = m2.group(3)
                start = try_parse_date(f"{date_str} {t1}")
                if t2:
                    end = try_parse_date(f"{date_str} {t2}")
        # Pattern 3
        if not start:
            m3 = DATE_PATTERNS[2].search(text)
            if m3:
                start = try_parse_date(f"{m3.group(1)} {m3.group(2)}")

    # Location
    loc = ""
    # Prefer a Google Maps link text if present
    map_link = dsoup.find("a", href=re.compile(r"(?:maps\.app|google\.com/maps)", re.I))
    if map_link:
        loc = clean_text(map_link.get_text())
    if not loc:
        loc = parse_address_fallback(dsoup.get_text(" ", strip=True))

    # Description: grab a paragraph near a "Description/Details" header, otherwise first decent paragraph
    desc = ""
    hdr = dsoup.find(lambda t: t.name in ["h2","h3","h4"] and re.search(r"(description|details|about)", t.get_text(), re.I))
    if hdr:
        parts = []
        for sib in hdr.find_all_next(["p","li"], limit=14):
            parts.append(sib.get_text(" ", strip=True))
        desc = clean_text(" ".join(parts))[:1200]
    if not desc:
        p = dsoup.find("p")
        if p:
            desc = clean_text(p.get_text(" ", strip=True))[:600]

    all_day = False
    if start and isinstance(start, datetime) and end is None:
        # if exact time wasn't found and JSON-LD gave date only, could be all-day, but keep False unless clearly date-only
        pass

    return normalize_event(title, start, end, all_day, loc, url, source_label, desc)

# ---------- List page crawlers ----------
def collect_detail_links(list_url, soup):
    """
    Collect likely event detail links from a listing page.
    Handles GrowthZone/ChamberMaster and generic patterns.
    """
    links = set()
    base = list_url

    # Common GrowthZone/ChamberMaster detail pattern
    for a in soup.select("a[href*='/events/details/']"):
        href = a.get("href")
        if href:
            links.add(urljoin(base, href))

    # GNFCC pattern
    for a in soup.select("a[href*='/chamber-events/Details/']"):
        href = a.get("href")
        if href:
            links.add(urljoin(base, href))

    # Generic 'event' links with ids (Cherokee etc.)
    for a in soup.select("a[href*='event']"):
        href = a.get("href")
        if href and ("id=" in href or "/event/" in href or href.endswith("/event") or "details" in href.lower()):
            links.add(urljoin(base, href))

    # De-dupe cross-page anchors to full URLs in same host
    return sorted(links)

def crawl_list_page(list_url, source_label):
    out = []
    try:
        r = fetch(list_url)
    except Exception as e:
        print(f"[list] fetch error {list_url}: {e}", file=sys.stderr)
        return out

    soup = BeautifulSoup(r.text, "html.parser")
    detail_links = collect_detail_links(list_url, soup)

    if not detail_links:
        # Some calendars render an initial month via a nested iframe or widget; try to follow iframes
        for iframe in soup.select("iframe[src]"):
            src = urljoin(list_url, iframe["src"])
            try:
                ir = fetch(src)
                isoup = BeautifulSoup(ir.text, "html.parser")
                detail_links.extend(collect_detail_links(src, isoup))
            except Exception as e:
                print(f"[iframe] fetch error {src}: {e}", file=sys.stderr)

    seen_links = set()
    for href in detail_links:
        if href in seen_links:
            continue
        seen_links.add(href)
        ev = parse_detail_page(href, source_label)
        if ev:
            out.append(ev)
        time.sleep(SLEEP_BETWEEN)

    return out

# ---------- (Optional) ICS/RSS generic support ----------
ICS_URLS = []  # add if you obtain ICS links
RSS_URLS = []  # add if you obtain RSS links

def from_ics(u):
    out = []
    try:
        r = fetch(u)
        cal = Calendar.from_ical(r.content)
        for comp in cal.walk():
            if comp.name != "VEVENT":
                continue
            title = str(comp.get("summary", "")) or "(Untitled)"
            desc = str(comp.get("description", ""))
            loc  = str(comp.get("location", ""))
            dtstart = comp.get("dtstart").dt if comp.get("dtstart") else None
            dtend   = comp.get("dtend").dt if comp.get("dtend") else None
            all_day = (hasattr(dtstart, "hour") is False) if dtstart else False
            url_val = str(comp.get("url", "")) if comp.get("url") else ""
            out.append(normalize_event(title, dtstart, dtend, all_day, loc, url_val, source=u, description=desc))
    except Exception as e:
        print(f"[ICS] {u}: {e}", file=sys.stderr)
    return out

def from_rss(u):
    out = []
    try:
        d = feedparser.parse(u)
        for e in d.entries:
            title = e.get("title", "") or "(Untitled)"
            link  = e.get("link", "")
            desc  = e.get("summary", "") or e.get("description", "")
            start = None
            for k in ("start_time", "published", "updated", "created"):
                val = e.get(k)
                if val:
                    start = try_parse_date(val) or start
            out.append(normalize_event(title, start, None, False, "", link, source=u, description=desc))
    except Exception as e:
        print(f"[RSS] {u}: {e}", file=sys.stderr)
    return out

# ---------- Main ----------
def main():
    all_events = []

    # Generic feeds if you add any
    for u in ICS_URLS:
        all_events += from_ics(u)
    for u in RSS_URLS:
        all_events += from_rss(u)

    # Your six sources
    for list_url, label in LIST_SOURCES:
        print(f"[crawl] {label}: {list_url}")
        all_events += crawl_list_page(list_url, label)

    # Deduplicate by (title, start, source, url)
    seen = set()
    dedup = []
    for e in all_events:
        key = (e["title"].lower(), e["start"], e["source"], e["url"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)

    # Sort by start date ascending (nulls last)
    def sort_key(ev):
        s = ev["start"]
        return (1, "") if not s else (0, s)
    dedup.sort(key=sort_key)

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(dedup, f, ensure_ascii=False, indent=2)
    print(f"Wrote events.json with {len(dedup)} events")

if __name__ == "__main__":
    # lazy import used inside jsonld_event_times
    import json  # noqa: E402
    main()
