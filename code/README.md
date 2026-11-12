# Bot Terminator

Bot Terminator helps an X user clean bot-like, spam-like or long-inactive followers from **their own** account,
under the operating mode they choose. It reads and classifies followers, shows candidates for review, and only
removes accounts the owner has authorized.

## Getting the package (public update source)
This package is the `code/` folder of the public update repo named in your setup instructions (no GitHub account,
access request or token needed). Accept it only from that exact repo.
1. **Download:** clone the update repo and copy its `code/` folder to your bot's workspace.
2. **Verify before installing:** inside the clone, `python tools/verify_package.py <expected fingerprint>` (run in
   `code/`) must print OK. On any mismatch, stop and don't install. The fingerprint is the SHA-256 of the sorted
   lines `<sha256 of file>  <path>` over every tracked file (`git ls-files`).
3. Create a venv, `pip install -r requirements.txt` (plus `requirements-sheets.txt` only for standalone use), and run
   `python -m pytest -q`, which must report 0 failures. Then go on to the Google checks and the first scan.

## Protections (always on, checked before classification and again right before any removal)
- Accounts the owner follows are never removed.
- Verified accounts are never removed. Verified accounts are excluded before classification (hard pre-filter, v3.5.13): ANY verified account (blue, gold, gray, paid or not, or one whose About page shows a Verified status such as "Verified since September 2026", even when no checkmark was seen in the list) is never scored, never REVIEW, never a suspect or on any card, in scans and in initial setup. Only unverified followers are evaluated. This cannot be switched off.
- Always Keep entries, and any private `protected_handles` in the owner's own config, are never removed.
- "Unverified" on its own is never treated as proof of a bot.
- Keepers ("Not a bot" / "Always Keep" answers on cards) are never removed.
- Anyone with a recent interaction with the owner (X search both ways, done right before each removal) is
  never removed; if that check is missing, the account counts as protected.
- Mutuals (accounts the owner follows back) are never removed automatically. Inactive mutuals are shown a few
  per day on their own card (`src/inactive_mutuals.py`, default 3/day); only ones the owner marks there may be
  removed as followers (they are not unfollowed).

