#!/usr/bin/env python3

import requests
import json
import time
import os
import random
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
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
        
        # Use a more recent Chrome user agent
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        })
        
        # Configure session with connection pooling and timeouts
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=3,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # Precompile regex patterns used during extraction (avoids recompiling on every call)
        self._rank_re = re.compile(
            r'(Private First Class|Staff Sergeant|Sergeant First Class|Master Sergeant|'
            r'First Sergeant|Sergeant Major|Second Lieutenant|First Lieutenant|Captain|'
            r'Major|Lieutenant Colonel|Colonel|Brigadier General|Major General|'
            r'Lieutenant General|General|Corporal|Sergeant|Private|'
            r'Seaman|Petty Officer|Chief Petty Officer|Warrant Officer|Ensign|'
            r'Lieutenant Commander|Commander|Admiral|Airman|Senior Airman|'
            r'Technical Sergeant|Senior Master Sergeant|Chief Master Sergeant)',
            re.IGNORECASE
        )
        self._age_re = re.compile(r'age (\d+)', re.IGNORECASE)
        self._hometown_res = [
            re.compile(r'of ([^,]+, [A-Z]{2})', re.IGNORECASE),
            re.compile(r'from ([^,]+, [A-Z]{2})', re.IGNORECASE),
            re.compile(r'hometown[:\s]+([^,\n]+)', re.IGNORECASE),
        ]
        self._unit_res = [
            re.compile(r'(\d+(?:st|nd|rd|th)?\s+[^,\n]+(?:Division|Regiment|Battalion|Company|Squadron))', re.IGNORECASE),
            re.compile(r'(Special Operations [^,\n]+)', re.IGNORECASE),
            re.compile(r'(Rangers?[^,\n]*)', re.IGNORECASE),
        ]
        self._circumstance_res = [
            re.compile(r'(killed in action[^.]*\.)', re.IGNORECASE),
            re.compile(r'(died from[^.]*\.)', re.IGNORECASE),
            re.compile(r'(was killed when[^.]*\.)', re.IGNORECASE),
        ]
    
    def test_connection(self):
        """Test if we can connect to Military Times website"""
        try:
            print("🔗 Testing connection to Military Times...")
            response = self.session.get(self.base_url, timeout=15)
            
            if response.status_code == 200:
                print("✅ Successfully connected to Military Times")
                return True
            else:
                print(f"⚠️ Connection test failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Connection test failed: {str(e)}")
            return False
    
    def get_single_hero_for_date(self, target_date):
        """
        Find a RANDOM fallen hero for the given date efficiently.
        Only downloads the photo of the selected hero, not all heroes.
        """
        if not self.test_connection():
            print("❌ Cannot connect to Military Times. Aborting.")
            return None
        
        print(f"🔍 Searching for heroes who died on {target_date.strftime('%B %d')} (any year)")
        
        # Collect basic info (names, links) from ALL years first - NO image downloads yet
        all_hero_refs = []  # Just references, not full data
        current_year = datetime.now().year
        
        # Search all years from 2003 to current year
        years = list(range(2003, current_year + 1))
        random.shuffle(years)  # Randomize the order we search years
        
        for year in years:
            year_date = target_date.replace(year=year)
            print(f"📅 Checking {year_date.strftime('%B %d, %Y')}")
            
            try:
                # Get basic hero info WITHOUT downloading images
                fallen_list = self.get_fallen_service_members_basic(year_date)
                
                if fallen_list:
                    # Add all hero references from this year to our collection
                    for fallen in fallen_list:
                        fallen['year'] = year  # Add year info
                        all_hero_refs.append(fallen)
                    print(f"  ✅ Found {len(fallen_list)} hero(s) for {year}")
                
            except Exception as e:
                print(f"  ⚠️ Error searching year {year}: {str(e)}")
                continue
            
            # Rate limit between year searches
            time.sleep(1)
        
        if not all_hero_refs:
            print("ℹ️ No fallen heroes found for this date across all years")
            return None
        
        print(f"\n🎲 Found {len(all_hero_refs)} total heroes across all years. Selecting one randomly...")
        
        # Pick a completely random hero from all years
        selected_fallen = random.choice(all_hero_refs)
        selected_year = selected_fallen.get('year', 'Unknown')
        
        print(f"🎯 Randomly selected: {selected_fallen.get('name', 'Unknown')} from {selected_year}")
        print(f"📸 Will download ONLY this hero's photo (not all heroes)")
        
        # Convert to our hero data format
        hero_data = self.convert_to_hero_data(selected_fallen)
        
        # Scrape additional details if profile link is available
        if selected_fallen.get('link'):
            print(f"🔍 Getting additional details for {selected_fallen.get('name', 'Unknown')}")
            time.sleep(2)  # Rate limit before profile scraping
            additional_data = self.scrape_hero_profile(selected_fallen['link'])
            if additional_data:
                hero_data.update(additional_data)
        
        return hero_data
    
    def get_fallen_service_members_basic(self, date):
        """
        Get basic hero info (name, link) WITHOUT trying to get images from search results.
        Images will be obtained later from individual profile pages.
        """
        base_url = "https://thefallen.militarytimes.com/search"
        formatted_date = date.strftime("%m%%2F%d%%2F%Y")
        query_url = f"{base_url}?year=&year_month=&first_name=&last_name=&start_date={formatted_date}&end_date={formatted_date}&conflict=&home_state=&home_town="
        
        proxies = {"http": self.proxy, "https": self.proxy} if self.use_proxy and self.proxy else None
        
        try:
            response = self.session.get(query_url, proxies=proxies, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ HTTP Error {response.status_code}")
                return []
                
            if "Access Denied" in response.text or "Captcha" in response.text:
                print(f"❌ Access blocked or CAPTCHA detected")
                return []
            
            if "cloudflare" in response.text.lower() or "security check" in response.text.lower():
                print(f"❌ Cloudflare or security check detected")
                return []
            
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Connection error: {str(e)}")
            return []
        except requests.exceptions.Timeout as e:
            print(f"❌ Request timeout: {str(e)}")
            return []
        except requests.RequestException as e:
            print(f"❌ Request error: {str(e)}")
            return []
            
        try:
            soup = BeautifulSoup(response.text, "html.parser")
            fallen_list = []
            entries = soup.select(".data-box")
            
            for entry in entries:
                try:
                    name_tag = entry.select_one(".data-box-right h3 a")
                    name = name_tag.text.strip() if name_tag else "Unknown"
                    
                    date_tag = entry.select_one(".data-box-right .blue-bold")
                    date_of_death = date_tag.text.strip() if date_tag else "Unknown Date"
                    
                    profile_link = name_tag["href"] if name_tag and "href" in name_tag.attrs else ""
                    if profile_link:
                        profile_link = profile_link.rstrip(':').rstrip()
                        if profile_link.startswith('/'):
                            profile_link = f"https://thefallen.militarytimes.com{profile_link}"
                    
                    if name and name != "Unknown" and profile_link:
                        fallen_list.append({
                            "name": name,
                            "date": date_of_death,
                            "link": profile_link,
                            "image_url": None  # Will be obtained from profile page
                        })
                    
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"❌ Error parsing HTML: {str(e)}")
            return []
            
        return fallen_list
    
    def get_fallen_service_members(self, date):
        """Query fallen service members for a specific date using the proven method with better error handling"""
        base_url = "https://thefallen.militarytimes.com/search"
        formatted_date = date.strftime("%m%%2F%d%%2F%Y")
        query_url = f"{base_url}?year=&year_month=&first_name=&last_name=&start_date={formatted_date}&end_date={formatted_date}&conflict=&home_state=&home_town="
        
        proxies = {"http": self.proxy, "https": self.proxy} if self.use_proxy and self.proxy else None
        
        try:
            print(f"🌐 Requesting: {query_url}")
            response = self.session.get(query_url, proxies=proxies, timeout=30)
            
            # Check response status and content
            if response.status_code != 200:
                print(f"❌ HTTP Error {response.status_code}")
                return []
                
            if "Access Denied" in response.text or "Captcha" in response.text:
                print(f"❌ Access blocked or CAPTCHA detected")
                return []
            
            if "cloudflare" in response.text.lower() or "security check" in response.text.lower():
                print(f"❌ Cloudflare or security check detected")
                return []
            
            print(f"✅ Successfully received response ({len(response.text)} chars)")
            
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Connection error: {str(e)}")
            return []
        except requests.exceptions.Timeout as e:
            print(f"❌ Request timeout: {str(e)}")
            return []
        except requests.RequestException as e:
            print(f"❌ Request error: {str(e)}")
            return []
            
        try:
            soup = BeautifulSoup(response.text, "html.parser")
            fallen_list = []
            entries = soup.select(".data-box")
            
            print(f"🔍 Found {len(entries)} potential entries")
            
            for i, entry in enumerate(entries):
                try:
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
                    
                    if name and name != "Unknown":
                        fallen_list.append({
                            "name": name,
                            "date": date_of_death,
                            "link": profile_link,
                            "image_url": image_url
                        })
                        print(f"  ✅ Entry {i+1}: {name}")
                    
                except Exception as e:
                    print(f"  ⚠️ Error processing entry {i+1}: {str(e)}")
                    continue
                    
        except Exception as e:
            print(f"❌ Error parsing HTML: {str(e)}")
            return []
            
        print(f"✅ Successfully parsed {len(fallen_list)} valid service members")
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
        ONLY get the S3 image URL from the profile page.
        """
        try:
            print(f"🔍 Scraping profile: {profile_url}")
            response = self.session.get(profile_url, timeout=30)
            if response.status_code != 200:
                print(f"⚠️ Profile page returned HTTP {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text()  # Extract once, reused by all extract_* methods

            # Extract hero information
            hero_data = {
                'rank': self.extract_rank(text),
                'age': self.extract_age(text),
                'hometown': self.extract_hometown(text),
                'branch': self.extract_branch(text),
                'unit': self.extract_unit(text),
                'location': self.extract_location(text),
                'circumstances': self.extract_circumstances(text),
                'image_url': self.extract_s3_image_url(soup)  # soup needed for CSS selectors
            }
            
            return hero_data
            
        except Exception as e:
            print(f"❌ Error scraping profile {profile_url}: {str(e)}")
            return None
    
    def extract_s3_image_url(self, soup):
        """
        Extract ONLY S3 image URLs from the profile page using the exact structure:
        <div class="content-div">
            <div class="record-image">
                <img src="https://s3.amazonaws.com/static.militarytimes.com/thefallen/hero_name_lg.jpg" width="125">
        """
        # Look specifically for the content-div > record-image > img structure
        content_div = soup.select_one(".content-div")
        if content_div:
            record_image_div = content_div.select_one(".record-image")
            if record_image_div:
                img_tag = record_image_div.select_one("img")
                if img_tag and img_tag.get("src"):
                    src = img_tag.get("src")
                    if src.startswith("https://s3.amazonaws.com/static.militarytimes.com/thefallen/"):
                        print(f"✅ Found S3 image in content-div > record-image: {src}")
                        return src
                    else:
                        print(f"⚠️ Found non-S3 image in record-image: {src}")
        
        # Fallback: look for any record-image div (in case structure varies slightly)
        record_image_div = soup.select_one(".record-image")
        if record_image_div:
            img_tag = record_image_div.select_one("img")
            if img_tag and img_tag.get("src"):
                src = img_tag.get("src")
                if src.startswith("https://s3.amazonaws.com/static.militarytimes.com/thefallen/"):
                    print(f"✅ Found S3 image in record-image (fallback): {src}")
                    return src
                else:
                    print(f"⚠️ Found non-S3 image in record-image (fallback): {src}")
        
        # Final fallback: search all images for the specific S3 thefallen path
        all_images = soup.find_all('img')
        for img in all_images:
            src = img.get('src', '')
            if src.startswith("https://s3.amazonaws.com/static.militarytimes.com/thefallen/"):
                print(f"✅ Found S3 thefallen image in document: {src}")
                return src
        
        print("⚠️ No S3 thefallen image found on profile page")
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
    
    def extract_rank(self, text):
        """Extract military rank"""
        match = self._rank_re.search(text)
        return match.group(1) if match else ""

    def extract_age(self, text):
        """Extract age at time of death"""
        match = self._age_re.search(text)
        return match.group(1) if match else ""

    def extract_hometown(self, text):
        """Extract hometown information"""
        for pattern in self._hometown_res:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return ""

    def extract_branch(self, text):
        """Extract military branch"""
        branches = ['Army', 'Navy', 'Air Force', 'Marines', 'Coast Guard']
        text_lower = text.lower()
        for branch in branches:
            if branch.lower() in text_lower:
                return f"U.S. {branch}"
        return ""

    def extract_unit(self, text):
        """Extract military unit information"""
        for pattern in self._unit_res:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return ""

    def extract_date_of_death(self, text):
        """Extract date of death"""
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

    def extract_location(self, text):
        """Extract location of death"""
        locations = ['Afghanistan', 'Iraq', 'Syria', 'Kuwait', 'Qatar']
        text_lower = text.lower()
        for location in locations:
            if location.lower() in text_lower:
                return location
        return ""

    def extract_circumstances(self, text):
        """Extract circumstances of death"""
        for pattern in self._circumstance_res:
            match = pattern.search(text)
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
        self.session = requests.Session()
        
        # Use same headers as scraper for consistency
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site'
        })
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def download_hero_image(self, hero_data):
        """
        Download hero's image with S3 URL validation and placeholder fallback.
        """
        image_url = hero_data.get('image_url')
        name = hero_data.get('name', 'unknown')
        
        # Create safe filename
        safe_name = re.sub(r'[^a-z0-9\s]', '', name.lower())
        safe_name = re.sub(r'\s+', '_', safe_name.strip())
        filename = f"{safe_name}.jpg"
        filepath = os.path.join(self.download_dir, filename)
        
        # Check if we have a valid S3 image URL
        if image_url and image_url.startswith("https://s3.amazonaws.com/"):
            print(f"📥 Downloading S3 image from: {image_url}")
            
            try:
                # Add delay before downloading image
                time.sleep(3)
                
                response = self.session.get(image_url, stream=True, timeout=30)
                
                if response.status_code == 200:
                    # Check if it's actually an image
                    content_type = response.headers.get('content-type', '')
                    if content_type.startswith('image/'):
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        
                        # Verify the file was downloaded and has content
                        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                            self.optimize_image(filepath)
                            print(f"✅ Downloaded and optimized S3 image: {filename}")
                            return filename
                        else:
                            print(f"❌ Downloaded S3 file is empty")
                    else:
                        print(f"⚠️ S3 URL doesn't return an image: {content_type}")
                else:
                    print(f"❌ Failed to download S3 image: HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"❌ Error downloading S3 image: {str(e)}")
        
        # If no S3 image or download failed, create a placeholder
        print(f"📷 No S3 image available for {name}. Creating placeholder...")
        return self.create_placeholder_image(name, filepath)
    
    def create_placeholder_image(self, hero_name, filepath):
        """
        Create a placeholder image for heroes without photos.
        """
        try:
            # Create a 1080x1080 image with military colors
            img = Image.new('RGB', (1080, 1080), color='#1a472a')  # Military green
            draw = ImageDraw.Draw(img)
            
            # Try to load a font, fall back to default if not available
            try:
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 80)
                font_medium = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 60)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 40)
            except:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # Draw text
            text_color = '#ffffff'  # White text
            
            # Title
            title = "IN MEMORY OF"
            bbox = draw.textbbox((0, 0), title, font=font_medium)
            title_width = bbox[2] - bbox[0]
            draw.text(((1080 - title_width) // 2, 300), title, fill=text_color, font=font_medium)
            
            # Hero name (split into lines if too long)
            name_words = hero_name.split()
            if len(' '.join(name_words)) > 20:  # If name is too long
                # Split into two lines
                mid_point = len(name_words) // 2
                line1 = ' '.join(name_words[:mid_point])
                line2 = ' '.join(name_words[mid_point:])
                
                bbox1 = draw.textbbox((0, 0), line1, font=font_large)
                line1_width = bbox1[2] - bbox1[0]
                draw.text(((1080 - line1_width) // 2, 450), line1, fill=text_color, font=font_large)
                
                bbox2 = draw.textbbox((0, 0), line2, font=font_large)
                line2_width = bbox2[2] - bbox2[0]
                draw.text(((1080 - line2_width) // 2, 550), line2, fill=text_color, font=font_large)
            else:
                bbox = draw.textbbox((0, 0), hero_name, font=font_large)
                name_width = bbox[2] - bbox[0]
                draw.text(((1080 - name_width) // 2, 450), hero_name, fill=text_color, font=font_large)
            
            # Bottom text
            bottom_text = "FALLEN HERO"
            bbox = draw.textbbox((0, 0), bottom_text, font=font_medium)
            bottom_width = bbox[2] - bbox[0]
            draw.text(((1080 - bottom_width) // 2, 650), bottom_text, fill=text_color, font=font_medium)
            
            # Save the placeholder image
            img.save(filepath, 'JPEG', quality=90)
            
            filename = os.path.basename(filepath)
            print(f"✅ Created placeholder image: {filename}")
            return filename
            
        except Exception as e:
            print(f"❌ Error creating placeholder image: {str(e)}")
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
                data = {'published': 'false'}
                headers = {"Authorization": f"Bearer {self.access_token}"}

                response = requests.post(url, files=files, data=data, headers=headers)

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
            'message': memorial_text,
            'attached_media[0]': json.dumps({'media_fbid': photo_id}),
            'published': 'true'
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = requests.post(url, data=data, headers=headers)
            
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
    Main function - now optimized to find and post just ONE hero to avoid server overload
    """
    print("🇺🇸 Starting Fallen Heroes Memorial Script 🇺🇸")
    print(f"Search Mode: {os.getenv('SEARCH_MODE', 'daily')}")
    print(f"Timestamp: {datetime.now()}")
    
    # Get configuration
    access_token = os.getenv('FB_ACCESS_TOKEN')
    page_id = os.getenv('FB_PAGE_ID')
    
    if not access_token or not page_id:
        print("❌ Missing Facebook credentials")
        return
    
    # Initialize components
    scraper = MilitaryTimesScraper()
    downloader = ImageDownloader()
    poster = FacebookPoster(access_token, page_id)
    
    # Use today's date
    today = datetime.now()
    
    print(f"🔍 Searching for ONE hero who died on {today.strftime('%B %d')} (any year since 2003)")
    
    # Find just one hero to avoid overloading servers
    hero = scraper.get_single_hero_for_date(today)
    
    if not hero:
        print(f"ℹ️ No fallen heroes found for {today.strftime('%B %d')} across all years")
        return
    
    print(f"✅ Selected hero: {hero.get('name', 'Unknown')}")
    print(f"📅 Date of death: {hero.get('date_of_death', 'Unknown')}")
    
    # Download hero image
    print(f"\n--- Processing: {hero.get('name', 'Unknown')} ---")
    image_filename = downloader.download_hero_image(hero)
    
    if not image_filename:
        print("❌ Failed to download hero image. Cannot create post.")
        return
    
    image_path = os.path.join(downloader.download_dir, image_filename)
    
    # Post memorial to Facebook
    print(f"\n📝 Creating Facebook memorial post...")
    success = poster.post_text_with_image(hero, image_path)
    
    if success:
        print(f"\n🎯 SUCCESS!")
        print(f"✅ Memorial post created for {hero.get('name', 'Unknown')}")
        print(f"🇺🇸 Hero honored and remembered 🇺🇸")
    else:
        print(f"\n❌ Failed to create memorial post for {hero.get('name', 'Unknown')}")
    
    print(f"\n📊 SUMMARY:")
    print(f"📅 Search date: {today.strftime('%B %d')}")
    print(f"👤 Hero: {hero.get('name', 'Unknown')}")
    print(f"📝 Post created: {'Yes' if success else 'No'}")

if __name__ == "__main__":
    main()
