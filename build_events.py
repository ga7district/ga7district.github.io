#!/usr/bin/env python3
# build_events.py — Aggregates events from several chamber sites into events.json for events.html

import json
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup

# Optional libs (already in requirements.txt)
import feedparser
from icalendar import Calendar

# ---------- HTTP ----------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "LocalEventsAggregator/1.2 (+congressional office) PythonRequests"
})
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN = 0.25  # be polite

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

def domain_of(u: str) -> str:
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""

def strip_tracking_params(u: str) -> str:
    """
    Remove common tracking/query noise while preserving important parts.
    """
    p = urlparse(u)
    # keep only "id" if present; drop utm etc.
    allowed = {"id"}
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k in allowed]
    new_q = urlencode(q, doseq=True)
    # drop fragments
    clean = p._replace(query=new_q, fragment="")
    # normalize scheme/host lower-case; drop trailing slash later if needed
    return urlunparse(clean)

def canonical_from_head(soup, base_url: str) -> str | None:
    """
    If a <link rel="canonical"> exists, return its absolute URL.
    """
    link = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
    if link and link.get("href"):
        return urljoin(base_url, link["href"])
    return None

def extract_growthzone_id(u: str) -> str | None:
    """
    Extract numeric event ID from GrowthZone/ChamberMaster URLs:
    .../events/<slug>-9074/details
    """
    m = re.search(r"/events/[^/]*-(\d+)/(?:details|details/)?", urlparse(u).path)
    return m.group(1) if m else None

# ---------- JSON-LD + title extraction ----------
def jsonld_event_info(soup):
    """
    Return (name, start, end) if found in schema.org/Event JSON-LD.
    """
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue

        def scan(obj):
            if not isinstance(obj, dict):
                return None
            # graph container
            if "@graph" in obj and isinstance(obj["@graph"], list):
                for g in obj["@graph"]:
                    res = scan(g)
                    if res:
                        return res
            # Event node
            types = obj.get("@type")
            is_event = False
            if isinstance(types, str):
                is_event = types.lower() == "event"
            elif isinstance(types, list):
                is_event = any(isinstance(t, str) and t.lower() == "event" for t in types)
            if is_event:
                name = clean_text(obj.get("name", "") or "")
                s = obj.get("startDate")
                e = obj.get("endDate")
                sd = try_parse_date(s) if s else None
                ed = try_parse_date(e) if e else None
                return name or None, sd, ed
            return None

        if isinstance(data, list):
            for item in data:
                res = scan(item)
                if res:
                    return res
        elif isinstance(data, dict):
            res = scan(data)
            if res:
                return res
    return None, None, None

def extract_title(dsoup: BeautifulSoup, url: str) -> str:
    """
    Robust title extraction: JSON-LD name → og:title → h1/h2 → <title>
    """
    name, _, _ = jsonld_event_info(dsoup)
    if name:
        return name

    og = dsoup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return clean_text(og["content"])

    h = dsoup.find(["h1", "h2"], string=True)
    if h:
        return clean_text(h.get_text())

    # fall back to <title> minus site suffix
    t = dsoup.find("title")
    if t and t.string:
        # common pattern: "<Event Name> - Chamber Name"
        return clean_text(re.split(r"\s+[–|-]\s+", t.string)[0])

    # last resort: slug from URL
    slug = urlparse(url).path.rstrip("/").split("/")[-2:-1] or urlparse(url).path.rstrip("/").split("/")[-1:]
    if slug:
        return clean_text(slug[0].replace("-", " ").replace("_", " ")).title()
    return "(Untitled)"

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
    m = re.search(r"\d{2,5}\s+[A-Za-z][A-Za-z0-9 .,'&-]{3,}\s+(?:Ave|Ave\.|St|St\.|Rd|Rd\.|Blvd|Blvd\.|Dr|Dr\.|Hwy|Pkwy|Way|Lane|Ln|Ct|Cir|Trail|Trl)\b.*?(?:\n|,|$)", text, re.I)
    return clean_text(m.group(0))[:200] if m else ""

