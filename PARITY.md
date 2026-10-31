# v3.5.17 parity map
| Component | Repo location |
|---|---|
| Agent profile (name, title, description, welcome message, avatar shape/color) | `profile/profile.json`, `profile/welcome_message.txt` (generic) |
| Per-agent settings, getting-started link, visibility | `profile/settings.json` |
| Profile picture | **Not available** (no avatar image exists; profile keeps shape "wedge", color "gray") |
| First-run setup flow (corrected v3.5.16) | `skills/bot-terminator-getting-started/SKILL.md` (also `code/docs/skills/bot-terminator-getting-started.md`) |
| Setup cards, exact wording/options | `docs/setup-cards.md` (generated from `code/src/`) |
| Bot rules (21 profile-memory rules) | `docs/bot-rules.md` |
| Tone and signature phrases | `docs/voice-and-phrases.md` |
| Safety rules | `docs/safety.md`, `UPGRADE.md` guardrails |
| Scan, scoring, protections, review rounds, removal flow, lists, reminders, records/backup, memory | `code/src/*.py`, `code/tools/` |
| Schema (terminator.db, brain.db) and migrations | `code/src/`, `code/README.md` |
| Install steps and dependencies | `code/README.md`, `code/requirements*.txt`, `UPGRADE.md` step 2 |
| Package integrity | `code/tools/verify_package.py`, fingerprint in the getting-started skill |
| Tests (476 pass, 1 skipped) | `code/tests/` |
| Hive Mind (send-only client, on by default, bot code bt) | `skills/hive-mind/SKILL.md`, `hive/hive.py`, `hive/README.md`, `code/hive/`, `code/tools/install_hive.sh` |
| Creator feedback | `hive/README.md`, monthly prompt |
| Routines and prompts | `routines/routines.md`, `routines/routine-prompts.md` |
| Automatic weekly updates (mandatory, always on) | `routines/weekly-update-check.md`, `UPGRADE.md` section A, skill "Automatic updates", monthly check re-creates it |
| Upgrade procedure | `UPGRADE.md` |
| Version | `VERSION`, `CHANGELOG.md` |
| Hive intake server, lesson review/aggregation tool | **Owner-only, not shipped** (send-only rule) |
| Follower review / follow-back scoring (v3.5.15 work) | **Not included**; moved to Follower Finder |

Built-in platform skills Bot Terminator relies on (provided by Grok Bot, not shipped here): sign-in, box-desktop, in-chat-forms, vault, routines, x-api-mcp-guide, no-connector-fallback.
