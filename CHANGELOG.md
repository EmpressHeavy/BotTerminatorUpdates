# Changelog

## v3.5.21
- Subscription is $4.49/month, or $8.99/month bundled with Follower Finder, at https://empressheavy.com/subscribe/.
- Before a scan, removal, or block, this copy checks the license server at https://empress-license.empressheavy.workers.dev. If it is not paid, the bot stops and links to that server's checkout for this install (`/pay?install_id=...&product=bt`) or to https://empressheavy.com/subscribe/. Records and the X login stay put. Offline grace is 72 hours after the last active answer.
- License register and check send `User-Agent: BotTerminator/<version>` so Cloudflare does not reject urllib's default agent (error 1010).
- Package fingerprint for `code/` (`python3 tools/verify_package.py <fp>`): `4c99c68ee58937a6a52b8f5a8fd2bd4ba08918688e15dafcc1bdfe99a1e411b9`

## v3.5.20
- Hive Mind records owner-taught capabilities: when an owner teaches this copy a method, skill, routine, storage, or workflow the shipped build does not have, the bot records kind `capability` (`self_upgrade` is an alias) with personal details removed, and includes it in that week's batch under its own heading.
- Weekly Hive Mind batches skip any hash already sent, so the same correction is not resent every week. A successful send marks those rows shared so they leave the weekly pool.
- Template version is read from the package `VERSION` file (fallback `v3.5.20`), so Hive Mind reports match the release.
- Every upgrade reinstalls the Hive Mind client (`sh tools/install_hive.sh`); it only copies files and does not change Hive Mind on/off.
- Package fingerprint for `code/` (`python3 tools/verify_package.py <fp>`): `899ef9936b234c35e92b921dd7ad5477478ed33fc54150052d1ee90b1b314a04`

## v3.5.19
- Terminate reminder setup uses cadence cards before a routine is created (still optional, off by default). Prompt: "How often do you want me to remind you to terminate bots?" with Daily / Weekly (Monday–Thursday) / More days; More days offers Friday–Sunday or No, not now. Daily or any weekly day then asks for a time.
- Owners who already have a terminate-reminder schedule are not asked again; a missing `cadence` is treated as daily.
- Status, Book change lines, and the monthly check-in say `daily at HH:MM` or `weekly (Monday) at HH:MM`.
- Package fingerprint for `code/` (`python3 tools/verify_package.py <fp>`): `25bf68c3a8c817657421d307bb2de72526b63b7a63532009e3bb49048e97bc03`

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
