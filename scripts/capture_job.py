#!/usr/bin/env python3
"""Capture a job posting from a URL.

Priority chain:
    1. requests + BeautifulSoup (cheap, text-only). Used if the page returns
       a substantial body that looks like a job posting.
    2. Playwright headless Chromium: full-page screenshot + rendered HTML +
       text extraction. Used when (1) returns thin/blocked content.
    3. Manual paste fallback: emits a stub instructing the user to paste the
       posting manually (and reminds them they can use Claude-in-Chrome to
       grab it).

Artifacts written into <out_dir>:
    job-source.html      raw or rendered HTML
    job-screenshot.png   full-page screenshot (Playwright only)
    job-description.md   extracted text (or a paste-here stub)
    capture.log          which path was taken, why

Importable: `from capture_job import capture`.
"""

from __future__ import annotations

import argparse
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from urllib.parse import urlparse, parse_qs
from html import unescape as _html_unescape

from job_validation import validate_job_text


UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

# Below this many extracted words, we assume the page didn't actually serve
# the job description (login wall, JS-only render, etc.) and escalate.
THIN_CONTENT_WORD_THRESHOLD = 80

# Domains we know need a real browser. Skip requests, go straight to Playwright.
JS_REQUIRED_HOSTS = {
    "linkedin.com",
    "www.linkedin.com",
    "workday.com",
    "myworkdayjobs.com",
    "greenhouse.io",
    "boards.greenhouse.io",
    "lever.co",
    "jobs.lever.co",
    "ashbyhq.com",
    "jobs.ashbyhq.com",
}


# ----- text extraction ---------------------------------------------------

def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    # Drop structural noise.
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header",
                     "form", "aside", "svg", "button"]):
        tag.decompose()
    # Drop obvious non-description blocks by class/id (benefits, perks, cookie
    # banners, nav, social) — these are what naive extraction wrongly grabs.
    noise = re.compile(
        r"(benefit|perk|cookie|consent|subscribe|newsletter|footer|header|"
        r"nav|menu|social|related|sidebar|promo|banner)", re.I)
    for el in soup.find_all(attrs={"class": noise}):
        el.decompose()
    for el in soup.find_all(attrs={"id": noise}):
        el.decompose()
    # Prefer a semantic main/article region if present.
    root = (soup.find("main") or soup.find("article")
            or soup.find(attrs={"role": "main"}) or soup)
    # Heuristic: the largest job-description-ish container within the root.
    candidates = root.find_all(
        attrs={"class": re.compile(
            r"(job|description|posting|content|role|qualif|responsib)", re.I)}
    )
    text = ""
    for c in candidates:
        t = c.get_text("\n", strip=True)
        if len(t.split()) > len(text.split()):
            text = t
    if not text:
        text = root.get_text("\n", strip=True)
    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _word_count(text: str) -> int:
    return len(text.split())


# ----- capture strategies -----------------------------------------------

def _try_requests(url: str) -> Optional[tuple[str, str]]:
    """Returns (html, text) or None if it clearly failed."""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20, allow_redirects=True)
    except requests.RequestException as e:
        return ("", f"REQUESTS_ERROR: {e}")
    if resp.status_code >= 400:
        return ("", f"REQUESTS_HTTP_{resp.status_code}")
    html = resp.text or ""
    text = _extract_text(html)
    return (html, text)


