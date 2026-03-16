# audio-collection

A collection of royalty-free background music tracks plus an Instagram DM polling script that automatically downloads newly shared media (images & videos) and uploads them to Google Drive.

---

## Instagram → Google Drive poller

### How it works

`instagram_poller.py` runs a continuous loop that:

1. Fetches all Instagram Direct Message conversations for your account via the [Instagram Graph API](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/direct-messaging).
2. Identifies messages that contain image or video attachments **not yet seen** (state is persisted in `last_seen.json`).
3. Downloads each new media file.
4. Uploads it to a specified Google Drive folder using a service account.

### Prerequisites

| Requirement | Notes |
|---|---|
| Python ≥ 3.10 | Uses modern type-hint syntax |
| Instagram Business or Creator account | Required for the Messaging API |
| Facebook App with `instagram_manage_messages` permission | Generates the access token |
| Google Cloud project with Drive API enabled | Needed for uploads |
| Google service-account JSON key | Must be shared to the target Drive folder |

### Setup

#### 1 – Install Python dependencies

```bash
pip install -r requirements.txt
```

#### 2 – Create the `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|---|---|
| `INSTAGRAM_ACCESS_TOKEN` | Long-lived Instagram access token |
| `INSTAGRAM_USER_ID` | Your IG Business/Creator user ID |
| `POLL_INTERVAL` | Seconds between polls (default `60`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to your service-account `.json` key file |
| `GOOGLE_DRIVE_FOLDER_ID` | ID of the destination Google Drive folder |
| `STATE_FILE` | Path to the state file (default `last_seen.json`) |

#### 3 – Share the Google Drive folder with the service account

Open the target folder in Drive → **Share** → paste the service-account email (found in the JSON key under `client_email`) → grant **Editor** access.

#### 4 – Run the poller

```bash
python instagram_poller.py
```

The script runs indefinitely. Use a process manager such as `systemd`, `supervisor`, or `screen`/`tmux` to keep it alive in the background.

### Obtaining credentials

#### Instagram access token

1. Create a [Meta Developer App](https://developers.facebook.com/apps/).
2. Add the **Instagram Graph API** product.
3. Request the `instagram_manage_messages` permission.
4. Generate a long-lived user access token (valid for 60 days; refresh before expiry).
5. Copy the token and your Instagram User ID into `.env`.

#### Google service-account key

1. In [Google Cloud Console](https://console.cloud.google.com/), navigate to **IAM & Admin → Service Accounts**.
2. Create a new service account, then create and download a JSON key.
3. Enable the **Google Drive API** for your project.
4. Save the JSON key file and set `GOOGLE_SERVICE_ACCOUNT_JSON` in `.env`.

### State file

`last_seen.json` stores the IDs of messages that have already been processed, keyed by conversation ID.  Delete this file to reprocess all existing messages from scratch.
