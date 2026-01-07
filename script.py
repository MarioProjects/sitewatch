import os
import requests
import hashlib
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from dotenv import load_dotenv
from loguru import logger
import resend

# Load environment variables
load_dotenv()

# Configuration from environment variables
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
MONITOR_URLS = [url.strip() for url in os.environ.get("MONITOR_URLS", "").split(",") if url.strip()]
EMAIL_RECIPIENTS = [email.strip() for email in os.environ.get("EMAIL_RECIPIENTS", "").split(",") if email.strip()]
EMAIL_FROM = os.environ.get("EMAIL_FROM", "Notification <onboarding@resend.dev>")
EMAIL_SUBJECT = os.environ.get("EMAIL_SUBJECT", "Page Updated")
EMAIL_HTML_TEMPLATE = os.environ.get("EMAIL_HTML", "The page has been updated! <br> <a href='{url}'>View page</a>")

# Directory to store webpage versions
SAVE_DIR = "webpage_versions"

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

def get_url_hash(url):
    """Returns a short hash for a given URL to use in file paths."""
    return hashlib.md5(url.encode()).hexdigest()[:10]

def get_page_content(url):
    """Fetches the HTML content of a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def extract_visible_text(html):
    """
    Parses HTML and returns only the visible text content (no scripts/styles).
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    # Get text and clean up whitespace
    visible_text = soup.get_text(separator="\n")
    lines = [line.strip() for line in visible_text.splitlines()]
    clean_text = "\n".join(line for line in lines if line)

    return clean_text

def save_content(url, content):
    """Saves content to a file with a hash of the URL and a timestamp."""
    url_hash = get_url_hash(url)
    url_dir = os.path.join(SAVE_DIR, url_hash)
    os.makedirs(url_dir, exist_ok=True)
    
    utc_now = datetime.now(timezone.utc)
    timestamp = int(utc_now.timestamp() * 1_000)
    file_path = os.path.join(url_dir, f"{timestamp}.md")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path

def load_last_saved_file(url):
    """Gets the last saved file for a specific URL."""
    url_hash = get_url_hash(url)
    url_dir = os.path.join(SAVE_DIR, url_hash)
    
    if not os.path.exists(url_dir):
        return None
        
    files = os.listdir(url_dir)
    if not files:
        return None
    
    files.sort(reverse=True)
    last_file_path = os.path.join(url_dir, files[0])
    
    try:
        with open(last_file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading last file for {url}: {e}")
        return None

def cleanup_old_files(url, minimum_files=10):
    """Removes old files for a specific URL, keeping only the latest N files."""
    url_hash = get_url_hash(url)
    url_dir = os.path.join(SAVE_DIR, url_hash)
    
    if not os.path.exists(url_dir):
        return
        
    files = [f for f in os.listdir(url_dir) if f.endswith('.md')]
    if len(files) <= minimum_files:
        return
    
    files.sort()
    for file in files[:-minimum_files]:
        try:
            os.remove(os.path.join(url_dir, file))
        except Exception as e:
            logger.error(f"Error deleting old file {file}: {e}")

def notify_change(url):
    """Sends an email notification using Resend."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set. Skipping notification.")
        return

    if not EMAIL_RECIPIENTS:
        logger.warning("EMAIL_RECIPIENTS not set. Skipping notification.")
        return

    try:
        html_content = EMAIL_HTML_TEMPLATE.format(url=url)
        params: resend.Emails.SendParams = {
            "from": EMAIL_FROM,
            "to": EMAIL_RECIPIENTS,
            "subject": EMAIL_SUBJECT,
            "html": html_content,
        }
        resend.Emails.send(params)
        logger.info(f"Notification sent for {url}")
    except Exception as e:
        logger.error(f"Failed to send notification for {url}: {e}")

def monitor_site(url):
    """Monitors a single URL for changes."""
    logger.info(f"Checking {url}...")
    
    previous_content = load_last_saved_file(url)
    
    html = get_page_content(url)
    if html is None:
        return

    current_content = extract_visible_text(html)
    if current_content is None:
        return

    # If it's the first time we see this URL, just save it and return
    if previous_content is None:
        logger.info(f"First time monitoring {url}. Saving initial content.")
        save_content(url, current_content)
        return

    if current_content != previous_content:
        logger.info(f"Change detected for {url}!")
        save_content(url, current_content)
        notify_change(url)
    else:
        logger.info(f"No changes for {url}.")

    cleanup_old_files(url, 10)

def main():
    if not MONITOR_URLS:
        logger.error("No URLs to monitor. Please set MONITOR_URLS environment variable.")
        return

    os.makedirs(SAVE_DIR, exist_ok=True)
    
    for url in MONITOR_URLS:
        try:
            monitor_site(url)
        except Exception as e:
            logger.error(f"Unexpected error monitoring {url}: {e}")

if __name__ == "__main__":
    main()
