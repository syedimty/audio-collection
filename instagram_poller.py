#!/usr/bin/env python3
"""
instagram_poller.py

Polls Instagram Direct Messages for new media (images/videos) shared as posts,
downloads each attachment, and uploads it to a Google Drive folder.

Setup:
1. Copy .env.example to .env and fill in your credentials.
2. Install dependencies:  pip install -r requirements.txt
3. Run:  python instagram_poller.py
"""

import io
import json
import logging
import mimetypes
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

INSTAGRAM_ACCESS_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
INSTAGRAM_USER_ID = os.environ["INSTAGRAM_USER_ID"]
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json"
)
GOOGLE_DRIVE_FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]
STATE_FILE = os.getenv("STATE_FILE", "last_seen.json")

INSTAGRAM_GRAPH_BASE = "https://graph.instagram.com/v19.0"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State helpers (track which messages have already been processed)
# ---------------------------------------------------------------------------


def load_state(path: str) -> dict:
    """Load persisted state from *path*, returning an empty dict on first run."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def save_state(path: str, state: dict) -> None:
    """Persist *state* to *path* atomically."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Instagram Graph API helpers
# ---------------------------------------------------------------------------


def _graph_get(path: str, params: dict | None = None) -> dict:
    """Perform a GET request against the Instagram Graph API."""
    url = f"{INSTAGRAM_GRAPH_BASE}/{path.lstrip('/')}"
    p = {"access_token": INSTAGRAM_ACCESS_TOKEN}
    if params:
        p.update(params)
    response = requests.get(url, params=p, timeout=30)
    response.raise_for_status()
    return response.json()


def get_conversations() -> list[dict]:
    """Return all Instagram DM conversations for the authenticated user."""
    data = _graph_get(
        f"{INSTAGRAM_USER_ID}/conversations",
        {"platform": "instagram", "fields": "id,updated_time"},
    )
    return data.get("data", [])


def get_messages(conversation_id: str) -> list[dict]:
    """Return messages in *conversation_id*, newest first."""
    data = _graph_get(
        f"{conversation_id}/messages",
        {"fields": "id,created_time,from,attachments"},
    )
    return data.get("data", [])


def get_attachment_urls(message_id: str) -> list[dict]:
    """
    Return a list of attachment info dicts for *message_id*.

    Each dict has at minimum the keys ``name`` and ``file_url``.
    Instagram also returns ``mime_type`` and ``size`` when available.
    """
    data = _graph_get(
        message_id,
        {"fields": "attachments"},
    )
    nodes = data.get("attachments", {}).get("data", [])
    results = []
    for node in nodes:
        image_data = node.get("image_data") or {}
        video_data = node.get("video_data") or {}
        url = image_data.get("url") or video_data.get("url") or node.get("file_url")
        if url:
            results.append(
                {
                    "name": node.get("name", f"{message_id}_attachment"),
                    "url": url,
                    "mime_type": image_data.get("mime_type")
                    or video_data.get("mime_type")
                    or node.get("mime_type"),
                }
            )
    return results


def download_media(url: str) -> bytes:
    """Download media bytes from *url* using the access token."""
    response = requests.get(
        url,
        params={"access_token": INSTAGRAM_ACCESS_TOKEN},
        timeout=120,
    )
    response.raise_for_status()
    return response.content


# ---------------------------------------------------------------------------
# Google Drive helpers
# ---------------------------------------------------------------------------


def build_drive_service():
    """Build and return an authorised Google Drive API service."""
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_JSON,
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def upload_to_drive(
    service,
    filename: str,
    data: bytes,
    mime_type: str | None,
    folder_id: str,
) -> str:
    """
    Upload *data* as *filename* into the Drive *folder_id*.

    Returns the newly created file's Drive ID.
    """
    if not mime_type:
        mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)
    try:
        file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        return file.get("id", "")
    except HttpError as exc:
        logger.error("Drive upload failed for '%s': %s", filename, exc)
        raise


# ---------------------------------------------------------------------------
# Core polling loop
# ---------------------------------------------------------------------------


def process_new_messages(state: dict, drive_service) -> dict:
    """
    Check every conversation for unseen media messages, download each
    attachment, and upload it to Google Drive.

    Returns an updated copy of *state*.
    """
    conversations = get_conversations()
    logger.info("Found %d conversation(s).", len(conversations))

    for conv in conversations:
        conv_id = conv["id"]
        seen_ids: set[str] = set(state.get(conv_id, []))

        messages = get_messages(conv_id)
        new_media_count = 0

        for msg in messages:
            msg_id = msg["id"]
            if msg_id in seen_ids:
                continue

            attachments = get_attachment_urls(msg_id)
            for att in attachments:
                url = att["url"]
                name = att["name"]
                mime = att["mime_type"]

                # Only process image and video attachments
                if mime and not (
                    mime.startswith("image/") or mime.startswith("video/")
                ):
                    logger.debug("Skipping non-media attachment '%s' (%s)", name, mime)
                    continue

                try:
                    logger.info("Downloading attachment '%s' from message %s …", name, msg_id)
                    data = download_media(url)
                    drive_id = upload_to_drive(
                        drive_service, name, data, mime, GOOGLE_DRIVE_FOLDER_ID
                    )
                    logger.info(
                        "Uploaded '%s' to Google Drive (file ID: %s).", name, drive_id
                    )
                    new_media_count += 1
                except requests.exceptions.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code in (
                        401,
                        403,
                    ):
                        # Authentication / permission failure – stop the whole run
                        raise
                    logger.error(
                        "HTTP error processing attachment '%s' from message %s: %s",
                        name,
                        msg_id,
                        exc,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to process attachment '%s' from message %s",
                        name,
                        msg_id,
                    )

            seen_ids.add(msg_id)

        state[conv_id] = sorted(seen_ids)
        if new_media_count:
            logger.info(
                "Conversation %s: processed %d new media file(s).",
                conv_id,
                new_media_count,
            )

    return state


def run_poll_loop() -> None:
    """Run the polling loop indefinitely, sleeping *POLL_INTERVAL* seconds between runs."""
    logger.info(
        "Starting Instagram media poller (interval: %ds, Drive folder: %s).",
        POLL_INTERVAL,
        GOOGLE_DRIVE_FOLDER_ID,
    )
    drive_service = build_drive_service()
    state = load_state(STATE_FILE)

    while True:
        try:
            state = process_new_messages(state, drive_service)
            save_state(STATE_FILE, state)
        except requests.exceptions.RequestException as exc:
            logger.error("Network error during polling: %s", exc)
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error during polling")

        logger.info("Sleeping %d seconds …", POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    run_poll_loop()
