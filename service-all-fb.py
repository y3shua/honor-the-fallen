#!/usr/bin/env python3
"""
Daily Heroes Multi-Post Script
Creates a single Facebook post with ALL fallen heroes for the day
Includes multiple images with captions and comprehensive hero information
"""

import requests
import json
import time
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
from bs4 import BeautifulSoup
import re
import random

class MilitaryTimesScraper:
    def __init__(self):
        self.base_url = "https://thefallen.militarytimes.com"
        self.use_proxy = os.getenv('USE_PROXY', 'false').lower() == 'true'
        self.proxy = os.getenv('PROXY_URL') if self.use_proxy else None
        self.session = requests.Session()
        
        # Use updated Chrome user agent
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
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
    
    def get_all_heroes_for_date(self, target_date):
        """
        Get ALL fallen heroes for the given date across all years.
        Returns list of complete hero data with images.
        """
        print(f"🔍 Searching for ALL heroes who died on {target_date.strftime('%B %d')} (across all years)")
        
        all_heroes = []
        current_year = datetime.now().year
        
        # Search all years from 2003 to current year
        for year in range(2003, current_year + 1):
            year_date = target_date.replace(year=year)
            print(f"📅 Checking {year_date.strftime('%B %d, %Y')}")
            
            try:
                fallen_list = self.get_fallen_service_members(year_date)
                
                if fallen_list:
                    print(f"  ✅ Found {len(fallen_list)} hero(s) for {year}")
                    
                    # Process each hero from this year
                    for fallen in fallen_list:
                        hero_data = self.convert_to_hero_data(fallen)
                        hero_data['year'] = year
                        
                        # Get additional details from profile
                        if fallen.get('link'):
                            print(f"    🔍 Getting details for {fallen.get('name', 'Unknown')}")
                            additional_data = self.scrape_hero_profile(fallen['link'])
                            if additional_data:
                                hero_data.update(additional_data)
                            time.sleep(1)  # Rate limit between profile scrapes
                        
                        all_heroes.append(hero_data)
                
            except Exception as e:
                print(f"  ⚠️ Error searching year {year}: {str(e)}")
                continue
            
            time.sleep(1)  # Rate limit between years
        
        print(f"\n✅ Found {len(all_heroes)} total heroes for {target_date.strftime('%B %d')}")
        return all_heroes
    
    def get_fallen_service_members(self, date):
        """Get fallen service members for a specific date"""
        base_url = "https://thefallen.militarytimes.com/search"
        formatted_date = date.strftime("%m%%2F%d%%2F%Y")
        query_url = f"{base_url}?year=&year_month=&first_name=&last_name=&start_date={formatted_date}&end_date={formatted_date}&conflict=&home_state=&home_town="
        
        proxies = {"http": self.proxy, "https": self.proxy} if self.use_proxy and self.proxy else None
        
        try:
            response = self.session.get(query_url, proxies=proxies, timeout=30)
            
            if response.status_code != 200:
                return []
            
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
                            "link": profile_link
                        })
                    
                except Exception as e:
                    continue
            
            return fallen_list
            
        except Exception as e:
            print(f"❌ Error fetching data: {str(e)}")
            return []
    
    def convert_to_hero_data(self, fallen):
        """Convert fallen service member data to hero data format"""
        return {
            'name': fallen.get('name', 'Unknown Hero'),
            'date_of_death': fallen.get('date', ''),
            'profile_url': fallen.get('link', ''),
            'rank': '',
            'age': '',
            'hometown': '',
            'branch': '',
            'unit': '',
            'location': '',
            'circumstances': '',
            'image_url': None
        }
    
    def scrape_hero_profile(self, profile_url):
        """Scrape detailed information from hero's profile page"""
        try:
            response = self.session.get(profile_url, timeout=30)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            return {
                'rank': self.extract_rank(soup),
                'age': self.extract_age(soup),
                'hometown': self.extract_hometown(soup),
                'branch': self.extract_branch(soup),
                'unit': self.extract_unit(soup),
                'location': self.extract_location(soup),
                'circumstances': self.extract_circumstances(soup),
                'image_url': self.extract_s3_image_url(soup)
            }
            
        except Exception as e:
            print(f"❌ Error scraping profile: {str(e)}")
            return None
    
    def extract_s3_image_url(self, soup):
        """Extract S3 image URL from profile page"""
        # Look for content-div > record-image > img structure
        content_div = soup.select_one(".content-div")
        if content_div:
            record_image_div = content_div.select_one(".record-image")
            if record_image_div:
                img_tag = record_image_div.select_one("img")
                if img_tag and img_tag.get("src"):
                    src = img_tag.get("src")
                    if src.startswith("https://s3.amazonaws.com/static.militarytimes.com/thefallen/"):
                        return src
        
        # Fallback: look for any record-image div
        record_image_div = soup.select_one(".record-image")
        if record_image_div:
            img_tag = record_image_div.select_one("img")
            if img_tag and img_tag.get("src"):
                src = img_tag.get("src")
                if src.startswith("https://s3.amazonaws.com/static.militarytimes.com/thefallen/"):
                    return src
        
        return None
    
    def extract_rank(self, soup):
        """Extract military rank"""
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
        return age_match.group(1) if age_match else ""
    
    def extract_hometown(self, soup):
        """Extract hometown information"""
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
        """Extract military unit"""
        text = soup.get_text()
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

