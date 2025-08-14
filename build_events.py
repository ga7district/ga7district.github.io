#!/usr/bin/env python3
# build_events.py
# Aggregate local events into a normalized events.json for use by events.html

import json
import re
import sys
import time
import traceback
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Optional libs; install via requirements.txt
import feedparser                # For RSS/Atom
from icalendar import Calendar   # For ICS/iCal


# --------------------
# 0) HTTP defaults
# --------------------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "LocalEventsAggregator/1.0 (+contact: congressional office) PythonRequests"
})
REQUEST_TIMEOUT = 30


# --------------------
# 1) Configure sources
# --------------------
# Tip: many cities, chambers, libraries, universities publish ICS/RSS
ICS_URLS = [
    # Example: "https://example.gov/calendar.ics",
]

RSS_URLS = [
    # Example: "https://example.gov/events/feed/",
]

# Your three sites:
GNFCC_CAL_LIST = "https://gzdev.gnfcc.com/chamber-events"  # We'll crawl list → detail pages
CHEROKEE_WIDGETS_LIST = "https://widgets.cherokeechamber.com/feeds/events/event.aspx?cid=94&wid=701"
ROTARY_FORSYTH_CAL = "https://www.rotaryclubofforsythcounty.org/?p=calendar"  # dynamic via JS (stubbed)


# --------------------
# 2) Helpers
# --------------------
def to_iso(dt):
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt  # already a string or None

def clean_text(s):
    return re.sub(r"\s+", " ", (s or "").strip())

def try_parse_date(s):
    """Best-effort date parser without extra deps."""
    if not s:
        return None
    fmts = [
        "%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y", "%m/%d/%y", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p",
        "%b %d, %Y", "%b %d, %Y %I:%M %p", "%B %d, %Y", "%B %d, %Y %I:%M %p",
        "%Y%m%dT%H%M%S", "%Y%m%d"
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
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
        "description": clean_text(description)
    }

def fetch(url):
    r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r

def safe_get_text(el):
    return el.get_text(" ", strip=True) if el else ""


# --------------------
# 3) Generic fetchers (ICS, RSS)
# --------------------
def from_ics(u):
    out = []
    try:
        r = fetch(u)
        cal = Calendar.from_ical(r.content)
        for comp in cal.walk():
            if comp.name != "VEVENT":
                continue
            title = str(comp.get("summary", ""))
            desc = str(comp.get("description", ""))
            loc  = str(comp.get("location", ""))
            dtstart = comp.get("dtstart").dt if comp.get("dtstart") else None
            dtend   = comp.get("dtend").dt if comp.get("dtend") else None
            all_day = (hasattr(dtstart, "hour") is False) if dtstart else False
            url_val = str(comp.get("url", "")) if comp.get("url") else ""
            out.append(normalize_event(title, dtstart, dtend, all_day, loc, url_val, source=u, description=desc))
    except Exception as e:
        print(f"[ICS] Error {u}: {e}", file=sys.stderr)
    return out

def from_rss(u):
    out = []
    try:
        d = feedparser.parse(u)
        for e in d.entries:
            title = e.get("title", "") or "(Untitled)"
            link  = e.get("link", "")
            desc  = e.get("summary", "") or e.get("description","")
            # Find any time-like field commonly present
            start = None
            for k in ("start_time", "published", "updated", "created"):
                val = e.get(k)
                if val:
                    start = try_parse_date(val) or start
            out.append(normalize_event(title, start, None, False, "", link, source=u, description=desc))
    except Exception as e:
        print(f"[RSS] Error {u}: {e}", file=sys.stderr)
    return out