def parse_detail_page(url, source_label):
    try:
        dr = fetch(url)
    except Exception as e:
        print(f"[detail] fetch error {url}: {e}", file=sys.stderr)
        return None

    dsoup = BeautifulSoup(dr.text, "html.parser")

    # Use canonical URL if present (helps dedupe)
    canon = canonical_from_head(dsoup, url) or url
    canon = strip_tracking_params(canon)

    # Title (robust; fixes FOCO untitled)
    title = extract_title(dsoup, canon)

    # Start/End: JSON-LD first
    _, start, end = jsonld_event_info(dsoup)

    # Text fallback patterns
    if not start:
        text = dsoup.get_text("\n", strip=True)
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
        if not start:
            m2 = DATE_PATTERNS[1].search(text)
            if m2:
                date_str = m2.group(1)
                t1 = m2.group(2)
                t2 = m2.group(3)
                start = try_parse_date(f"{date_str} {t1}")
                if t2:
                    end = try_parse_date(f"{date_str} {t2}")
        if not start:
            m3 = DATE_PATTERNS[2].search(text)
            if m3:
                start = try_parse_date(f"{m3.group(1)} {m3.group(2)}")

    # Location
    loc = ""
    map_link = dsoup.find("a", href=re.compile(r"(?:maps\.app|google\.com/maps)", re.I))
    if map_link:
        loc = clean_text(map_link.get_text())
    if not loc:
        loc = parse_address_fallback(dsoup.get_text(" ", strip=True))

    # Description: near "Description/Details/About"
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

    all_day = False  # conservative

    return normalize_event(title, start, end, all_day, loc, canon, source_label, desc)

# ---------- List page crawlers ----------
def collect_detail_links(list_url, soup):
    links = set()
    base = list_url

    # GrowthZone/ChamberMaster detail pattern
    for a in soup.select("a[href*='/events/details/']"):
        href = a.get("href")
        if href:
            links.add(urljoin(base, href))

    # GNFCC pattern
    for a in soup.select("a[href*='/chamber-events/Details/']"):
        href = a.get("href")
        if href:
            links.add(urljoin(base, href))

    # Generic 'event' links with obvious IDs
    for a in soup.select("a[href*='event']"):
        href = a.get("href")
        if not href:
            continue
        u = urljoin(base, href)
        if ("id=" in u) or ("/event/" in u) or u.endswith("/event") or ("details" in u.lower()):
            links.add(u)

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
        # Some calendars render via iframes; try to follow them
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
            out.append(normalize_event(title, dtstart, dtend, all_day, loc, strip_tracking_params(url_val), source=u, description=desc))
    except Exception as e:
        print(f"[ICS] {u}: {e}", file=sys.stderr)
    return out

def from_rss(u):
    out = []
    try:
        d = feedparser.parse(u)
        for e in d.entries:
            title = e.get("title", "") or "(Untitled)"
            link  = strip_tracking_params(e.get("link", "") or "")
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

    # Crawl your six sources
    for list_url, label in LIST_SOURCES:
        print(f"[crawl] {label}: {list_url}")
        all_events += crawl_list_page(list_url, label)

    # ---------- De-duplication ----------
    # Normalize URLs and build multiple candidate keys
    seen = set()
    dedup = []
    aux_index = {}  # (domain, title_lower) -> list of (idx, start_dt)

    def as_dt(iso_s):
        return datetime.fromisoformat(iso_s) if iso_s else None

    for e in all_events:
        # Prefer canonical/clean URL already set in parse_detail_page; still sanitize here:
        e["url"] = strip_tracking_params(e["url"])
        dom = domain_of(e["url"])

        # Key 1: explicit GrowthZone ID if present
        gzid = extract_growthzone_id(e["url"])
        k1 = ("gzid", dom, gzid) if gzid else None

        # Key 2: exact URL
        k2 = ("url", e["url"])

        # Key 3: fuzzy — same domain + same title (lower) + start within ±2 minutes
        tl = e["title"].lower().strip()
        sd = as_dt(e["start"])

        dup = False
        if k1 and gzid:
            if k1 in seen:
                dup = True
            else:
                seen.add(k1)

        if not dup:
            if k2 in seen:
                dup = True
            else:
                seen.add(k2)

        if not dup and tl and sd:
            key3 = ("title_date", dom, tl)
            near_list = aux_index.setdefault(key3, [])
            # see if any existing event is within 2 minutes
            for _, existing_dt in near_list:
                if existing_dt and abs((sd - existing_dt).total_seconds()) <= 120:
                    dup = True
                    break
            if not dup:
                near_list.append((len(dedup), sd))

        if dup:
            continue

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
    main()
