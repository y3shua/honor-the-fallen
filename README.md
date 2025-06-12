# Fallen Heroes Memorial Project 🇺🇸

A Python script that automatically honors fallen service members by posting their photos and detailed information to Facebook daily using GitHub Actions.

## Overview

This project queries the Military Times fallen service members database and creates memorial posts on Facebook to ensure our fallen heroes are never forgotten. The script runs daily via GitHub Actions, searching for service members who made the ultimate sacrifice on this day in history.

## Features

- **Daily Automated Posts**: GitHub Actions runs the script daily at a scheduled time
- **Comprehensive Search**: Searches across multiple years for service members who died on the current date
- **Detailed Profiles**: Extracts detailed information including rank, unit, hometown, and circumstances
- **Photo Processing**: Downloads and optimizes photos for Facebook posting
- **Respectful Presentation**: Creates detailed captions honoring each service member
- **Rate Limiting**: Implements proper delays to respect API limits

## Setup

### Prerequisites

- Python 3.8+
- Facebook Page with appropriate permissions
- Facebook App with Pages API access
- GitHub repository with Actions enabled

### Environment Variables

Set these as GitHub Secrets:

```bash
FB_ACCESS_TOKEN=your_facebook_page_access_token
FB_PAGE_ID=your_facebook_page_id
USE_PROXY=false  # Set to true if using proxy
PROXY_URL=your_proxy_url  # Only if using proxy
SEARCH_MODE=daily  # Options: daily, comprehensive, recent
```

### Dependencies

```bash
pip install requests beautifulsoup4 pillow
```

## Usage

### Local Development

```bash
python complete_fallen_heroes_script.py
```

### GitHub Actions

The script runs automatically via GitHub Actions. See `.github/workflows/` for the workflow configuration.

## Search Modes

- **daily** (default): Searches for service members who died on today's date across multiple years (2003-2025)
- **comprehensive**: Searches from Iraq invasion (March 20, 2003) to present
- **recent**: Searches the last 30 days

## Data Sources

- **Primary**: [Military Times - The Fallen](https://thefallen.militarytimes.com/)
- **Profiles**: Individual service member profile pages with detailed information

## Script Features

### Information Extracted

- Full name and rank
- Branch of service and unit
- Age and hometown
- Date and location of sacrifice
- Circumstances of death
- Service photo

### Facebook Post Format

Each post includes:
- Hero's photo (optimized for Facebook)
- Detailed caption with military information
- Respectful emojis and formatting
- Link to full Military Times profile
- Relevant hashtags

### Image Processing

- Downloads original photos from Military Times
- Resizes to optimal Facebook dimensions (1080x1080)
- Maintains aspect ratio with neutral background
- High-quality JPEG output

## Development History

### Key Development Sessions

- **Initial Development**: [Claude Chat - Script Development](https://claude.ai/share/b978d747-2c97-4e01-91d0-6468d30c9f44)
  - Core script architecture
  - Facebook API integration
  - Image processing implementation
  - Error handling and rate limiting

## Project Structure

```
fallen-heroes-memorial/
├── complete_fallen_heroes_script.py  # Main script
├── .github/
│   └── workflows/
│       └── daily-memorial.yml        # GitHub Actions workflow
├── README.md                         # This file
├── REFERENCES.md                     # Development references and resources
└── requirements.txt                  # Python dependencies
```

## Rate Limiting & Best Practices

- 3-second delay between Facebook posts
- 1-second delay between Military Times queries
- Comprehensive error handling for network issues
- Respectful scraping with proper User-Agent headers
- Proxy support for restricted environments

## Contributing

This project honors fallen service members. When contributing:

1. Maintain respectful tone in all code and documentation
2. Test thoroughly to ensure posts are accurate and appropriate
3. Follow existing code style and error handling patterns
4. Respect rate limits and website terms of service

## Mission Statement

**"We will never forget their service and sacrifice."**

This project ensures that the ultimate sacrifice made by our service members is remembered and honored daily. Every automated post represents a life lost in service to our country, and we treat this responsibility with the utmost respect and dignity.

## Support

For technical issues or suggestions, please open an GitHub issue. For questions about specific service members or their information, please refer to the [Military Times](https://thefallen.militarytimes.com/) database.

---

*🇺🇸 In memory of all who have made the ultimate sacrifice for our freedom 🇺🇸*