def _try_playwright(url: str, out_dir: Path) -> Optional[tuple[str, str]]:
    """Returns (html, text). Also writes the full-page screenshot.
    Raises if Playwright/chromium aren't installed."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 1800})
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        # Give SPAs a moment to render the description
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        page.screenshot(path=str(out_dir / "job-screenshot.png"), full_page=True)
        html = page.content()
        # Embedded ATS boards render the posting inside an <iframe> — a separate
        # document NOT included in page.content(). Extract text from every frame
        # and keep whichever yields the most. This catches iframe-embedded
        # boards generically, without a per-provider handler.
        candidates = [(_extract_text(html), html)]
        for fr in page.frames:
            if fr is page.main_frame:
                continue
            try:
                fhtml = fr.content()
            except Exception:
                continue
            candidates.append((_extract_text(fhtml), fhtml))
        browser.close()
    best_text, best_html = max(candidates, key=lambda c: len(c[0].split()))
    return (best_html, best_text)


# ----- Ashby (hosted + embedded job boards) ------------------------------

ASHBY_POSTING_API = (
    "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"
)

# Subdomain labels / TLDs that are never a board token, so a domain-derived
# guess (company.careers → "company") can skip them.
_NON_TOKEN_LABELS = {"www", "careers", "career", "jobs", "job", "apply",
                     "boards", "work", "com", "io", "co", "net", "org", "ai"}


def _dedupe(seq: list) -> list:
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def _domain_token_candidates(host: str) -> list:
    """Best-effort ATS board-token guesses from the host: the company label.
    e.g. www.instacart.careers / careers.instacart.com → ['instacart']."""
    labels = [l for l in host.lower().split(".") if l]
    cands = []
    if len(labels) >= 2 and labels[-2] not in _NON_TOKEN_LABELS:
        cands.append(labels[-2])
    for l in labels:
        if l not in _NON_TOKEN_LABELS and l not in cands:
            cands.append(l)
    return cands


def _ashby_ids(url: str) -> tuple[Optional[str], Optional[str]]:
    """(org, job_id) if this looks like an Ashby posting, else (None, None).
    Handles jobs.ashbyhq.com/<org>/<id> and embedded boards (?ashby_jid=<id>)."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    jid = (parse_qs(parsed.query).get("ashby_jid") or [None])[0]
    org = None
    if host.endswith("ashbyhq.com"):
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            org = parts[0]
        if not jid and len(parts) >= 2:
            jid = parts[1]
    return org, jid


def _ashby_org_from_html(html: str) -> Optional[str]:
    """Embedded boards reference their org as jobs.ashbyhq.com/<org> or
    /<org>/embed in the page HTML/script."""
    for pat in (r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)",
                r"/([A-Za-z0-9_.-]+)/embed"):
        m = re.search(pat, html or "")
        if m and m.group(1) != "embed":
            return m.group(1)
    return None


def _try_ashby(url: str) -> Optional[tuple[str, str, str]]:
    """If the URL is an Ashby posting (hosted or embedded), fetch the real
    description from Ashby's public posting API. Returns (text, html, via) or
    None. The page HTML is just a JS shell, so scraping it yields marketing /
    benefits noise — the API is the source of truth."""
    if "ashby_jid=" not in url and "ashbyhq.com" not in url.lower():
        return None
    org, jid = _ashby_ids(url)
    if not jid:
        return None
    if not org:  # embedded board on a company domain — find the org in the page
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            org = _ashby_org_from_html(resp.text)
        except requests.RequestException:
            org = None
    if not org:  # last resort: guess the org from the company domain
        guesses = _domain_token_candidates(_host_of(url))
        org = guesses[0] if guesses else None
    if not org:
        return None
    try:
        resp = requests.get(ASHBY_POSTING_API.format(org=org),
                            headers={"User-Agent": UA}, timeout=30)
        if resp.status_code >= 400:
            return None
        jobs = (resp.json() or {}).get("jobs", [])
    except (requests.RequestException, ValueError):
        return None
    job = next((j for j in jobs if j.get("id") == jid), None)
    if not job:
        return None
    desc = (job.get("descriptionPlain") or "").strip()
    if not desc:
        return None
    header = []
    if job.get("title"):
        header.append(f"# {job['title']}")
    meta = []
    if job.get("location"):
        meta.append(job["location"])
    if job.get("employmentType"):
        meta.append(job["employmentType"])
    if job.get("isRemote"):
        meta.append("Remote")
    if meta:
        header.append("**" + " · ".join(dict.fromkeys(meta)) + "**")
    if job.get("jobUrl"):
        header.append(f"Source: {job['jobUrl']}")
    text = ("\n\n".join(header) + "\n\n" + desc).strip() if header else desc
    return (text, job.get("descriptionHtml") or "", f"ashby-api:{org}")


# ----- Greenhouse (hosted + embedded job boards) -------------------------

GREENHOUSE_JOB_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{jid}"


