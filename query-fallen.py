#!/usr/bin/env python3
"""
Fallen Heroes Memorial Script
Queries fallen service members from militarytimes.com and posts detailed memorials to Facebook
Enhanced with album posting - creates single post with multiple photos
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import time
import re
from PIL import Image, ImageDraw, ImageFont
import io

# Environment variables
ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
PAGE_ID = os.getenv("FB_PAGE_ID")
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
PROXY = os.getenv("PROXY_URL")
SEARCH_MODE = os.getenv("SEARCH_MODE", "daily")  # daily, comprehensive, or date_range

def get_fallen_service_members(date):
    """Query fallen service members for a specific date"""
    base_url = "https://thefallen.militarytimes.com/search"
    formatted_date = date.strftime("%m%%2F%d%%2F%Y")
    query_url = f"{base_url}?year=&year_month=&first_name=&last_name=&start_date={formatted_date}&end_date={formatted_date}&conflict=&home_state=&home_town="

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    proxies = {"http": PROXY, "https": PROXY} if USE_PROXY and PROXY else None
    
    try:
        response = requests.get(query_url, headers=headers, proxies=proxies, timeout=30)
    except requests.RequestException as e:
        print(f"[!] Network error fetching {query_url}: {e}")
        return []

    if response.status_code != 200 or "Access Denied" in response.text or "Captcha" in response.text:
        print(f"[!] Failed or blocked when fetching {query_url} (Status: {response.status_code})")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    fallen_list = []

    entries = soup.select(".data-box")
    for entry in entries:
        name_tag = entry.select_one(".data-box-right h3 a")
        name = name_tag.text.strip() if name_tag else "Unknown"
        
        date_tag = entry.select_one(".data-box-right .blue-bold")
        date_of_death = date_tag.text.strip() if date_tag else "Unknown Date"
        
        profile_link = name_tag["href"] if name_tag and "href" in name_tag.attrs else ""
        # Clean up profile link - remove any trailing colons or extra characters
        if profile_link:
            profile_link = profile_link.rstrip(':').rstrip()
        
        image_tag = entry.select_one(".data-box-left img, .record-image img")
        image_url = image_tag["src"] if image_tag and "src" in image_tag.attrs else ""
        
        # Check for S3 bucket URLs or make sure image URL is absolute
        if image_url:
            if image_url.startswith("https://s3.amazonaws.com/"):
                # S3 URL is already absolute, use as-is
                pass
            elif image_url.startswith("/"):
                image_url = f"https://thefallen.militarytimes.com{image_url}"
        
        # Also check for record-image div for higher quality S3 images
        record_image_div = entry.select_one(".record-image")
        if record_image_div and not image_url.startswith("https://s3.amazonaws.com/"):
            record_img = record_image_div.select_one("img")
            if record_img and record_img.get("src"):
                potential_s3_url = record_img["src"]
                if potential_s3_url.startswith("https://s3.amazonaws.com/"):
                    image_url = potential_s3_url  # Prefer S3 URLs for better quality

        fallen_list.append({
            "name": name,
            "date": date_of_death,
            "link": profile_link,
            "image_url": image_url
        })

    return fallen_list

def search_comprehensive_range(start_date, end_date):
    """Search for all fallen service members in a date range"""
    print(f"[*] Comprehensive search from {start_date.strftime('%m/%d/%Y')} to {end_date.strftime('%m/%d/%Y')}")
    
    all_service_members = []
    current_date = start_date
    
    while current_date <= end_date:
        print(f"[*] Searching {current_date.strftime('%m/%d/%Y')}...")
        fallen = get_fallen_service_members(current_date)
        
        if fallen:
            print(f"    Found {len(fallen)} service members")
            for person in fallen:
                if person["image_url"]:
                    all_service_members.append(person)
                    print(f"    ✅ {person['name']} - {person['date']} (has photo)")
        
        current_date += timedelta(days=1)
        time.sleep(1)  # Rate limiting for comprehensive search
    
    return all_service_members

def get_detailed_service_member_info(profile_link):
    """Get detailed information from the service member's profile page"""
    if not profile_link:
        return {}
    
    # Clean the profile link - remove any trailing colons or whitespace
    profile_link = profile_link.rstrip(':').rstrip().lstrip('/')
    if not profile_link.startswith('/'):
        profile_link = '/' + profile_link
    
    full_url = f"https://thefallen.militarytimes.com{profile_link}"
    print(f"    → Fetching: {full_url}")  # Debug URL
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    proxies = {"http": PROXY, "https": PROXY} if USE_PROXY and PROXY else None
    
    try:
        response = requests.get(full_url, headers=headers, proxies=proxies, timeout=30)
        if response.status_code != 200:
            print(f"[!] Failed to fetch profile: {full_url} (Status: {response.status_code})")
            return {}
        
        soup = BeautifulSoup(response.text, "html.parser")
        details = {}
        
        # Get all text content and parse it
        content = soup.get_text()
        
        # Also check if there's a better quality S3 image URL in the profile
        profile_image_div = soup.select_one(".record-image")
        if profile_image_div:
            profile_img = profile_image_div.select_one("img")
            if profile_img and profile_img.get("src"):
                s3_image_url = profile_img["src"]
                if s3_image_url.startswith("https://s3.amazonaws.com/"):
                    details["high_quality_image_url"] = s3_image_url
                    print(f"    → Found S3 image: {s3_image_url}")
        
        # Extract age using regex
        age_match = re.search(r'Age:?\s*(\d+)', content, re.IGNORECASE)
        if age_match:
            details["age"] = age_match.group(1)
        
        # Extract rank - look for common military ranks
        rank_pattern = r'\b(PVT|PFC|SPC|CPL|SGT|SSG|SFC|MSG|1SG|SGM|CSM|2LT|1LT|CPT|MAJ|LTC|COL|BG|MG|LTG|GEN|ENS|LTJG|LT|LCDR|CDR|CAPT|RDML|RADM|VADM|ADM|Airman|A1C|SrA|SSgt|TSgt|MSgt|SMSgt|CMSgt|2d Lt|1st Lt|Maj|Lt Col|Brig Gen|Maj Gen|Lt Gen|Pvt|Lance Cpl|Cpl|Sgt|Staff Sgt|Gunnery Sgt|Master Sgt|1st Sgt|Master Gunnery Sgt|Sgt Maj|2ndLt|1stLt|Capt|Major|Lt Colonel|Colonel|Brigadier General|Major General|Lieutenant General|General)\b'
        rank_match = re.search(rank_pattern, content, re.IGNORECASE)
        if rank_match:
            details["rank"] = rank_match.group(1)
        
        # Extract hometown/location (where they're from) - REMOVED DUE TO PARSING ISSUES
        # Removed location extraction as it was causing incorrect state parsing
        
        # Extract location of death/incident (where they died)
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
        
        # Extract branch of service
        branch_pattern = r'\b(Army|Navy|Marine Corps|Marines|Air Force|Coast Guard|Space Force)\b'
        branch_match = re.search(branch_pattern, content, re.IGNORECASE)
        if branch_match:
            details["branch"] = branch_match.group(1)
        
        # Get unit information - look for common unit patterns
        unit_patterns = [
            r'(\d+(?:st|nd|rd|th)?\s+[^,\n]{10,50}(?:Battalion|Regiment|Brigade|Division|Squadron|Wing|Group))',
            r'([A-Z][\w\s]*(Battalion|Regiment|Brigade|Division|Squadron|Wing|Group)[^,\n]{0,30})'
        ]
        for pattern in unit_patterns:
            unit_match = re.search(pattern, content, re.IGNORECASE)
            if unit_match:
                details["unit"] = unit_match.group(1).strip()
                break
        
        # Extract circumstances/incident details
        incident_section = soup.select_one('.incident-details, .profile-details, .bio')
        if incident_section:
            incident_text = incident_section.get_text().strip()
            if len(incident_text) > 50:
                # Truncate to first sentence or 200 characters
                sentences = incident_text.split('.')
                if sentences and len(sentences[0]) < 200:
                    details["circumstances"] = sentences[0] + "."
                else:
                    details["circumstances"] = incident_text[:200] + "..."
        
        return details
        
    except Exception as e:
        print(f"[!] Error getting details for {profile_link}: {e}")
        return {}

