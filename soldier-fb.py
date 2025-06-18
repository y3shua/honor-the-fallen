#!/usr/bin/env python3
“””
Honor the Fallen - Complete Facebook Posting Script
Scrapes real fallen heroes data from Military Times and posts to Facebook as text posts with images
“””

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
def **init**(self):
self.base_url = “https://thefallen.militarytimes.com”
self.session = requests.Session()
self.session.headers.update({
‘User-Agent’: ‘Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36’
})

```
def get_heroes_for_date(self, target_date):
    """
    Search for fallen heroes who died on the given date.
    Returns list of hero data dictionaries.
    """
    heroes = []
    
    # Search across multiple years for the same date
    current_year = datetime.now().year
    for year in range(2003, current_year + 1):
        search_date = target_date.replace(year=year)
        year_heroes = self.search_by_date(search_date)
        heroes.extend(year_heroes)
        time.sleep(1)  # Rate limiting
    
    return heroes

def search_by_date(self, search_date):
    """
    Search for heroes who died on a specific date.
    """
    print(f"🔍 Searching for heroes who died on {search_date.strftime('%B %d, %Y')}")
    
    # Format date for search
    month = search_date.strftime('%m')
    day = search_date.strftime('%d')
    year = search_date.year
    
    search_url = f"{self.base_url}/search"
    search_params = {
        'death_month': month,
        'death_day': day,
        'death_year': year
    }
    
    try:
        response = self.session.get(search_url, params=search_params)
        if response.status_code != 200:
            print(f"⚠️ Search failed for {search_date}: HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        hero_links = soup.find_all('a', href=re.compile(r'/[^/]+-[^/]+-[^/]+/'))
        
        heroes = []
        for link in hero_links:
            href = link.get('href')
            if href and href.startswith('/'):
                hero_url = self.base_url + href
                hero_data = self.scrape_hero_profile(hero_url)
                if hero_data:
                    heroes.append(hero_data)
                    print(f"✅ Found: {hero_data.get('name', 'Unknown')}")
                time.sleep(1)  # Rate limiting
        
        return heroes
        
    except Exception as e:
        print(f"❌ Error searching for date {search_date}: {str(e)}")
        return []

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
```

class ImageDownloader:
def **init**(self, download_dir=“hero_images”):
self.download_dir = download_dir
os.makedirs(download_dir, exist_ok=True)

```
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
```

class FacebookPoster:
def **init**(self, access_token, page_id):
self.access_token = access_token
self.page_id = page_id
self.base_url = “https://graph.facebook.com/v18.0”

```
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
```

def main():
“””
Main function that orchestrates the entire process:
1. Scrape fallen heroes data from Military Times
2. Download their images
3. Post memorials to Facebook as text posts with images
“””
print(“🇺🇸 Starting Fallen Heroes Memorial Script 🇺🇸”)
print(f”Search Mode: {os.getenv(‘SEARCH_MODE’, ‘daily’)}”)
print(f”Timestamp: {datetime.now()}”)

```
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

# Determine search date
today = datetime.now()
if search_mode == 'daily':
    search_date = today
elif search_mode == 'recent':
    search_date = today - timedelta(days=1)  # Yesterday
else:
    search_date = today

print(f"🔍 Searching for heroes who died on {search_date.strftime('%B %d')} (any year)")

# Scrape heroes data
heroes = scraper.get_heroes_for_date(search_date)

if not heroes:
    print("ℹ️ No fallen heroes found for today's date")
    return

print(f"✅ Found {len(heroes)} fallen hero(s)")

# Process each hero
successful_posts = 0
failed_posts = 0

for i, hero in enumerate(heroes):
    print(f"\n--- Processing {i+1}/{len(heroes)}: {hero.get('name', 'Unknown')} ---")
    
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
    if i < len(heroes) - 1:
        print("⏳ Waiting 3 seconds before next post...")
        time.sleep(3)

print(f"\n🎯 POSTING SUMMARY:")
print(f"✅ Successful posts: {successful_posts}")
print(f"❌ Failed posts: {failed_posts}")
print(f"📊 Total processed: {len(heroes)}")
```

if **name** == “**main**”:
main()
