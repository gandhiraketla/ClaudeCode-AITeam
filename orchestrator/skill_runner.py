import json
import os
import re
from pathlib import Path
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from .models import SkillContext
from . import console

load_dotenv()

SKILLS_DIR = Path(__file__).parent.parent / ".claude" / "skills"
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def load_skill_prompt(skill_name: str) -> str:
    skill_file = SKILLS_DIR / f"{skill_name}.md"
    if not skill_file.exists():
        raise FileNotFoundError(f"Skill not found: {skill_file}")
    return skill_file.read_text(encoding="utf-8")


def extract_json(raw: str) -> str:
    """Extract JSON from raw response — handles markdown fences and extra text."""
    raw = raw.strip()

    # Strip markdown fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first line (```json or ```) and last line (```)
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        raw = "\n".join(inner).strip()

    # If still not starting with {, find the first {
    if not raw.startswith("{"):
        idx = raw.find("{")
        if idx != -1:
            raw = raw[idx:]

    # Find the matching closing brace
    depth = 0
    end = -1
    in_string = False
    escape = False
    for i, ch in enumerate(raw):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end != -1:
        raw = raw[:end + 1]

    return raw


async def run_skill(skill_name: str, context: SkillContext) -> dict:
    system_prompt = load_skill_prompt(skill_name)
    context_json = context.model_dump_json(indent=2)

    user_message = f"""You are being invoked as the {skill_name} skill in the ClaudeForge pipeline.

Here is your full context:
```json
{context_json}
```

Follow your skill instructions exactly. Respond ONLY with a valid JSON object matching the output contract defined in your skill. No markdown fences, no explanation outside the JSON. Keep all string values concise to avoid truncation."""

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    stop_reason = response.stop_reason

    if stop_reason == "max_tokens":
        console.error(skill_name, "Response truncated at max_tokens — JSON may be incomplete")

    try:
        cleaned = extract_json(raw)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        console.error(skill_name, f"JSON parse error: {e}\nRaw (first 500): {raw[:500]}")
        raise ValueError(f"Skill {skill_name} returned invalid JSON: {e}")