def process_image_original_size(image_data):
    """Process image maintaining original dimensions - no resizing"""
    try:
        # Open image with PIL to ensure it's valid and convert if needed
        image = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if necessary (handles RGBA, P mode, etc.)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Keep original dimensions - DO NOT RESIZE
        print(f"    → Keeping original image size: {image.size[0]}x{image.size[1]}")
        
        # Save to bytes with high quality, maintaining original size
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=95, optimize=True)
        return output.getvalue()
        
    except Exception as e:
        print(f"[!] Error processing image: {e}")
        return image_data  # Return original if processing fails

def test_facebook_credentials():
    """Test if Facebook credentials are valid"""
    print("[*] Testing Facebook credentials...")
    
    if not ACCESS_TOKEN or not PAGE_ID:
        print("❌ Missing ACCESS_TOKEN or PAGE_ID")
        return False
    
    # Test basic API access
    test_url = f"https://graph.facebook.com/v18.0/{PAGE_ID}?access_token={ACCESS_TOKEN}"
    
    try:
        response = requests.get(test_url, timeout=30)
        
        if response.status_code == 200:
            page_info = response.json()
            print(f"✅ Successfully connected to page: {page_info.get('name', 'Unknown')}")
            return True
        else:
            print(f"❌ Failed to connect: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing credentials: {e}")
        return False

