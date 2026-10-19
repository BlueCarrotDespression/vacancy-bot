"""Vacancy scraper: checks career pages, sends each new vacancy to Telegram once.

python scraper.py           normal run (sends new vacancies, updates seen.json)
python scraper.py --doctor  test run: sends a per-site report, saves page HTML to debug/, changes nothing
"""
import hashlib
import html as htmllib
import json
import os
import re
import sys
import time
import traceback
from urllib.parse import urljoin, urlparse, urlencode, parse_qsl, urlunparse

import requests
from bs4 import BeautifulSoup

from sites import SITES

STATE_FILE = "seen.json"
MAX_SEEN_PER_SITE = 3000
MAX_NEW_PER_RUN = 40          # per site; the rest are sent on the next run
FAIL_ALERT_AFTER = 12         # consecutive failed runs before a Telegram alert (~2-3 h)
SEND_EXISTING = os.environ.get("SEND_EXISTING", "false").lower() == "true"

DOCTOR = "--doctor" in sys.argv
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ru,en;q=0.9"})


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


# ---------------------------------------------------------------- fetching

_pw = None
_browser = None


def browser():
    global _pw, _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch()
    return _browser


def get_html(url, render=False, click_more=None):
    if not render:
        r = S.get(url, timeout=40)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        return r.text
    ctx = browser().new_context(user_agent=UA, locale="ru-RU")
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        for _ in range(4):
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(700)
        if click_more:
            for _ in range(15):
                btn = page.get_by_text(re.compile(click_more, re.I))
                if btn.count() == 0 or not btn.first.is_visible():
                    break
                try:
                    btn.first.click(timeout=5000)
                    page.wait_for_timeout(1500)
                except Exception:
                    break
        page.wait_for_timeout(2500)
        return page.content()
    finally:
        ctx.close()