def _greenhouse_ids(url: str) -> tuple[Optional[str], Optional[str]]:
    """(board_token, job_id) for a Greenhouse posting, else (None, None).
    Handles boards.greenhouse.io/<token>/jobs/<id> and boards embedded on a
    company site (…?gh_jid=<id>)."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    jid = (parse_qs(parsed.query).get("gh_jid") or [None])[0]
    token = None
    if host.endswith("greenhouse.io"):
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[0] != "embed":
            token = parts[0]
        if not jid and "jobs" in parts:
            i = parts.index("jobs")
            if i + 1 < len(parts):
                jid = parts[i + 1]
        if not token:
            token = (parse_qs(parsed.query).get("for") or [None])[0]
    return token, jid


def _greenhouse_token_from_html(html: str) -> Optional[str]:
    """Embedded boards reference their token as boards.greenhouse.io/<token>,
    embed/job_board?for=<token>, or a `for=<token>` config value."""
    for pat in (r"boards\.greenhouse\.io/embed/job_board\?for=([A-Za-z0-9_]+)",
                r"boards\.greenhouse\.io/([A-Za-z0-9_]+)",
                r"job_board\?for=([A-Za-z0-9_]+)",
                r"[\"']for[\"']\s*[:=]\s*[\"']([A-Za-z0-9_]+)[\"']"):
        m = re.search(pat, html or "")
        if m and m.group(1) not in ("embed", "job_board"):
            return m.group(1)
    return None


def _try_greenhouse(url: str) -> Optional[tuple[str, str, str]]:
    """If the URL is a Greenhouse posting (hosted or embedded), fetch the real
    description from Greenhouse's public board API. Returns (text, html, via)
    or None. Embedded company pages are often pure-JS (no token in the static
    HTML), so we also guess the board token from the domain and validate it
    against the API."""
    if "gh_jid=" not in url and "greenhouse.io" not in url.lower():
        return None
    token, jid = _greenhouse_ids(url)
    if not jid:
        return None
    candidates = [token] if token else []
    if not token:
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            t = _greenhouse_token_from_html(resp.text)
            if t:
                candidates.append(t)
        except requests.RequestException:
            pass
        candidates += _domain_token_candidates(_host_of(url))
    for tok in _dedupe(candidates):
        try:
            resp = requests.get(GREENHOUSE_JOB_API.format(token=tok, jid=jid),
                                headers={"User-Agent": UA}, timeout=30)
            if resp.status_code >= 400:
                continue
            job = resp.json() or {}
        except (requests.RequestException, ValueError):
            continue
        raw = job.get("content") or ""
        if not raw:
            continue
        # Greenhouse returns the body as HTML with entities escaped.
        desc = BeautifulSoup(_html_unescape(raw), "lxml").get_text("\n", strip=True)
        desc = re.sub(r"\n{3,}", "\n\n", desc).strip()
        if not desc:
            continue
        header = []
        if job.get("title"):
            header.append(f"# {job['title']}")
        loc = (job.get("location") or {}).get("name")
        if loc:
            header.append(f"**{loc}**")
        if job.get("absolute_url"):
            header.append(f"Source: {job['absolute_url']}")
        text = ("\n\n".join(header) + "\n\n" + desc).strip() if header else desc
        return (text, raw, f"greenhouse-api:{tok}")
    return None


# ----- main capture flow -------------------------------------------------

def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def capture(url: str, out_dir: Path) -> dict:
    """Run the capture chain. Returns a small dict with what happened."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log_lines = [f"[{datetime.utcnow().isoformat()}Z] capture_job url={url}"]
    host = _host_of(url)
    js_required = (any(host.endswith(h) for h in JS_REQUIRED_HOSTS)
                   or "ashby_jid=" in url or host.endswith("ashbyhq.com")
                   or "gh_jid=" in url)

    html, text = "", ""
    via = "unknown"

    # 0) Embedded ATS boards (Ashby, Greenhouse, …) serve the real description
    #    from a public API; the page itself is a JS shell that scrapes into
    #    marketing/benefits noise or nothing. Try those APIs first.
    for _ats in (_try_ashby, _try_greenhouse):
        if _word_count(text) >= THIN_CONTENT_WORD_THRESHOLD:
            break
        _res = _ats(url)
        if _res is not None:
            text, html, via = _res
            log_lines.append(f"{via}: {_word_count(text)} words")

    # 1) requests (cheap) for non-JS hosts, unless we already have the content.
    if _word_count(text) < THIN_CONTENT_WORD_THRESHOLD and not js_required:
        result = _try_requests(url)
        if result is not None:
            r_html, r_text = result
            if r_text.startswith("REQUESTS_"):
                log_lines.append(f"requests failed: {r_text}")
            else:
                html, text = r_html, r_text
                via = "requests"
                log_lines.append(f"requests OK: {_word_count(text)} words")
    elif js_required and _word_count(text) < THIN_CONTENT_WORD_THRESHOLD:
        log_lines.append(f"host {host} requires JS, skipping requests")

    # 2) Playwright when we still don't have enough text OR the capture looks
    #    incomplete — we want a full-page screenshot for the skill's universal
    #    screenshot→LLM extraction fallback even if some text came through.
    if (_word_count(text) < THIN_CONTENT_WORD_THRESHOLD
            or not validate_job_text(text)["complete"]):
        log_lines.append("escalating to Playwright (thin or incomplete)")
        try:
            pw_html, pw_text = _try_playwright(url, out_dir)
            if _word_count(pw_text) > _word_count(text):
                html, text = pw_html, pw_text
                via = "playwright"
                log_lines.append(f"playwright OK: {_word_count(text)} words")
            else:
                log_lines.append(f"playwright thin: {_word_count(pw_text)} words")
        except Exception as e:
            log_lines.append(f"playwright failed: {e}")
            log_lines.append(traceback.format_exc().splitlines()[-1])

    # Always keep the raw/rendered HTML for re-parsing or the screenshot→LLM
    # extraction fallback.
    if html:
        (out_dir / "job-source.html").write_text(html, encoding="utf-8")

    slug = out_dir.name
    has_text = _word_count(text) >= THIN_CONTENT_WORD_THRESHOLD
    v = validate_job_text(text)
    missing = v["missing"]

    if not has_text:
        status, complete = "needs_manual_paste", False
        missing = ["description", "duties", "requirements"]
        body = (
            f"<!-- AUTOMATED CAPTURE FAILED for {url} -->\n\n"
            "# Job description (needs extraction)\n\n"
            "Automated text capture was too thin (JS-only render, login wall, or "
            "anti-bot). A full-page screenshot was saved as `job-screenshot.png` "
            "if the browser could reach the page.\n\n"
            f"**Next:** run `/capture-job jobs/{slug}` in Claude Code to extract "
            "the posting from the screenshot, or paste it manually below.\n\n"
            f"URL: <{url}>\n\n"
            "---\n\n"
            "<!-- paste the job description here -->\n"
        )
    else:
        complete = v["complete"]
        status = "captured" if complete else "incomplete"
        banner = ""
        if not complete:
            banner = (
                f"> ⚠️ **INCOMPLETE CAPTURE** — automated extraction appears to be "
                f"missing: **{', '.join(missing)}**.\n"
                f"> Run `/capture-job jobs/{slug}` in Claude Code to extract the full "
                f"posting from `job-screenshot.png`, or paste/clean it in below.\n\n"
            )
        body = (
            f"<!-- captured via {via} from {url} at "
            f"{datetime.utcnow().isoformat()}Z (status={status}) -->\n\n"
            + banner +
            "# Job description (extracted)\n\n"
            "_Verify the extraction below against the original posting. "
            "If text was truncated or includes navigation/footer noise, "
            "clean it up here — this file is the source of truth for tailoring._\n\n"
            "---\n\n"
            + text
        )

    (out_dir / "job-description.md").write_text(body, encoding="utf-8")

    log_lines.append(
        f"final: status={status} complete={complete} missing={missing} "
        f"via={via} words={_word_count(text)}")
    (out_dir / "capture.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    return {"status": status, "via": via, "words": _word_count(text),
            "complete": complete, "missing": missing}


def main():
    parser = argparse.ArgumentParser(description="Capture a job posting.")
    parser.add_argument("url")
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    result = capture(args.url, args.out_dir)
    print(result)


if __name__ == "__main__":
    main()