def create_individual_hero_caption(person, details, hero_number, total_heroes):
    """Create a caption for an individual hero post"""
    today = datetime.today()
    caption_parts = []
    
    # Header with hero number
    caption_parts.append("🇺🇸 HONORING OUR FALLEN HERO 🇺🇸")
    caption_parts.append(f"📅 {today.strftime('%B %d')} Memorial - Hero {hero_number} of {total_heroes}")
    caption_parts.append("")
    
    # Hero's name prominently displayed
    caption_parts.append(f"🎗️ {person['name'].upper()}")
    caption_parts.append("")
    
    # Military information in clean format
    military_info = []
    if details.get("rank") and details.get("branch"):
        military_info.append(f"🎖️ {details['branch']} {details['rank']}")
    elif details.get("rank"):
        military_info.append(f"🎖️ {details['rank']}")
    elif details.get("branch"):
        military_info.append(f"⚔️ {details['branch']}")
    
    if details.get("unit"):
        military_info.append(f"🏛️ {details['unit']}")
    
    if details.get("age"):
        military_info.append(f"👤 Age {details['age']}")
    
    # Add military info
    caption_parts.extend(military_info)
    caption_parts.append("")
    
    # Sacrifice information
    caption_parts.append(f"📅 Date of Sacrifice: {person['date']}")
    if details.get("death_location"):
        caption_parts.append(f"📍 Location: {details['death_location']}")
    
    caption_parts.append("")
    
    # Circumstances if available
    if details.get("circumstances"):
        caption_parts.append("💔 How They Served:")
        caption_parts.append(details['circumstances'])
        caption_parts.append("")
    
    # Footer
    caption_parts.append("🕊️ We will never forget your service and sacrifice.")
    caption_parts.append("🙏 Thank you for your ultimate sacrifice for our freedom.")
    caption_parts.append("⭐ A true American hero.")
    caption_parts.append("")
    caption_parts.append(f"🔗 Learn more: https://thefallen.militarytimes.com{person['link'].rstrip(':').rstrip()}")
    caption_parts.append("")
    caption_parts.append("#FallenHeroes #NeverForget #Military #Sacrifice #Honor #Memorial #GoldStar #Hero #Freedom")
    
    return "\n".join(caption_parts)

