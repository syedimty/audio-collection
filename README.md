# audio-collection

A collection of royalty-free background music tracks plus an Instagram DM polling script that automatically downloads newly shared media (images & videos) and uploads them to Google Drive.

## About this project

This repository has two purposes:

1. **Royalty-free music library** – 25 background music tracks (MP3) that are free to use in videos, presentations, and other projects.
2. **Instagram → Google Drive automation** – a Python script (`instagram_poller.py`) that watches an Instagram Business/Creator account's Direct Messages, detects newly shared images and videos, and automatically uploads them to a designated Google Drive folder.

The automation runs as a scheduled GitHub Actions workflow (every 30 minutes) so no always-on server is required.  All credentials are stored as GitHub repository secrets — nothing sensitive is ever committed to the repository.

---

## Instagram → Google Drive poller

### How it works

`instagram_poller.py` polls Instagram Direct Message conversations for new media:

1. Fetches all Instagram Direct Message conversations for your account via the [Instagram Graph API](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/direct-messaging).
2. Identifies messages that contain image or video attachments **not yet seen** (state is persisted in `last_seen.json`).
3. Downloads each new media file.
4. Uploads it to a specified Google Drive folder using a service account.

The script supports two run modes:
- **Continuous loop** (default) – runs indefinitely, sleeping `POLL_INTERVAL` seconds between polls.  Suitable for always-on servers.
- **Single poll** (`RUN_ONCE=true`) – performs one poll and exits.  Used by the GitHub Actions cron job.

---

### GitHub Actions cron job (every 30 minutes)

The repository ships a pre-configured workflow at `.github/workflows/poll_instagram.yml` that runs the poller automatically every 30 minutes.

#### Required repository secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Description |
|---|---|
| `INSTAGRAM_ACCESS_TOKEN` | Long-lived Instagram access token |
| `INSTAGRAM_USER_ID` | Your Instagram Business/Creator user ID |
| `GOOGLE_DRIVE_FOLDER_ID` | ID of the destination Google Drive folder |
| `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT` | Full contents of the service-account JSON key file (paste the raw JSON text) |

Once the secrets are in place the workflow will fire on its own schedule and can also be triggered manually from the **Actions** tab.

> **State persistence** – The workflow caches `last_seen.json` between runs using [actions/cache](https://github.com/actions/cache) so already-processed messages are never re-downloaded.

---

### Local / self-hosted setup

#### Prerequisites

| Requirement | Notes |
|---|---|
| Python ≥ 3.10 | Uses modern type-hint syntax |
| Instagram Business or Creator account | Required for the Messaging API |
| Facebook App with `instagram_manage_messages` permission | Generates the access token |
| Google Cloud project with Drive API enabled | Needed for uploads |
| Google service-account JSON key | Must be shared to the target Drive folder |

#### 1 – Install Python dependencies

```bash
pip install -r requirements.txt
```

#### 2 – Create the `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `INSTAGRAM_ACCESS_TOKEN` | ✅ | Long-lived Instagram access token |
| `INSTAGRAM_USER_ID` | ✅ | Your IG Business/Creator user ID |
| `GOOGLE_DRIVE_FOLDER_ID` | ✅ | ID of the destination Google Drive folder |
| `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT` | ✅ (CI/CD) | Raw JSON content of the service-account key (recommended for CI/CD) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ✅ (local) | Path to the service-account `.json` key file (used when `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT` is not set) |
| `POLL_INTERVAL` | – | Seconds between polls in continuous mode (default `60`) |
| `STATE_FILE` | – | Path to the state file (default `last_seen.json`) |
| `RUN_ONCE` | – | Set to `true` to run a single poll and exit (default `false`) |

#### 3 – Share the Google Drive folder with the service account

Open the target folder in Drive → **Share** → paste the service-account email (found in the JSON key under `client_email`) → grant **Editor** access.

#### 4 – Run the poller

```bash
python instagram_poller.py
```

The script runs indefinitely by default. Use a process manager such as `systemd`, `supervisor`, or `screen`/`tmux` to keep it alive in the background.

To run a single poll and exit (e.g. from your own cron):

```bash
RUN_ONCE=true python instagram_poller.py
```

---

### Obtaining credentials

#### Instagram access token

1. Create a [Meta Developer App](https://developers.facebook.com/apps/).
2. Add the **Instagram Graph API** product.
3. Request the `instagram_manage_messages` permission.
4. Generate a long-lived user access token (valid for 60 days; refresh before expiry).
5. Copy the token and your Instagram User ID into `.env` (or GitHub secrets).

#### Google service-account key

1. In [Google Cloud Console](https://console.cloud.google.com/), navigate to **IAM & Admin → Service Accounts**.
2. Create a new service account, then create and download a JSON key.
3. Enable the **Google Drive API** for your project.
4. For **GitHub Actions**: copy the full JSON text into the `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT` secret.
5. For **local development**: save the JSON key file and set `GOOGLE_SERVICE_ACCOUNT_JSON` to its path in `.env`.

---

### State file

`last_seen.json` stores the IDs of messages that have already been processed, keyed by conversation ID.  Delete this file to reprocess all existing messages from scratch.
