#!/usr/bin/env python3
"""
Fallen Heroes Memorial Script
Queries fallen service members from militarytimes.com and posts detailed memorials to Facebook.
Enhanced with album posting - creates single post with multiple photos.
Refactored for efficiency and maintainability.
"""

import os
import re
import io
import time
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from PIL import Image

# Setup logging
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s', level=logging.INFO
)
log = logging.getLogger(__name__)

# Environment variables
ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
PAGE_ID = os.getenv("FB_PAGE_ID")
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
PROXY = os.getenv("PROXY_URL")
SEARCH_MODE = os.getenv("SEARCH_MODE", "daily")  # daily, comprehensive, or date_range

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
}

def get_requests_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    if USE_PROXY and PROXY:
        session.proxies.update({"http": PROXY, "https": PROXY})
    return session

def get_fallen_service_members(session, date):
    """Query fallen service members for a specific date."""
    base_url = "https://thefallen.militarytimes.com/search"
    formatted_date = date.strftime("%m%%2F%d%%2F%Y")
    query_url = (
        f"{base_url}?year=&year_month=&first_name=&last_name="
        f"&start_date={formatted_date}&end_date={formatted_date}"
        f"&conflict=&home_state=&home_town="
    )

    try:
        response = session.get(query_url, timeout=30)
        if response.status_code != 200 or "Access Denied" in response.text or "Captcha" in response.text:
            log.warning(f"Blocked or failed fetching {query_url} (Status: {response.status_code})")
            return []
    except requests.RequestException as e:
        log.error(f"Network error fetching {query_url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    fallen_list = []

    for entry in soup.select(".data-box"):
        name_tag = entry.select_one(".data-box-right h3 a")
        name = name_tag.text.strip() if name_tag else "Unknown"
        date_tag = entry.select_one(".data-box-right .blue-bold")
        date_of_death = date_tag.text.strip() if date_tag else "Unknown Date"
        profile_link = name_tag["href"].rstrip(':').rstrip() if name_tag and "href" in name_tag.attrs else ""
        image_tag = entry.select_one(".data-box-left img")
        image_url = image_tag["src"] if image_tag and "src" in image_tag.attrs else ""
        if image_url and image_url.startswith("/"):
            image_url = f"https://thefallen.militarytimes.com{image_url}"
        fallen_list.append({
            "name": name,
            "date": date_of_death,
            "link": profile_link,
            "image_url": image_url
        })
    return fallen_list

def search_comprehensive_range(session, start_date, end_date):
    """Search for all fallen service members in a date range."""
    all_service_members = []
    for n in range((end_date - start_date).days + 1):
        date = start_date + timedelta(days=n)
        log.info(f"Searching {date.strftime('%m/%d/%Y')}...")
        fallen = get_fallen_service_members(session, date)
        for person in filter(lambda p: p["image_url"], fallen):
            all_service_members.append(person)
            log.info(f"  ✅ {person['name']} - {person['date']} (has photo)")
        time.sleep(1)  # Rate limiting
    return all_service_members

def get_detailed_service_member_info(session, profile_link):
    """Get detailed information from the service member's profile page."""
    if not profile_link:
        return {}

    profile_link = profile_link.rstrip(':').rstrip().lstrip('/')
    if not profile_link.startswith('/'):
        profile_link = '/' + profile_link
    full_url = f"https://thefallen.militarytimes.com{profile_link}"

    try:
        response = session.get(full_url, timeout=30)
        if response.status_code != 200:
            log.warning(f"Failed to fetch profile: {full_url} (Status: {response.status_code})")
            return {}

        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        details = {}

        # Age
        age_match = re.search(r'Age:?\s*(\d+)', content, re.IGNORECASE)
        if age_match: details["age"] = age_match.group(1)

        # Rank
        rank_pattern = r'\b(PVT|PFC|SPC|CPL|SGT|SSG|SFC|MSG|1SG|SGM|CSM|2LT|1LT|CPT|MAJ|LTC|COL|BG|MG|LTG|GEN|ENS|LTJG|LT|LCDR|CDR|CAPT|RDML|RADM|VADM|ADM|Airman|A1C|SrA|SSgt|TSgt|MSgt|SMSgt|CMSgt|2d Lt|1st Lt|Capt|Maj|Lt Col|Col|Brig Gen|Maj Gen|Lt Gen|Gen)\b'
        rank_match = re.search(rank_pattern, content, re.IGNORECASE)
        if rank_match: details["rank"] = rank_match.group(1)

        # Location
        location_patterns = [
            r'of ([^,\n]+(?:, [A-Z]{2})?)',
            r'from ([^,\n]+(?:, [A-Z]{2})?)',
            r'([A-Za-z\s]+, [A-Z]{2})'
        ]
        for pattern in location_patterns:
            location_match = re.search(pattern, content)
            if location_match:
                location = location_match.group(1).strip()
                if len(location) > 3 and not location.lower().startswith(('the', 'was', 'and', 'who')):
                    details["location"] = location
                    break

        # Death location
        death_location_patterns = [
            r'killed in ([^,\n.]+(?:, [A-Za-z]+)?)',
            r'died in ([^,\n.]+(?:, [A-Za-z]+)?)',
            r'in ([A-Za-z\s]+(?:, Iraq|, Afghanistan|, Syria))',
            r'(Iraq|Afghanistan|Syria|Kuwait|Pakistan|Jordan|Somalia|Yemen)',
            r'province of ([A-Za-z\s]+)',
            r'near ([A-Za-z\s]+(?:, Iraq|, Afghanistan))'
        ]
        for pattern in death_location_patterns:
            death_location_match = re.search(pattern, content, re.IGNORECASE)
            if death_location_match:
                death_location = death_location_match.group(1).strip()
                if len(death_location) > 2 and not death_location.lower().startswith(('the', 'was', 'and', 'who', 'a ')):
                    details["death_location"] = death_location
                    break

        # Branch
        branch_pattern = r'\b(Army|Navy|Marine Corps|Marines|Air Force|Coast Guard|Space Force)\b'
        branch_match = re.search(branch_pattern, content, re.IGNORECASE)
        if branch_match: details["branch"] = branch_match.group(1)

        # Unit
        unit_patterns = [
            r'(\d+(?:st|nd|rd|th)?\s+[^,\n]{10,50}(?:Battalion|Regiment|Brigade|Division|Squadron|Wing|Group))',
            r'([A-Z][\w\s]*(Battalion|Regiment|Brigade|Division|Squadron|Wing|Group)[^,\n]{0,30})'
        ]
        for pattern in unit_patterns:
            unit_match = re.search(pattern, content, re.IGNORECASE)
            if unit_match:
                details["unit"] = unit_match.group(1).strip()
                break

        # Incident details
        incident_section = soup.select_one('.incident-details, .profile-details, .bio')
        if incident_section:
            incident_text = incident_section.get_text().strip()
            if len(incident_text) > 50:
                sentences = incident_text.split('.')
                details["circumstances"] = (
                    sentences[0] + "." if sentences and len(sentences[0]) < 200 else incident_text[:200] + "..."
                )
        return details

    except Exception as e:
        log.error(f"Error getting details for {profile_link}: {e}")
        return {}

def resize_image_for_facebook(image_data):
    """Resize image to optimal Facebook dimensions to prevent stretching."""
    try:
        image = Image.open(io.BytesIO(image_data))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        target_size = (1200, 1200)
        width, height = image.size
        if width != height:
            size = min(width, height)
            left, top = (width - size) // 2, (height - size) // 2
            right, bottom = left + size, top + size
            image = image.crop((left, top, right, bottom))
        resized_image = image.resize(target_size, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        resized_image.save(output, format='JPEG', quality=98, optimize=True)
        return output.getvalue()
    except Exception as e:
        log.error(f"Error resizing image: {e}")
        return image_data

def test_facebook_credentials(session):
    """Test if Facebook credentials are valid."""
    if not ACCESS_TOKEN or not PAGE_ID:
        log.error("Missing ACCESS_TOKEN or PAGE_ID")
        return False

    test_url = f"https://graph.facebook.com/v18.0/{PAGE_ID}?access_token={ACCESS_TOKEN}"
    try:
        response = session.get(test_url, timeout=30)
        if response.status_code == 200:
            page_info = response.json()
            log.info(f"Connected to page: {page_info.get('name', 'Unknown')}")
            return True
        else:
            log.error(f"Failed to connect: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        log.error(f"Error testing credentials: {e}")
        return False

def fetch_profile_details_parallel(session, service_members):
    """Fetch details for each person (parallelized)."""
    details_list = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_person = {
            executor.submit(get_detailed_service_member_info, session, person["link"]): person
            for person in service_members
        }
        for future in as_completed(future_to_person):
            person = future_to_person[future]
            try:
                details = future.result()
                details_list.append((person, details))
            except Exception as exc:
                log.error(f"Error fetching details for {person['name']}: {exc}")
    return details_list

def download_and_resize_image(session, image_url):
    """Download and resize image for Facebook."""
    try:
        response = session.get(image_url, timeout=30)
        if response.status_code != 200 or len(response.content) < 1000:
            return None
        return resize_image_for_facebook(response.content)
    except Exception as e:
        log.error(f"Error downloading image {image_url}: {e}")
        return None

def upload_photos_to_album(session, service_member_details):
    """Upload photos to Facebook without publishing, return photo IDs for album creation."""
    log.info(f"Uploading {len(service_member_details)} photos to Facebook album...")
    photo_ids = []
    for i, (person, details) in enumerate(service_member_details, 1):
        if not person["image_url"]:
            log.warning(f"No image for {person['name']}, skipping...")
            continue
        log.info(f"Processing {i}/{len(service_member_details)}: {person['name']}")
        image_data = download_and_resize_image(session, person["image_url"])
        if not image_data:
            log.warning(f"Failed to process image for {person['name']}")
            continue
        upload_url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/photos"
        files = {'source': ('hero_photo.jpg', image_data, 'image/jpeg')}
        data = {
            "access_token": ACCESS_TOKEN,
            "published": "false",
            "caption": f"{person['name']} - {person['date']}"
        }
        try:
            response = session.post(upload_url, data=data, files=files, timeout=60)
            if response.status_code == 200:
                result = response.json()
                photo_id = result.get("id")
                if photo_id: photo_ids.append(photo_id)
                log.info(f"Uploaded (Photo ID: {photo_id})")
            else:
                log.error(f"Facebook API error: {response.status_code} {response.text}")
        except Exception as e:
            log.error(f"Error uploading photo for {person['name']}: {e}")
        if i < len(service_member_details):
            time.sleep(2)
    log.info(f"Uploaded {len(photo_ids)} out of {len(service_member_details)} photos")
    return photo_ids

def create_album_post_caption(service_member_details):
    today = datetime.today()
    caption = [
        "🇺🇸 HONORING OUR FALLEN HEROES 🇺🇸",
        f"📅 Service Members Who Made the Ultimate Sacrifice on {today.strftime('%B %d')}",
        "",
        "🎗️ TODAY WE REMEMBER:",
        ""
    ]
    for i, (person, details) in enumerate(service_member_details, 1):
        member_info = [f"#{i} {person['name'].upper()}"]
        if details.get("rank") and details.get("branch"):
            member_info.append(f"   🎖️ {details['branch']} {details['rank']}")
        elif details.get("rank"):
            member_info.append(f"   🎖️ {details['rank']}")
        elif details.get("branch"):
            member_info.append(f"   ⚔️ {details['branch']}")
        if details.get("age"):
            member_info.append(f"   👤 Age {details['age']}")
        if details.get("location"):
            member_info.append(f"   🏠 {details['location']}")
        member_info.append(f"   📅 {person['date']}")
        if details.get("death_location"):
            member_info.append(f"   📍 {details['death_location']}")
        caption.extend(member_info)
        caption.append("")
    caption.extend([
        "🕊️ We will never forget their service and sacrifice.",
        "🙏 Each of these heroes gave their life for our freedom.",
        "⭐ True American heroes, all.",
        "",
        "🔗 Learn more about each hero:",
        "https://thefallen.militarytimes.com/",
        "",
        "#FallenHeroes #NeverForget #Military #Sacrifice #Honor #Memorial #GoldStar #Heroes #Freedom #RememberThem"
    ])
    return "\n".join(caption)

def create_multi_photo_post(session, photo_ids, service_member_details):
    """Create a single Facebook post with multiple photos."""
    if not photo_ids:
        log.warning("No photo IDs to create post with")
        return False
    log.info(f"Creating album post with {len(photo_ids)} photos...")
    caption = create_album_post_caption(service_member_details)
    attached_media = [{"media_fbid": photo_id} for photo_id in photo_ids]
    post_url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
    post_data = {
        "message": caption,
        "attached_media": attached_media,
        "access_token": ACCESS_TOKEN
    }
    try:
        response = session.post(post_url, json=post_data, timeout=60)
        if response.status_code == 200:
            post_id = response.json().get("id", "unknown")
            log.info(f"Successfully created album post (Post ID: {post_id})")
            return True
        else:
            log.error(f"Failed to create album post: {response.status_code}\n{response.text}")
            return False
    except Exception as e:
        log.error(f"Error creating album post: {e}")
        return False

def post_images_to_facebook(session, service_members):
    """Upload photos and create a single album post with all service members."""
    log.info(f"Creating memorial album with {len(service_members)} service members...")
    service_member_details = fetch_profile_details_parallel(session, service_members)
    photo_ids = upload_photos_to_album(session, service_member_details)
    if not photo_ids:
        log.error("No photos were uploaded successfully")
        return 0
    success = create_multi_photo_post(session, photo_ids, service_member_details)
    if success:
        log.info(f"Created memorial album post with {len(photo_ids)} heroes")
        return len(photo_ids)
    else:
        log.error("Failed to create album post")
        return 0

def main():
    log.info("=" * 60)
    log.info("🇺🇸 FALLEN HEROES MEMORIAL FACEBOOK POSTING SCRIPT 🇺🇸")
    log.info("=" * 60)
    log.info(f"ACCESS_TOKEN: {'Set' if ACCESS_TOKEN else 'NOT SET'}")
    log.info(f"PAGE_ID: {'Set' if PAGE_ID else 'NOT SET'}")
    log.info(f"USE_PROXY: {USE_PROXY}")
    log.info(f"SEARCH_MODE: {SEARCH_MODE}")
    if not ACCESS_TOKEN or not PAGE_ID:
        log.error("Missing required environment variables! Please set FB_ACCESS_TOKEN and FB_PAGE_ID")
        return 1
    if not PAGE_ID.isdigit():
        log.error(f"PAGE_ID should be numeric, got: {PAGE_ID}")
        return 1
    session = get_requests_session()
    if not test_facebook_credentials(session):
        log.error("Facebook credential test failed!")
        return 1
    today = datetime.today()
    all_service_members = []
    if SEARCH_MODE == "comprehensive":
        iraq_invasion_date = datetime(2003, 3, 20)
        log.info(f"Comprehensive search: {iraq_invasion_date.strftime('%m/%d/%Y')} to {today.strftime('%m/%d/%Y')}")
        all_service_members = search_comprehensive_range(session, iraq_invasion_date, today)
    elif SEARCH_MODE == "recent":
        start_date = today - timedelta(days=30)
        log.info(f"Recent search: Last 30 days ({start_date.strftime('%m/%d/%Y')} to {today.strftime('%m/%d/%Y')})")
        all_service_members = search_comprehensive_range(session, start_date, today)
    else:
        search_years = list(range(2003, today.year + 1))
        log.info(f"Daily search: Searching for fallen service members on {today.strftime('%B %d')} across multiple years...")
        for year in search_years:
            try:
                search_date = today.replace(year=year)
                log.info(f"Checking {search_date.strftime('%B %d, %Y')}...")
                fallen = get_fallen_service_members(session, search_date)
                for person in filter(lambda p: p["image_url"], fallen):
                    all_service_members.append(person)
                    log.info(f"  ✅ {person['name']} - {person['date']} (has photo)")
                time.sleep(1)
            except ValueError:
                log.info(f"Skipping {year} (date doesn't exist)")
                continue
    log.info("=" * 60)
    if all_service_members:
        log.info(f"Found {len(all_service_members)} service members with photos")
        log.info("Starting Facebook album creation process...")
        log.info("=" * 60)
        success_count = post_images_to_facebook(session, all_service_members)
        log.info("=" * 60)
        if success_count > 0:
            log.info(f"COMPLETED: Successfully created memorial album with {success_count} heroes")
        else:
            log.error("FAILED: No memorial album was created")
        log.info("🇺🇸 Honor and remember our fallen heroes 🇺🇸")
        log.info("=" * 60)
        return 0 if success_count > 0 else 1
    else:
        log.info("No fallen service members with images found for this search.")
        log.info("🇺🇸 We honor all who have served 🇺🇸")
        log.info("=" * 60)
        return 0

if __name__ == "__main__":
    exit(main())