def post_individual_heroes(service_members):
    """Post individual photos with captions for each service member as separate posts"""
    print(f"[*] Creating individual posts for {len(service_members)} heroes...")
    successful_posts = 0
    total_heroes = len(service_members)
    
    for i, person in enumerate(service_members, 1):
        if not person["image_url"]:
            print(f"[!] No image for {person['name']}, skipping...")
            continue
        
        print(f"[*] Processing {i}/{total_heroes}: {person['name']}...")
        
        # Get detailed information
        print(f"    → Fetching profile details...")
        details = get_detailed_service_member_info(person["link"])
        
        # Use high-quality S3 image if available from profile, otherwise use original
        image_url_to_use = details.get("high_quality_image_url", person["image_url"])
        print(f"    → Using image: {image_url_to_use}")
        
        # Create individual hero caption
        caption = create_individual_hero_caption(person, details, i, total_heroes)
        
        try:
            # Download the image (prefer S3 URL if available)
            print(f"    → Downloading image from source...")
            proxies = {"http": PROXY, "https": PROXY} if USE_PROXY and PROXY else None
            image_response = requests.get(image_url_to_use, proxies=proxies, timeout=30)
            
            if image_response.status_code != 200:
                print(f"    ❌ Failed to download image (Status: {image_response.status_code})")
                continue
            
            original_image_data = image_response.content
            
            # Validate image data
            if len(original_image_data) < 1000:  # Less than 1KB is probably not a valid image
                print(f"    ❌ Image file too small, likely invalid")
                continue
            
            # Process image maintaining original size
            print(f"    → Processing image at original size...")
            processed_image_data = process_image_original_size(original_image_data)
            
            # Create unique filename to prevent any potential overwrites
            import hashlib
            timestamp = str(int(time.time()))
            name_hash = hashlib.md5(person['name'].encode()).hexdigest()[:8]
            unique_filename = f"hero_{name_hash}_{timestamp}.jpg"
            
            # Post photo directly with caption (simpler, more reliable method)
            print(f"    → Posting directly to Facebook...")
            upload_url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/photos"
            
            files = {'source': (unique_filename, processed_image_data, 'image/jpeg')}
            data = {
                "message": caption,
                "access_token": ACCESS_TOKEN,
                "published": "true",  # Publish immediately
                "no_story": "false"  # Ensure it appears in feed
            }
            
            response = requests.post(upload_url, data=data, files=files, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                post_id = result.get("post_id", result.get("id", "unknown"))
                print(f"    ✅ Successfully posted (Post ID: {post_id})")
                successful_posts += 1
                
                # Add delay to ensure posts are completely separate
                if i < total_heroes:  # Don't delay after the last post
                    print(f"    → Waiting 10 seconds before next hero...")
                    time.sleep(10)  # Longer delay to ensure complete separation
                
            else:
                print(f"    ❌ Facebook API error: {response.status_code}")
                print(f"    Error details: {response.text}")
                
                # If direct photo post fails, let's try the feed API as backup
                print(f"    → Trying alternative posting method...")
                
                # Try posting as a feed post with link instead
                feed_url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
                feed_data = {
                    "message": caption,
                    "access_token": ACCESS_TOKEN
                }
                
                feed_response = requests.post(feed_url, data=feed_data, timeout=60)
                
                if feed_response.status_code == 200:
                    feed_result = feed_response.json()
                    post_id = feed_result.get("id", "unknown")
                    print(f"    ✅ Posted as text post (Post ID: {post_id})")
                    successful_posts += 1
                else:
                    print(f"    ❌ Both posting methods failed")
                
        except Exception as e:
            print(f"    ❌ Error processing {person['name']}: {e}")
            continue
    
    print(f"\n[*] ✅ Successfully created {successful_posts} individual posts out of {total_heroes} heroes")
    return successful_posts

def post_images_to_facebook(service_members):
    """Create individual posts for each service member with their photo and information"""
    print(f"[*] Creating individual memorial posts for {len(service_members)} service members...")
    
    # Create individual posts for each hero
    success_count = post_individual_heroes(service_members)
    
    if success_count > 0:
        print(f"\n✅ Successfully created {success_count} individual memorial posts")
        return success_count
    else:
        print(f"\n❌ Failed to create memorial posts")
        return 0

def main():
    """Main function"""
    print("=" * 60)
    print("🇺🇸 FALLEN HEROES MEMORIAL FACEBOOK POSTING SCRIPT 🇺🇸")
    print("=" * 60)
    
    # Debug environment variables (don't print actual values for security)
    print(f"ACCESS_TOKEN: {'✅ Set (' + str(len(ACCESS_TOKEN)) + ' chars)' if ACCESS_TOKEN else '❌ NOT SET'}")
    print(f"PAGE_ID: {'✅ Set (' + PAGE_ID + ')' if PAGE_ID else '❌ NOT SET'}")
    print(f"USE_PROXY: {USE_PROXY}")
    print(f"SEARCH_MODE: {SEARCH_MODE}")
    
    if not ACCESS_TOKEN or not PAGE_ID:
        print("\n❌ Missing required environment variables!")
        print("Please set FB_ACCESS_TOKEN and FB_PAGE_ID")
        return 1
    
    # Validate PAGE_ID is numeric
    if not PAGE_ID.isdigit():
        print(f"\n❌ PAGE_ID should be numeric, got: {PAGE_ID}")
        return 1
    
    # Test credentials
    if not test_facebook_credentials():
        print("\n❌ Facebook credential test failed!")
        return 1
    
    today = datetime.today()
    all_service_members = []
    
    if SEARCH_MODE == "comprehensive":
        # Search from Iraq invasion start date to present
        iraq_invasion_date = datetime(2003, 3, 20)
        print(f"\n[*] 🔍 COMPREHENSIVE SEARCH: Iraq invasion ({iraq_invasion_date.strftime('%m/%d/%Y')}) to present...")
        all_service_members = search_comprehensive_range(iraq_invasion_date, today)
        
    elif SEARCH_MODE == "recent":
        # Search last 30 days
        start_date = today - timedelta(days=30)
        print(f"\n[*] 🔍 RECENT SEARCH: Last 30 days ({start_date.strftime('%m/%d/%Y')} to {today.strftime('%m/%d/%Y')})...")
        all_service_members = search_comprehensive_range(start_date, today)
        
    else:
        # Default: search today across multiple years
        search_years = [2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
        print(f"\n[*] 🔍 DAILY SEARCH: Searching for fallen service members on {today.strftime('%B %d')} across multiple years...")
        
        for year in search_years:
            try:
                search_date = today.replace(year=year)
                print(f"\n[*] Checking {search_date.strftime('%B %d, %Y')}...")
                
                fallen = get_fallen_service_members(search_date)
                
                if fallen:
                    print(f"    Found {len(fallen)} service members")
                    # Only add those with images
                    for person in fallen:
                        if person["image_url"]:
                            all_service_members.append(person)
                            print(f"    ✅ {person['name']} - {person['date']} (has photo)")
                        else:
                            print(f"    ⚠️  {person['name']} - {person['date']} (no photo)")
                else:
                    print(f"    No service members found")
                    
                time.sleep(1)  # Rate limiting
                
            except ValueError:
                # Handle leap year issues (Feb 29)
                print(f"    Skipping {year} (date doesn't exist)")
                continue

    print(f"\n" + "=" * 60)
    
    if all_service_members:
        print(f"📊 SUMMARY: Found {len(all_service_members)} service members with photos")
        print(f"🚀 Starting individual Facebook memorial posts...")
        print("=" * 60)
        
        success_count = post_images_to_facebook(all_service_members)
        
        print("\n" + "=" * 60)
        if success_count > 0:
            print(f"✅ COMPLETED: Successfully created {success_count} individual memorial posts")
        else:
            print("❌ FAILED: No memorial posts were created")
        print("🇺🇸 Honor and remember our fallen heroes 🇺🇸")
        print("=" * 60)
        
        return 0 if success_count > 0 else 1
    else:
        print("📭 No fallen service members with images found for this search.")
        print("🇺🇸 We honor all who have served 🇺🇸")
        print("=" * 60)
        return 0

if __name__ == "__main__":
    exit(main())
