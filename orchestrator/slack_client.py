import os
from pathlib import Path
from slack_sdk.web.async_client import AsyncWebClient
from dotenv import load_dotenv

load_dotenv()

PERSONAS = {
    "ba": {
        "username": "Business Analyst",
        "icon_emoji": ":brain:",
    },
    "architect": {
        "username": "Solution Architect",
        "icon_emoji": ":building_construction:",
    },
    "agent-implementer": {
        "username": "Agent Implementer",
        "icon_emoji": ":robot_face:",
    },
    "security": {
        "username": "Security Reviewer",
        "icon_emoji": ":shield:",
    },
    "implementer": {
        "username": "Implementer",
        "icon_emoji": ":computer:",
    },
    "reviewer": {
        "username": "Code Reviewer",
        "icon_emoji": ":mag:",
    },
    "tester": {
        "username": "Tester",
        "icon_emoji": ":test_tube:",
    },
    "devops": {
        "username": "DevOps",
        "icon_emoji": ":rocket:",
    },
}

_client: AsyncWebClient = None


def get_client() -> AsyncWebClient:
    global _client
    if _client is None:
        _client = AsyncWebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    return _client


async def post_message(channel: str, text: str, thread_ts: str,
                       persona: str = "ba") -> str:
    p = PERSONAS.get(persona, PERSONAS["ba"])
    resp = await get_client().chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=text,
        username=p["username"],
        icon_emoji=p["icon_emoji"],
    )
    return resp["ts"]


async def post_thinking(channel: str, thread_ts: str, persona: str = "ba") -> str:
    p = PERSONAS.get(persona, PERSONAS["ba"])
    resp = await get_client().chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text="_thinking..._",
        username=p["username"],
        icon_emoji=p["icon_emoji"],
    )
    return resp["ts"]


async def update_message(channel: str, ts: str, text: str, persona: str = "ba"):
    p = PERSONAS.get(persona, PERSONAS["ba"])
    await get_client().chat_update(
        channel=channel,
        ts=ts,
        text=text,
        username=p["username"],
        icon_emoji=p["icon_emoji"],
    )


async def add_reaction(channel: str, ts: str, reaction: str):
    try:
        await get_client().reactions_add(channel=channel, timestamp=ts, name=reaction)
    except Exception:
        pass


async def remove_reaction(channel: str, ts: str, reaction: str):
    try:
        await get_client().reactions_remove(channel=channel, timestamp=ts, name=reaction)
    except Exception:
        pass


async def upload_file(channel: str, thread_ts: str, file_path: str, title: str):
    path = Path(file_path)
    if not path.exists():
        return
    with open(path, "rb") as f:
        await get_client().files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            file=f,
            filename=path.name,
            title=title,
        )


async def post_approval_request(channel: str, thread_ts: str,
                                 persona: str, summary: str):
    divider = "─" * 40
    text = (
        f"{summary}\n\n"
        f"{divider}\n"
        f"Reply *approved* to continue  |  Reply *changes* + feedback to revise"
    )
    return await post_message(channel, text, thread_ts, persona)
