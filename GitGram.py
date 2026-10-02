#!/usr/bin/env python3

from logging import basicConfig, getLogger, INFO
from flask import Flask, request, jsonify
from html import escape
from requests import get, post
from os import environ
import config

from telegram.ext import CommandHandler, Updater

server = Flask(__name__)

basicConfig(level=INFO)
log = getLogger()

ENV = bool(environ.get('ENV', False))

if ENV:
    BOT_TOKEN = environ.get('BOT_TOKEN', None)
    PROJECT_NAME = environ.get('PROJECT_NAME', None)
    ip_addr = environ.get('APP_URL', None)
    GIT_REPO_URL = environ.get(
        'GIT_REPO_URL',
        "https://github.com/TheArchon/GitHub-"
    )
else:
    BOT_TOKEN = config.BOT_TOKEN
    PROJECT_NAME = config.PROJECT_NAME
    ip_addr = get('https://api.ipify.org').text
    GIT_REPO_URL = config.GIT_REPO_URL


updater = Updater(token=BOT_TOKEN, workers=1)
dispatcher = updater.dispatcher

print("If you need more help, join @ArchonCare in Telegram.")


def start(_bot, update):
    """/start message for bot"""
    message = update.effective_message
    message.reply_text(
        f"This is the Updates watcher for {PROJECT_NAME}. "
        "I am just notify users about what's happen on their Git repositories "
        "thru webhooks.\n\n"
        "You need to [self-host](https://waa.ai/GitGram) "
        "or see /help to use this bot on your groups.",
        parse_mode="markdown"
    )


def help(_bot, update):
    """/help message for the bot"""
    message = update.effective_message
    message.reply_text(
        f"*Available Commands*\n\n"
        f"`/connect` - Setup how to connect this chat to receive "
        f"Git activity notifications.\n"
        f"`/support` - Get links to get support if you're stuck.\n"
        f"`/source` - Get the Git repository URL.",
        parse_mode="markdown"
    )


def connect(_bot, update):
    """Show GitHub webhook configuration for the current Telegram chat."""
    message = update.effective_message
    chat = update.effective_chat

    if not chat:
        return

    # APP_URL from .env is preferred.
    # If APP_URL is not set, the old public-IP detection is used.
    base_url = (environ.get("APP_URL") or ip_addr or "").rstrip("/")

    webhook_url = f"{base_url}/{chat.id}"

    message.reply_text(
        f"*GitHub Webhook Setup*\n\n"
        f"*Chat ID:*\n`{chat.id}`\n\n"
        f"*Payload URL:*\n`{webhook_url}`\n\n"
        f"*Content type:*\n`application/json`\n\n"
        f"*GitHub setup:*\n"
        f"1. Open your GitHub repository.\n"
        f"2. Go to Settings → Webhooks.\n"
        f"3. Click Add webhook.\n"
        f"4. Paste the Payload URL above.\n"
        f"5. Select `application/json`.\n"
        f"6. Select the events you want, or use Push events.\n"
        f"7. Keep Active enabled.\n"
        f"8. Save the webhook.\n\n"
        f"After that, GitHub events from this repository will be "
        f"sent to this Telegram chat.",
        parse_mode="markdown"
    )


def support(_bot, update):
    """Links to Support"""
    message = update.effective_message
    message.reply_text(
        f"*Getting Support*\n\n"
        f"To get support in using the bot, join "
        f"[the GitGram support](https://t.me/ArchonCare).",
        parse_mode="markdown"
    )


def source(_bot, update):
    """Link to Source"""
    message = update.effective_message
    message.reply_text(
        f"*Source*:\n[GitGram Repo](https://waa.ai/GitGram).",
        parse_mode="markdown"
    )


def getSourceCodeLink(_bot, update):
    """Pulls link to the source code."""
    message = update.effective_message
    message.reply_text(
        f"{GIT_REPO_URL}"
    )


# Telegram command handlers
start_handler = CommandHandler("start", start)
help_handler = CommandHandler("help", help)
connect_handler = CommandHandler("connect", connect)
supportCmd = CommandHandler("support", support)
sourcecode = CommandHandler("source", source)


