#!/usr/bin/env python3
"""
Honor the Fallen - Facebook Posting Script
Modified to create proper text posts with embedded images instead of photo uploads
"""

import requests
import json
import time
import os
from datetime import datetime
from PIL import Image
import io

class FacebookPoster:
    def __init__(self, access_token, page_id):
        self.access_token = access_token
        self.page_id = page_id
        self.base_url = "https://graph.facebook.com/v18.0"
        
    def upload_image_unpublished(self, image_path):
        """
        Upload image to Facebook without publishing it.
        Returns photo ID for later use in text post.
        """
        url = f"{self.base_url}/{self.page_id}/photos"
        
        try:
            with open(image_path, 'rb') as image_file:
                files = {'source': image_file}
                data = {
                    'access_token': self.access_token,
                    'published': 'false'  # Key: Don't publish the image directly
                }
                
                response = requests.post(url, files=files, data=data)
                
                if response.status_code == 200:
                    result = response.json()
                    photo_id = result.get('id')
                    print(f"✅ Image uploaded successfully. Photo ID: {photo_id}")
                    return photo_id
                else:
                    print(f"❌ Image upload failed: {response.text}")
                    return None
                    
        except Exception as e:
            print(f"❌ Error uploading image: {str(e)}")
            return None
    
    def create_memorial_text(self, hero_data):
        """
        Create comprehensive memorial text for the fallen hero.
        This becomes the primary searchable content of the post.
        """
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
        
        # Additional details
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
        
        # Hashtags for discoverability
        hashtags = [
            "#FallenHero", "#NeverForget", "#HonorTheFallen", 
            "#MemorialDay", "#Military", "#Sacrifice", 
            "#Freedom", "#Heroes", "#RememberThem", 
            "#Service", "#Gratitude", "#UltimatePrice"
        ]
        
        # Add branch-specific hashtags
        branch = hero_data.get('branch', '').lower()
        if 'army' in branch:
            hashtags.extend(["#Army", "#USArmy"])
        elif 'navy' in branch:
            hashtags.extend(["#Navy", "#USNavy"])
        elif 'air force' in branch or 'airforce' in branch:
            hashtags.extend(["#AirForce", "#USAF"])
        elif 'marine' in branch:
            hashtags.extend(["#Marines", "#USMC", "#SemperFi"])
        elif 'coast guard' in branch:
            hashtags.extend(["#CoastGuard", "#USCG"])
        
        lines.append(" ".join(hashtags))
        
        # Profile link if available
        if hero_data.get('profile_url'):
            lines.append("")
            lines.append(f"📖 Learn more: {hero_data['profile_url']}")
        
        lines.append("")
        lines.append("🇺🇸 \"All gave some, some gave all\" 🇺🇸")
        
        return "\n".join(lines)
    
    def post_text_with_image(self, hero_data, image_path):
        """
        Create a Facebook text post with embedded image.
        This is the main method to replace your current photo upload.
        """
        print(f"📝 Creating memorial post for {hero_data.get('name', 'Unknown Hero')}")
        
        # Step 1: Upload image without publishing
        photo_id = self.upload_image_unpublished(image_path)
        if not photo_id:
            return False
        
        # Step 2: Create text post with attached image
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
                print(f"✅ Memorial post created successfully! Post ID: {post_id}")
                return True
            else:
                print(f"❌ Post creation failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error creating post: {str(e)}")
            return False

def process_fallen_heroes(heroes_data, images_directory):
    """
    Process multiple fallen heroes with proper rate limiting.
    Replace your current posting loop with this function.
    """
    # Get Facebook credentials from environment variables
    access_token = os.getenv('FB_ACCESS_TOKEN')
    page_id = os.getenv('FB_PAGE_ID')
    
    if not access_token or not page_id:
        print("❌ Missing Facebook credentials. Set FB_ACCESS_TOKEN and FB_PAGE_ID environment variables.")
        return
    
    poster = FacebookPoster(access_token, page_id)
    
    successful_posts = 0
    failed_posts = 0
    
    for i, hero in enumerate(heroes_data):
        print(f"\n--- Processing {i+1}/{len(heroes_data)}: {hero.get('name', 'Unknown')} ---")
        
        # Construct image path
        image_filename = hero.get('image_filename')
        if not image_filename:
            print(f"⚠️ No image file for {hero.get('name', 'Unknown')}")
            failed_posts += 1
            continue
        
        image_path = os.path.join(images_directory, image_filename)
        
        if not os.path.exists(image_path):
            print(f"⚠️ Image file not found: {image_path}")
            failed_posts += 1
            continue
        
        # Post the memorial
        success = poster.post_text_with_image(hero, image_path)
        
        if success:
            successful_posts += 1
        else:
            failed_posts += 1
        
        # Rate limiting - wait between posts
        if i < len(heroes_data) - 1:
            print("⏳ Waiting 3 seconds before next post...")
            time.sleep(3)
    
    print(f"\n🎯 POSTING SUMMARY:")
    print(f"✅ Successful posts: {successful_posts}")
    print(f"❌ Failed posts: {failed_posts}")
    print(f"📊 Total processed: {len(heroes_data)}")

# Example of how to modify your existing hero data structure
def example_hero_data():
    """
    Example of the hero data structure your script should create.
    Modify your Military Times scraping to populate this structure.
    """
    return {
        'name': 'John Doe',
        'rank': 'Staff Sergeant',
        'age': '28',
        'hometown': 'Springfield, Illinois',
        'branch': 'U.S. Army',
        'unit': '1st Infantry Division',
        'date_of_death': 'June 18, 2024',
        'location': 'Afghanistan',
        'circumstances': 'Killed in action during combat operations against enemy forces.',
        'profile_url': 'https://thefallen.militarytimes.com/army-staff-sgt-john-doe',
        'image_filename': 'john_doe.jpg'  # This should be the downloaded image filename
    }

# Integration with your existing script
def main():
    """
    Main function showing how to integrate with your existing script.
    Replace your current Facebook posting code with this approach.
    """
    
    # This is where your existing Military Times scraping code would go
    # For now, using example data
    heroes_today = [
        example_hero_data(),
        # Add more heroes from your scraping results
    ]
    
    # Directory where you save downloaded hero images
    images_dir = "hero_images"  # Adjust to match your directory structure
    
    # Process and post all heroes
    process_fallen_heroes(heroes_today, images_dir)

if __name__ == "__main__":
    main()
