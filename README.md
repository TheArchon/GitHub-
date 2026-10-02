# GitGram — modernized GitHub → Telegram notifications

GitGram receives GitHub webhooks and sends repository activity to a Telegram chat.

## What changed

This fork is modernized for **Python 3.10+** and current 2026-era libraries:

- Flask 3.1.3
- Requests 2.34.2
- python-telegram-bot 22.8
- Modern async Telegram command handlers
- Request timeouts and error handling
- GitHub `X-Hub-Signature-256` verification when `GITHUB_WEBHOOK_SECRET` is configured
- Safer HTML escaping for GitHub-controlled content
- Correct pull-request comment links
- Correct forced branch message formatting
- No third-party paste service for unknown webhook payloads
- Telegram's 4096-character message limit is handled
- Environment variables are supported for deployment

## Install

Python **3.10 or newer** is required.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configure

The existing `config.py` format is still supported:

```python
BOT_TOKEN = "your-token"
PROJECT_NAME = "GitGram"
GIT_REPO_URL = "https://github.com/your-user/GitGram"
```

For production, environment variables are preferred. See `.env.example`.

> If a real bot token has ever been committed to GitHub or shared publicly, rotate it with BotFather even if you believe it is expired.

## Run

```bash
python GitGram.py
```

The HTTP server listens on `PORT` (default `8080`). Telegram commands are handled by polling in a background thread.

## GitHub webhook

For a chat/group ID such as `-1001234567890`, configure the webhook URL as:

```text
https://your-domain.example/-1001234567890
```

Use `application/json` as the content type.

Recommended events include:

- Pushes
- Issues
- Issue comments
- Pull requests
- Pull request reviews/comments
- Releases
- Create/delete
- Forks
- Wiki pages

The handler also supports generic `action` events where possible.

### Webhook security

Set a GitHub webhook secret and configure the same value in:

```text
GITHUB_WEBHOOK_SECRET=your-secret
```

When configured, GitGram validates `X-Hub-Signature-256` before processing a webhook.

## Commands

- `/start`
- `/help`
- `/support`
- `/source`

## Important note about the original token

This modernization intentionally preserves the existing `config.py` token because the requested token was described as expired. It is **not recommended** for a live deployment. Replace it with a fresh token before using the bot.
