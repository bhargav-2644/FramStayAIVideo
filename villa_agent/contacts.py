"""Find the owner's published email and Instagram on their own website, and score the lead."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
INSTAGRAM_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I)
CONTACT_PATHS = ("", "/contact", "/contact-us", "/about", "/about-us")
NOT_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
NOT_EMAIL_DOMAINS = ("example.com", "sentry.io", "wixpress.com", "domain.com")
INSTAGRAM_NOT_HANDLES = {"p", "reel", "reels", "explore", "accounts", "stories", "tv"}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FarmStayPreview/0.1)"}


def find_emails(html: str) -> list[str]:
    found = []
    for m in EMAIL_RE.findall(html):
        e = m.strip(".").lower()
        if e.endswith(NOT_EMAIL_SUFFIXES) or e.split("@")[1] in NOT_EMAIL_DOMAINS:
            continue
        if e not in found:
            found.append(e)
    return found


def find_instagram(html: str) -> str | None:
    for handle in INSTAGRAM_RE.findall(html):
        if handle.lower() not in INSTAGRAM_NOT_HANDLES:
            return handle.rstrip(".")
    return None


def best_email(emails: list[str], website: str) -> str | None:
    """Prefer an address on the property's own domain, then any other."""
    host = urlparse(website).netloc.lower().removeprefix("www.")
    for e in emails:
        if host and e.split("@")[1].endswith(host):
            return e
    return emails[0] if emails else None


def scrape_contacts(website: str, session: requests.Session | None = None) -> dict:
    """Look at the home page and common contact pages for an email and Instagram."""
    http = session or requests.Session()
    emails: list[str] = []
    sources: dict[str, str] = {}
    instagram = None
    for path in CONTACT_PATHS:
        url = urljoin(website.rstrip("/") + "/", path.lstrip("/"))
        try:
            r = http.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException:
            continue
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
            continue
        for e in find_emails(r.text):
            if e not in emails:
                emails.append(e)
                sources[e] = url
        instagram = instagram or find_instagram(r.text)
        if emails and instagram:
            break
    email = best_email(emails, website)
    return {"email": email, "email_source": sources.get(email), "instagram": instagram}


def score(lead: dict, rules: dict) -> tuple[int, str | None]:
    """0 to 100, and a reason when the lead should be rejected."""
    if not lead.get("email"):
        return 0, "no email published on the website"
    if (lead.get("rating") or 0) < rules.get("min_rating", 4.0):
        return 0, f"rating {lead.get('rating')} below {rules.get('min_rating', 4.0)}"
    if (lead.get("review_count") or 0) < rules.get("min_reviews", 20):
        return 0, f"only {lead.get('review_count') or 0} reviews"
    if (lead.get("photo_count") or 0) < rules.get("min_photos", 3):
        return 0, f"only {lead.get('photo_count') or 0} photos"
    points = 40
    points += min(30, int(((lead["rating"] or 0) - 4.0) * 30))
    points += min(20, (lead["review_count"] or 0) // 25)
    points += 10 if lead.get("instagram") else 0
    return min(points, 100), None
