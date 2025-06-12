#!/bin/python3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
PAGE_ID = os.getenv("FB_PAGE_ID")

def get_fallen_service_members(date):
    base_url = "https://thefallen.militarytimes.com/search"
    formatted_date = date.strftime("%m%%2F%d%%2F%Y")
    query_url = f"{base_url}?year=&year_month=&first_name=&last_name=&start_date={formatted_date}&end_date={formatted_date}&conflict=&home_state=&home_town="

    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    proxies = {"http": PROXY, "https": PROXY} if USE_PROXY and PROXY else None
    response = requests.get(query_url, headers=headers, proxies=proxies)

    if response.status_code != 200 or "Access Denied" in response.text or "Captcha" in response.text:
        print(f"[!] Failed or blocked when fetching {query_url}")
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
        image_tag = entry.select_one(".data-box-left img")
        image_url = image_tag["src"] if image_tag and "src" in image_tag.attrs else ""

        fallen_list.append({
            "name": name,
            "date": date_of_death,
            "link": profile_link,
            "image_url": image_url
        })

    return fallen_list

def post_images_to_facebook(captions_and_urls):
    print("[*] Uploading images to Facebook...")
    uploaded_media = []
    for caption, image_url in captions_and_urls:
        try:
            proxies = {"http": PROXY, "https": PROXY} if USE_PROXY and PROXY else None
            image_data = requests.get(image_url, proxies=proxies).content
        except Exception as e:
            print(f"[!] Failed to download image: {image_url} - {e}")
            continue

        upload_url = "https://graph.facebook.com/v23.0/photos"
        files = {'source': ('image.jpg', image_data, 'image/jpeg')}
        data = {
            "caption": caption,
            "access_token": ACCESS_TOKEN,
            "published": "false",
            "page_id": PAGE_ID
        }

        response = requests.post(upload_url, data=data, files=files)
        if response.status_code == 200:
            media_id = response.json().get("id")
            uploaded_media.append({"media_fbid": media_id})
            print(f"✔ Uploaded image for: {caption.splitlines()[0]}")
        else:
            print(f"[X] Upload failed: {response.status_code} - {response.text}")

    if not uploaded_media:
        print("[!] No images uploaded. Skipping post.")
        return

    post_url = f"https://graph.facebook.com/{PAGE_ID}/feed"
    payload = {
        "message": "🕊 Honoring Our Fallen Heroes 🕊\n\nToday we remember their service and sacrifice.",
        "access_token": ACCESS_TOKEN,
        "attached_media": uploaded_media
    }

    response = requests.post(post_url, json=payload)
    if response.status_code == 200:
        print("✅ Facebook post created successfully.")
    else:
        print(f"[X] Failed to post to Facebook: {response.status_code} - {response.text}")

def main():
    today = datetime.today()
    search_years = [2005, 2010, 2015, 2020, 2025]
    all_captions_and_images = []

    for year in search_years:
        search_date = today.replace(year=year)
        fallen = get_fallen_service_members(search_date)
        for person in fallen:
            if not person["image_url"]:
                continue
            caption = f"{person['name']}\n📅 {person['date']}\n🔗 https://thefallen.militarytimes.com{person['link']}"
            all_captions_and_images.append((caption, person["image_url"]))

    if all_captions_and_images:
        post_images_to_facebook(all_captions_and_images)
    else:
        print("[*] No fallen service members with images found for this date.")

if __name__ == "__main__":
    main()