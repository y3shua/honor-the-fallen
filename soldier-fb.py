#!/usr/bin/env python3
"""
Honor the Fallen - Complete Facebook Posting Script
Scrapes real fallen heroes data from Military Times and posts to Facebook as text posts with images
"""

import requests
import json
import time
import os
from datetime import datetime, timedelta
from PIL import Image
import io
from bs4 import BeautifulSoup
import re
import urllib.parse

class MilitaryTimesScraper:
    def __init__(self):
        self.base_url = "https://thefallen.militarytimes.com"
        self.use_proxy = os.getenv('USE_PROXY', 'false').lower() == 'true'
        self.proxy = os.getenv('PROXY_URL') if self.use_proxy else None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def get_heroes_for_date(self, target_date):
        """
        Search for fallen heroes who died on the given date using the proven search method.
        Returns list of hero data dictionaries.
        """
        print(f"🔍 Searching for heroes who died on {target_date.strftime('%B %d, %Y')}")
        
        # Use the proven search function
        fallen_list = self.get_fallen_service_members(target_date)
        
        if not fallen_list:
            print(f"ℹ️ No fallen heroes found for {target_date.strftime('%B %d, %Y')}")
            return []
        
        print(f"✅ Found {len(fallen_list)} fallen hero(s)")
        
        # Convert to our hero data format and scrape additional details
        heroes = []
        for fallen in fallen_list:
            hero_data = self.convert_to_hero_data(fallen)
            
            # Scrape additional details from profile if available
            if fallen.get('link'):
                additional_data = self.scrape_hero_profile(fallen['link'])
                if additional_data:
                    hero_data.update(additional_data)
            
            heroes.append(hero_data)
            time.sleep(1)  # Rate limiting
        
        return heroes
    
    def get_fallen_service_members(self, date):
        """Query fallen service members for a specific date using the proven method"""
        base_url = "https://thefallen.militarytimes.com/search"
        formatted_date = date.strftime("%m%%2F%d%%2F%Y")
        query_url = f"{base_url}?year=&year_month=&first_name=&last_name=&start_date={formatted_date}&end_date={formatted_date}&conflict=&home_state=&home_town="
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        proxies = {"http": self.proxy, "https": self.proxy} if self.use_proxy and self.proxy else None
        
        try:
            response = requests.get(query_url, headers=headers, proxies=proxies, timeout=30)
        except requests.RequestException as e:
            print(f"❌ Network error fetching {query_url}: {e}")
            return []
            
        if response.status_code != 200 or "Access Denied" in response.text or "Captcha" in response.text:
            print(f"❌ Failed or blocked when fetching {query_url} (Status: {response.status_code})")
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
                # Make sure profile link is absolute
                if profile_link.startswith('/'):
                    profile_link = f"https://thefallen.militarytimes.com{profile_link}"
            
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
            
        print(f"✅ Found {len(fallen_list)} service members for {date.strftime('%B %d, %Y')}")
        return fallen_list
    
    def convert_to_hero_data(self, fallen):
        """Convert the fallen service member data to our hero data format"""
        return {
            'name': fallen.get('name', 'Unknown Hero'),
            'date_of_death': fallen.get('date', ''),
            'profile_url': fallen.get('link', ''),
            'image_url': fallen.get('image_url', ''),
            'rank': '',  # Will be filled by profile scraping
            'age': '',
            'hometown': '',
            'branch': '',
            'unit': '',
            'location': '',
            'circumstances': ''
        }
    
    def scrape_hero_profile(self, profile_url):
        """
        Scrape detailed information from a hero's profile page.
        """
        try:
            response = self.session.get(profile_url)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract hero information
            hero_data = {
                'profile_url': profile_url,
                'name': self.extract_name(soup),
                'rank': self.extract_rank(soup),
                'age': self.extract_age(soup),
                'hometown': self.extract_hometown(soup),
                'branch': self.extract_branch(soup),
                'unit': self.extract_unit(soup),
                'date_of_death': self.extract_date_of_death(soup),
                'location': self.extract_location(soup),
                'circumstances': self.extract_circumstances(soup),
                'image_url': self.extract_image_url(soup)
            }
            
            return hero_data
            
        except Exception as e:
            print(f"❌ Error scraping profile {profile_url}: {str(e)}")
            return None
    
    def extract_name(self, soup):
        """Extract hero's name from profile page"""
        # Look for name in various possible locations
        selectors = ['h1', '.hero-name', '.profile-name', 'title']
        for selector in selectors:
            element = soup.select_one(selector)
            if element and element.text.strip():
                text = element.text.strip()
                # Clean up the text (remove extra whitespace, etc.)
                return re.sub(r'\s+', ' ', text)
        return "Unknown Hero"
    
    def extract_rank(self, soup):
        """Extract military rank"""
        # Look for rank patterns
        text = soup.get_text()
        rank_patterns = [
            r'(Private First Class|Staff Sergeant|Sergeant First Class|Master Sergeant|'
            r'First Sergeant|Sergeant Major|Second Lieutenant|First Lieutenant|Captain|'
            r'Major|Lieutenant Colonel|Colonel|Brigadier General|Major General|'
            r'Lieutenant General|General|Corporal|Sergeant|Private|'
            r'Seaman|Petty Officer|Chief Petty Officer|Warrant Officer|Ensign|'
            r'Lieutenant Commander|Commander|Admiral|Airman|Senior Airman|'
            r'Technical Sergeant|Master Sergeant|Senior Master Sergeant|Chief Master Sergeant)'
        ]
        
        for pattern in rank_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return ""
    
    def extract_age(self, soup):
        """Extract age at time of death"""
        text = soup.get_text()
        age_match = re.search(r'age (\d+)', text, re.IGNORECASE)
        if age_match:
            return age_match.group(1)
        return ""
    
    def extract_hometown(self, soup):
        """Extract hometown information"""
        # Look for hometown patterns
        text = soup.get_text()
        hometown_patterns = [
            r'of ([^,]+, [A-Z]{2})',
            r'from ([^,]+, [A-Z]{2})',
            r'hometown[:\s]+([^,\n]+)'
        ]
        
        for pattern in hometown_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""
    
    def extract_branch(self, soup):
        """Extract military branch"""
        text = soup.get_text()
        branches = ['Army', 'Navy', 'Air Force', 'Marines', 'Coast Guard']
        for branch in branches:
            if branch.lower() in text.lower():
                return f"U.S. {branch}"
        return ""
    
    def extract_unit(self, soup):
        """Extract military unit information"""
        text = soup.get_text()
        # Look for unit patterns
        unit_patterns = [
            r'(\d+(?:st|nd|rd|th)?\s+[^,\n]+(?:Division|Regiment|Battalion|Company|Squadron))',
            r'(Special Operations [^,\n]+)',
            r'(Rangers?[^,\n]*)'
        ]
        
        for pattern in unit_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""
    
    def extract_date_of_death(self, soup):
        """Extract date of death"""
        text = soup.get_text()
        # Look for date patterns
        date_patterns = [
            r'died[:\s]+([A-Z][a-z]+ \d{1,2}, \d{4})',
            r'killed[:\s]+([A-Z][a-z]+ \d{1,2}, \d{4})',
            r'(\d{1,2}/\d{1,2}/\d{4})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""
    
    def extract_location(self, soup):
        """Extract location of death"""
        text = soup.get_text()
        locations = ['Afghanistan', 'Iraq', 'Syria', 'Kuwait', 'Qatar']
        for location in locations:
            if location.lower() in text.lower():
                return location
        return ""
    
    def extract_circumstances(self, soup):
        """Extract circumstances of death"""
        text = soup.get_text()
        # Look for circumstance patterns
        circumstance_patterns = [
            r'(killed in action[^.]*\.)',
            r'(died from[^.]*\.)',
            r'(was killed when[^.]*\.)'
        ]
        
        for pattern in circumstance_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""
    
    def extract_image_url(self, soup):
        """Extract profile image URL"""
        # Look for image in various locations
        img_selectors = ['img.hero-photo', '.profile-image img', '.hero-image img', 'img']
        
        for selector in img_selectors:
            img = soup.select_one(selector)
            if img and img.get('src'):
                src = img.get('src')
                if src.startswith('/'):
                    return self.base_url + src
                elif src.startswith('http'):
                    return src
        return None

class ImageDownloader:
    def __init__(self, download_dir="hero_images"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
    
    def download_hero_image(self, hero_data):
        """
        Download hero's image and return the local filename.
        """
        image_url = hero_data.get('image_url')
        if not image_url:
            print(f"⚠️ No image URL for {hero_data.get('name', 'Unknown')}")
            return None
        
        try:
            # Create safe filename
            name = hero_data.get('name', 'unknown').lower()
            safe_name = re.sub(r'[^a-z0-9\s]', '', name)
            safe_name = re.sub(r'\s+', '_', safe_name.strip())
            filename = f"{safe_name}.jpg"
            filepath = os.path.join(self.download_dir, filename)
            
            # Download image
            response = requests.get(image_url, stream=True)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Optimize image for Facebook
                self.optimize_image(filepath)
                
                print(f"✅ Downloaded image: {filename}")
                return filename
            else:
                print(f"❌ Failed to download image for {hero_data.get('name', 'Unknown')}")
                return None
                
        except Exception as e:
            print(f"❌ Error downloading image: {str(e)}")
            return None
    
    def optimize_image(self, filepath):
        """
        Optimize image for Facebook posting (resize, format, etc.)
        """
        try:
            with Image.open(filepath) as img:
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize to optimal Facebook dimensions (1080x1080 max)
                img.thumbnail((1080, 1080), Image.Resampling.LANCZOS)
                
                # Save optimized image
                img.save(filepath, 'JPEG', quality=90, optimize=True)
                
        except Exception as e:
            print(f"⚠️ Could not optimize image {filepath}: {str(e)}")

class FacebookPoster:
    def __init__(self, access_token, page_id):
        self.access_token = access_token
        self.page_id = page_id
        self.base_url = "https://graph.facebook.com/v18.0"
        
    def upload_image_unpublished(self, image_path):
        """Upload image to Facebook without publishing it."""
        url = f"{self.base_url}/{self.page_id}/photos"
        
        try:
            with open(image_path, 'rb') as image_file:
                files = {'source': image_file}
                data = {
                    'access_token': self.access_token,
                    'published': 'false'
                }
                
                response = requests.post(url, files=files, data=data)
                
                if response.status_code == 200:
                    result = response.json()
                    photo_id = result.get('id')
                    print(f"✅ Image uploaded. Photo ID: {photo_id}")
                    return photo_id
                else:
                    print(f"❌ Image upload failed: {response.text}")
                    return None
                    
        except Exception as e:
            print(f"❌ Error uploading image: {str(e)}")
            return None
    
    def create_memorial_text(self, hero_data):
        """Create comprehensive memorial text for the fallen hero."""
        lines = []
        
        # Header
        lines.append("🇺🇸 HONORING OUR FALLEN HERO 🇺🇸")
        lines.append("")
        
        # Hero information
        name = hero_data.get('name', 'Unknown Hero')
        rank = hero_data.get('rank', '')
        
        if rank and name:
            lines.append(f"📛 {rank} {name}")
        else:
            lines.append(f"📛 {name}")
        
        if hero_data.get('age'):
            lines.append(f"👤 Age: {hero_data['age']}")
        
        if hero_data.get('hometown'):
            lines.append(f"🏠 Hometown: {hero_data['hometown']}")
        
        if hero_data.get('branch'):
            lines.append(f"⭐ Branch: {hero_data['branch']}")
        
        if hero_data.get('unit'):
            lines.append(f"🎖️ Unit: {hero_data['unit']}")
        
        lines.append("")
        
        # Service details
        if hero_data.get('date_of_death'):
            lines.append(f"📅 Date of Sacrifice: {hero_data['date_of_death']}")
        
        if hero_data.get('location'):
            lines.append(f"📍 Location: {hero_data['location']}")
        
        if hero_data.get('circumstances'):
            lines.append(f"💭 {hero_data['circumstances']}")
        
        lines.append("")
        
        # Memorial message
        lines.append("🌟 Today we honor and remember this brave service member who made the ultimate sacrifice for our freedom. Their courage, dedication, and selfless service will never be forgotten.")
        lines.append("")
        lines.append("💙 Our thoughts and prayers are with their family, friends, and fellow service members. We are forever grateful for their sacrifice.")
        lines.append("")
        lines.append("🙏 Please take a moment to honor their memory. Share their story. Remember their sacrifice.")
        lines.append("")
        
        # Hashtags
        hashtags = [
            "#FallenHero", "#NeverForget", "#HonorTheFallen", 
            "#MemorialDay", "#Military", "#Sacrifice", 
            "#Freedom", "#Heroes", "#RememberThem", 
            "#Service", "#Gratitude"
        ]
        
        # Add branch-specific hashtags
        branch = hero_data.get('branch', '').lower()
        if 'army' in branch:
            hashtags.extend(["#Army", "#USArmy"])
        elif 'navy' in branch:
            hashtags.extend(["#Navy", "#USNavy"])
        elif 'air force' in branch:
            hashtags.extend(["#AirForce", "#USAF"])
        elif 'marine' in branch:
            hashtags.extend(["#Marines", "#USMC", "#SemperFi"])
        elif 'coast guard' in branch:
            hashtags.extend(["#CoastGuard", "#USCG"])
        
        lines.append(" ".join(hashtags))
        
        if hero_data.get('profile_url'):
            lines.append("")
            lines.append(f"📖 Learn more: {hero_data['profile_url']}")
        
        lines.append("")
        lines.append("🇺🇸 \"All gave some, some gave all\" 🇺🇸")
        
        return "\n".join(lines)
    
    def post_text_with_image(self, hero_data, image_path):
        """Create a Facebook text post with embedded image."""
        print(f"📝 Creating memorial post for {hero_data.get('name', 'Unknown Hero')}")
        
        # Upload image without publishing
        photo_id = self.upload_image_unpublished(image_path)
        if not photo_id:
            return False
        
        # Create text post with attached image
        url = f"{self.base_url}/{self.page_id}/feed"
        memorial_text = self.create_memorial_text(hero_data)
        
        data = {
            'access_token': self.access_token,
            'message': memorial_text,
            'attached_media[0]': json.dumps({'media_fbid': photo_id}),
            'published': 'true'
        }
        
        try:
            response = requests.post(url, data=data)
            
            if response.status_code == 200:
                result = response.json()
                post_id = result.get('id')
                print(f"✅ Memorial post created! Post ID: {post_id}")
                return True
            else:
                print(f"❌ Post creation failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error creating post: {str(e)}")
            return False

def main():
    """
    Main function that orchestrates the entire process:
    1. Scrape fallen heroes data from Military Times for today's date
    2. Download their images
    3. Post memorials to Facebook as text posts with images
    """
    print("🇺🇸 Starting Fallen Heroes Memorial Script 🇺🇸")
    print(f"Search Mode: {os.getenv('SEARCH_MODE', 'daily')}")
    print(f"Timestamp: {datetime.now()}")
    
    # Get configuration
    access_token = os.getenv('FB_ACCESS_TOKEN')
    page_id = os.getenv('FB_PAGE_ID')
    search_mode = os.getenv('SEARCH_MODE', 'daily')
    
    if not access_token or not page_id:
        print("❌ Missing Facebook credentials")
        return
    
    # Initialize components
    scraper = MilitaryTimesScraper()
    downloader = ImageDownloader()
    poster = FacebookPoster(access_token, page_id)
    
    # Determine search date - always use today's month/day but search across years
    today = datetime.now()
    search_date = today
    
    print(f"🔍 Searching for heroes who died on {search_date.strftime('%B %d')} (any year since 2003)")
    
    # Search for fallen heroes across all years for today's date
    all_heroes = []
    current_year = datetime.now().year
    
    for year in range(2003, current_year + 1):
        year_date = search_date.replace(year=year)
        print(f"📅 Checking {year_date.strftime('%B %d, %Y')}")
        
        year_heroes = scraper.get_fallen_service_members(year_date)
        
        # Convert to our hero data format
        for fallen in year_heroes:
            hero_data = scraper.convert_to_hero_data(fallen)
            
            # Scrape additional details from profile if available
            if fallen.get('link'):
                print(f"🔍 Scraping profile for {fallen.get('name', 'Unknown')}")
                additional_data = scraper.scrape_hero_profile(fallen['link'])
                if additional_data:
                    hero_data.update(additional_data)
            
            all_heroes.append(hero_data)
        
        time.sleep(1)  # Rate limiting between years
    
    if not all_heroes:
        print(f"ℹ️ No fallen heroes found for {search_date.strftime('%B %d')} across all years")
        return
    
    print(f"✅ Found {len(all_heroes)} total fallen hero(s) for {search_date.strftime('%B %d')}")
    
    # Process each hero
    successful_posts = 0
    failed_posts = 0
    
    for i, hero in enumerate(all_heroes):
        print(f"\n--- Processing {i+1}/{len(all_heroes)}: {hero.get('name', 'Unknown')} ---")
        
        # Download hero image
        image_filename = downloader.download_hero_image(hero)
        if not image_filename:
            failed_posts += 1
            continue
        
        image_path = os.path.join(downloader.download_dir, image_filename)
        
        # Post memorial to Facebook
        success = poster.post_text_with_image(hero, image_path)
        
        if success:
            successful_posts += 1
        else:
            failed_posts += 1
        
        # Rate limiting between posts
        if i < len(all_heroes) - 1:
            print("⏳ Waiting 3 seconds before next post...")
            time.sleep(3)
    
    print(f"\n🎯 POSTING SUMMARY:")
    print(f"✅ Successful posts: {successful_posts}")
    print(f"❌ Failed posts: {failed_posts}")
    print(f"📊 Total processed: {len(all_heroes)}")
    print(f"📅 Search date: {search_date.strftime('%B %d')} (across all years 2003-{current_year})")

if __name__ == "__main__":
    main()
