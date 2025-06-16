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
        
        # Extract structured information from record-txt div
        record_txt = soup.select_one(".record-txt")
        if record_txt:
            # Get rank, branch, and name from h1
            h1_tag = record_txt.select_one("h1.h1-size")
            if h1_tag:
                full_name_rank = h1_tag.get_text().strip()
                details["full_name_with_rank"] = full_name_rank
                print(f"    → Found name with rank: {full_name_rank}")
            
            # Get operation and date from h2
            h2_tag = record_txt.select_one("h2")
            if h2_tag:
                h2_text = h2_tag.get_text().strip()
                details["death_info"] = h2_text
                print(f"    → Found death info: {h2_text}")
                
                # Extract date from h2 text
                import re
                date_match = re.search(r'Died ([^S]+) Serving', h2_text)
                if date_match:
                    details["formatted_date"] = date_match.group(1).strip()
                
                # Extract operation
                if "Operation" in h2_text:
                    operation_match = re.search(r'Operation ([^"]+)', h2_text)
                    if operation_match:
                        details["operation"] = f"Operation {operation_match.group(1).strip()}"
            
            # Get branch from hidden input
            branch_input = record_txt.select_one('input[name="dimension2"]')
            if branch_input:
                details["branch"] = branch_input.get("value", "").strip()
                print(f"    → Found branch: {details['branch']}")
        
        # Get age, hometown, unit, and circumstances from content between <hr> tags
        if record_txt:
            # Find the content between <hr> tags or after the first <hr>
            hr_tags = record_txt.find_all("hr")
            if hr_tags:
                # Get text content after first <hr> and before second <hr> (if exists)
                content_after_hr = ""
                if len(hr_tags) >= 1:
                    # Get all text between the <hr> tags or after the first one
                    current = hr_tags[0].next_sibling
                    while current and (len(hr_tags) < 2 or current != hr_tags[1]):
                        if hasattr(current, 'get_text'):
                            content_after_hr += current.get_text()
                        elif isinstance(current, str):
                            content_after_hr += current
                        current = current.next_sibling
                
                if content_after_hr:
                    content_text = content_after_hr.strip()
                    print(f"    → Found detailed content: {content_text}")
                    
                    # Parse the structured content
                    # Format: "29, of Morgantown, Ky.; assigned to the 617th Military Police Company..."
                    
                    # Extract age and hometown (before first semicolon)
                    parts = content_text.split(';')
                    if parts:
                        age_hometown_part = parts[0].strip()
                        
                        # Extract age (number at start)
                        age_match = re.match(r'^(\d+)', age_hometown_part)
                        if age_match:
                            details["age"] = age_match.group(1)
                            print(f"    → Found age: {details['age']}")
                        
                        # Extract hometown (after "of")
                        hometown_match = re.search(r'of\s+([^;]+)', age_hometown_part)
                        if hometown_match:
                            hometown = hometown_match.group(1).strip().rstrip('.')
                            details["hometown"] = hometown
                            print(f"    → Found hometown: {hometown}")
                    
                    # Extract unit assignment (after "assigned to")
                    unit_match = re.search(r'assigned to (?:the\s+)?([^;,]+(?:Company|Battalion|Regiment|Brigade|Division|Squadron|Wing|Group)[^;]*)', content_text, re.IGNORECASE)
                    if unit_match:
                        unit = unit_match.group(1).strip()
                        # Filter out non-military units like publisher information
                        if not any(exclude in unit for exclude in ['Sightline Media Group', 'Military Times', 'Stars and Stripes']):
                            details["unit"] = unit
                            print(f"    → Found unit: {unit}")
                        else:
                            print(f"    → Ignored non-military unit: {unit}")
                    
                    # Extract circumstances of death (usually after the last semicolon)
                    if len(parts) > 1:
                        circumstances_part = parts[-1].strip()
                        if len(circumstances_part) > 20:  # Only if substantial content
                            # Clean up the circumstances
                            circumstances = circumstances_part.rstrip('.')
                            if not circumstances.endswith('.'):
                                circumstances += '.'
                            details["circumstances"] = circumstances
                            print(f"    → Found circumstances: {circumstances}")
            
            # Fallback: try to find the first <p> after record-txt if no <hr> content
            if not details.get("age"):
                next_p = record_txt.find_next_sibling("p")
                if next_p:
                    p_text = next_p.get_text().strip()
                    print(f"    → Fallback paragraph: {p_text}")
                    
                    # Extract age (number at start of paragraph)
                    age_match = re.match(r'^(\d+)', p_text)
                    if age_match:
                        details["age"] = age_match.group(1)
                        print(f"    → Found age (fallback): {details['age']}")
                    
                    # Extract hometown (everything after "of ")
                    hometown_match = re.search(r'of (.+)', p_text)
                    if hometown_match:
                        hometown = hometown_match.group(1).strip().rstrip('.')
                        details["hometown"] = hometown
                        print(f"    → Found hometown (fallback): {hometown}")
        
        # Also check if there's a better quality S3 image URL in the profile
        profile_image_div = soup.select_one(".record-image")
        if profile_image_div:
            profile_img = profile_image_div.select_one("img")
            if profile_img and profile_img.get("src"):
                s3_image_url = profile_img["src"]
                if s3_image_url.startswith("https://s3.amazonaws.com/"):
                    details["high_quality_image_url"] = s3_image_url
                    print(f"    → Found S3 image: {s3_image_url}")
        
        # Get all text content for additional parsing if needed
        content = soup.get_text()
        
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
    
    # Header
    caption_parts.append(f"📅 {today.strftime('%B %d')} Memorial")
    caption_parts.append("")
    
    # Hero's name prominently displayed (use full name with rank if available)
    if details.get("full_name_with_rank"):
        caption_parts.append(f"🎗️ {details['full_name_with_rank'].upper()}")
    else:
        caption_parts.append(f"🎗️ {person['name'].upper()}")
    caption_parts.append("")
    
    # Military information in clean format
    military_info = []
    
    # Use branch from structured data
    if details.get("branch"):
        military_info.append(f"⚔️ {details['branch']}")
    
    if details.get("unit"):
        military_info.append(f"🏛️ {details['unit']}")
    
    if details.get("operation"):
        military_info.append(f"🌟 {details['operation']}")
    
    if details.get("age"):
        military_info.append(f"👤 Age {details['age']}")
    
    if details.get("hometown"):
        military_info.append(f"🏠 {details['hometown']}")
    
    # Add military info
    caption_parts.extend(military_info)
    caption_parts.append("")
    
    # Sacrifice information - use structured date if available
    if details.get("formatted_date"):
        caption_parts.append(f"📅 Date of Sacrifice: {details['formatted_date']}")
    else:
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
    caption_parts.append(f"🔗 Learn more: {person['link'].rstrip(':').rstrip()}")
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
<<<<<<< HEAD
    """Select one random service member and create a single memorial post"""
    if not service_members:
        print("❌ No service members to post")
        return 0
    
    import random
    
    # Select one random hero for today's memorial
    selected_hero = random.choice(service_members)
    print(f"[*] Selected hero of the day: {selected_hero['name']}")
    print(f"[*] Creating single memorial post...")
    
    # Create individual post for the selected hero
    success_count = post_individual_heroes([selected_hero])  # Pass as single-item list
    
    if success_count > 0:
        print(f"\n✅ Successfully created memorial post for {selected_hero['name']}")
        return success_count
    else:
        print(f"\n❌ Failed to create memorial post")
