"""Generate ClaudeForge architecture diagram as PNG."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1400, 1000
BG = "#FFFFFF"

# Colors
C_SLACK     = ("#4A154B", "#F4EBF7")
C_NGROK     = ("#1864AB", "#E7F5FF")
C_FASTAPI   = ("#2B8A3E", "#EBFBEE")
C_STATE     = ("#E67700", "#FFF9DB")
C_SKILL     = ("#862E9C", "#F8F0FC")
C_PERSONAS  = ("#C92A2A", "#FFF5F5")
C_WORKSPACE = ("#1864AB", "#E7F5FF")
C_GIT       = ("#2B8A3E", "#EBFBEE")
C_ARROW     = "#343A40"
C_TEXT      = "#1A1A2E"
C_TITLE     = "#1A1A2E"

img = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

# Try to load a font, fall back to default
try:
    font_title  = ImageFont.truetype("arial.ttf", 28)
    font_head   = ImageFont.truetype("arial.ttf", 18)
    font_body   = ImageFont.truetype("arial.ttf", 14)
    font_small  = ImageFont.truetype("arial.ttf", 12)
except:
    font_title  = ImageFont.load_default()
    font_head   = font_title
    font_body   = font_title
    font_small  = font_title


def box(x, y, w, h, stroke, fill, radius=12):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius,
                            fill=fill, outline=stroke, width=2)


def label(x, y, w, h, lines, font, color=C_TEXT, align="center"):
    line_h = font.size if hasattr(font, 'size') else 14
    total = len(lines) * (line_h + 4)
    start_y = y + (h - total) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        if align == "center":
            tx = x + (w - tw) // 2
        else:
            tx = x + 12
        draw.text((tx, start_y + i * (line_h + 4)), line, fill=color, font=font)


def arrow(x1, y1, x2, y2, label_text=""):
    draw.line([(x1, y1), (x2, y2)], fill=C_ARROW, width=2)
    # Arrowhead
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 10
    p1 = (x2 - size * math.cos(angle - 0.4), y2 - size * math.sin(angle - 0.4))
    p2 = (x2 - size * math.cos(angle + 0.4), y2 - size * math.sin(angle + 0.4))
    draw.polygon([(x2, y2), p1, p2], fill=C_ARROW)
    if label_text:
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2
        bbox = draw.textbbox((0, 0), label_text, font=font_small)
        tw = bbox[2] - bbox[0]
        draw.rectangle([mx - tw//2 - 3, my - 8, mx + tw//2 + 3, my + 8], fill="white")
        draw.text((mx - tw//2, my - 7), label_text, fill="#555", font=font_small)


def dbl_arrow(x1, y1, x2, y2, label_text=""):
    """Double-headed arrow."""
    import math
    draw.line([(x1, y1), (x2, y2)], fill=C_ARROW, width=2)
    for (xa, ya, xb, yb) in [(x1, y1, x2, y2), (x2, y2, x1, y1)]:
        angle = math.atan2(yb - ya, xb - xa)
        size = 10
        p1 = (xb - size * math.cos(angle - 0.4), yb - size * math.sin(angle - 0.4))
        p2 = (xb - size * math.cos(angle + 0.4), yb - size * math.sin(angle + 0.4))
        draw.polygon([(xb, yb), p1, p2], fill=C_ARROW)
    if label_text:
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2
        bbox = draw.textbbox((0, 0), label_text, font=font_small)
        tw = bbox[2] - bbox[0]
        draw.rectangle([mx - tw//2 - 3, my - 8, mx + tw//2 + 3, my + 8], fill="white")
        draw.text((mx - tw//2, my - 7), label_text, fill="#555", font=font_small)


# ── Title ──────────────────────────────────────────────────────────────────
title = "ClaudeForge  —  System Architecture"
bbox = draw.textbbox((0, 0), title, font=font_title)
tw = bbox[2] - bbox[0]
draw.text(((W - tw) // 2, 22), title, fill=C_TITLE, font=font_title)

# ── Row 1: Slack  ←→  ngrok  ←→  FastAPI ─────────────────────────────────
# Slack
box(60, 80, 160, 90, *C_SLACK)
label(60, 80, 160, 90, ["Slack", "#channel"], font_head, C_SLACK[0])

# ngrok
box(300, 80, 160, 90, *C_NGROK)
label(300, 80, 160, 90, ["ngrok tunnel", "HTTPS → :8000"], font_head, C_NGROK[0])

# FastAPI
box(540, 80, 200, 90, *C_FASTAPI)
label(540, 80, 200, 90, ["FastAPI Orchestrator", "localhost:8000"], font_head, C_FASTAPI[0])

# Arrows row 1
dbl_arrow(220, 125, 300, 125, "events / messages")
arrow(460, 125, 540, 125, "POST /slack/events")

# ── Row 2: State Machine  |  Skill Runner ─────────────────────────────────
# State Machine
box(540, 240, 190, 200, *C_STATE)
label(540, 240, 190, 30, ["State Machine (SQLite)"], font_head, C_STATE[0])
states = ["DISCOVERY", "ARCH_DISCOVERY", "ARCHITECTURE",
          "AGENT_DESIGN", "IMPLEMENT", "REVIEW",
          "SECURITY", "TESTING", "DEVOPS", "COMPLETE"]
for i, s in enumerate(states):
    draw.text((556, 278 + i * 16), f"  {s}", fill=C_STATE[0], font=font_small)

# Skill Runner
box(780, 240, 200, 200, *C_SKILL)
label(780, 240, 200, 30, ["Skill Runner"], font_head, C_SKILL[0])
label(780, 275, 200, 165,
      ["(Anthropic SDK)", "", "system: persona.md", "user: context JSON", "returns: struct JSON"],
      font_body, C_SKILL[0])

# Arrows FastAPI → children
arrow(640, 170, 640, 240, "")
arrow(880, 170, 880, 240, "")
# label on arrows
draw.text((650, 200), "manages", fill="#777", font=font_small)
draw.text((890, 200), "invokes", fill="#777", font=font_small)

# ── Row 3: 8 Personas ─────────────────────────────────────────────────────
box(60, 500, 1280, 180, *C_PERSONAS)
label(60, 500, 1280, 30, ["8 AI PERSONAS  (.claude/skills/)"], font_head, C_PERSONAS[0])

personas = [
    ("Business\nAnalyst", "ba.md", "#D63384"),
    ("Solution\nArchitect", "architect.md", "#0D6EFD"),
    ("Agent\nImplementer", "agent-implementer.md", "#6F42C1"),
    ("Implementer", "implementer.md", "#198754"),
    ("Code\nReviewer", "reviewer.md", "#FD7E14"),
    ("Security\nReviewer", "security.md", "#DC3545"),
    ("Tester", "tester.md", "#0DCAF0"),
    ("DevOps", "devops.md", "#20C997"),
]

px = 80
for name, skill, color in personas:
    box(px, 538, 140, 120, color, "#FFFFFF", radius=8)
    lines = name.split("\n")
    label(px, 538, 140, 70, lines, font_body, color)
    draw.text((px + 8, 620), skill, fill="#666", font=font_small)
    if px + 140 + 20 < 1320:
        arrow(px + 140, 598, px + 162, 598, "")
    px += 162

# Arrows FastAPI → Personas
arrow(640, 440, 640, 500, "routes to")

# ── Row 4: Workspace  |  Git ───────────────────────────────────────────────
box(200, 740, 400, 200, *C_WORKSPACE)
label(200, 740, 400, 30, ["Project Workspace"], font_head, C_WORKSPACE[0])
ws_lines = [
    "workspace/{project-name}/",
    "  artifacts/   ← design docs (.md)",
    "  src/         ← generated code",
    "  evals/       ← LangSmith scripts",
    "  tests/",
    "  requirements.txt  .env.example",
    "  demo.py",
]
for i, line in enumerate(ws_lines):
    draw.text((215, 778 + i * 18), line, fill=C_WORKSPACE[0], font=font_small)

box(680, 740, 400, 200, *C_GIT)
label(680, 740, 400, 30, ["Git  (commit + push every stage)"], font_head, C_GIT[0])
git_lines = [
    "feat(ba):                requirements.md",
    "feat(architect):         architecture.md",
    "feat(agent-implementer): agent-design.md",
    "feat(implementer):       src/ code",
    "feat(reviewer):          code-review.md",
    "feat(security):          security-audit.md",
    "feat(tester):            test-plan.md",
]
for i, line in enumerate(git_lines):
    draw.text((695, 778 + i * 18), line, fill=C_GIT[0], font=font_small)

# Arrows personas → workspace / git
arrow(520, 680, 400, 740, "")
arrow(800, 680, 800, 740, "")
draw.text((390, 706), "writes files", fill="#777", font=font_small)
draw.text((810, 706), "commits", fill="#777", font=font_small)

# ── Border ─────────────────────────────────────────────────────────────────
draw.rounded_rectangle([8, 8, W-8, H-8], radius=16,
                        outline="#CCCCCC", width=2)

out = "docs/architecture.png"
os.makedirs("docs", exist_ok=True)
img.save(out, "PNG", dpi=(150, 150))
print(f"Saved: {out}  ({W}x{H}px)")