class ImageProcessor:
    def __init__(self, download_dir="daily_heroes_images"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
        })
    
    def process_all_hero_images(self, heroes):
        """
        Process images for all heroes - download S3 images or create placeholders.
        Returns list of image paths with captions.
        """
        image_data = []
        
        for i, hero in enumerate(heroes):
            print(f"\n📸 Processing image {i+1}/{len(heroes)}: {hero.get('name', 'Unknown')}")
            
            # Create filename
            name = hero.get('name', 'unknown').lower()
            safe_name = re.sub(r'[^a-z0-9\s]', '', name)
            safe_name = re.sub(r'\s+', '_', safe_name.strip())
            filename = f"{safe_name}.jpg"
            filepath = os.path.join(self.download_dir, filename)
            
            # Download S3 image or create placeholder
            success = self.download_or_create_image(hero, filepath)
            
            if success:
                # Create caption for this image (rank + name)
                rank = hero.get('rank', '').strip()
                name = hero.get('name', 'Unknown').strip()
                caption = f"{rank} {name}".strip() if rank else name
                
                image_data.append({
                    'filepath': filepath,
                    'caption': caption,
                    'hero': hero
                })
            
            # Rate limit between image processing
            time.sleep(2)
        
        return image_data
    
    def download_or_create_image(self, hero_data, filepath):
        """Download S3 image or create placeholder"""
        image_url = hero_data.get('image_url')
        
        # Try to download S3 image first
        if image_url and image_url.startswith("https://s3.amazonaws.com/static.militarytimes.com/thefallen/"):
            try:
                print(f"📥 Downloading S3 image...")
                response = self.session.get(image_url, stream=True, timeout=30)
                
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '')
                    if content_type.startswith('image/'):
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        
                        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                            self.optimize_image(filepath)
                            print(f"✅ Downloaded S3 image")
                            return True
            
            except Exception as e:
                print(f"⚠️ Failed to download S3 image: {str(e)}")
        
        # Create placeholder if S3 download failed or no S3 image
        print(f"📷 Creating placeholder image...")
        return self.create_placeholder_image(hero_data, filepath)
    
    def create_placeholder_image(self, hero_data, filepath):
        """Create placeholder image for hero"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Create 1080x1080 image
            img = Image.new('RGB', (1080, 1080), color='#1a472a')  # Military green
            draw = ImageDraw.Draw(img)
            
            # Load fonts
            try:
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 70)
                font_medium = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 50)
            except:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
            
            text_color = '#ffffff'
            
            # Title
            title = "IN MEMORY OF"
            bbox = draw.textbbox((0, 0), title, font=font_medium)
            title_width = bbox[2] - bbox[0]
            draw.text(((1080 - title_width) // 2, 350), title, fill=text_color, font=font_medium)
            
            # Hero name
            hero_name = hero_data.get('name', 'Unknown Hero')
            rank = hero_data.get('rank', '').strip()
            
            # Combine rank and name
            full_name = f"{rank} {hero_name}".strip() if rank else hero_name
            
            # Handle long names
            if len(full_name) > 25:
                words = full_name.split()
                mid_point = len(words) // 2
                line1 = ' '.join(words[:mid_point])
                line2 = ' '.join(words[mid_point:])
                
                bbox1 = draw.textbbox((0, 0), line1, font=font_large)
                line1_width = bbox1[2] - bbox1[0]
                draw.text(((1080 - line1_width) // 2, 450), line1, fill=text_color, font=font_large)
                
                bbox2 = draw.textbbox((0, 0), line2, font=font_large)
                line2_width = bbox2[2] - bbox2[0]
                draw.text(((1080 - line2_width) // 2, 530), line2, fill=text_color, font=font_large)
            else:
                bbox = draw.textbbox((0, 0), full_name, font=font_large)
                name_width = bbox[2] - bbox[0]
                draw.text(((1080 - name_width) // 2, 480), full_name, fill=text_color, font=font_large)
            
            # Bottom text
            bottom_text = "FALLEN HERO"
            bbox = draw.textbbox((0, 0), bottom_text, font=font_medium)
            bottom_width = bbox[2] - bbox[0]
            draw.text(((1080 - bottom_width) // 2, 650), bottom_text, fill=text_color, font=font_medium)
            
            # Save image
            img.save(filepath, 'JPEG', quality=90)
            print(f"✅ Created placeholder image")
            return True
            
        except Exception as e:
            print(f"❌ Error creating placeholder: {str(e)}")
            return False
    
    def optimize_image(self, filepath):
        """Optimize image for Facebook"""
        try:
            with Image.open(filepath) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((1080, 1080), Image.Resampling.LANCZOS)
                img.save(filepath, 'JPEG', quality=90, optimize=True)
        except Exception as e:
            print(f"⚠️ Could not optimize image: {str(e)}")

class FacebookMultiPoster:
    def __init__(self, access_token, page_id):
        self.access_token = access_token
        self.page_id = page_id
        self.base_url = "https://graph.facebook.com/v18.0"
    
    def create_multi_hero_post(self, heroes, image_data, date):
        """
        Create a single Facebook post with multiple hero images and comprehensive text.
        """
        print(f"\n📝 Creating multi-hero Facebook post for {len(heroes)} heroes...")
        
        # Step 1: Upload all images (unpublished) and collect photo IDs
        photo_ids = []
        for img_data in image_data:
            photo_id = self.upload_image_with_caption(img_data['filepath'], img_data['caption'])
            if photo_id:
                photo_ids.append(photo_id)
            time.sleep(1)  # Rate limit between uploads
        
        if not photo_ids:
            print("❌ No images uploaded successfully")
            return False
        
        print(f"✅ Uploaded {len(photo_ids)} images")
        
        # Step 2: Create comprehensive post text
        post_text = self.create_comprehensive_post_text(heroes, date)
        
        # Step 3: Create the main post with all attached images
        return self.create_post_with_multiple_images(post_text, photo_ids)
    
    def upload_image_with_caption(self, image_path, caption):
        """Upload image with caption but don't publish it"""
        url = f"{self.base_url}/{self.page_id}/photos"
        
        try:
            with open(image_path, 'rb') as image_file:
                files = {'source': image_file}
                data = {
                    'access_token': self.access_token,
                    'caption': caption,  # Individual image caption
                    'published': 'false'
                }
                
                response = requests.post(url, files=files, data=data)
                
                if response.status_code == 200:
                    result = response.json()
                    photo_id = result.get('id')
                    print(f"  ✅ Uploaded: {caption}")
                    return photo_id
                else:
                    print(f"  ❌ Failed to upload {caption}: {response.text}")
                    return None
                    
        except Exception as e:
            print(f"  ❌ Error uploading {caption}: {str(e)}")
            return None
    
    def create_comprehensive_post_text(self, heroes, date):
        """Create comprehensive text for the multi-hero post"""
        lines = []
        
        # Header
        lines.append("🇺🇸 HONORING OUR FALLEN HEROES 🇺🇸")
        lines.append("")
        lines.append(f"📅 On this day, {date.strftime('%B %d')}, we remember these brave service members who made the ultimate sacrifice:")
        lines.append("")
        
        # List each hero with details
        for i, hero in enumerate(heroes, 1):
            name = hero.get('name', 'Unknown Hero')
            rank = hero.get('rank', '').strip()
            date_of_death = hero.get('date_of_death', '').strip()
            location = hero.get('location', '').strip()
            year = hero.get('year', '')
            
            # Format hero entry
            hero_line = f"{i}. "
            if rank:
                hero_line += f"{rank} {name}"
            else:
                hero_line += name
            
            lines.append(hero_line)
            
            # Add death details if available
            details = []
            if date_of_death and date_of_death != 'Unknown Date':
                details.append(f"Died: {date_of_death}")
            elif year:
                details.append(f"Died: {year}")
            
            if location:
                details.append(f"Location: {location}")
            
            if details:
                lines.append(f"   {' | '.join(details)}")
            
            lines.append("")
        
        # Memorial message
        lines.append("🌟 Each of these heroes answered the call to serve our nation with courage and dedication. Their sacrifice will never be forgotten, and their memory will live on in the hearts of all Americans.")
        lines.append("")
        lines.append("💙 We honor their service and extend our deepest gratitude to their families, friends, and fellow service members who continue to carry their legacy forward.")
        lines.append("")
        lines.append("🙏 Please take a moment to read their names, honor their memory, and share their stories. They gave everything for our freedom.")
        lines.append("")
        
        # Hashtags
        hashtags = [
            "#FallenHeroes", "#NeverForget", "#HonorTheFallen", 
            "#MemorialDay", "#Military", "#Sacrifice", 
            "#Freedom", "#Heroes", "#RememberThem", 
            "#Service", "#Gratitude", "#UltimatePrice"
        ]
        
        # Add branch-specific hashtags
        branches_found = set()
        for hero in heroes:
            branch = hero.get('branch', '').lower()
            if 'army' in branch:
                branches_found.add('Army')
            elif 'navy' in branch:
                branches_found.add('Navy')
            elif 'air force' in branch:
                branches_found.add('AirForce')
            elif 'marine' in branch:
                branches_found.add('Marines')
            elif 'coast guard' in branch:
                branches_found.add('CoastGuard')
        
        for branch in branches_found:
            if branch == 'Army':
                hashtags.extend(['#Army', '#USArmy'])
            elif branch == 'Navy':
                hashtags.extend(['#Navy', '#USNavy'])
            elif branch == 'AirForce':
                hashtags.extend(['#AirForce', '#USAF'])
            elif branch == 'Marines':
                hashtags.extend(['#Marines', '#USMC', '#SemperFi'])
            elif branch == 'CoastGuard':
                hashtags.extend(['#CoastGuard', '#USCG'])
        
        lines.append(" ".join(hashtags))
        lines.append("")
        lines.append("🇺🇸 \"All gave some, some gave all\" 🇺🇸")
        
        return "\n".join(lines)
    
    def create_post_with_multiple_images(self, post_text, photo_ids):
        """Create the final post with multiple attached images"""
        url = f"{self.base_url}/{self.page_id}/feed"
        
        # Prepare attached media
        attached_media = {}
        for i, photo_id in enumerate(photo_ids):
            attached_media[f'attached_media[{i}]'] = json.dumps({'media_fbid': photo_id})
        
        data = {
            'access_token': self.access_token,
            'message': post_text,
            'published': 'true',
            **attached_media
        }
        
        try:
            response = requests.post(url, data=data)
            
            if response.status_code == 200:
                result = response.json()
                post_id = result.get('id')
                print(f"✅ Multi-hero post created successfully! Post ID: {post_id}")
                return True
            else:
                print(f"❌ Post creation failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error creating post: {str(e)}")
            return False

