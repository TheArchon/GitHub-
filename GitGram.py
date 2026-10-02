#!/usr/bin/env python3
"""GitGram: GitHub webhook notifications for Telegram.

Modernized for Python 3.10+ and python-telegram-bot 22.x.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
from html import escape
from typing import Any

import requests
from flask import Flask, jsonify, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import config


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("gitgram")
server = Flask(__name__)

# Keep the original config.py token support, while allowing environment variables
# for deployments. The bundled token is intentionally left untouched by this port.
BOT_TOKEN = os.getenv("BOT_TOKEN") or config.BOT_TOKEN
PROJECT_NAME = os.getenv("PROJECT_NAME") or config.PROJECT_NAME
GIT_REPO_URL = os.getenv("GIT_REPO_URL") or config.GIT_REPO_URL
APP_URL = os.getenv("APP_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", "8080"))

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "GitGram/2026"})


def tg_request(method: str, **kwargs: Any) -> dict[str, Any]:
    """Call Telegram Bot API with a timeout and useful error logging."""
    try:
        response = HTTP.post(f"{TG_API}/{method}", timeout=15, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            log.error("Telegram API %s failed: %s", method, payload)
        return payload
    except requests.RequestException:
        log.exception("Telegram API request failed: %s", method)
        return {"ok": False, "description": "Telegram API request failed"}


def post_tg(chat: str, message: str, parse_mode: str = "HTML") -> dict[str, Any]:
    # Telegram messages are limited to 4096 characters.
    if len(message) > 4096:
        message = message[:4090] + "..."
    return tg_request(
        "sendMessage",
        params={
            "chat_id": chat,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        },
    )


def verify_github_signature(raw_body: bytes) -> bool:
    """Verify GitHub's X-Hub-Signature-256 when a secret is configured."""
    if not WEBHOOK_SECRET:
        return True
    supplied = request.headers.get("X-Hub-Signature-256", "")
    if not supplied.startswith("sha256="):
        return False
    digest = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(supplied, f"sha256={digest}")


def link(url: str, label: str) -> str:
    return f'<a href="{escape(str(url), quote=True)}">{escape(str(label))}</a>'


def value(obj: dict[str, Any], key: str, default: str = "") -> str:
    val = obj.get(key, default)
    return str(val) if val is not None else default


# ---------------- Telegram commands ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            f"This is the Updates watcher for {PROJECT_NAME}. "
            "It notifies Telegram chats about GitHub repository activity via webhooks.\n\n"
            "Use /help for commands and connect a GitHub webhook to this bot's endpoint.",
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Available Commands\n\n"
            "/connect - Show how to connect a GitHub webhook.\n"
            "/support - Get support information.\n"
            "/source - Show the source repository."
        )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Support: https://t.me/GitGramChat"
        )


async def source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(GIT_REPO_URL)


def build_telegram_application() -> Application:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("source", source))
    return application


def run_bot_polling() -> None:
    """Run PTB polling in a background thread so Flask can serve webhooks."""
    try:
        application = build_telegram_application()
        application.run_polling(drop_pending_updates=True, stop_signals=None)
    except Exception:
        log.exception("Telegram polling stopped")


# ---------------- GitHub webhook formatting ----------------
def repository_info(data: dict[str, Any]) -> tuple[str, str]:
    repo = data.get("repository") or {}
    return value(repo, "name", "repository"), value(repo, "html_url")


def sender_info(data: dict[str, Any]) -> tuple[str, str]:
    sender = data.get("sender") or {}
    return value(sender, "login", "unknown"), value(sender, "html_url")