## How followers are judged (check order)
1. **Handle/bio screen** (first pass only): a number-style handle is a weak hint shown on the card, never
   proof and never a counted signal (many real people keep X's default handle).
2. **Real replies to other people** -> a real person, kept.
3. **The numbers:** no or almost no posts, very low followers and high following are bot signs; real or
   verified followers mean a real person. Missing numbers never clear or condemn an account (it stays in review).
Only accounts that fail both 2 and 3 go on a removal card. Location stays one input among many. Possible
impersonators (of accounts you follow, or celebrity "manager"/fan-page scams) are flagged on the card.
Every card and suggestion shows post, follower and following counts.

## Getting the follower list
The X connector can read profiles and counts, but it can't list your followers or remove them. The bot's
signed-in box browser (computerUse; signed in by the owner via the sign-in skill / request_box_help) does that:
Profile > Followers, and the bot itself removes the accounts the owner checks. The owner never removes accounts
by hand and never gets a TXT/DOCX/HTML report; the only file is the optional CSV backup (`src/removal_flow.py`).

## What this package does and doesn't do (by design)
- It does **not** fetch followers from X and contains no X login or sessions. In normal use the agent's
  browser (the bot's own box browser, signed in by the owner) brings followers in and writes them to `scan_raw/`.
  This package classifies, builds the review cards and sheet, records decisions, and enforces the removal
  rules in `src/removal_runner.py`; the actual click on X's native "Remove this follower" is done by the
  agent's browser through a pluggable adapter (see "Removal runner").
- It only removes followers during normal termination sessions, and blocks Graveyard returns when the user authorizes it. Graveyard returns (accounts removed before that follow again) are detected on each scan and handled by
  `src/graveyard_returns.py`; the actual click on X's native "Block" is likewise done by the agent's browser
  adapter, outside this package (see "Graveyard returns").
- Optional offline path: import followers from your own X account archive ZIP (see below).
- After setup, the first run is a real run on your account: there is no separate practice run.

## Setup
1. Python 3.11+ and a virtual environment:
   ```
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt        # standard library only (no Word/HTML reports)
   pip install -r requirements-dev.txt    # + pytest 9.1.1 (only to run tests)
   pip install -r requirements-sheets.txt # ONLY outside Grok Bot: manual Google key fallback
   ```
2. Sign in to X yourself, on your own machine/box. This package contains no account sessions, sheet IDs,
   doc IDs or personal settings.
3. Create your config (creates `data/users/<user_key>/` and its `scan_raw/` folder (0755) with `config.json` (0600) and sets `data_root_relative` for you):
   ```
   python -m src.new_user --user <user_key> --handle @your_handle --daily-cap 10 --scan-time 09:00 [--lists yes] \
       [--reminder] [--terminate-reminder yes --terminate-time 18:00] [--protect @someone] [--manual]
   ```
   Setup asks (`new_user.SETUP_QUESTIONS`): the **daily removal cap** (1-100, required; start low, e.g. 10),
   the **daily scan time** (HH:MM, your time zone), whether you want a reminder through your front-door bot,
   and whether to turn on **list checks** (see "Lists"; **default: off**, `--lists yes` turns them on). The three
   list tabs are created either way, so turning list checks on later needs no sheet change. It also asks, as an
   optional last step, whether you want the **Terminate reminder** (see below; **default: off**,
   `--terminate-reminder yes --terminate-time HH:MM` turns it on) and, if yes, the time to send it.
   Then the bot runs `new_user.setup_plans(cfg)` with your connectors:
   - **Bot Terminator Book** (`src/rules_book.py`, template `templates/bot_terminator_book.md`): your rules doc
     in Google Docs (Job, Always kept, How bots are judged, Approval and pace, Where things live, Routines,
     Lessons learned, Change log). It is read before every scan or removal (`preflight.record_book_read`;
     runs refuse without a read in this session within the last 60 minutes) and appended to, with a Change
     log line, whenever you change a rule (`rules_book.rule_change_plan`).
   - **Log sheet** (`src/sheet_layout.py`) with tabs **Actions**, **Keepers**, **In review**, **List Graveyard**, **Kept Lists** and **Protected Lists**.
   - **Daily scan routine** (`src/daily_routine.py`) at your time: two cards, likely bots and a few inactive
     mutuals. Nothing is removed without your marks.
   `<user_key>`: lowercase letters, digits, `_ . -`. **Required:** `owner_x_handle` (your X handle; set by
   `--handle`; `x_handle` is kept as the same value). Optional: `protected_handles`, `hide_verified_forced`.
   Manual alternative: copy `config/default_user_config.json` to `data/users/<user_key>/config.json` and set
   `user_key`, `owner_x_handle` and `data_root_relative` to exactly `data/users/<user_key>` (anything else is rejected).
   Defaults: Automatic Mode (switch with `--manual` or later), graveyard returnees go to review. Optional
   removal settings: `time_zone` (e.g. `America/New_York`; default: this computer's zone),
   `daily_removal_cap` (asked at setup; default 10, max 100), `max_snapshot_age_days` (default 7).
4. Bring followers in (the agent's browser, or the archive importer below), then run a scan:
   ```
   python src/run_classify_pipeline.py --user <user_key>
   ```
   If no follower records are found, it prints a warning, saves nothing, and exits with code 2.

## Follower input: `data/users/<user_key>/scan_raw/batch_NNN.json`
Each file is a JSON array of follower records. `username` is required; the rest improves classification
(missing fields mean "Not available", never a guess). Example with made-up values:
```json
[
  {"username": "demo_01", "name": "Demo Account 01", "user_id": "2000000001",
   "verified": false, "verified_type": "none", "you_follow_them": false, "follows_you": true,
   "followers_count": 12, "following_count": 3400, "post_count": 2100,
   "created_at": "2026-08-17", "account_age_days": 60,
   "bio": "", "has_default_avatar": true, "profile_complete": false,
   "days_inactive": 1, "account_country_unavailable": true, "deep_inspected": true,
   "activity": {"original": 1, "replies": 1, "quotes": 0, "reposts": 98, "sample_size": 100}}
]
```
Offline archive import (writes the next free `batch_NNN.json`; the X archive schema is not verified, so only
recognised fields are copied):
```
python -m src.import_x_archive --user <user_key> [--handle @your_handle] path/to/your-x-archive.zip
```

## Writing the review sheet
**Inside Grok Bot, the Google Sheets and Google Drive connectors are both required.** Connect them in your Grok Bot before the first run, because the bot doesn't work without them. `src/preflight.py` enforces this. The classify pipeline, the removal runner and the block runner refuse to start
unless both connections were rechecked in the **current session**:
- **Each session:** at session start the bot calls `preflight.start_session(user_key)`, which drops old
  confirmations. It then runs a quick Drive `search_files` and a Sheets `read_range` on the review sheet. After each
  success it calls `preflight.record_confirmation(user_key, "google_drive" | "google_sheets")`.
- **Expiry:** confirmations from another session, or from a session started over 12 hours ago, are refused with a
  "recheck" message.
- **Failures:** if a connector call fails mid-session, the bot calls `preflight.record_failure(user_key, conn, error)`,
  and every run refuses until a fresh successful check of that connection.
- **Locked to Grok Bot:** the default config sets `"runtime": "grokbot"`, and a missing runtime counts as grokbot. In
  grokbot runtime, `sheets.backend` must be `connector`; `google_api` and `csv` are refused, not honored.
  `preflight.set_runtime` and `preflight.set_sheets_backend` refuse to move a grokbot config off grokbot or the
  connector, and the mode switch only knows Automatic and Manual.
- **Standalone only (not the Grok Bot template):** people running the package on their own computer, outside Grok Bot,
  use a separate config with `"runtime": "standalone"` AND set the env var `BOT_TERMINATOR_STANDALONE=1`. Only then
  are the connectors not required and `google_api` / `csv` allowed.
- The shipped default config has no confirmations, so a new user is refused until both connections are checked. The backend is `sheets.backend` = `connector`. The manual Google key (`google_api`) is only for running the package outside Grok Bot.
Each user connects Google Sheets in their own Grok Bot, so writes land in their own Drive. No keys ship with
the package. The package never calls Google itself on this path. It returns a fixed write plan, and the agent
runs it with its own connector:
1. `plan = sheet_connector.read_step(spreadsheet_id, "In review")`. Call the connector tool `read_range`
   with `plan["arguments"]` (range `A1:R`).
2. `existing = sheet_connector.rows_from_read_result(<read_range result>)`. Accepts the result dict, its JSON
   text (surrounding text is fine) or bare CSV.
3. `p = sheet_connector.plan_append(rows, spreadsheet_id, existing, dedupe_key=...)`. For In review rows, use
   `sheet_connector.in_review_plan(user_key, snapshot_id, spreadsheet_id, existing)`. If `p` is None, there is
   nothing new to write, so don't call anything.
4. Call the connector tool `append_rows` with `p["arguments"]` exactly as given (`parseInput: true` = USER_ENTERED,
   `insertRows: true`, range `A3:R`). Don't use `append_values`, because it stores raw text and the formulas
   won't work.
5. `start = sheet_connector.start_row_from_response(<append_rows result>, p)` gives the first data row written.
   Read the sheet again before trusting a read-back, because connector reads right after a write can be stale.

The plan is produced by the same writer code as the other backends. It appends only, so existing rows are never
overwritten. An empty tab gets the header on row 3 and data from row 4. Rows already present are skipped
(dedupe). Formulas don't depend on row position. IDs and dates are stored as exact text.

In review list: `review_followup.write_in_review(user_key, snapshot_id, spreadsheet_id=...)` follows
`sheets.backend` too. With the connector (the default) it makes no Google call. The first call returns
`out["sheet"]["read"]`, the read step. Run it, then call again with `existing=<read_range result>` to get
`out["sheet"]["plan"]`, the single `append_rows` call (None if every row is already there). The local
`reports/in_review_<snapshot>.csv` is always written. `google_api` and `csv` follow the fallback rules below.
This is the package's only sheet-write caller. `review_sheet_writer.create_or_open_sheet` (direct API, which
creates a new sheet) is used only by the `google_api` fallback. With the connector, create the sheet with the
connector's own tools, after the user says yes.

Backends and fallback (`sheet_connector.select_backend(cfg, connector_available)`). `google_api` and `csv` are for running outside Grok Bot. They're honored only in standalone mode (`runtime: "standalone"` plus `BOT_TERMINATOR_STANDALONE=1`); in Grok Bot they're refused:
- `connector` (default, required inside Grok Bot). If Google Sheets isn't connected, the write is REFUSED
  (`backend: "refused"`, and `write_in_review` raises `PreflightError`). There's no CSV or `google_api` fallback
  inside Grok Bot. The local CSV report is still saved as a file.
- `google_api`: only for running outside Grok Bot, used only when chosen explicitly (own OAuth client or service account; see
  `review_sheet_writer.py`).
- `csv`: writes `queue.csv` for File > Import. It's for running outside Grok Bot, or as a last-resort record. It doesn't replace the required connector.

## Review cards and sheet
- **Round-based review (v3.5.7, the default termination UX).** `build_candidate_cards.build_cards_for_snapshot(user_key,
  snapshot_id)` puts the flagged accounts in rounds of 5, BOT-LIKE first, then REVIEW, and writes the card answer file
  `snapshots/<id>/chat_numbering.json`. Each round has two parts:
  (a) a chat message (`round_message`) listing its accounts: number, clickable markdown `[@handle](https://x.com/handle)`
  link, label (likely bot / worth a closer look), posts, followers, following, join date and reason;
  (b) a multi-select card titled "Round N of M: which should I terminate?" with those accounts plus a last option
  "Mark all K for termination" (danger style; K is the round's real count, 5 except maybe the last round), no free text.
  After each pick, `review_rounds.run_round(user_key, snapshot_id, n, answer, adapter)` records it and terminates the
  selected accounts right away: about 10 s apart, each verified on X and written to the Graveyard immediately, then
  the backup is pushed (sheet-mirror format to the owner's GitHub records repo). Unselected accounts stay in review.
  Any X warning stops removals for the day. It returns a checklist (each account checked off) to post after the
  round; then send the next round until all rounds are done. Picks come only from the round card: there is no
  all-at-once list and no typed-number replies. Accounts not eligible for removal (person check passed) and inactive
  mutuals never appear on removal cards.
- Inactive mutuals card: `inactive_mutuals.build_card(user_key, snapshot_id)` (a few per day, never repeated);
  the owner's marks are recorded with `inactive_mutuals.record_answer`.
- Final-review "Always Keep" choices are saved to your `always_keep.json` (by X user ID, handle as fallback)
  after a backup, via `record_chat_selection.commit_final_review`.
- Review sheet rows: `populate_review_sheet.build_rows(<snapshot_dir>, <batch_id>, <date>, <first_row>)`.
  - CSV export (outside Grok Bot / backup record): `review_sheet_writer.write_rows_csv(rows, "queue.csv")`, then in Google Sheets: File > Import > Upload.
  - Google Sheets API (ONLY for running outside Grok Bot; **so far tested only with a mocked stand-in, not a real Google login**):
    install `requirements-sheets.txt`. You sign in to **your own Google account**, so your Bot Terminator sheet
    is created in **your own Google Drive**: create an OAuth "Desktop app" client in your own Google Cloud
    project and set `BOT_TERMINATOR_GOOGLE_OAUTH_CLIENT=/path/to/client.json`, then call
    `review_sheet_writer.create_or_open_sheet(user_key=...)` and `write_rows_to_sheet(rows, spreadsheet_id=..., user_key=...)`.
- **Row placement (atomic append):** every sheet write is a single Google `spreadsheets.values.append`
  (`USER_ENTERED`, `insertDataOption=INSERT_ROWS`, anchored on `'<tab>'!A3:R`). Google itself puts the rows
  after the table's last row, so a change made between our read and our write can't cause an overwrite.
  - Empty tab: the header and rows are appended together, giving the header on row 3 and data from row 4.
  - The header is written only when the tab is empty.
  - A read happens first only to detect an empty tab and to skip duplicates.
  - `start_row` in the result comes from the append response (`updates.updatedRange`).
  - Review-row formulas are position-independent (`INDIRECT("K"&ROW())`), so they're correct wherever the
    row lands.
  - IDs and dates keep a leading `'` so they stay text.
  - CSV files are appended to, with a header only when the file is new.
  - The in-review list and the Graveyard returns CSV skip accounts already listed for that snapshot.
  - Rows are only ever added, so an older row keeps its old status; the newest row or the history is the
    current state.
    The first call opens a browser sign-in; the token is cached in `data/users/<user_key>/google_token.json` (0600).
    (Alternative: a service-account key via `BOT_TERMINATOR_GOOGLE_CREDENTIALS`, used only with a sheet already
    in your Drive and shared with it.) Keep the sheet ID in your own config (`review_sheet_id`). No credentials,
    client secrets or tokens are bundled.

## Inactive detection
Inactive and bot-like are separate labels. Protections (accounts you follow, verified, Always Keep) run first and
are unchanged. The day threshold is `protection.inactivity_days_threshold` (default 90).
- **Activity sample present** (30-day recent-posts fingerprint): it takes precedence; the days-since-activity rule
  works as before.
- **No activity sample**: the classifier uses fields already in the scan/profile data, never invents them:
  - a dated last post/activity (`days_inactive`, `days_inactive_cheap`, or a date in `last_post_at`,
    `last_tweet_at`, `most_recent_post_at`, `status_created_at`, `last_status_at`, `last_activity_at`) at or
    past the threshold → INACTIVE. Future or unreadable dates are ignored.
  - zero posts on an account at least `zero_posts_min_account_age_days` old (default 365), or a lifetime post rate
    under `low_post_rate_per_year` (default 1) on an account at least `low_post_rate_min_account_age_days` old
    (default 730) → hints only → REVIEW ("Needs your look"), never INACTIVE on their own.
  - no date fields → "Last post date: Not available"; never INACTIVE.
- Settings live in the `inactivity` block of the user config; `use_profile_fields_without_sample: false` restores
  the older sample-only behaviour.
- Large lists: classification runs over every follower in chunks (`classify_chunk_size`, default 1000) with a
  resume file at `tasks/classify_progress.json`; there's no sampling cap. Anything not classified (interrupted or
  an unreadable record) is labelled `NOT EVALUATED`, never KEEP. `last_scan_report.json` → `classification_coverage`
  gives the counts. No X calls are made by the package.

## About this account (v3.5.8, Stage 2 only)
For followers that survive Stage 1, the deep check reads X's "About this account" page (click "Joined <Month Year>"
on the profile, or open `https://x.com/<handle>/about`), paced with `about_account.AboutReadPacer` to avoid 429s.
`about_account.parse_about_text` reads date joined, account based in, verified, ID verified, username changes and
connected via; anything not shown is "Not available". Signals: a based-in / connected-via country mismatch is
moderate (+1, never proof alone); 3+ username changes is a signal; ID verified is a strong keep (never bot-like);
location alone never counts. Cards show the available fields in the stats line. Step-by-step:
`docs/about_page_runbook.md`. Old snapshots without these fields still load (all "Not available").

## Hive Mind client (v3.5.9)
`hive/hive.py` is the opt-in Hive Mind lesson-sharing client, byte-identical to the one in the hive-mind skill.
Install it with `sh tools/install_hive.sh` (writes `~/memory/hive.py` and a `~/bin/hive` wrapper; sends nothing).
Every upgrade re-runs that script (or copies `hive/hive.py` to `~/memory/hive.py`) so the installed client matches the template. The copy does not change Hive Mind on/off.
It stays off until the owner says yes (`hive on --bot bt`).

## Where your data lives
- **On the computer running the bot:** everything under `data/users/<user_key>/` (config, follower input,
  snapshots, Always Keep, history, reports, the journal, your private memory `memory/brain.db`). Only that computer holds these files.
- **In your own Google Drive (required):** the review sheet, written through your Grok Bot's Google Sheets connection. Google Drive must be connected too. It is separate
  from the local folders: deleting local files doesn't delete the sheet, and vice versa.

## File permissions
Set explicitly by the code (not left to the system umask):

| Mode | Applies to |
|---|---|
| `0755` (others can list/read, not change) | `data/users/<user_key>/` and every folder inside it |
| `0644` (readable) | `journal.md`; reports: everything in `reports/` (CSV export) |
| `0600` (owner only) | all other files = main data: `config.json`, `always_keep.json`, `backups/always_keep/*`, `checkpoints.json`, `last_scan_report.json`, `scan_raw/*`, snapshot `candidates.json` / `meta.json` / `selections.json` / `review_index.json` / `metrics.json` / `chat_numbering.json`, `history/history.jsonl`, `graveyard.jsonl`, `mode.json`, `google_token.json` |

Because folders are 0755, other accounts on the same computer can see file names and open the 0644 files
(journal and reports). Main data files stay owner-only.

## Removal runner
`src/removal_runner.py` enforces the rules; a pluggable adapter performs the click. There is **no practice
mode**: a run with a real adapter removes real followers.
```
python -m src.removal_runner --user <user_key> --snapshot <snapshot_id> --adapter your_module:YourAdapter [--start-followers N]
```
Adapter interface (implemented by the agent's browser bridge; the package ships none for real use):
- `lookup(account) -> dict` with fresh `{user_id, handle, i_follow, verified_type, recent_interaction,
  follows_me}` (use `None` when unknown). `recent_interaction`: X search both ways between the owner and the
  account; `follows_me`: whether the account still follows the owner.
- `remove(account) -> RemovalResult(status, message)` where status is `ok`, `warning`, `rate_limited` or `error`

Rules the runner enforces:
- **Authorized list only:** accounts selected in a recorded, authorized chat selection for that snapshot
  (Automatic Mode card answers, or Manual Mode selections confirmed with `record_manual_confirmation`).
  Without one it refuses.
- **Snapshot age:** refuses snapshots older than `max_snapshot_age_days` (config, default 7).
- **One run at a time:** a per-user lock (`run.lock`). If a run was interrupted it may have finished some
  removals: check state on X with `reconcile_interrupted_run()` (it logs accounts already gone and clears
  the lock only when every account's state is known) before re-running or reporting.
- **Confirmed on X:** after each removal the account is looked up again; it's logged as REMOVED only when it
  no longer follows you. Otherwise REMOVAL_NOT_CONFIRMED is logged and the run stops.
- **Protection recheck right before each removal**, fail-safe: followed by you (waived only for inactive
  mutuals you marked on their own card), verified, Always Keep, Keepers, recent interactions with you,
  `protected_handles`; matched by X user ID first (so renamed accounts still match), handle as fallback;
  missing follow or verified data counts as protected.
- **Daily cap:** `daily_removal_cap` per user per calendar day in your `time_zone` (config; chosen at
  setup, default 10, never above 100), counting earlier removals today from history.
- **Fixed pacing:** `PACING_SECONDS = 10` between removals, no random jitter or timing tricks.
- **Stop on the first X warning or rate limit:** recorded; no more removals that day; earlier selections are
  void, so resuming (on a later day) needs a new authorized selection. Other errors stop the session.
- **Removal only on this path:** It only removes followers during normal termination sessions, and blocks Graveyard returns when the user authorizes it. The removal runner calls only `lookup()` and
  `remove()`; it never blocks, and skips any account flagged as a Graveyard return. Blocking happens only in
  the separate Graveyard-return flow below. Neither path ever unfollows, mutes, sends DMs or posts.
- **Records:** every removal, skip and stop goes into your hash-chained `history/history.jsonl`; each removal
  also goes into `graveyard.jsonl`. A session summary is printed (start count if known, removed, skipped as
  protected, removals today vs cap, stop reason).

## Graveyard returns (block, only when you authorize it)
It only removes followers during normal termination sessions, and blocks Graveyard returns when the user authorizes it.
- **Detection (every scan):** any follower whose X user ID is in your `graveyard.jsonl` is flagged
  `GRAVEYARD_RETURN` (handle is used only when an ID is missing, so a reused handle never matches someone else;
  a renamed returnee still matches by ID). Returnees go to `snapshots/<id>/graveyard_returns.json` and
  `reports/graveyard_returns_<snapshot>.csv` (a separate list, the "returns" section of your review), get their
  own card (`graveyard_returns.returns_card`), and are kept OUT of removal cards and removal runs.
- **Chat card flow (`src/graveyard_return_cards.py`, all users):** after detection the bot sends, in order:
  a notice ("N bots have reattached to your account, and I have them recorded in the Graveyard."; singular for
  1; nothing at all for 0), a fixed disclaimer that these repeat offenders will be blocked rather than removed,
  a list with one clickable `x.com/<handle>` line per returnee (removed date, came-back date, "new handle, was
  @old" when renamed; missing dates show "Not available"), then cards of up to 5 returnees plus
  "Mark all for blocking" (multi-select, no free text, max 6 options, numbering continuous across cards and
  matching the list). Prompt: "Graveyard returns (i of k): block these repeat followers? Unmarked accounts will
  be kept in review." `record_card_answer` turns the picks into the per-returnee block authorization; unmarked
  returnees are logged as kept in review and listed by `kept_in_review()` for the final review card. The card
  numbering is saved in `snapshots/<id>/graveyard_return_numbering.json` (0600). With `auto_block` the notice
  and list are shown but no cards (the setting already authorizes the blocks).
- **Action is BLOCK, never remove**, so a returnee can't keep re-attaching.
- **Authorization:** a block runs only for returnees named in a recorded `BLOCK_AUTHORIZATION`
  (`record_block_authorization`, your card answer). Config `graveyard_return_action`: `"review"` (default for new
  users: each block needs your OK) or `"auto_block"` (your standing setting authorizes detected returnees).
- **Same safeguards as removals:** protection recheck right before each block (followed, verified, Always Keep,
  `protected_handles`/IDs; ID first; missing data = protected), fixed 10 s pacing, ONE shared daily cap for
  removals + blocks (max 100, your time zone), stop and pause BOTH for the day on the first X warning or rate
  limit, stale-snapshot refusal, every block/skip/stop in the hash-chained history.
- The block path calls only `lookup()` and `block(account) -> RemovalResult`; never `remove()` or anything else.
- `graveyard.jsonl` is append-only: `REMOVED`, `RETURN_DETECTED` and `BLOCKED` events are new lines.
- CLI: `python -m src.graveyard_returns detect --user K --snapshot S` (also runs automatically after each scan)
  and `python -m src.graveyard_returns block --user K --snapshot S --adapter your_module:YourAdapter`.
- Honest scope: the package enforces the rules and keeps the records; the real X "Block" click is performed by
  the agent's browser adapter outside the package (none ships for real use). Tested only with the test adapter.


## Lists (v3.1.0, optional; asked at setup, default off)
Turn on with `--lists yes` at setup, or in the monthly check-in (config `lists.enabled`). Nothing here runs unless it's on.
Nothing on X happens without your explicit "Remove me" selection on a frozen snapshot. **Tapping a Remove button IS the
authorization to act right now** (Automatic Mode, the default; in Manual Mode the bot asks for a yes first). The exact
browser steps are in [`docs/list_runbook.md`](docs/list_runbook.md); `src/list_flow.py` is the glue.
0. **Scope card (before each run):** `lists_scan.scope_card()`: "Only lists from people I don't follow back"
   or "Show all lists". The choice (`parse_scope`) is saved in that run's snapshot and strictly enforced
   (cards and the runner never touch out-of-scope lists).
1. **Memberships page:** the bot's signed-in browser opens `https://x.com/<handle>/lists/memberships` and
   scrolls to the end. That page has no descriptions or list URLs, and some rows show "N followers including
   @someone" instead of the owner. Rows go to `data/users/<user_key>/lists_raw/*.json`.
2. **Deep inspection:** `lists_scan.inspection_plan` opens EVERY list page (plain names too) to read the list
   URL, name, description, owner display name + @handle, member/follower counts, an optional member sample and
   whether you and the owner follow each other. This is how missing owners get filled. Results go to
   `lists_inspect/*.json`; `build_snapshot` merges them (list-page data wins) and freezes the snapshot.
3. **Tone:** `classify_list` flags only really negative content (harassment, hate, spam/bot rings, scams,
   blocklists, mocking/targeting). Playful or plain names are OK; "Grok Bot" is a product name, not a bot signal. Unclear = REVIEW (watched); nothing is flagged
   on a name alone. Lists whose owner is a mutual are never flagged; they're marked "watch".
4. **Watch:** watched lists are saved in `lists_watch.json` and rechecked on later scans (`rechecks`).
5. **Protected Lists:** lists whose owner you follow go on the **Protected Lists** sheet tab and aren't
   re-inspected. The only ongoing check is `lists_scan.recheck_protected`: if you unfollowed the owner, the list
   leaves Protected Lists (logged with the date) and goes back to normal review.
6. **Batches:** `list_cards.build_cards` / `next_batch` show every in-scope list, 4 at a time (chat card widgets allow at most 6 options: 4 lists + 2 action buttons). Each batch is a
   links message (each list's link, the owner's @handle with an x.com link underneath, member count, mutual
   yes/no/Not available), then a multi-select card with one button per list and two action buttons:
   **"Remove me from these lists"** (the selected lists are marked for removal; unselected ones in that batch
   are *skipped*: not kept, not removed) and **"Keep all these lists"** (every list in the batch goes to Kept
   Lists). Either one moves to the next batch (`record_answer`).
   **Final card** (`final_skipped_card` / `record_final_answer`), after the last batch, if anything was skipped:
   "Some lists were skipped during review. Keep these, or select ones to remove?" Paged in groups of 4 (page
   index kept in the review state, numbering continuous across pages), each page with **"Remove me from selected
   lists"** then **"Keep all skipped lists"**; every page is answered and recorded separately. Lists left
   unselected there stay in review (not kept, not removed; shown again on the next run).
   **Kept Lists** (sheet tab; `sheet_layout.kept_rows`): name, link, owner handle, date, snapshot ID. Kept lists
   aren't reviewed again unless the owner or the list name changes (then logged as KEPT_LIST_RECHECK and back to
   review).
7. **Leaving a list (v3.1.0, runs on the tap):** `list_flow.handle_answer` records the tap and says whether to
   execute now. Then, for each selected list, one at a time (`list_runner.run_list_removals`; frozen snapshot
   re-checked; one run at a time via the shared lock): check the list on `https://x.com/<handle>/lists/memberships`,
   check the owner; owner profile > three dots > Block > confirm, **wait 10 s**, Blocked button or three dots > Unblock
   > confirm; then verify on the memberships page that the list is gone and the owner isn't left blocked. Skipped (and
   logged): owners already blocked (never unblocked), owners on Always Keep / protected, lists you're already off.
   If you already follow the owner, the pre-card message warns you (leaving also unfollows them); nothing else gates it.
   10 s between lists; each list counts 2 toward the shared daily cap; stops for the day at any X warning or rate
   limit; `reconcile_interrupted_list_run` checks state on X after an interruption (it never acts, and reports any
   owner left blocked). **Keep** = logged as kept (Kept Lists tab).
   Two ways to run, same checks: *step mode* (the bot drives its own browser per the runbook, then calls
   `list_flow.leave_list(...)` with what it saw; `next_task` gives the next list) and *adapter mode*
   (`list_flow.run_now` with the adapter below).
   **Each list is written to List Graveyard the moment its task finishes**, right after the verified result, never in a
   later batch step (`on_logged` hook; step mode returns `sheet_plan` and `book_plan` for that one list, run them at once,
   then `mark_written`). Failed, unverified, skipped and stopped lists are logged with what actually happened. A
   Change log line goes into the Book the same way (`rules_book.action_log_plan`). If a write fails the run stops;
   `list_flow.catch_up` writes anything saved but not yet written. Sheet and Book IDs come from your config
   (`sheets.spreadsheet_id`, `book.document_id`).
8. **Log:** sheet tab **List Graveyard** (`sheet_layout.list_rows` / `append_plan`; it was called List Removals in v3.0.0-v3.0.1, so rename that tab); **Protected Lists** (`protected_rows`).
9. **Daily routine:** rescans your lists and runs `list_runner.detect_returns` for owners you soft-blocked who
   added you again. **Repeat offenders:** `build_repeat_offender_card` (buttons + Done; paged, 5 owners per card so it never exceeds 6 options), then
   `run_owner_blocks` blocks them for good (or `graveyard_return_action: auto_block`). Always Keep / protected
   owners are skipped.
Browser adapter methods (adapter mode; step mode replays what the bot saw via `list_flow.ObservedAdapter`): `list_state(list)`, `owner_state(owner)`, `block(owner)`, `unblock(owner)`.

## Terminate reminder (v3.2.0, optional; asked at setup, default off; v3.5.19 cadence)
A nudge, sent by the bot itself in your chat (`src/terminate_reminder.py`), daily or on one weekday, at a time you choose
(config `terminate_reminder`: `enabled`, `time`, `tz`, `cadence` `"daily"` or `"weekly"`, `weekday` null or 0=Sunday … 6=Saturday,
`snoozed_until`, `last_answer_date`). A missing `cadence` means daily, so a schedule you already turned on stays as it is.
It is **separate from the "reminder through your front-door bot" option**, which pings you through a different bot; you can have either,
both or neither. Offered at setup (default off) and shown, with on/off and "daily at HH:MM" or "weekly (Monday) at HH:MM", in the monthly settings check-in
(`build_monthly_settings_card`, `terminate_reminder.set_reminder`). It never scans or removes anything by itself.

Setup asks with cards (no free-text box, at most 6 buttons). First card (`cadence_card`): "How often do you want me to remind you to terminate bots?"
with Daily, Weekly (Monday), Weekly (Tuesday), Weekly (Wednesday), Weekly (Thursday), More days. More days opens `cadence_more_card`:
"Which day should I remind you?" with Weekly (Friday), Weekly (Saturday), Weekly (Sunday), No, not now.
No / not now / skip leaves it off and does not ask for a time. Daily or any Weekly (Day) (typed "daily" or "weekly monday" too, via `parse_cadence_answer`)
then asks for a time. The routine is daily cron `{mm} {hh} * * *` or weekly `{mm} {hh} * * {dow}`.

Message: **"Hey, want to terminate some bots?"**, with a card of exactly three buttons (no free text):
- **Yes**: starts the normal scan and card flow right now (`handle_answer` returns `start_scan_now` with the same
  steps as the daily scan: preflight, Book read, daily cap, protections; nothing is removed without your marks).
- **Remind me later**: asks for a time (small card of presets, or type one: `18:30`, `6:30 PM`, `noon`,
  `tomorrow 9am`, `in 2 hours`; a bare `6` is refused as ambiguous; up to 24 hours ahead). The bot then sends the same
  message and card at that time as a one-off routine (`schedule_later` returns `schedule_one_off`; the pending
  follow-up is recorded in config and history). Picking "later" again schedules another one.
- **Not today**: does nothing today (no scan, no repeat today). It asks again the next day at your normal time.

Each answer is written to your own append-only history (`TERMINATE_REMINDER_SENT / _YES / _LATER_ASKED /
_LATER_SCHEDULED / _NOT_TODAY / _SETTING`). All state lives under your own `data/users/<user_key>/`.

## Accounts in review (follow-up card)
Accounts left unmarked on ANY card (normal removal cards and Graveyard returns cards) keep status `IN_REVIEW`.
They are never moved to Always Keep, Keepers or Not a bot automatically. `src/review_followup.py`:
- `collect_in_review` merges both sources (numbered continuously), leaving out anything already authorized,
  acted on, or decided keep (including decisions from the older 3-button final review card).
- `write_in_review` writes them to `reports/in_review_<snapshot>.csv` and, with a sheet ID, to the sheet's
  In review tab: Status "In review", Source `CANDIDATE` or `GRAVEYARD_RETURN`, and a note saying
  whether terminating means remove or block.
- After the user taps done, the follow-up uses two steps per group of up to 5 (6-option limit):
  1. Terminate card: "N. @handle — remove" or "N. @handle — block (Graveyard return)" plus "Mark all for
     termination". Marked candidates get a removal authorization; marked returnees get a block
     authorization. Protections recheck, pacing, the shared cap and stop-on-warning still apply when the
     runners execute (Manual Mode still needs confirmation).
  2. Keep card for the rest: tap an account to keep it as Not a bot (moved to Keepers), plus an optional
     "Add the ones I keep to Always Keep". Anything unmarked stays In review for a later card.
- Numbering persists in `snapshots/<id>/review_followup_numbering.json`; history stays append-only.

## Per-user memory (v3.3.0+, habits v3.4.0; backup optional, default off)
Every owner gets their own private SQLite "brain" on their own bot's computer:
`data/users/<user_key>/memory/brain.db` (folder 0755, file 0600). `new_user.create_user` creates it **empty** from
`templates/memory_schema.sql` (tables entity, person, bot, account_platform, quest, project, rule, capability,
routine, fact with valid_from/valid_to, event_log, plus full-text search `notes_fts`). Nothing ships pre-filled and
no owner can see another owner's memory.
```
MEM_USER=<user_key> tools/mem boot                       # session start: safety rules, rules, projects, routines, current settings, recent events
MEM_USER=<user_key> tools/mem add rule text="..." category=owner
MEM_USER=<user_key> tools/mem fact settings daily_cap 15 # closes the current row, adds the new one
MEM_USER=<user_key> tools/mem log scan "scanned 50: 8 likely bots"
MEM_USER=<user_key> tools/mem q "SELECT kind,summary FROM event_log ORDER BY id DESC LIMIT 5"   # read-only
MEM_USER=<user_key> tools/mem find removal
```
(`python -m src.memory --user <user_key> ...` is the same.) The bot runs `mem boot` at the start of every session
and writes as things happen, each write in its own short transaction (never a daily batch): `memory.record_scan`,
`record_rule_change` (rules and settings), `record_removal`, `record_list_action`, `record_project_status`.
**No secrets, ever:** writes that look like a password, token, API key, cookie, private key or card number are
refused (`memory.SecretRejected`), and the export refuses too.

**Backup (optional, OFF by default).** Offered at setup (`memory.SETUP_QUESTION`) and in the monthly check-in
(`memory.status_line`, `memory.set_backup`). When on, `memory.backup_plan` exports `schema.sql` + one JSONL per table
and pushes it to a GitHub repo **you own**, using **your own** `gh` login (`gh auth setup-git`). The repo must be
private: the plan creates it with `--private` and checks `gh repo view --json visibility` says PRIVATE before any push
(`memory.check_backup_target`). No token is ever written to a file, the config, the template or the remote URL
(`https://github.com/<owner>/<name>.git`).

**Every push re-checks privacy (v3.4.0).** The plan's last step runs `tools/mem backup` (`memory.push_backup`):
export, commit, then **immediately before each push** it asks `gh repo view` for the visibility again and refuses the
push unless it says PRIVATE and the remote URL has no login/token. A repo flipped to public after setup is never
pushed to.

### Memory habits (v3.4.0)
```
MEM_USER=<user_key> tools/mem boot "<bot name>"                     # start of every session
MEM_USER=<user_key> tools/mem lessons lists                         # before a task: what went wrong before
MEM_USER=<user_key> tools/mem supersede rule 4 "new way" --why "..." # replace outdated know-how; never add a duplicate
MEM_USER=<user_key> tools/mem lesson lists "what went wrong" "what worked"   # after a mistake
MEM_USER=<user_key> tools/mem history rule 4                        # old methods, oldest to newest
```
- `find` marks outdated rows `[OLD]`: never follow an [OLD] row. `boot` shows only current rules plus top lessons.
- Nothing is deleted: superseded rules/capabilities keep their text with `status=superseded`, `superseded_by`,
  `reason`, `changed_on`; lessons are kept and their `uses` count goes up when the same lesson repeats.
- Before saying something can't be done, search for a connector (SearchPlugins) and try the signed-in browser.
- The `lesson` table uses the same columns as the optional Hive Mind client (topic, wrong, right, uses, src, status)
  and `fact` carries a plain `subject` column, so the Hive Mind can read this brain.db with
  `MEM_DB=data/users/<user_key>/memory/brain.db`. Older (v3.3.0) databases are upgraded in place on the next write.

## Records (v3.5.0): your own terminator.db, backed up where you choose

Every owner gets a local SQLite file at `data/users/<user_key>/terminator.db` (mode 0600, schema in
`templates/records_schema.sql`). It is the main store for scans, removals, the graveyard and the allowlist (Always Keep).
History is **append-only**: triggers block UPDATE and DELETE; a keep that is taken off is a new `remove` row.

- **Write-through.** `storage.save_snapshot`, `storage.save_always_keep`, `graveyard_returns.append_graveyard`,
  `removal_runner` (graveyard lines) and `list_flow.leave_list` each write the action immediately, then call
  `records.after_write`. A records failure never stops a removal; it is saved in `records/backup_state.json`
  (`needs_attention.tell_owner`) so the bot tells the owner.
- **Backup choice** (`config.records.backup.method`, setup card text = `records.SETUP_MESSAGE`):
  `github` (recommended; a private repo you own, re-checked PRIVATE before every push attempt, 2 attempts, then the
  owner is told), `cloud_csv` (CSVs to one folder in your own cloud via your connector; the bot looks for one with
  SearchPlugins, otherwise sends the file), `download` (a zip, with a weekly reminder when anything changed),
  and nothing else. **v3.5.2: a backup can't be skipped.** The card has exactly those three options. A "skip" / "not
  now" reply gets a gentle re-ask (`records.handle_setup_answer`). Until a backup is chosen, the method is `pending`:
  records stay saved locally and **no file is sent (v3.5.7)**; a file goes out only when the owner picked the
  CSV/download backup or asks for their history. `records.backup_reminder` re-asks at
  each session start and from a light reminder routine (every 3 days) until a backup is set, then the routine is
  deleted. Migrating off Sheets also needs one of the three (`migrate_from_sheets` rejects `skip`/`pending`/`sheets`).
  **v3.5.1:** Google Sheets is no longer offered at new setup (fewer tokens, free, and big sheets eat Drive
  storage and get slow). **v3.5.2: existing Sheets owners are migrated, not
  asked.** When a Sheet in use is detected (`records.needs_migration`), the bot sends `records.migration_card()`, which
  explains that Sheets is being retired (bulky, slow, more tokens) and has no "keep" option. Then
  `records.migrate_from_sheets(user_key, cfg, sheet_values)` copies the tabs into terminator.db (read only,
  idempotent), sets the method to `pending` (Sheet writes and Google checks stop) and returns the setup card (no file). The owner then picks GitHub / cloud CSV / download, with the usual reminders if they stall. Every
  step is appended to `records/migration_log.jsonl`. The Sheet is never deleted, cleared or overwritten; it stays as
  their old copy.
  **v3.5.4 (found by a real end-to-end test):** older configs may have no `records` section and no saved sheet ID
  while a Sheet is still in use. At session start, if `records.legacy_sheet_search(cfg)` returns a query, run that
  Google Drive search read only ("Bot Terminator Review - @handle"). If it finds the Sheet, call
  `needs_migration(cfg, found_sheet_id=...)` and `migrate_from_sheets(..., found_sheet_id=...)`. The import now reads
  the connector's CSV `content`, the alpha-era tabs (GRAVEYARD, KEEPERS, PROTECTED, List Graveyard; repeated
  headers: the first one wins; placeholder IDs ignored) and `TERMINATED` history entries, without duplicating
  removals. Allowlist sync matches accounts by ID, then handle (no remove/add churn). terminator.db now also keeps
  append-only `candidates` (label + reasons per scan), `scan_metrics` (protected/verified/KEEP/REVIEW/BOT-LIKE/
  INACTIVE counts) and `audit_log`; all three are in the export and restore.
  **v3.5.5:** no Word or HTML review files exist any more; review and removal happen only in chat cards. The
  only file an owner gets is the CSV export of their termination history, when they chose the file/cloud CSV backup
  or ask for it. The migration copies EVERY Sheet tab in full (`sheet_mirror.import_sheet`: tables `sheet_tabs` +
  `sheet_rows`, every column in order, preamble rows, `=HYPERLINK` formulas) and reports per-tab counts to check.
  The GitHub backup now pushes the standard `records/` mirror: `records/sheet/NN_<tab>.json` (same column names),
  `records/db/<table>.json`, `records/xref/accounts.json` (by X user ID, else @handle), `records/xref/snapshots.json`
  (by snapshot ID), `index.json`, `README.md` and `dump.sql`, all pretty-printed. `restore_from_github` reads it;
  `sheet_mirror.sheet_values_from_mirror` rebuilds the Sheet grid; `sheet_mirror.verify_mirror` checks counts.
  **v3.5.6 (found on the live migration):** `import_legacy` also accepts ONE `read_range` result covering many tabs
  (`{"ranges": [...]}`), so Keepers, Protected and List Graveyard rows reach the keep list and list history.
- **Google is not required for any new owner.** Preflight requires Google Sheets/Drive only for existing owners still on
  `sheets` (or older configs that have no `records` section yet). The Book read is required only if the owner has a Book doc.
- **Restore after a wipe:** `records.restore_plan(cfg)`, `restore_from_github`, `restore_from_dir`, `restore_from_file`
  (zip or CSV). Restores are idempotent.
- **Upgrade card** ("Have you used Bot Terminator before?" Yes / No / Not sure): `records.handle_upgrade_answer`.
  Yes / Not sure: find a backup, else ask the older bot (SendToAgent, `records.EXPORT_REQUEST`), then
  `records.import_legacy` (old files, CSV export, or log-sheet tab values), back up, confirm counts. No: fresh start.
- CLI: `python3 src/records.py --user <key> summary|graveyard|counts|export|restore|backup|pending`.

### Send feedback to the creator (v3.5.14: via Hive Mind, opt-in)
When an owner asks for a feature or complains, the bot offers to pass it on (`feedback.OFFER`). The request is always
saved in the owner's own memory (`kind=feedback`) and as a private Hive item (`hive feedback add <kind> ...`). Only on a
clear yes (`feedback.hive_steps`): `hive feedback --bot bt --category bug|request|praise|other "text" --dry-run` is shown
verbatim to the owner, then the same command without `--dry-run` runs only on a second yes, to the Hive intake (`URL` in
`hive/hive.py`). It sends ONLY that one item (`{"batch":[item],"direct":true}`), never the pending weekly batch, and has
its own allowance (3 accepted per install per UTC day, client and intake), so it is not blocked by the weekly/urgent
limits. On HTTP 422 (looks private) the bot rewords, dry-runs again and resends right away (rejected posts don't count).
`tools/mem hive ...` runs the same client on the owner's `brain.db` (`MEM_USER=<user_key> tools/mem hive feedback ...`).
No email draft is used any more.

## Per-user storage (strict isolation)
Every function that reads or writes private data requires a `user_key`; there is no global fallback.
Everything for one owner lives under `data/users/<user_key>/`:

| What | Path |
|---|---|
| Config | `config.json` |
| Follower input | `scan_raw/batch_NNN.json` |
| Always Keep list | `always_keep.json` |
| Always Keep backups | `backups/always_keep/` |
| Checkpoints | `checkpoints.json` |
| Snapshots, card answer file | `snapshots/<snapshot_id>/` (`chat_numbering.json`) |
| Audit log (hash-chained) | `history/history.jsonl` |
| Reports | `reports/`, `last_scan_report.json` |
| Journal | `journal.md` |

A config whose `user_key` doesn't match, a backup belonging to another user, or a history entry for another user
is rejected.

## Tests
`python -m pytest -q tests` (run from this folder; needs `requirements-dev.txt`). Tests use only files inside
`tests/` and never read `data/`.
- `tests/test_no_owner_identifiers.py`: fails if any shipped file contains the publisher's personal handles, account
  IDs, sheet/doc IDs or private paths (v3.3.0 per-user isolation).
- `tests/test_memory.py`: per-user memory (empty per-user db, commands, no secrets, isolation, private-only backup, privacy re-check before every push, lessons/supersede/history, nothing deleted).
- `tests/fixtures/sample_scan.json`: small fixture derived from a real follower scan; every follower handle,
  display name and user ID is replaced with a made-up value (`sample_user_NN`), profile images and bios removed.
- `tests/fixtures/demo_followers.json`: fully made-up `demo_NN` followers with enough fields that some classify
  as bot-like through the real classifier (followed and verified ones stay protected).
- `tests/fixtures/synthetic_x_archive/`: tiny synthetic archive ZIPs for the importer.
- `tests/sheet_connector_bridge.py`: test helper that runs the real sheet writer against rows read through another channel.
- `tests/removal_test_adapter.py`: a TEST-ONLY adapter (lookup/remove/block) for the removal runner and
  Graveyard-return tests (never touches X; not a practice mode).

- **Real Google Sheet check (2026-10-16):** the writer's own `write_rows_to_sheet` code was run against a real,
  throwaway Google Sheet in the owner's Drive using fake demo rows only. `tests/sheet_connector_bridge.py`
  feeds the sheet's current rows into the writer and performs the writer's exact `values.append` call on the real sheet. Four
  rounds verified (and on 2026-10-16 ~8:10 PM PT, after the switch to the atomic append, a further run on the
  same sheet plus a fresh empty tab confirmed: rows land after the last row with nothing overwritten, the header
  is written once on row 3, duplicates are skipped, 19-digit IDs and dates are exact, and the new formulas match
  the old fixed-row ones on both a TRUE and a FALSE row):
  - an empty tab got the header on row 3;
  - later rows were appended after the last row, in order;
  - nothing was overwritten and the header wasn't repeated;
  - repeat in-review writes were skipped;
  - the GRAVEYARD_RETURN tag and the BLOCK note came through;
  - row formulas pointed at their own row and evaluated;
  - links showed as @handle;
  - IDs stayed text.

  That run found and fixed one bug: in-review rows' IDs and dates were being read as numbers (long X IDs would
  have been rounded). The package's own Google sign-in path (OAuth through google-api-python-client) was NOT
  exercised. `tests/test_sheet_integration_optin.py` covers it and is skipped unless you set it up:
  1. `pip install -r requirements-sheets.txt`
  2. In your own Google Cloud project, create an OAuth client of type "Desktop app", download its JSON, and set
     `BOT_TERMINATOR_GOOGLE_OAUTH_CLIENT=/path/to/client.json`. Or use a service-account key in
     `BOT_TERMINATOR_GOOGLE_CREDENTIALS` and share the test sheet with that account's email.
  3. Create an empty throwaway spreadsheet (never your real review sheet) and set
     `BOT_TERMINATOR_TEST_SHEET_ID=<its id>`.
  4. Run `python -m pytest -q tests/test_sheet_integration_optin.py`. The first run opens a browser sign-in. The
     test writes fake rows only, to a `BT_INTEGRATION_TEST` tab.

## Building and verifying the package
`bash tools/build_package.sh` writes `bot-terminator.tgz` and `bot-terminator.tgz.sha256` next to this folder
(the checksum names only the file). To verify, in the folder holding both files: `sha256sum -c bot-terminator.tgz.sha256`.

### v3.5.10
Fix: the identifier test now allows the creator's public Hive Mind intake endpoint in `hive/hive.py` and its fixture (v3.5.9 failed this test on a fresh clone).

### v3.5.11
- **Hive Mind is also the owner-feedback channel.** Any time an owner corrects the bot, asks for a different way, declines a feature, requests one, reports something broken or uses a workaround, the bot records a Hive item right away (`hive feedback add <kind> ...`), even if it happens only once. Feedback is eligible to share after 1 use (lessons still after 2).
- `hive/hive.py`: new `kind` field (v2 lines), real template version in `tv`, `names()` tolerates a missing `fact` table, `hive auto --dry-run` (offline, logged as dry-run in `hive shared`), and at most one urgent broken-only batch per day on top of the weekly batch.
- Intake Worker source (`intake/worker.js`, D1 `intake/schema.sql`, offline `intake/worker_selftest.mjs`), Python mirror of its checks (`intake/validate.py`), local mock (`tools/hive_mock_intake.py`) and the creator's review tool (`tools/hive_review.py`). Deploy and review steps: `docs/hive_intake_deploy.md`. The hive-mind skill text lives in `docs/skills/hive-mind.md`.

### v3.5.12
Fix: `tools/hive_review.py` now sends `user-agent: hive-review/1` on every request (Cloudflare blocked Python's default user-agent with HTTP 403, so `pull` failed against the live intake), and prints "approved"/"rejected" correctly. Template version bumped to v3.5.12.

### v3.5.14
The getting-started feedback step no longer drafts an email. New one-shot client command `hive feedback --bot B --category bug|request|praise|other "text" [--dry-run]` (`feedback add` unchanged): sends only that item as a `direct` payload (kinds broken|request|praise|other), PII-stripped, with its own allowance of 3 per day so a reworded retry after HTTP 422 goes right away; dry run prints the exact bytes. `tools/mem hive ...` routes to `hive/hive.py`. Intake (`intake/worker.js`, `validate.py`, mock, `schema.sql`) accepts `direct: true` (one item, praise/other allowed only there, own 3/day limit); the live Worker needs redeploy plus `ALTER TABLE batches ADD COLUMN direct INTEGER NOT NULL DEFAULT 0`. Tests: `tests/test_hive_direct_v3514.py`. Template version bumped to v3.5.14.

### v3.5.13
Fix: a paid-verified follower (About page "Verified, since September 2026", no checkmark seen in the list) was labelled REVIEW. Verified is now a hard pre-filter in `protections.apply_protections` via `protections.verified_reason`: list checkmark, `verified`/`is_blue_verified`/`verified_type` (blue, business, government) or an About page Verified status all count; `exclude_verified_from_removal` can no longer turn it off. `classify` re-checks after deep inspection (About read), and candidate cards / automatic policy exclude About-verified accounts. The About parser now reads "Verified, since ...". Tests: `tests/test_verified_prefilter_v3513.py`. Template version bumped to v3.5.13.
### v3.5.16
Fix: a published copy gave a new owner a TXT file and told them to remove followers by hand. Cause: the getting-started skill said to sign in with a browser "on this owner's own computer", never named the box browser (computerUse / request_box_help), and had no rule against file handoff. The canonical skill is now in `docs/skills/bot-terminator-getting-started.md`: box-browser sign-in, review in chat in rounds of 5 (link, label, reason, stats), a "Mark all 5 for termination" card, bot-run removal via "Remove this follower" about 10 seconds apart, "Follows you" check, Graveyard log, stop on any X warning; never TXT/DOCX/HTML reports or manual steps (only the CSV backup). New `src/removal_flow.py` and `tests/test_removal_flow_v3516.py`. Template version v3.5.16.
Update-repo distribution: the package now ships publicly as the `code/` folder of the update repo. The Hive Mind client is send-only (the lesson `import` command is removed; clones never pull lessons). The Hive intake server, its tests and the creator's review tool are not shipped.

### v3.5.22
An unpaid install is shown a clickable Subscribe link to https://empressheavy.com/subscribe/?product=bt&install_id=... (product and install ID already filled in), plus the install ID and the license-server `/pay` fallback. Records and the X login are left as they are. Template version v3.5.22.

### v3.5.21
Subscription is $4.49/month, or $8.99/month bundled with Follower Finder, at https://empressheavy.com/subscribe/. Scans, removals, and blocks check https://empress-license.empressheavy.workers.dev first. An unpaid install is told to subscribe at that server's `/pay?install_id=...&product=bt` link or at https://empressheavy.com/subscribe/. Records and the X login are left as they are. Template version v3.5.21.

### v3.5.20
Hive Mind now records what an owner teaches their own copy. New feedback kind `capability` (label "Owner-taught capability"; `hive feedback add self_upgrade` is stored as `capability`). After any owner-driven change that adds or changes a method, skill, routine, storage, or workflow so THIS copy does something the shipped build does not, the bot runs `hive feedback add capability "<area>" "<shipped behavior>" "<generalized new capability>"`. Same scrub as other Hive lines (handles, paths, secrets, private quotes, account IDs dropped or masked; 150 characters per part). Eligible after one use. Not urgent unless a separate `broken` item is recorded. Weekly batches, not only urgent ones, skip any hash already in `hive_sent_h`; a successful send marks those rows shared so they leave the weekly pool. The template version is read from `VERSION` (fallback kept in lockstep). Every upgrade re-runs `sh tools/install_hive.sh` (or copies `hive/hive.py` to `~/memory/hive.py`) and does not change Hive Mind on/off, turn on removals, messages, logins or deletions, or default a new optional setting on; snapshot first and roll back on failure. `hive_review.py list` and the feedback digest have an "Owner-taught capabilities" section. Template version v3.5.20.

### v3.5.19
The optional Terminate reminder (still off by default) asks new owners how often, then what time. First card: "How often do you want me to remind you to terminate bots?" with Daily, Weekly (Monday), Weekly (Tuesday), Weekly (Wednesday), Weekly (Thursday), More days (no free-text box). More days: "Which day should I remind you?" with Weekly (Friday), Weekly (Saturday), Weekly (Sunday), No, not now. No / not now / skip leaves it off and does not ask for a time. Daily or Weekly (Day) asks for a time, then creates a daily cron `{mm} {hh} * * *` or weekly `{mm} {hh} * * {dow}` (0=Sunday … 6=Saturday). Typed "daily" and "weekly monday" parse too. Config gains `cadence` and `weekday`; a missing cadence stays daily, and an owner who already has a schedule is not asked again. Status, Book lines and the monthly check-in say "daily at HH:MM" or "weekly (Monday) at HH:MM". Template version v3.5.19.

### v3.5.18
Bot Terminator sets its own profile picture. The getting-started skill has a new unconditional Step 0, run by the bot itself before any question or delegation: download `skills/bot-terminator-getting-started/bot-terminator-avatar.jpg` from the public update repo to `/workspace/bot-terminator-avatar.jpg` (retry once), read the UpdateAvatar schema (GetDynamicTools, namespace cursor), call UpdateAvatar set with that local path, confirm in one line, or say "I couldn't set my profile picture just now; ask me anytime to try again" and carry on. Updates apply `profile/avatar.png` (512x512 PNG) the same way (UPGRADE.md 5b). Image copies in `assets/`. New `tests/test_avatar_v3518.py`. Template version v3.5.18.

### v3.5.17
Hive Mind is ON by default. First-run setup quietly installs the client, runs `hive on --bot bt`, confirms `hive status` and creates the weekly "Hive Mind weekly share" routine (`hive auto`, silent unless it fails), then sends one notice (no opt-in card, buttons or question). The "Why leave this on?" card (Keep Hive Mind on / Turn off Hive Mind) appears only when the owner asks to turn it off; turning off runs `hive off` and deletes the weekly routine, turning on again recreates it. The monthly check-in shows the Hive Mind status with a one-line reminder and a multi-select card of every on/off setting (`build_monthly_settings_card.build_toggle_card`), flipping only what is picked, with no nudge. New `src/hive_setup.py`, `tests/test_hive_default_on_v3517.py`. Template version v3.5.17.