# Register handlers
dispatcher.add_handler(start_handler)
dispatcher.add_handler(help_handler)
dispatcher.add_handler(connect_handler)
dispatcher.add_handler(supportCmd)
dispatcher.add_handler(sourcecode)


updater.start_polling()


TG_BOT_API = f'https://api.telegram.org/bot{BOT_TOKEN}/'

checkbot = get(TG_BOT_API + "getMe").json()

if not checkbot['ok']:
    log.error("[ERROR] Invalid Token!")
    exit(1)
else:
    username = checkbot['result']['username']
    log.info(
        f"[INFO] Logged in as @{username}, waiting for webhook requests..."
    )


def post_tg(chat, message, parse_mode):
    """Send message to desired group"""
    response = post(
        TG_BOT_API + "sendMessage",
        params={
            "chat_id": chat,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
    ).json()

    return response


def reply_tg(chat, message_id, message, parse_mode):
    """reply to message_id"""
    response = post(
        TG_BOT_API + "sendMessage",
        params={
            "chat_id": chat,
            "reply_to_message_id": message_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
    ).json()

    return response


@server.route("/", methods=['GET'])
def helloWorld():
    # Just send 'Hello, world!' to tell that our server is up.
    return 'Hello, world!'


@server.route("/<groupid>", methods=['GET', 'POST'])
def git_api(groupid):
    """Requests to api.github.com"""

    data = request.json

    if not data:
        return (
            f"<b>Add this url:</b> "
            f"{ip_addr}/{groupid} to webhooks of the project"
        )

    if data.get('hook'):
        repo_url = data['repository']['html_url']
        repo_name = data['repository']['name']
        sender_url = data['sender']['html_url']
        sender_name = data['sender']['login']

        response = post_tg(
            groupid,
            f"🙌 Successfully set webhook for "
            f"<a href='{repo_url}'>{repo_name}</a> "
            f"by <a href='{sender_url}'>{sender_name}</a>!",
            "html"
        )

        return response

    if data.get('commits'):
        commits_text = ""

        rng = len(data['commits'])

        if rng > 10:
            rng = 10

        for x in range(rng):
            commit = data['commits'][x]

            if len(escape(commit['message'])) > 300:
                commit_msg = escape(commit['message']).split("\n")[0]
            else:
                commit_msg = escape(commit['message'])

            commits_text += (
                f"{commit_msg}\n"
                f"<a href='{commit['url']}'>{commit['id'][:7]}</a> - "
                f"{commit['author']['name']} "
                f"{escape('<')}{commit['author']['email']}{escape('>')}\n\n"
            )

            if len(commits_text) > 1000:
                text = (
                    f"✨ <b>{escape(data['repository']['name'])}</b> - "
                    f"New {len(data['commits'])} commits "
                    f"({escape(data['ref'].split('/')[-1])})\n"
                    f"{commits_text}"
                )

                response = post_tg(groupid, text, "html")
                commits_text = ""

        if not commits_text:
            return jsonify({
                "ok": True,
                "text": "Commits text is none"
            })

        text = (
            f"✨ <b>{escape(data['repository']['name'])}</b> - "
            f"New {len(data['commits'])} commits "
            f"({escape(data['ref'].split('/')[-1])})\n"
            f"{commits_text}"
        )

        if len(data['commits']) > 10:
            text += (
                f"\n\n<i>And "
                f"{len(data['commits']) - 10} other commits</i>"
            )

        response = post_tg(groupid, text, "html")

        return response

    if data.get('issue'):
        if data.get('comment'):
            text = (
                f"💬 New comment: "
                f"<b>{escape(data['repository']['name'])}</b>\n"
                f"{escape(data['comment']['body'])}\n\n"
                f"<a href='{data['comment']['html_url']}'>"
                f"Issue #{data['issue']['number']}</a>"
            )

            response = post_tg(groupid, text, "html")
            return response

        text = (
            f"🚨 New {data['action']} issue for "
            f"<b>{escape(data['repository']['name'])}</b>\n"
            f"<b>{escape(data['issue']['title'])}</b>\n"
            f"{escape(data['issue']['body'])}\n\n"
            f"<a href='{data['issue']['html_url']}'>"
            f"issue #{data['issue']['number']}</a>"
        )

        response = post_tg(groupid, text, "html")
        return response

    if data.get('pull_request'):
        if data.get('comment'):
            text = (
                f"❗ There is a new pull request for "
                f"<b>{escape(data['repository']['name'])}</b> "
                f"({data['pull_request']['state']})\n"
                f"{escape(data['comment']['body'])}\n\n"
                f"<a href='{data['comment']['html_url']}'>"
                f"Pull request #{data['issue']['number']}</a>"
            )

            response = post_tg(groupid, text, "html")
            return response

        text = (
            f"❗ New {data['action']} pull request for "
            f"<b>{escape(data['repository']['name'])}</b>\n"
            f"<b>{escape(data['pull_request']['title'])}</b> "
            f"({data['pull_request']['state']})\n"
            f"{escape(data['pull_request']['body'])}\n\n"
            f"<a href='{data['repository']['html_url']}'>"
            f"Pull request #{data['pull_request']['number']}</a>"
        )

        response = post_tg(groupid, text, "html")
        return response

    if data.get('forkee'):
        response = post_tg(
            groupid,
            f"🍴 <a href='{data['sender']['html_url']}'>"
            f"{data['sender']['login']}</a> forked "
            f"<a href='{data['repository']['html_url']}'>"
            f"{data['repository']['name']}</a>!\n"
            f"Total forks now are "
            f"{data['repository']['forks_count']}",
            "html"
        )

        return response

    if data.get('action'):

        if data.get('action') == "published" and data.get('release'):
            text = (
                f"<a href='{data['sender']['html_url']}'>"
                f"{data['sender']['login']}</a> "
                f"{data['action']} "
                f"<a href='{data['repository']['html_url']}'>"
                f"{data['repository']['name']}</a>!"
            )

            text += (
                f"\n\n<b>{data['release']['name']}</b> "
                f"({data['release']['tag_name']})\n"
                f"{data['release']['body']}\n\n"
                f"<a href='{data['release']['tarball_url']}'>"
                f"Download tar</a> | "
                f"<a href='{data['release']['zipball_url']}'>"
                f"Download zip</a>"
            )

            response = post_tg(groupid, text, "html")
            return response

        if data.get('action') == "started":
            text = (
                f"🌟 <a href='{data['sender']['html_url']}'>"
                f"{data['sender']['login']}</a> gave a star to "
                f"<a href='{data['repository']['html_url']}'>"
                f"{data['repository']['name']}</a>!\n"
                f"Total stars are now "
                f"{data['repository']['stargazers_count']}"
            )

            response = post_tg(groupid, text, "html")
            return response

        if data.get('action') == "edited" and data.get('release'):
            text = (
                f"<a href='{data['sender']['html_url']}'>"
                f"{data['sender']['login']}</a> "
                f"{data['action']} "
                f"<a href='{data['repository']['html_url']}'>"
                f"{data['repository']['name']}</a>!"
            )

            text += (
                f"\n\n<b>{data['release']['name']}</b> "
                f"({data['release']['tag_name']})\n"
                f"{data['release']['body']}\n\n"
                f"<a href='{data['release']['tarball_url']}'>"
                f"Download tar</a> | "
                f"<a href='{data['release']['zipball_url']}'>"
                f"Download zip</a>"
            )

            response = post_tg(groupid, text, "html")
            return response

        if data.get('action') == "created":
            return jsonify({
                "ok": True,
                "text": "Pass trigger for created"
            })

        response = post_tg(
            groupid,
            f"<a href='{data['sender']['html_url']}'>"
            f"{data['sender']['login']}</a> "
            f"{data['action']} "
            f"<a href='{data['repository']['html_url']}'>"
            f"{data['repository']['name']}</a>!",
            "html"
        )

        return response

    if data.get('ref_type'):
        response = post_tg(
            groupid,
            f"A new {data['ref_type']} on "
            f"<a href='{data['repository']['html_url']}'>"
            f"{data['repository']['name']}</a> was created by "
            f"<a href='{data['sender']['html_url']}'>"
            f"{data['sender']['login']}</a>!",
            "html"
        )

        return response

    if data.get('created'):
        response = post_tg(
            groupid,
            f"Branch {data['ref'].split('/')[-1]} "
            f"<b>{data['ref'].split('/')[-2]}</b> on "
            f"<a href='{data['repository']['html_url']}'>"
            f"{data['repository']['name']}</a> was created by "
            f"<a href='{data['sender']['html_url']}'>"
            f"{data['sender']['login']}</a>!",
            "html"
        )

        return response

    if data.get('deleted'):
        response = post_tg(
            groupid,
            f"Branch {data['ref'].split('/')[-1]} "
            f"<b>{data['ref'].split('/')[-2]}</b> on "
            f"<a href='{data['repository']['html_url']}'>"
            f"{data['repository']['name']}</a> was deleted by "
            f"<a href='{data['sender']['html_url']}'>"
            f"{data['sender']['login']}</a>!",
            "html"
        )

        return response

    if data.get('forced'):
        response = post_tg(
            groupid,
            f"Branch {data['ref'].split('/')[-1]} "
            f"<b>{data['ref'].split('/')[-2]}</b>"
            f" on <a href='{data['repository']['html_url']}'>"
            f"{data['repository']['name']}</a> was"
            f" forced by <a href='{data['sender']['html_url']}'>"
            f"{data['sender']['login']}</a>!",
            "html"
        )

        return response

    if data.get('pages'):
        text = (
            f"<a href='{data['repository']['html_url']}'>"
            f"{data['repository']['name']}</a> wiki pages were updated by "
            f"<a href='{data['sender']['html_url']}'>"
            f"{data['sender']['login']}</a>!\n\n"
        )

        for x in data['pages']:
            summary = ""

            if x['summary']:
                summary = f"{x['summary']}\n"

            text += (
                f"📝 <b>{escape(x['title'])}</b> "
                f"({x['action']})\n"
                f"{summary}"
                f"<a href='{x['html_url']}'>{x['page_name']}</a> - "
                f"{x['sha'][:7]}"
            )

            if len(data['pages']) >= 2:
                text += "\n=====================\n"

            response = post_tg(groupid, text, "html")

        return response

    if data.get('context'):
        if data.get('state') == "pending":
            emo = "⏳"
        elif data.get('state') == "success":
            emo = "✔️"
        elif data.get('state') == "failure":
            emo = "❌"
        else:
            emo = "🌀"

        text = (
            f"{emo} <a href='{data['target_url']}'>"
            f"{data['description']}</a>"
            f" on <a href='{data['repository']['html_url']}'>"
            f"{data['repository']['name']}</a>"
            f" by <a href='{data['sender']['html_url']}'>"
            f"{data['sender']['login']}</a>!"
            f"\nLatest commit:\n"
            f"<a href='{data['commit']['commit']['url']}'>"
            f"{escape(data['commit']['commit']['message'])}</a>"
        )

        response = post_tg(groupid, text, "html")
        return response

    # Original DelDog debugging system
    url = deldog(data)

    response = post_tg(
        groupid,
        "🚫 Webhook endpoint for this chat has received something "
        "that doesn't understood yet. "
        f"\n\nLink to logs for debugging: {url}",
        "markdown"
    )

    return response


def deldog(data):
    """Pasing the stings to del.dog"""
    BASE_URL = 'https://del.dog'

    r = post(
        f'{BASE_URL}/documents',
        data=str(data).encode('utf-8')
    )

    if r.status_code == 404:
        r.raise_for_status()

    res = r.json()

    if r.status_code != 200:
        r.raise_for_status()

    key = res['key']

    if res['isUrl']:
        reply = (
            f'DelDog URL: {BASE_URL}/{key}\n'
            f'You can view stats, etc. '
            f'[here]({BASE_URL}/v/{key})'
        )
    else:
        reply = f'{BASE_URL}/{key}'

    return reply


if __name__ == "__main__":
    # We can't use port 80 due to the root access requirement.
    port = int(environ.get("PORT", 8080))
    server.run(host="0.0.0.0", port=port)
