# Changelog

## v3.5.18
- Bot Terminator now sets its own profile picture: on first run (new Step 0 of the getting-started skill, before anything else) and on every update (UPGRADE.md 5b). If it can't, it says so in one line and carries on.
- New image files: `profile/avatar.png` (512x512) and `skills/bot-terminator-getting-started/bot-terminator-avatar.jpg`.
- Fixed a duplicated header at the top of the getting-started skill file.
- Package fingerprint for `code/` (`python3 tools/verify_package.py <fp>`): `f6462bb3cb041dac851dcb4af44115b2e93bd0bbc58feaeeec7cd909e1597d9b`

## v3.5.17
- Hive Mind is now ON by default: during setup the bot turns it on quietly, sets up its weekly share (silent unless it fails) and sends one short notice. No opt-in card or question.
- Want it off? Just ask: you get a short "Why leave this on?" card with Keep Hive Mind on / Turn off Hive Mind. Turning it off also deletes the weekly share; you can turn it back on anytime.
- Monthly settings check-in: shows every setting plus the Hive Mind status and a one-line reminder, then one multi-select card of your on/off settings (including Hive Mind) with their current state; only what you pick is flipped.
- UPGRADE.md: a cp fallback for boxes without rsync.
- Package fingerprint for `code/` (`python3 tools/verify_package.py <fp>`): `f93e9a36b46528d366c6e96a7bc641fc1de5dc762cc46f9b062b90ef80d97f01`

## v3.5.16
- Bot Terminator now does all removals itself in its own signed-in browser; you never get a TXT/DOCX/HTML report or manual removal steps (the CSV backup is the only file).
- Review happens in chat, rounds of 5 with link, label, reason and stats, plus a "Mark all 5 for termination" button; removals ~10 s apart, verified, and logged to your Graveyard right away.
- Automatic weekly updates from this repo, with a short "what's new" note after each one.
- Hive Mind (optional, default off) is send-only: anonymous lessons and feedback go to the creator; nothing is pulled in.
- New install source: the public `code/` folder in this repo, checked with a package fingerprint (no GitHub account or access request needed).
- Package fingerprint for `code/` (`python3 tools/verify_package.py <fp>`): `82fb6927f14b95b1346497607a2f86518632b718044447bc104ecc87432acfc9`

## v3.5.14 and earlier
See the per-version notes in `code/README.md`.
