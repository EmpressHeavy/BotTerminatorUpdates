# Changelog

## v3.5.16
- Bot Terminator now does all removals itself in its own signed-in browser; you never get a TXT/DOCX/HTML report or manual removal steps (the CSV backup is the only file).
- Review happens in chat, rounds of 5 with link, label, reason and stats, plus a "Mark all 5 for termination" button; removals ~10 s apart, verified, and logged to your Graveyard right away.
- Automatic weekly updates from this repo, with a short "what's new" note after each one.
- Hive Mind (optional, default off) is send-only: anonymous lessons and feedback go to the creator; nothing is pulled in.
- New install source: the public `code/` folder in this repo, checked with a package fingerprint (no GitHub account or access request needed).
- Package fingerprint for `code/` (`python3 tools/verify_package.py <fp>`): `82fb6927f14b95b1346497607a2f86518632b718044447bc104ecc87432acfc9`

## v3.5.14 and earlier
See the per-version notes in `code/README.md`.
