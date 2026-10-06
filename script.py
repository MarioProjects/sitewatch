"""
SiteWatch: A simple script to monitor webpages for changes and send email notifications.

This script fetches the content of specified URLs, extracts visible text,
compares it with previously saved versions, and sends an email via Resend
if a change is detected. It also emails when a URL keeps failing to load, and
again when it recovers.
"""

import hashlib
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
import resend
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# Configuration from environment variables
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
MONITOR_URLS = [
    url.strip() for url in os.environ.get("MONITOR_URLS", "").split(",") if url.strip()
]
EMAIL_RECIPIENTS = [
    email.strip()
    for email in os.environ.get("EMAIL_RECIPIENTS", "").split(",")
    if email.strip()
]
EMAIL_FROM = os.environ.get("EMAIL_FROM", "Notification <onboarding@resend.dev>")
EMAIL_SUBJECT = os.environ.get("EMAIL_SUBJECT", "Page Updated")
EMAIL_HTML_TEMPLATE = os.environ.get(
    "EMAIL_HTML", "The page has been updated! <br> <a href='{url}'>View page</a>"
)
# Consecutive failed fetches of a URL before an alert email is sent (0 disables)
FAILURE_ALERT_THRESHOLD = int(os.environ.get("FAILURE_ALERT_THRESHOLD") or 15)

# Directory to store webpage versions
SAVE_DIR = Path("webpage_versions")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def get_url_hash(url):
    """
    Returns a short hash for a given URL to use in file paths.

    Args:
        url (str): The URL to hash.

    Returns:
        str: A 10-character MD5 hash of the URL.
    """
    return hashlib.md5(url.encode()).hexdigest()[:10]


def get_page_content(url):
    """
    Fetches the HTML content of a URL.

    Args:
        url (str): The URL to fetch.

    Returns:
        str: The HTML content.

    Raises:
        requests.RequestException: If the page could not be fetched.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def extract_visible_text(html):
    """
    Parses HTML and returns only the visible text content (no scripts/styles).

    Args:
        html (str): The HTML content to parse.

    Returns:
        str | None: Cleaned visible text content, or None if input is empty.
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
    """
    Saves content to a file with a hash of the URL and a timestamp.

    Args:
        url (str): The URL associated with the content.
        content (str): The text content to save.

    Returns:
        str: The path to the saved file.
    """
    url_hash = get_url_hash(url)
    url_dir = SAVE_DIR / url_hash
    url_dir.mkdir(parents=True, exist_ok=True)

    utc_now = datetime.now(timezone.utc)
    timestamp = int(utc_now.timestamp() * 1_000)
    file_path = url_dir / f"{timestamp}.md"

    with file_path.open("w", encoding="utf-8") as f:
        f.write(content)
    return str(file_path)


def load_last_saved_file(url):
    """
    Gets the last saved file for a specific URL.

    Args:
        url (str): The URL to load content for.

    Returns:
        str | None: The content of the last saved file, or None if no file exists.
    """
    url_hash = get_url_hash(url)
    url_dir = SAVE_DIR / url_hash

    if not url_dir.exists():
        return None

    files = sorted([f for f in url_dir.iterdir() if f.is_file()], reverse=True)
    if not files:
        return None

    last_file_path = files[0]

    try:
        with last_file_path.open("r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading last file for {url}: {e}")
        return None


def cleanup_old_files(url, minimum_files=10):
    """
    Removes old files for a specific URL, keeping only the latest N files.

    Args:
        url (str): The URL to clean up files for.
        minimum_files (int): The number of latest files to keep. Defaults to 10.
    """
    url_hash = get_url_hash(url)
    url_dir = SAVE_DIR / url_hash

    if not url_dir.exists():
        return

    files = sorted([f for f in url_dir.iterdir() if f.suffix == ".md"])
    if len(files) <= minimum_files:
        return

    for file_path in files[:-minimum_files]:
        try:
            file_path.unlink()
        except Exception as e:
            logger.error(f"Error deleting old file {file_path.name}: {e}")