# --------------------
# 3b) Site-specific scrapers
# --------------------
def gnfcc_events():
    """
    Crawl the GNFCC Chamber Events list, then follow each /chamber-events/Details/... page.
    """
    out = []
    try:
        r = fetch(GNFCC_CAL_LIST)
        soup = BeautifulSoup(r.text, "html.parser")

        # Collect every link that points to a Details page
        detail_links = []
        for a in soup.select("a[href*='/chamber-events/Details/']"):
            href = a.get("href", "")
            if href:
                full = urljoin(GNFCC_CAL_LIST, href)
                if full not in detail_links:
                    detail_links.append(full)

        for href in detail_links:
            try:
                dr = fetch(href)
                dsoup = BeautifulSoup(dr.text, "html.parser")

                # Title (usually h1)
                title_el = dsoup.find(["h1","h2"], string=True)
                title = clean_text(title_el.get_text()) if title_el else "(Untitled)"

                # Date/Time pattern like: "Thursday, August 14, 2025 (5:30 PM - 7:00 PM) (EDT)"
                text = dsoup.get_text("\n", strip=True)
                start = end = None
                all_day = False
                m = re.search(r"([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})\s*\(([^)]+)\)", text)
                if m:
                    date_str = m.group(1)
                    times = m.group(2)
                    tm = re.findall(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", times, re.I)
                    if tm:
                        start = try_parse_date(f"{date_str} {tm[0]}")
                        if len(tm) > 1:
                            end = try_parse_date(f"{date_str} {tm[1]}")
                    else:
                        start = try_parse_date(date_str)
                        all_day = True

                # Location: prefer Google Maps link text; fallback to addressy text
                loc = ""
                loc_el = dsoup.find("a", href=re.compile(r"(?:maps\.app|google\.com/maps)", re.I))
                if loc_el:
                    loc = clean_text(loc_el.get_text())
                else:
                    addr = re.search(r"\d{2,5}\s+[A-Za-z].{5,100}", text)
                    if addr:
                        loc = clean_text(addr.group(0))[:200]

                # Description: look for a "Description" header then collect following paragraphs
                desc = ""
                desc_hdr = dsoup.find(lambda t: t.name in ["h2","h3"] and "Description" in t.get_text())
                if desc_hdr:
                    parts = []
                    for sib in desc_hdr.find_all_next(["p","li"], limit=12):
                        parts.append(sib.get_text(" ", strip=True))
                    desc = clean_text(" ".join(parts))[:1200]

                out.append(normalize_event(title, start, end, all_day, loc, href, source="GNFCC Chamber", description=desc))
                time.sleep(0.2)  # be polite
            except Exception as e:
                print(f"[GNFCC] Detail error {href}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[GNFCC] List error: {e}", file=sys.stderr)
    return out


def cherokee_events():
    """
    Crawl the Cherokee Chamber widgets list, follow each event (id=...), parse.
    """
    out = []
    try:
        r = fetch(CHEROKEE_WIDGETS_LIST)
        soup = BeautifulSoup(r.text, "html.parser")

        # Links look like ...event.aspx?cid=94&id=4048&wid=701
        links = []
        for a in soup.select("a[href*='event.aspx?'][href*='id=']"):
            href = a.get("href")
            if href:
                full = urljoin(CHEROKEE_WIDGETS_LIST, href)
                if full not in links:
                    links.append(full)

        for href in links:
            try:
                dr = fetch(href)
                dsoup = BeautifulSoup(dr.text, "html.parser")

                # Title (often last h1/h2 near the top)
                title = "(Untitled)"
                h_candidates = dsoup.find_all(["h1","h2"], string=True)
                if h_candidates:
                    title = clean_text(h_candidates[-1].get_text())

                page_text = dsoup.get_text("\n", strip=True)

                # Start/End like: "Start: Thursday, August 14, 2025 at 4:00 PM"
                start_m = re.search(
                    r"Start:\s*([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})\s+at\s+(\d{1,2}:\d{2}\s*(AM|PM))",
                    page_text, re.I)
                end_m = re.search(
                    r"End:\s*([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})\s+at\s+(\d{1,2}:\d{2}\s*(AM|PM))",
                    page_text, re.I)
                start = try_parse_date(f"{start_m.group(1)} {start_m.group(2)}") if start_m else None
                end   = try_parse_date(f"{end_m.group(1)} {end_m.group(2)}") if end_m else None

                # Location: prefer Google Maps block; fallback to an address-like match
                loc = ""
                venue = dsoup.find("a", href=re.compile(r"maps\.google\.com", re.I))
                if venue:
                    loc = clean_text(venue.parent.get_text(" ", strip=True).replace("Get directions:", ""))[:200]
                else:
                    m = re.search(r"[A-Za-z][A-Za-z &'.,-]{2,100}\s+\d{1,5}\s+[A-Za-z].{3,80}", page_text)
                    if m:
                        loc = clean_text(m.group(0))[:200]

                # Description: near a "Details" header
                desc = ""
                details_hdr = dsoup.find(lambda t: t.name in ["h2","h3"] and "Details" in t.get_text())
                if details_hdr:
                    p = details_hdr.find_next("p")
                    if p:
                        desc = clean_text(p.get_text(" ", strip=True))[:1200]

                out.append(normalize_event(title, start, end, False, loc, href, source="Cherokee Chamber", description=desc))
                time.sleep(0.2)
            except Exception as e:
                print(f"[Cherokee] Detail error {href}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[Cherokee] List error: {e}", file=sys.stderr)
    return out


def rotary_forsyth_events_stub():
    """
    The Rotary site renders events via JavaScript (DACdb) and doesn't expose a stable
    public HTML/ICS endpoint here. This stub returns an empty list but documents the source.
    If you obtain a public ICS/RSS, add it to ICS_URLS/RSS_URLS above.
    """
    print("[Rotary Forsyth] Skipped: dynamic calendar (DACdb) with no public ICS/RSS configured.", file=sys.stderr)
    return []


# --------------------
# 4) Main
# --------------------
def main():
    all_events = []

    # Generic sources
    for u in ICS_URLS:
        all_events += from_ics(u)

    for u in RSS_URLS:
        all_events += from_rss(u)

    # Site-specific sources
    all_events += gnfcc_events()
    all_events += cherokee_events()
    all_events += rotary_forsyth_events_stub()

    # Deduplicate by (title, start, source, url)
    seen = set()
    dedup = []
    for e in all_events:
        key = (e["title"].lower(), e["start"], e["source"], e["url"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)

    # Sort by start date ascending (missing dates last)
    def sort_key(e):
        s = e["start"]
        return (1, "") if not s else (0, s)
    dedup.sort(key=sort_key)

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(dedup, f, ensure_ascii=False, indent=2)
    print(f"Wrote events.json with {len(dedup)} events")

if __name__ == "__main__":
    main()
