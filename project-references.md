# Development References and Resources

## Claude AI Development Sessions

### Core Script Development
  - Initial script architecture and Facebook API integration
  - Military Times scraping implementation
  - Image processing and optimization for Facebook
  - Error handling and rate limiting
  - Search mode implementations (daily, comprehensive, recent)
  - Caption formatting and respectful presentation
  - Environment variable configuration

## Technical Resources

### Facebook API Documentation
- [Facebook Graph API - Pages](https://developers.facebook.com/docs/graph-api/reference/page/)
- [Facebook Graph API - Photo Publishing](https://developers.facebook.com/docs/graph-api/reference/page/photos/)
- [Facebook App Development](https://developers.facebook.com/apps/)

### Data Sources
- [Military Times - The Fallen Database](https://thefallen.militarytimes.com/)
- [Military Times Search API](https://thefallen.militarytimes.com/search)

### Python Libraries
- [Requests Documentation](https://docs.python-requests.org/)
- [Beautiful Soup Documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Pillow (PIL) Documentation](https://pillow.readthedocs.io/)

### GitHub Actions
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Scheduling Workflows](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule)
- [Using Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)

## Implementation Notes

### Key Development Decisions
1. **Image Processing**: Implemented square format (1080x1080) to prevent Facebook stretching
2. **Search Strategy**: Multi-year search on current date for maximum coverage
3. **Rate Limiting**: 3-second delays between posts, 1-second between queries
4. **Error Handling**: Comprehensive try-catch blocks with detailed logging
5. **Respectful Scraping**: Proper User-Agent headers and delay implementation

### Future Enhancement Ideas
- [ ] Add support for multiple social media platforms (Twitter, Instagram)
- [ ] Implement database storage for tracking posted heroes
- [ ] Add email notifications for daily posting summaries
- [ ] Create web dashboard for monitoring posting status
- [ ] Add support for memorial day special posts
- [ ] Implement photo enhancement/restoration features

## Deployment Configuration

### GitHub Actions Workflow
```yaml
# Suggested workflow file: .github/workflows/daily-memorial.yml
name: Daily Fallen Heroes Memorial
on:
  schedule:
    - cron: '0 12 * * *'  # Run daily at 12:00 PM UTC
  workflow_dispatch:      # Allow manual triggering

jobs:
  post-memorial:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        pip install requests beautifulsoup4 pillow
    - name: Run memorial script
      env:
        FB_ACCESS_TOKEN: ${{ secrets.FB_ACCESS_TOKEN }}
        FB_PAGE_ID: ${{ secrets.FB_PAGE_ID }}
        SEARCH_MODE: daily
      run: python complete_fallen_heroes_script.py
```

### Environment Variables Setup
1. Go to GitHub repository Settings → Secrets and variables → Actions
2. Add the following secrets:
   - `FB_ACCESS_TOKEN`: Your Facebook Page access token
   - `FB_PAGE_ID`: Your Facebook Page ID (numeric)

## Testing and Validation

### Pre-deployment Checklist
- [ ] Test Facebook API credentials locally
- [ ] Verify Military Times scraping works
- [ ] Test image processing with sample photos
- [ ] Validate caption formatting
- [ ] Test rate limiting and error handling
- [ ] Verify GitHub Actions workflow syntax

### Monitoring
- Check GitHub Actions logs for daily execution status
- Monitor Facebook page for successful posts
- Watch for any API rate limiting or blocking issues

## Legal and Ethical Considerations

- **Data Usage**: Public information from Military Times database
- **Image Rights**: Using publicly available memorial photos for honoring purposes
- **Respectful Automation**: Ensuring automated posts maintain dignity and respect
- **Terms of Service**: Compliance with Facebook and Military Times terms

## Contact and Support

For technical questions about this implementation, refer to the development session linked above or create GitHub issues for tracking.

---

*Last Updated: June 12, 2025*