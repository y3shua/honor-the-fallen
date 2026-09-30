#!/usr/bin/env python3
"""
Honor the Fallen daily memorial post.

Finds every service member in the Military Times "Honor the Fallen" database
who died on today's month/day in any year, scrapes each profile, builds a
uniform image for each (real photo or rank/name placeholder), and publishes
ONE Facebook Page post with every image attached.

Env:
  FB_ACCESS_TOKEN   Page access token (pages_manage_posts, pages_read_engagement)
  FB_PAGE_ID        Numeric Page ID
  GRAPH_VERSION     Graph API version (default v23.0)
  TARGET_DATE       Optional MM-DD override (default: today)
  START_YEAR        First year to search (default 2001)
  DRY_RUN           "true" writes preview/ files instead of posting
  USE_PROXY, PROXY_URL  Optional proxy for militarytimes.com requests
"""
import io
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://thefallen.militarytimes.com"
SEARCH_URL = f"{BASE}/search"
CANVAS = (1080, 1080)
LANCZOS = Image.Resampling.LANCZOS
DELAY = 1.0

TOKEN = os.getenv("FB_ACCESS_TOKEN", "").strip()
PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
GRAPH = f"https://graph.facebook.com/{os.getenv('GRAPH_VERSION', 'v23.0')}"
START_YEAR = int(os.getenv("START_YEAR", "2001"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
PROXY = os.getenv("PROXY_URL") if os.getenv("USE_PROXY", "false").lower() == "true" else None

NAVY, GOLD, WHITE, GREY = (22, 32, 48), (196, 164, 98), (240, 240, 236), (170, 178, 190)

BRANCH_PREFIXES = ("Marine Corps", "Air Force", "Coast Guard", "Space Force",
                   "Marines", "Marine", "Army", "Navy")
RANK_WORDS = {
    "1st", "2nd", "3rd", "first", "second", "third", "class", "staff", "master",
    "command", "lance", "gunnery", "petty", "officer", "chief", "senior",
    "warrant", "seaman", "airman", "ensign", "private", "specialist", "sergeant",
    "corporal", "hospitalman", "hospital", "corpsman", "apprentice", "recruit",
    "fireman", "constructionman", "technical", "tech.", "j.g.", "2", "3", "4", "5",
}
COUNTRIES = (r"(?:Iraq|Afghanistan|Syria|Kuwait|Qatar|Bahrain|Jordan|Pakistan|"
             r"Djibouti|Niger|Somalia|Kenya|Yemen|Oman|Saudi Arabia|"
             r"United Arab Emirates|Turkey|Uzbekistan|Kyrgyzstan|Egypt|Germany|"
             r"Kosovo|Libya|the Philippines|Mali|Cameroon|Chad|Persian Gulf|"
             r"Arabian Gulf|Arabian Sea|Red Sea|Gulf of Aden)")
PLACE_RE = re.compile(
    r"\b(?:in|near|at|outside)\s+((?:(?:[A-Z][\w'’.\-]*|al|as|ad|an|of|the|"
    r"province|district|city)[\s,]+){0,6}?" + COUNTRIES + r")\b")
HOMETOWN_RE = re.compile(r"^\s*(?:(\d{1,3}),\s*)?of\s+([^;]+?)\s*;", re.I)
GENERIC_IMG = re.compile(r"honor-the-fallen|no[-_]?photo|placeholder|default|silhouette|blank", re.I)

FONT_CANDIDATES = {
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


@dataclass
class Member:
    url: str
    title: str = ""
    branch: str = ""
    rank: str = ""
    name: str = ""
    died: date | None = None
    died_text: str = ""
    conflict: str = ""
    age: str = ""
    hometown: str = ""
    place: str = ""
    summary: str = ""
    photo_url: str | None = None
    thumb_url: str | None = None


def log(msg):
    print(msg, flush=True)


def make_session(proxy=None):
    s = requests.Session()
    s.headers["User-Agent"] = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


SCRAPE = make_session(PROXY)
FB = make_session()


def norm(text):
    return " ".join((text or "").split())


def clean_url(href, base):
    return urljoin(base, href.strip().rstrip(":").strip())


def get_soup(url, params=None):
    try:
        r = SCRAPE.get(url, params=params, timeout=30)
    except requests.RequestException as e:
        log(f"  request failed: {url}: {e}")
        return None, url
    if r.status_code != 200 or "Access Denied" in r.text or "Captcha" in r.text:
        log(f"  blocked or failed ({r.status_code}): {r.url}")
        return None, r.url
    return BeautifulSoup(r.text, "html.parser"), r.url


# ---------------------------------------------------------------- search

def next_page(soup, current):
    a = soup.find("a", rel="next", href=True)
    if not a:
        labels = {"next", "next »", "next ›", "»", "›"}
        a = next((x for x in soup.find_all("a", href=True)
                  if x.get_text(strip=True).lower() in labels), None)
    if not a:
        return None
    nxt = clean_url(a["href"], current)
    return None if nxt == current else nxt


def find_profiles(month, day, today):
    """Return {profile_url: thumbnail_url} for every death on month/day, all years."""
    found = {}
    for year in range(START_YEAR, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue  # Feb 29 in non-leap years
        if d > today:
            continue
        stamp = d.strftime("%m/%d/%Y")
        params = {"year": "", "year_month": "", "first_name": "", "last_name": "",
                  "start_date": stamp, "end_date": stamp, "conflict": "",
                  "home_state": "", "home_town": ""}
        before, url, pages = len(found), SEARCH_URL, 0
        while url and pages < 20:
            soup, final = get_soup(url, params if pages == 0 else None)
            if not soup:
                break
            pages += 1
            for box in soup.select(".data-box"):
                a = box.select_one(".data-box-right h3 a[href]")
                if not a:
                    continue
                img = box.select_one(".data-box-left img[src]")
                found.setdefault(clean_url(a["href"], final),
                                 clean_url(img["src"], final) if img else None)
            url = next_page(soup, final)
            time.sleep(DELAY)
        log(f"{stamp}: {len(found) - before} found")
    return found


# ---------------------------------------------------------------- profile

def hidden(rec, cls):
    el = rec.select_one(f"input.{cls}")
    return norm(el.get("value", "")) if el else ""


def official_summary(rec):
    """Text between the first and second <hr> in .record-txt (the casualty notice)."""
    hrs = rec.find_all("hr")
    if not hrs:
        return ""
    parts = []
    for sib in hrs[0].next_siblings:
        if getattr(sib, "name", None) == "hr":
            break
        parts.append(sib.get_text(" ") if hasattr(sib, "get_text") else str(sib))
    return norm(" ".join(parts))


def is_rank_token(tok):
    return tok.lower() in RANK_WORDS or bool(re.fullmatch(r"[A-Z][a-z]{1,4}\.", tok))


def split_title(title, branch):
    """'Army Spc. Anthony D. Kinslow' -> ('Army', 'Spc.', 'Anthony D. Kinslow')"""
    rest, found_branch = title, branch
    for b in ((branch,) if branch else ()) + BRANCH_PREFIXES:
        if rest.lower().startswith(b.lower() + " "):
            rest, found_branch = rest[len(b):].strip(), found_branch or b
            break
    tokens = rest.split()
    i = 0
    while i < len(tokens) - 1 and is_rank_token(tokens[i]):
        i += 1
    return found_branch, " ".join(tokens[:i]), " ".join(tokens[i:])


def parse_place(summary):
    m = re.search(r"\b(?:died|killed)\b", summary, re.I)
    text = summary[m.start():] if m else summary.split(";", 1)[-1]
    p = PLACE_RE.search(text)
    return p.group(1).strip(" ,") if p else ""


def scrape_profile(url, thumb):
    soup, _ = get_soup(url)
    if not soup:
        return None
    rec = soup.select_one(".record-txt")
    if not rec:
        log(f"  no record found: {url}")
        return None

    m = Member(url=url, thumb_url=thumb)
    h1, h2 = rec.select_one("h1"), rec.select_one("h2")
    m.title = norm(h1.get_text()) if h1 else ""
    h2_text = norm(h2.get_text()) if h2 else ""

    m.conflict = hidden(rec, "dimension1")
    if not m.conflict and (c := re.search(r"Serving During (.+)$", h2_text)):
        m.conflict = c.group(1)
    m.died_text = hidden(rec, "dimension3")
    if not m.died_text and (c := re.search(r"Died (.+?) Serving", h2_text)):
        m.died_text = c.group(1)
    try:
        m.died = datetime.strptime(m.died_text, "%B %d, %Y").date()
    except ValueError:
        pass

    m.branch, m.rank, m.name = split_title(m.title, hidden(rec, "dimension2"))
    m.summary = official_summary(rec)
    if hm := HOMETOWN_RE.search(m.summary):
        m.age, m.hometown = hm.group(1) or "", norm(hm.group(2))
    m.place = parse_place(m.summary)

    img = soup.select_one(".record-image img[src]")
    m.photo_url = clean_url(img["src"], url) if img else None
    return m


# ---------------------------------------------------------------- images

def font(size, bold=False):
    for path in FONT_CANDIDATES[bold]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def to_jpeg(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, optimize=True, progressive=True)
    return buf.getvalue()


def fetch_image(url):
    try:
        r = SCRAPE.get(url, timeout=30)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        img.load()
    except Exception as e:
        log(f"  image unavailable ({url}): {e}")
        return None
    return img if min(img.size) >= 60 else None


def compose_photo(img):
    """Fit the photo inside a square canvas over a blurred fill. No stretch, no crop."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    bg = ImageOps.fit(img, CANVAS, LANCZOS).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", CANVAS, (0, 0, 0)), 0.5)
    scale = min(CANVAS[0] / img.width, CANVAS[1] / img.height)
    fg = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), LANCZOS)
    bg.paste(fg, ((CANVAS[0] - fg.width) // 2, (CANVAS[1] - fg.height) // 2))
    return to_jpeg(bg)


def wrap(draw, text, fnt, max_width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def make_placeholder(m):
    W, H = CANVAS
    img = Image.new("RGB", CANVAS, NAVY)
    d = ImageDraw.Draw(img)
    d.rectangle([36, 36, W - 37, H - 37], outline=GOLD, width=3)
    d.rectangle([50, 50, W - 51, H - 51], outline=GOLD, width=1)

    name = m.name or m.title or "Unknown"
    size = 88
    while size > 40:
        name_font = font(size, bold=True)
        name_lines = wrap(d, name, name_font, W - 200)
        if len(name_lines) <= 3 and all(d.textlength(l, font=name_font) <= W - 200 for l in name_lines):
            break
        size -= 6

    blocks = []  # (text or None for rule, font, fill, gap_after)
    if m.branch:
        blocks.append((m.branch.upper(), font(34), GOLD, 28))
    if m.rank:
        blocks.append((m.rank, font(54), WHITE, 22))
    for i, line in enumerate(name_lines):
        blocks.append((line, name_font, WHITE, 12 if i < len(name_lines) - 1 else 40))
    blocks.append((None, None, GOLD, 40))
    if m.died_text:
        blocks.append((m.died_text, font(38), GREY, 14))
    if m.conflict:
        blocks.append((m.conflict, font(32), GREY, 0))

    heights = []
    for text, fnt, _, _ in blocks:
        heights.append(2 if text is None else d.textbbox((0, 0), text, font=fnt)[3]
                       - d.textbbox((0, 0), text, font=fnt)[1])
    y = (H - sum(h + b[3] for h, b in zip(heights, blocks))) // 2
    for (text, fnt, fill, gap), h in zip(blocks, heights):
        if text is None:
            d.line([(W // 2 - 90, y), (W // 2 + 90, y)], fill=fill, width=2)
        else:
            top = d.textbbox((0, 0), text, font=fnt)[1]
            d.text(((W - d.textlength(text, font=fnt)) / 2, y - top), text, font=fnt, fill=fill)
        y += h + gap
    return to_jpeg(img)


def build_image(m):
    for src in (m.photo_url, m.thumb_url):
        if src and not GENERIC_IMG.search(src):
            img = fetch_image(src)
            if img:
                return compose_photo(img), True
    return make_placeholder(m), False


# ---------------------------------------------------------------- text

def sentence(m):
    s = m.title or m.name
    if m.age:
        s += f", {m.age}"
    if m.hometown:
        s += f", of {m.hometown}"
    s += f", died {m.died_text}" if m.died_text else ", died"
    if m.place:
        s += f", in {m.place}"
    if m.conflict:
        s += f", during {m.conflict}"
    return s + "."


def photo_caption(m):
    return "\n".join(x for x in (sentence(m), m.summary, m.url) if x)


def build_post(members, label):
    n = len(members)
    who = "one American service member" if n == 1 else f"{n} American service members"
    lead = (f"On {label} in years past, {who} died while serving in the nation's post-9/11 "
            f"military operations. Their names, hometowns and where they died are recorded "
            f"below, drawn from the Military Times Honor the Fallen database.")
    body = "\n".join(sentence(m) for m in members)
    return f"{lead}\n\n{body}\n\nFull service records: {BASE}"


# ---------------------------------------------------------------- facebook

def graph_post(path, data, files=None):
    r = FB.post(f"{GRAPH}/{path}", data={**data, "access_token": TOKEN}, files=files, timeout=120)
    try:
        body = r.json()
    except ValueError:
        body = {"error": {"message": r.text}}
    if r.status_code != 200 or "error" in body:
        raise RuntimeError(f"Graph API {path}: {r.status_code} {body.get('error', body)}")
    return body


def upload_unpublished(jpeg, caption):
    return graph_post(f"{PAGE_ID}/photos",
                      {"published": "false", "message": caption},
                      files={"source": ("photo.jpg", jpeg, "image/jpeg")})["id"]


def publish(message, media_ids):
    data = {"message": message}
    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    return graph_post(f"{PAGE_ID}/feed", data)["id"]


def delete_photo(pid):
    try:
        FB.delete(f"{GRAPH}/{pid}", params={"access_token": TOKEN}, timeout=30)
    except requests.RequestException:
        pass


# ---------------------------------------------------------------- main

def main():
    today = date.today()
    if os.getenv("TARGET_DATE"):
        month, day = map(int, os.getenv("TARGET_DATE").split("-"))
    else:
        month, day = today.month, today.day
    label = f"{date(2000, month, day):%B} {day}"

    if not DRY_RUN and (not TOKEN or not PAGE_ID.isdigit()):
        log("FB_ACCESS_TOKEN and a numeric FB_PAGE_ID are required.")
        return 1

    log(f"Searching {label}, {START_YEAR}-{today.year}")
    profiles = find_profiles(month, day, today)
    log(f"{len(profiles)} unique profiles")

    members = []
    for url, thumb in profiles.items():
        m = scrape_profile(url, thumb)
        if m:
            members.append(m)
            log(f"  {m.title} | {m.died_text} | {m.place or 'place not listed'}")
        time.sleep(DELAY)
    if not members:
        log("No records for this date. Nothing posted.")
        return 0

    members.sort(key=lambda m: m.died or date.max)
    images = []
    for m in members:
        jpeg, real = build_image(m)
        images.append(jpeg)
        log(f"  image: {'photo' if real else 'placeholder'} for {m.title}")

    message = build_post(members, label)

    if DRY_RUN:
        os.makedirs("preview", exist_ok=True)
        for i, (m, jpeg) in enumerate(zip(members, images), 1):
            with open(f"preview/{i:02d}.jpg", "wb") as f:
                f.write(jpeg)
            with open(f"preview/{i:02d}.txt", "w") as f:
                f.write(photo_caption(m))
        with open("preview/post.txt", "w") as f:
            f.write(message)
        log(f"Dry run: {len(members)} images and post text written to preview/")
        return 0

    uploaded = []
    try:
        for m, jpeg in zip(members, images):
            uploaded.append(upload_unpublished(jpeg, photo_caption(m)))
            time.sleep(1)
        post_id = publish(message, uploaded)
    except Exception as e:
        log(f"Post failed, removing {len(uploaded)} unpublished photos: {e}")
        for pid in uploaded:
            delete_photo(pid)
        return 1

    log(f"Published post {post_id} with {len(uploaded)} images.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