def main():
    """
    Main function: Create a comprehensive daily heroes post
    """
    print("🇺🇸 Starting Daily Heroes Multi-Post Script 🇺🇸")
    print(f"Timestamp: {datetime.now()}")
    
    # Get configuration
    access_token = os.getenv('FB_ACCESS_TOKEN')
    page_id = os.getenv('FB_PAGE_ID')
    
    if not access_token or not page_id:
        print("❌ Missing Facebook credentials")
        return
    
    # Initialize components
    scraper = MilitaryTimesScraper()
    image_processor = ImageProcessor()
    poster = FacebookMultiPoster(access_token, page_id)
    
    # Use today's date
    today = datetime.now()
    
    print(f"\n🔍 Finding ALL heroes who died on {today.strftime('%B %d')} (any year)")
    
    # Get all heroes for today's date
    heroes = scraper.get_all_heroes_for_date(today)
    
    if not heroes:
        print(f"ℹ️ No fallen heroes found for {today.strftime('%B %d')}")
        return
    
    print(f"\n✅ Found {len(heroes)} total heroes for {today.strftime('%B %d')}")
    
    # Process all hero images
    print(f"\n📸 Processing images for all {len(heroes)} heroes...")
    image_data = image_processor.process_all_hero_images(heroes)
    
    if not image_data:
        print("❌ No images processed successfully")
        return
    
    print(f"✅ Processed {len(image_data)} images")
    
    # Create comprehensive Facebook post
    success = poster.create_multi_hero_post(heroes, image_data, today)
    
    if success:
        print(f"\n🎯 SUCCESS!")
        print(f"✅ Comprehensive memorial post created for {len(heroes)} heroes")
        print(f"📅 Date: {today.strftime('%B %d')}")
        print(f"👥 Heroes honored: {len(heroes)}")
        print(f"📸 Images included: {len(image_data)}")
        print(f"🇺🇸 All heroes honored and remembered 🇺🇸")
    else:
        print(f"\n❌ Failed to create comprehensive memorial post")

if __name__ == "__main__":
    main()