=======
    """Create individual posts for each service member with their photo and information"""
    print(f"[*] Creating individual memorial posts for {len(service_members)} service members...")
    
    # Create individual posts for each hero
    success_count = post_individual_heroes(service_members)
    
    if success_count > 0:
        print(f"\n✅ Successfully created {success_count} individual memorial posts")
        return success_count
    else:
        print(f"\n❌ Failed to create memorial posts")
>>>>>>> ab736e6 (ignore non unit words)
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
<<<<<<< HEAD
        print(f"🎯 Will randomly select 1 hero for today's memorial")
        print(f"🚀 Selecting random hero for today's memorial...")
=======
        print(f"🚀 Starting individual Facebook memorial posts...")
>>>>>>> ab736e6 (ignore non unit words)
        print("=" * 60)
        
        success_count = post_images_to_facebook(all_service_members)
        
        print("\n" + "=" * 60)
        if success_count > 0:
<<<<<<< HEAD
            print(f"✅ COMPLETED: Successfully created today's memorial post")
        else:
            print("❌ FAILED: No memorial post was created")
=======
            print(f"✅ COMPLETED: Successfully created {success_count} individual memorial posts")
        else:
            print("❌ FAILED: No memorial posts were created")
>>>>>>> ab736e6 (ignore non unit words)
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