def send_email(url, subject, html_content):
    """
    Sends an email about a URL to the configured recipients using Resend.

    Args:
        url (str): The URL the email is about.
        subject (str): The subject of the email.
        html_content (str): The HTML body of the email.

    Returns:
        bool: True if the email was sent, False otherwise.
    """
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set. Skipping notification.")
        return False

    if not EMAIL_RECIPIENTS:
        logger.warning("EMAIL_RECIPIENTS not set. Skipping notification.")
        return False

    try:
        params: resend.Emails.SendParams = {
            "from": EMAIL_FROM,
            "to": EMAIL_RECIPIENTS,
            "subject": subject,
            "html": html_content,
        }
        resend.Emails.send(params)
        logger.info(f"Notification sent for {url}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification for {url}: {e}")
        return False


def notify_change(url):
    """
    Sends an email notification using Resend when a change is detected.

    Args:
        url (str): The URL that has changed.
    """
    send_email(url, EMAIL_SUBJECT, EMAIL_HTML_TEMPLATE.format(url=url))


def get_failure_state_path(url):
    """
    Returns the path of the file that tracks failed fetches of a URL.

    It lives next to the URL's directory, not inside it, so it is never
    mistaken for a saved version of the page.

    Args:
        url (str): The URL to get the path for.

    Returns:
        Path: The path of the failure state file.
    """
    return SAVE_DIR / f"{get_url_hash(url)}.failures.json"


def load_failure_state(url):
    """
    Loads the failure state of a URL.

    Args:
        url (str): The URL to load the state for.

    Returns:
        dict | None: The failure state, or None if the last fetch succeeded.
    """
    state_path = get_failure_state_path(url)
    if not state_path.exists():
        return None

    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Error loading failure state for {url}: {e}")
        return None


def record_failure(url, error):
    """
    Records a failed fetch and emails once the failures reach the threshold.

    The alert is retried on every later failure until it is sent, since the
    cause of the failure may also prevent sending the email.

    Args:
        url (str): The URL that could not be fetched.
        error (Exception): The error raised while fetching it.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = load_failure_state(url) or {"count": 0, "first_failure": now}
    state["count"] += 1
    state["last_error"] = str(error)

    if (
        FAILURE_ALERT_THRESHOLD > 0
        and state["count"] >= FAILURE_ALERT_THRESHOLD
        and not state.get("alerted")
    ):
        logger.warning(f"{url} has failed {state['count']} times in a row.")
        state["alerted"] = send_email(
            url,
            f"SiteWatch cannot load a page: {url}",
            f"SiteWatch has failed to load <a href='{url}'>{url}</a> "
            f"{state['count']} times in a row since {state['first_failure']}, "
            "so changes to it are not being detected.<br><br>"
            f"Last error: {html.escape(state['last_error'])}",
        )

    get_failure_state_path(url).write_text(json.dumps(state), encoding="utf-8")


def clear_failure(url):
    """
    Clears the failure state of a URL after a successful fetch.

    Emails that the URL is back if it had failed enough times to alert.

    Args:
        url (str): The URL that was fetched successfully.
    """
    state = load_failure_state(url)
    state_path = get_failure_state_path(url)
    if state_path.exists():
        state_path.unlink()

    if state and 0 < FAILURE_ALERT_THRESHOLD <= state.get("count", 0):
        logger.info(f"{url} is reachable again after {state['count']} failures.")
        send_email(
            url,
            f"SiteWatch can load a page again: {url}",
            f"SiteWatch can load <a href='{url}'>{url}</a> again. It had failed "
            f"{state['count']} times in a row since {state['first_failure']}, so "
            "changes made in that period were only compared once it was back.",
        )


def monitor_site(url):
    """
    Monitors a single URL for changes.
    Fetches content, compares with last version, and notifies on change.

    Args:
        url (str): The URL to monitor.
    """
    logger.info(f"Checking {url}...")

    previous_content = load_last_saved_file(url)

    try:
        page_html = get_page_content(url)
    except requests.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        record_failure(url, e)
        return
    clear_failure(url)

    current_content = extract_visible_text(page_html)
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
    """
    Entry point for the script.
    Reads MONITOR_URLS from environment and starts monitoring.
    """
    if not MONITOR_URLS:
        logger.error("No URLs to monitor. Please set MONITOR_URLS environment variable.")
        return

    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    for url in MONITOR_URLS:
        try:
            monitor_site(url)
        except Exception as e:
            logger.error(f"Unexpected error monitoring {url}: {e}")


if __name__ == "__main__":
    main()
