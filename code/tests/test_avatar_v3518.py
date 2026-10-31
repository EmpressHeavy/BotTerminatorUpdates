"""v3.5.18: unconditional Step 0 sets the profile picture; avatar files are real images."""
import os, re, struct
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "docs", "skills", "bot-terminator-getting-started.md")
JPG_TAIL = "/BotTerminatorUpdates/main/skills/bot-terminator-getting-started/bot-terminator-avatar.jpg"
FAIL_LINE = "I couldn't set my profile picture just now; ask me anytime to try again"


def _skill():
    with open(SKILL, encoding="utf-8") as f:
        return f.read()


def test_step0_is_first_and_unconditional():
    t = _skill()
    i0 = t.index("## Step 0")
    assert i0 < t.index("1. **Greet and explain.**")
    step0 = t[i0:t.index("1. **Greet and explain.**")]
    assert "unconditional" in step0.lower()
    assert "before any greeting, question, card or delegation" in step0
    assert not re.search(r"\bif (the owner|they) (want|say|agree)", step0, re.I)
    # no question is asked before Step 0
    assert "?" not in t[:i0].split("# Bot Terminator: first conversation with a new owner", 1)[-1]


def test_step0_contents():
    s = _skill()
    step0 = s[s.index("## Step 0"):s.index("1. **Greet and explain.**")]
    assert re.search(r"curl -fsSL https://raw\.githubusercontent\.com/[A-Za-z0-9-]+" + re.escape(JPG_TAIL)
                     + r" -o /workspace/bot-terminator-avatar\.jpg", step0)
    assert "test -s /workspace/bot-terminator-avatar.jpg" in step0
    assert "retry once" in step0
    assert "GetDynamicTools" in step0 and "`cursor`" in step0
    assert '{"action":"set","path":"/workspace/bot-terminator-avatar.jpg"}' in step0
    assert "Subagents can't call UpdateAvatar" in step0
    assert "local file path, not a URL" in step0
    assert FAIL_LINE in step0 and "carry on" in step0


def _png_size(p):
    b = open(p, "rb").read(32)
    assert b[:8] == b"\x89PNG\r\n\x1a\n" and b[12:16] == b"IHDR"
    return struct.unpack(">II", b[16:24])


def _check_jpg(p):
    b = open(p, "rb").read()
    assert b[:3] == b"\xff\xd8\xff" and b.rstrip(b"\x00")[-2:] == b"\xff\xd9" and len(b) > 10000


def test_private_assets_are_real_images():
    png = os.path.join(ROOT, "assets", "profile", "avatar.png")
    jpg = os.path.join(ROOT, "assets", "bot-terminator-avatar.jpg")
    if not os.path.exists(png):
        pytest.skip("assets not present in this layout")
    assert _png_size(png) == (512, 512) and os.path.getsize(png) > 10000
    _check_jpg(jpg)


def test_public_repo_images_when_present():
    top = os.path.dirname(ROOT)
    png = os.path.join(top, "profile", "avatar.png")
    jpg = os.path.join(top, "skills", "bot-terminator-getting-started", "bot-terminator-avatar.jpg")
    if not os.path.exists(os.path.join(top, "UPGRADE.md")) or not os.path.exists(png):
        pytest.skip("not inside the public update repo")
    assert _png_size(png) == (512, 512)
    _check_jpg(jpg)
    up = open(os.path.join(top, "UPGRADE.md"), encoding="utf-8").read()
    assert "Apply the profile and avatar" in up and "/main/profile/avatar.png" in up and "UpdateAvatar" in up
    top_skill = open(os.path.join(top, "skills", "bot-terminator-getting-started", "SKILL.md"), encoding="utf-8").read()
    assert top_skill.startswith("---\nname:") and top_skill.count("name: Bot Terminator getting started") == 1  # single frontmatter
    assert top_skill.index("## Step 0") < top_skill.index("1. **Greet and explain.**")