def html_to_text(h):
    soup = BeautifulSoup(h, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    return soup.get_text("\n")


def dump_debug(site, h, suffix=""):
    if not DOCTOR:
        return
    os.makedirs("debug", exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", site["name"].lower()).strip("-")
    with open(f"debug/{slug}{suffix}.html", "w", encoding="utf-8") as f:
        f.write(h)


def norm_url(u):
    p = urlparse(u)
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm")]
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", "", urlencode(q), ""))


def make_id(site, url):
    rx = site.get("id_regex")
    if rx:
        m = re.search(rx, url)
        if m:
            return m.group(1)
    return norm_url(url)


# ---------------------------------------------------------------- experience

EXP_WORD = re.compile(r"опыт|стаж|experience|өтіл|тәжірибе", re.I)
Y = r"(?:год|лет(?!н)|years?|yrs?|жыл)"
WORDNUMS = {
    "одного": 1, "один": 1, "двух": 2, "два": 2, "трех": 3, "трёх": 3, "три": 3,
    "четырех": 4, "четырёх": 4, "пяти": 5, "пять": 5, "шести": 6, "семи": 7, "десяти": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "ten": 10,
}
NO_EXP = re.compile(r"без опыта|опыт (работы )?не требуется|не требуется опыт|"
                    r"no (prior |previous )?experience (is )?(required|needed)|"
                    r"опыт работы:?\s*не требуется|тәжірибесіз", re.I)
RANGE = [
    re.compile(r"от\s*(\d+)\s*(?:год[аы]?|лет)?\s*до\s*(\d+)\s*" + Y, re.I),
    re.compile(r"between\s*(\d+)\s*and\s*(\d+)\s*" + Y, re.I),
    re.compile(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)\s*\+?\s*" + Y, re.I),
]
MIN = [
    re.compile(r"(?:не менее|не меньше|от|более|свыше|минимум|at least|minimum(?: of)?|min\.?|"
               r"over|more than|кемінде)\s*(\d+)\s*\+?\s*(?:-?х|-?ти|-?и)?\s*" + Y, re.I),
    re.compile(r"(\d+)\s*\+\s*" + Y, re.I),
    re.compile(r"(\d+)\s*" + Y + r"\w*\s*(?:and above|or more|и более|кем емес)", re.I),
]
PLAIN = re.compile(r"(\d+)\s*(?:-?х|-?ти|-?и)?\s*" + Y, re.I)


def _ok(*nums):
    return all(0 < int(n) <= 30 for n in nums)


def _match_window(w):
    if NO_EXP.search(w):
        return "No experience required"
    for rx in RANGE:
        m = rx.search(w)
        if m and _ok(m.group(1), m.group(2)) and int(m.group(1)) < int(m.group(2)):
            return f"{m.group(1)}-{m.group(2)} years"
    for rx in MIN:
        m = rx.search(w)
        if m and _ok(m.group(1)):
            return f"{m.group(1)}+ years"
    m = PLAIN.search(w)
    if m and _ok(m.group(1)):
        return f"{m.group(1)} years"
    return None


def extract_experience(text):
    if not text:
        return None
    t = text
    for w, n in WORDNUMS.items():
        t = re.sub(rf"\b{w}\b(?=\s*(?:\(\d+\)\s*)?(?:год|лет|years?|жыл))", str(n), t, flags=re.I)
    t = re.sub(r"\((\d+)\)", r"\1", t)
    t = re.sub(r"\b(\d+)\s+\1\b", r"\1", t)      # "трех (3) лет" -> "3 3 лет" -> "3 лет"
    lines = [clean(x) for x in re.split(r"[\n;•·]|(?<=[.!?])\s", t)]
    lines = [x for x in lines if x]
    for i, line in enumerate(lines):
        if EXP_WORD.search(line):
            window = " ".join(lines[i:i + 3]) if len(line) < 60 else line
            r = _match_window(window)
            if r:
                return r
    # postings that say "5+ years in ..." without the word "experience"
    for rx in MIN[:2]:
        m = rx.search(t)
        if m and _ok(m.group(1)):
            return f"{m.group(1)}+ years"
    return None


HH_EXP = {"noExperience": "No experience required", "between1And3": "1-3 years",
          "between3And6": "3-6 years", "moreThan6": "6+ years"}


def experience_for(site, item):
    if "exp" in item:
        return item["exp"]
    try:
        m = re.search(r"hh\.(?:ru|kz)/vacancy/(\d+)", item["url"])
        if m:
            d = S.get(f"https://api.hh.ru/vacancies/{m.group(1)}", timeout=30).json()
            return HH_EXP.get((d.get("experience") or {}).get("id"))
        if item.get("detail_text") is not None:
            return extract_experience(item["detail_text"])
        if item.get("detail_api"):
            d = S.get(item["detail_api"], headers={"Accept": "application/json"}, timeout=30).json()
            desc = (d.get("jobPostingInfo") or {}).get("jobDescription") or d.get("job_description") or ""
            return extract_experience(html_to_text(desc))
        h = get_html(item["url"], site.get("detail_render", site.get("render", False)))
        return extract_experience(html_to_text(h))
    except Exception as e:
        print(f"  experience lookup failed for {item['url']}: {e}")
        return None


# ---------------------------------------------------------------- scrapers

GENERIC = re.compile(r"^(подробнее|подробности|читать далее|read more|learn more|more|details|view|"
                     r"apply|apply now|откликнуться|узнать больше|смотреть|перейти|толығырақ)$", re.I)


def anchor_title(a):
    lines = [clean(x) for x in a.get_text("\n").split("\n") if clean(x)]
    first = next((x for x in lines if len(x) >= 4 and not GENERIC.match(x)), "")
    if first:
        return first[:200]
    node = a
    for _ in range(5):
        node = node.parent
        if node is None:
            break
        h = node.find(["h1", "h2", "h3", "h4", "h5", "strong", "b"])
        if h and len(clean(h.get_text(" "))) >= 4:
            return clean(h.get_text(" "))[:200]
    return clean(a.get("title") or a.get("aria-label") or "")[:200]


def scrape_links(site):
    pat = re.compile(site["pattern"], re.I)
    exc = re.compile(site["exclude"], re.I) if site.get("exclude") else None
    found = {}
    for n, url in enumerate(site.get("pages") or [site["url"]]):
        h = get_html(url, site.get("render", False), site.get("click_more"))
        dump_debug(site, h, f"-p{n + 1}" if site.get("pages") else "")
        soup = BeautifulSoup(h, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"].strip())
            if not pat.search(href) or (exc and exc.search(href)):
                continue
            if norm_url(href) == norm_url(url):
                continue
            jid = make_id(site, href)
            title = anchor_title(a)
            if jid not in found or (title and not found[jid]["title"]):
                found[jid] = {"id": jid, "title": title, "url": href}
    items = list(found.values())
    if not items and site.get("fallback"):
        fb = dict(site, **site["fallback"])
        fb["_html"] = h
        items = scrape_section(fb)
    return items


SKIP_LINE = re.compile(r"^(aksai|аксай|ақсай|field|office|офис|поле|вахта|rotation|\d{1,2}\s*/\s*\d{1,2})\b", re.I)


def scrape_section(site):
    h = site.get("_html") or get_html(site["url"], site.get("render", False))
    if "_html" not in site:
        dump_debug(site, h)
    text = html_to_text(h)
    end = text.find(site["end"]) if site.get("end") else -1
    if site.get("start"):
        # last heading occurrence before the end marker (skips menu links with the same text)
        start = text.rfind(site["start"], 0, end) if end > 0 else text.find(site["start"])
        if start < 0:
            return []
        start += len(site["start"])
    else:
        start = 0
    sec = text[start:end if end > start else len(text)]
    lines = [clean(x) for x in sec.split("\n") if clean(x)]
    anchor = re.compile(site["anchor"], re.I)
    idx = [i for i, l in enumerate(lines) if anchor.search(l)]
    items = []
    for k, i in enumerate(idx):
        title = ""
        for j in range(i - 1, max(i - 5, -1), -1):
            if len(lines[j]) >= 6 and not SKIP_LINE.match(lines[j]) and not anchor.search(lines[j]):
                title = lines[j]
                break
        if not title:
            continue
        block_end = idx[k + 1] - 1 if k + 1 < len(idx) else min(len(lines), i + 40)
        block = "\n".join(lines[i:block_end])
        jid = hashlib.sha1((title + "|" + lines[i]).encode()).hexdigest()[:16]
        items.append({"id": jid, "title": title, "url": site["url"],
                      "exp": extract_experience(block)})
    return items


def scrape_wordpress(site):
    base = site["base"].rstrip("/")
    try:
        cats = S.get(f"{base}/wp-json/wp/v2/categories", params={"slug": site["category"]}, timeout=30).json()
        cid = cats[0]["id"]
        posts = S.get(f"{base}/wp-json/wp/v2/posts",
                      params={"categories": cid, "per_page": 50}, timeout=30).json()
        return [{"id": str(p["id"]), "title": clean(htmllib.unescape(p["title"]["rendered"])),
                 "url": p["link"], "detail_text": html_to_text(p["content"]["rendered"])} for p in posts]
    except Exception as e:
        print(f"  WP REST failed ({e}), trying RSS")
    r = S.get(f"{base}/category/{site['category']}/feed/", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "xml")
    out = []
    for it in soup.find_all("item"):
        link = clean(it.link.get_text())
        body = it.find("encoded") or it.find("description")
        out.append({"id": norm_url(link), "title": clean(it.title.get_text()), "url": link,
                    "detail_text": html_to_text(body.get_text()) if body else None})
    return out


def _find_facet(node, name, parent_param=None):
    if isinstance(node, dict):
        param = node.get("facetParameter", parent_param)
        if clean(node.get("descriptor", "")).lower() == name.lower() and node.get("id"):
            return parent_param, node["id"]
        for v in node.get("values", []) or []:
            r = _find_facet(v, name, param)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _find_facet(v, name, parent_param)
            if r:
                return r
    return None


def scrape_workday(site):
    host, tenant, wsite = site["host"], site["tenant"], site["site"]
    api = f"https://{host}/wday/cxs/{tenant}/{wsite}/jobs"
    hdr = {"Accept": "application/json", "Content-Type": "application/json"}
    body = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
    if site.get("country"):
        d = S.post(api, json=body, headers=hdr, timeout=40).json()
        f = _find_facet(d.get("facets", []), site["country"])
        if not f:
            return []          # no open jobs in that country right now
        body["appliedFacets"] = {f[0]: [f[1]]}
    items = []
    for off in range(0, 200, 20):
        body["offset"] = off
        d = S.post(api, json=body, headers=hdr, timeout=40).json()
        posts = d.get("jobPostings", [])
        for p in posts:
            path = p["externalPath"]
            items.append({"id": path, "title": p.get("title", ""),
                          "url": f"https://{host}/{wsite}{path}",
                          "detail_api": f"https://{host}/wday/cxs/{tenant}/{wsite}{path}"})
        if len(posts) < 20:
            break
    return items


def scrape_eightfold(site):
    base = site["base"].rstrip("/")
    params = {"domain": site["domain"], "start": 0, "num": 100, "sort_by": "timestamp"}
    if site.get("location"):
        params["location"] = site["location"]
    d = S.get(f"{base}/api/apply/v2/jobs", params=params,
              headers={"Accept": "application/json"}, timeout=40).json()
    items = []
    for p in d.get("positions", []):
        locs = " ".join([p.get("location") or ""] + list(p.get("locations") or []))
        if site.get("location") and site["location"].lower() not in locs.lower():
            continue
        items.append({"id": str(p["id"]), "title": p.get("name", ""),
                      "url": p.get("canonicalPositionUrl") or f"{base}/careers?pid={p['id']}",
                      "detail_api": f"{base}/api/apply/v2/jobs/{p['id']}?domain={site['domain']}"})
    return items


def _walk_jobs(node):
    if isinstance(node, dict):
        jobs = node.get("jobs")
        if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict) and "title" in jobs[0]:
            return jobs
        for v in node.values():
            r = _walk_jobs(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _walk_jobs(v)
            if r:
                return r
    return None


def scrape_phenom(site):
    h = get_html(site["url"])
    dump_debug(site, h)
    jobs = None
    i = h.find("phApp.ddo")
    if i >= 0:
        j = h.find("{", i)
        try:
            ddo, _ = json.JSONDecoder().raw_decode(h[j:])
            jobs = _walk_jobs(ddo.get("eagerLoadRefineSearch", ddo))
        except Exception as e:
            print(f"  phenom JSON parse failed: {e}")
    items = []
    if jobs:
        loc_need = (site.get("location") or "").lower()
        for jb in jobs:
            loc = " ".join(str(jb.get(k, "")) for k in ("location", "city", "country", "multi_location"))
            if loc_need and loc_need not in loc.lower():
                continue
            seq = jb.get("jobSeqNo") or jb.get("jobId") or jb.get("reqId")
            items.append({"id": str(seq), "title": jb.get("title", ""), "url": site["job_base"] + str(seq)})
        return items
    # fallback: render the page and read job links
    fb = dict(site, mode="links", render=True,
              pattern=re.escape(site["job_base"].split("://", 1)[1]))
    return scrape_links(fb)


SCRAPERS = {"links": scrape_links, "section": scrape_section, "wordpress": scrape_wordpress,
            "workday": scrape_workday, "eightfold": scrape_eightfold, "phenom": scrape_phenom}


# ---------------------------------------------------------------- telegram

def tg_send(text):
    if not (TG_TOKEN and TG_CHAT):
        print("[telegram not configured]\n" + text + "\n")
        return True
    for attempt in range(5):
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          data={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": "true"}, timeout=30)
        if r.status_code == 200:
            time.sleep(1.1)
            return True
        if r.status_code == 429:
            time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1)
            continue
        print(f"Telegram error {r.status_code}: {r.text}")
        time.sleep(3)
    return False


def esc(s):
    return htmllib.escape(s or "", quote=False)


def format_vacancy(site, item, exp):
    return (f"<b>{esc(item['title']) or 'Untitled vacancy'}</b>\n"
            f"{esc(site['name'])}\n"
            f"Experience: {esc(exp) if exp else 'not stated'}\n"
            f"{esc(item['url'])}")


# ---------------------------------------------------------------- main

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"sites": {}}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def run_site(site):
    items = SCRAPERS[site["mode"]](site)
    for it in items:
        it["title"] = clean(it.get("title"))
    return items


def doctor():
    lines = ["<b>Scraper check</b>"]
    for site in SITES:
        print(f"== {site['name']}")
        try:
            items = run_site(site)
            exp = experience_for(site, items[0]) if items else None
            sample = "; ".join(esc(i["title"][:60]) for i in items[:3])
            lines.append(f"{'✅' if items else '⚪'} {esc(site['name'])}: {len(items)}"
                         + (f"\n   {sample}\n   exp of 1st: {esc(exp) or 'not stated'}" if items else ""))
            for i in items:
                print(f"   {i['title']} | {i['url']}")
        except Exception as e:
            traceback.print_exc()
            lines.append(f"❌ {esc(site['name'])}: {esc(type(e).__name__)} {esc(str(e)[:120])}")
    msg, chunks = "", []
    for l in lines:
        if len(msg) + len(l) > 3800:
            chunks.append(msg)
            msg = ""
        msg += l + "\n"
    chunks.append(msg)
    for c in chunks:
        tg_send(c)


def main():
    state = load_state()
    sites_state = state.setdefault("sites", {})
    seeded = []
    for site in SITES:
        name = site["name"]
        st = sites_state.setdefault(name, {"seen": [], "fails": 0, "initialized": False})
        print(f"== {name}")
        try:
            items = run_site(site)
        except Exception as e:
            traceback.print_exc()
            st["fails"] = st.get("fails", 0) + 1
            if st["fails"] == FAIL_ALERT_AFTER:
                tg_send(f"⚠️ {esc(name)}: scraping has failed {FAIL_ALERT_AFTER} runs in a row "
                        f"({esc(type(e).__name__)}). The site may have changed.")
            save_state(state)
            continue
        if st.get("fails", 0) >= FAIL_ALERT_AFTER:
            tg_send(f"✅ {esc(name)}: scraping works again.")
        st["fails"] = 0
        seen = set(st["seen"])
        new = [i for i in items if i["id"] not in seen]
        print(f"   {len(items)} found, {len(new)} new")
        if not st.get("initialized") and not SEND_EXISTING:
            st["seen"].extend(i["id"] for i in new)
            st["initialized"] = True
            print(f"   first run: {len(new)} existing vacancies marked as seen")
            seeded.append(f"{esc(name)}: {len(new)}")
        else:
            st["initialized"] = True
            for it in new[:MAX_NEW_PER_RUN]:
                exp = experience_for(site, it)
                if tg_send(format_vacancy(site, it, exp)):
                    st["seen"].append(it["id"])
                    seen.add(it["id"])
        st["seen"] = st["seen"][-MAX_SEEN_PER_SITE:]
        save_state(state)
    if seeded:
        tg_send("🟢 Now tracking (current vacancies skipped, only new ones will be sent):\n"
                + "\n".join(seeded))
    if _browser:
        _browser.close()
        _pw.stop()


if __name__ == "__main__":
    doctor() if DOCTOR else main()
