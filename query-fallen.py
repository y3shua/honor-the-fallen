#!/usr/bin/env python3
"""
Honor the Fallen daily memorial post.

Finds every service member in the Military Times "Honor the Fallen" database
who died on today's month/day in any year, renders them as cards on one image
(or a few, 9 per image), and publishes ONE Facebook Page post.

Env:
  FB_ACCESS_TOKEN, FB_PAGE_ID   Page token (pages_manage_posts) and numeric Page ID
  GRAPH_VERSION                 default v23.0
  TARGET_DATE                   optional MM-DD override
  START_YEAR                    default 2001
  DRY_RUN                       "true" writes preview/ instead of posting
  USE_PROXY, PROXY_URL          optional proxy for militarytimes.com
"""
import io
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://thefallen.militarytimes.com"
SEARCH_URL = f"{BASE}/search"
LANCZOS = Image.Resampling.LANCZOS
DELAY = 1.0

TOKEN = os.getenv("FB_ACCESS_TOKEN", "").strip()
PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
GRAPH = f"https://graph.facebook.com/{os.getenv('GRAPH_VERSION', 'v23.0')}"
START_YEAR = int(os.getenv("START_YEAR", "2001"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
PROXY = os.getenv("PROXY_URL") if os.getenv("USE_PROXY", "false").lower() == "true" else None

# Layout
COLS_MAX, PER_SHEET = 3, 9
CARD_W, PHOTO_H, CAPTION_H = 420, 525, 200
CARD_H = PHOTO_H + CAPTION_H
GAP, MARGIN, HEADER_H, FOOTER_H = 28, 48, 170, 70

BG, PANEL, NAVY = (16, 22, 34), (28, 38, 56), (22, 32, 48)
GOLD, WHITE, GREY = (196, 164, 98), (242, 242, 238), (170, 178, 190)

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
            continue
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


# ---------------------------------------------------------------- drawing helpers

@lru_cache(maxsize=None)
def font(size, bold=False):
    for path in FONT_CANDIDATES[bold]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def wrap(draw, text, fnt, max_w):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def fit(draw, text, max_w, size, min_size, max_lines=1, bold=False):
    """Largest font (size..min_size) where text wraps into max_lines within max_w."""
    while True:
        f = font(size, bold)
        lines = wrap(draw, text, f, max_w)
        if (len(lines) <= max_lines and all(draw.textlength(l, font=f) <= max_w for l in lines)) \
                or size <= min_size:
            return lines[:max_lines], f
        size -= 2


def draw_block(draw, blocks, box):
    """Draw [(lines, font, fill, gap_after)] centered in box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    def lh(f):
        a, d = f.getmetrics()
        return a + d
    total = sum(len(lines) * lh(f) + gap for lines, f, _, gap in blocks if lines)
    y = y0 + (y1 - y0 - total) // 2
    for lines, f, fill, gap in blocks:
        if not lines:
            continue
        for line in lines:
            draw.text((x0 + (x1 - x0 - draw.textlength(line, font=f)) / 2, y), line, font=f, fill=fill)
            y += lh(f)
        y += gap


def to_jpeg(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, optimize=True, progressive=True)
    return buf.getvalue()


# ---------------------------------------------------------------- images

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


def get_photo(m):
    for src in (m.photo_url, m.thumb_url):
        if src and not GENERIC_IMG.search(src):
            img = fetch_image(src)
            if img:
                return img
    return None


def fit_photo(img, size):
    """Contain the photo in size over a blurred fill. No stretch, no crop."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    bg = ImageOps.fit(img, size, LANCZOS).filter(ImageFilter.GaussianBlur(24))
    bg = Image.blend(bg, Image.new("RGB", size, (0, 0, 0)), 0.5)
    scale = min(size[0] / img.width, size[1] / img.height)
    fg = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), LANCZOS)
    bg.paste(fg, ((size[0] - fg.width) // 2, (size[1] - fg.height) // 2))
    return bg


def placeholder_panel(m, size):
    """Rank and name only, as large as they will fit."""
    w, h = size
    img = Image.new("RGB", size, NAVY)
    d = ImageDraw.Draw(img)
    d.rectangle([18, 18, w - 19, h - 19], outline=GOLD, width=2)
    max_w = w - 70
    rank = norm(f"{m.branch} {m.rank}") or ""
    name = m.name or m.title or "Unknown"
    rank_lines, rank_font = fit(d, rank, max_w, 48, 28, max_lines=2) if rank else ([], None)
    name_lines, name_font = fit(d, name, max_w, 76, 36, max_lines=3, bold=True)
    draw_block(d, [(rank_lines, rank_font, GOLD, 22), (name_lines, name_font, WHITE, 0)],
               (0, 0, w, h))
    return img


def render_card(m, photo):
    card = Image.new("RGB", (CARD_W, CARD_H), PANEL)
    top = fit_photo(photo, (CARD_W, PHOTO_H)) if photo else placeholder_panel(m, (CARD_W, PHOTO_H))
    card.paste(top, (0, 0))
    d = ImageDraw.Draw(card)
    d.line([(0, PHOTO_H), (CARD_W, PHOTO_H)], fill=GOLD, width=3)

    max_w = CARD_W - 36
    rank = norm(f"{m.branch} {m.rank}").upper()
    blocks = []
    if rank:
        blocks.append((*fit(d, rank, max_w, 24, 16), GOLD, 8))
    lines, f = fit(d, m.name or m.title, max_w, 36, 22, max_lines=2, bold=True)
    blocks.append((lines, f, WHITE, 10))
    if m.died_text:
        blocks.append((*fit(d, m.died_text, max_w, 24, 16), GREY, 4))
    if m.place:
        blocks.append((*fit(d, m.place, max_w, 22, 15), GREY, 0))
    draw_block(d, blocks, (0, PHOTO_H + 4, CARD_W, CARD_H))
    return card


def render_sheet(members, photos, label, index, total):
    n = len(members)
    cols = min(COLS_MAX, n)
    rows = math.ceil(n / cols)
    W = 2 * MARGIN + cols * CARD_W + (cols - 1) * GAP
    H = HEADER_H + rows * CARD_H + (rows - 1) * GAP + FOOTER_H + MARGIN
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)

    heading = f"Remembered on {label}" + (f"  ({index} of {total})" if total > 1 else "")
    draw_block(d, [(*fit(d, "HONOR THE FALLEN", W - 2 * MARGIN, 30, 18), GOLD, 10),
                   (*fit(d, heading, W - 2 * MARGIN, 52, 26, bold=True), WHITE, 0)],
               (0, 20, W, HEADER_H))

    for i, (m, photo) in enumerate(zip(members, photos)):
        r, c = divmod(i, cols)
        in_row = min(cols, n - r * cols)
        row_w = in_row * CARD_W + (in_row - 1) * GAP
        x = (W - row_w) // 2 + c * (CARD_W + GAP)
        y = HEADER_H + r * (CARD_H + GAP)
        sheet.paste(render_card(m, photo), (x, y))

    draw_block(d, [(*fit(d, "Source: Military Times, Honor the Fallen", W - 2 * MARGIN, 22, 14),
                    GREY, 0)],
               (0, H - FOOTER_H - MARGIN // 2, W, H - MARGIN // 2))
    return sheet


# ---------------------------------------------------------------- text

def entry(m):
    head = m.title + (f", {m.age}" if m.age else "")
    died = f"Died {m.died_text}" if m.died_text else "Died"
    if m.place:
        died += f", in {m.place}"
    if m.conflict:
        died += f" ({m.conflict})"
    return "\n".join(x for x in (head, m.hometown, died) if x)


def build_post(members, label):
    n = len(members)
    years = sorted({m.died.year for m in members if m.died})
    when = f"on {label}"
    if len(years) == 1:
        when += f", {years[0]},"
    elif years:
        when += f" between {years[0]} and {years[-1]}"
    who = "the American service member" if n == 1 else f"the {n} American service members"
    lead = (f"Today we remember {who} who died {when} while serving in the nation's "
            f"post-9/11 military operations.")
    body = "\n\n".join(entry(m) for m in members)
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
    return graph_post(f"{PAGE_ID}/photos", {"published": "false", "message": caption},
                      files={"source": ("sheet.jpg", jpeg, "image/jpeg")})["id"]


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
    photos = []
    for m in members:
        p = get_photo(m)
        photos.append(p)
        log(f"  {'photo' if p else 'placeholder'}: {m.title}")

    chunks = [range(i, min(i + PER_SHEET, len(members)))
              for i in range(0, len(members), PER_SHEET)]
    sheets = []
    for idx, rng in enumerate(chunks, 1):
        group = [members[i] for i in rng]
        img = render_sheet(group, [photos[i] for i in rng], label, idx, len(chunks))
        sheets.append((to_jpeg(img), "\n".join(m.title for m in group)))

    message = build_post(members, label)

    if DRY_RUN:
        os.makedirs("preview", exist_ok=True)
        for i, (jpeg, _) in enumerate(sheets, 1):
            with open(f"preview/sheet_{i}.jpg", "wb") as f:
                f.write(jpeg)
        with open("preview/post.txt", "w") as f:
            f.write(message)
        log(f"Dry run: {len(sheets)} image(s) and post text written to preview/")
        return 0

    uploaded = []
    try:
        for jpeg, caption in sheets:
            uploaded.append(upload_unpublished(jpeg, caption))
        post_id = publish(message, uploaded)
    except Exception as e:
        log(f"Post failed, removing {len(uploaded)} unpublished image(s): {e}")
        for pid in uploaded:
            delete_photo(pid)
        return 1

    log(f"Published post {post_id}: {len(members)} members on {len(sheets)} image(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