def format_event(data: dict[str, Any], event: str) -> str | None:
    repo, repo_url = repository_info(data)
    sender, sender_url = sender_info(data)
    repo_link = link(repo_url, repo)
    sender_link = link(sender_url, sender)

    if event == "ping" or data.get("hook"):
        return f"🙌 Webhook connected for {repo_link} by {sender_link}!"

    if event == "push" or data.get("commits"):
        commits = data.get("commits") or []
        shown = commits[:10]
        lines = []
        for commit in shown:
            msg = escape(value(commit, "message").splitlines()[0][:300])
            commit_url = value(commit, "url")
            sha = value(commit, "id")[:7]
            author = commit.get("author") or {}
            author_name = escape(value(author, "name", "unknown"))
            lines.append(f"{msg}\n{link(commit_url, sha)} — {author_name}")
        ref = value(data, "ref").split("/")[-1]
        extra = f"\n\n<i>And {len(commits) - 10} other commits</i>" if len(commits) > 10 else ""
        return f"✨ <b>{escape(repo)}</b> — {len(commits)} new commit(s) ({escape(ref)})\n\n" + "\n\n".join(lines) + extra

    issue = data.get("issue")
    if issue:
        action = escape(value(data, "action", "updated"))
        if data.get("comment"):
            comment = data["comment"]
            return (
                f"💬 New comment on <b>{escape(repo)}</b>\n"
                f"{escape(value(comment, 'body'))}\n\n"
                f"{link(value(issue, 'html_url'), 'Issue #' + value(issue, 'number'))}"
            )
        return (
            f"🚨 {action.title()} issue in <b>{escape(repo)}</b>\n"
            f"<b>{escape(value(issue, 'title'))}</b>\n"
            f"{escape(value(issue, 'body'))}\n\n"
            f"{link(value(issue, 'html_url'), 'Issue #' + value(issue, 'number'))}"
        )

    pull = data.get("pull_request")
    if pull:
        action = escape(value(data, "action", "updated"))
        if data.get("comment"):
            comment = data["comment"]
            return (
                f"💬 New pull-request comment in <b>{escape(repo)}</b>\n"
                f"{escape(value(comment, 'body'))}\n\n"
                f"{link(value(pull, 'html_url'), 'Pull request #' + value(pull, 'number'))}"
            )
        return (
            f"❗ {action.title()} pull request in <b>{escape(repo)}</b> "
            f"({escape(value(pull, 'state'))})\n"
            f"<b>{escape(value(pull, 'title'))}</b>\n"
            f"{escape(value(pull, 'body'))}\n\n"
            f"{link(value(pull, 'html_url'), 'Pull request #' + value(pull, 'number'))}"
        )

    if event == "fork" or data.get("forkee"):
        forkee = data.get("forkee") or data.get("repository") or {}
        return (
            f"🍴 {sender_link} forked {link(value(forkee, 'html_url'), value(forkee, 'name', repo))}!"
        )

    release = data.get("release")
    if release:
        action = escape(value(data, "action", "updated"))
        body = escape(value(release, "body"))
        downloads = []
        if value(release, "tarball_url"):
            downloads.append(link(value(release, "tarball_url"), "Download tar"))
        if value(release, "zipball_url"):
            downloads.append(link(value(release, "zipball_url"), "Download zip"))
        suffix = " | ".join(downloads)
        return (
            f"📦 {sender_link} {action} a release for {repo_link}!\n\n"
            f"<b>{escape(value(release, 'name'))}</b> ({escape(value(release, 'tag_name'))})\n"
            f"{body}\n\n{suffix}"
        )

    # Generic repository events (stars, branch/tag events, membership, etc.).
    action = data.get("action")
    if action:
        return f"🔔 {sender_link} {escape(value(data, 'action'))} {repo_link}."

    if data.get("ref_type"):
        return f"🏷️ A new {escape(value(data, 'ref_type'))} was created on {repo_link} by {sender_link}."

    if data.get("created") or data.get("deleted") or data.get("forced"):
        ref = escape(value(data, "ref").split("/")[-1])
        verb = "created" if data.get("created") else "deleted" if data.get("deleted") else "force-updated"
        return f"🌿 Branch/tag <b>{ref}</b> was {verb} on {repo_link} by {sender_link}."

    if data.get("pages"):
        pages = data.get("pages") or []
        lines = [f"📝 {escape(value(p, 'title'))} ({escape(value(p, 'action'))}) — {link(value(p, 'html_url'), value(p, 'page_name'))}" for p in pages]
        return f"📚 Wiki updated on {repo_link} by {sender_link}.\n\n" + "\n".join(lines)

    return None


@server.route("/", methods=["GET"])
def hello_world():
    return jsonify({"ok": True, "service": "GitGram", "status": "running"})


@server.route("/<groupid>", methods=["GET", "POST"])
def git_api(groupid: str):
    if request.method == "GET":
        if not APP_URL:
            return f"Webhook URL: /{escape(groupid)}"
        return f"Webhook URL: {escape(APP_URL)}/{escape(groupid)}"

    raw = request.get_data(cache=True)
    if not verify_github_signature(raw):
        log.warning("Rejected webhook with invalid GitHub signature")
        return jsonify({"ok": False, "error": "invalid signature"}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "JSON body required"}), 400

    event = request.headers.get("X-GitHub-Event", "").lower()
    message = format_event(data, event)
    if message is None:
        # Preserve the original GitGram debugging behavior: unknown webhook
        # payloads are sent to DelDog so the admin can inspect them.
        log_url = deldog(data)
        response = post_tg(
            groupid,
            "🚫 Webhook endpoint received an unsupported event."
            f"\n\nLink to logs for debugging: {log_url}",
            "html",
        )
        return jsonify(response), (200 if response.get("ok") else 502)

    result = post_tg(groupid, message)
    status = 200 if result.get("ok") else 502
    return jsonify(result), status


def deldog(data: dict) -> str:
    """Store an unsupported webhook payload on DelDog for debugging.

    This intentionally preserves GitGram's original third-party debugging
    behavior, but adds a timeout and clear error handling so a DelDog outage
    cannot hang the webhook request indefinitely.
    """
    base_url = "https://del.dog"
    try:
        response = post(
            f"{base_url}/documents",
            data=str(data).encode("utf-8"),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        key = payload.get("key")
        if not key:
            raise ValueError("DelDog response did not contain a document key")
        if payload.get("isUrl"):
            return f"{base_url}/{key}"
        return f"{base_url}/{key}"
    except Exception as exc:
        log.exception("Failed to upload webhook payload to DelDog: %s", exc)
        return "DelDog upload failed; check the server logs for the payload."


def validate_bot_token() -> bool:
    result = tg_request("getMe")
    if not result.get("ok"):
        log.error("Telegram bot token validation failed")
        return False
    log.info("Logged in as @%s", result["result"].get("username", "unknown"))
    return True


if __name__ == "__main__":
    log.info("Starting GitGram on port %s", PORT)
    if not validate_bot_token():
        raise SystemExit(1)

    threading.Thread(target=run_bot_polling, name="telegram-polling", daemon=True).start()
    server.run(host="0.0.0.0", port=PORT, threaded=True)
