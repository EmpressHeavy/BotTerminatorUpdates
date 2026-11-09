# Hive Mind (on by default: lesson and owner-feedback sharing)

## What it is
Your bot keeps Hive items in its private memory (`~/memory/brain.db`, table `lesson`, column `kind`):
- **Lessons** (kind `lesson`): something failed and a different approach then worked (avoid X -> do Y).
- **Owner feedback** (kinds `correction`, `request`, `declined`, `broken`, `workaround`): any time the owner has the bot do something differently from how it was built to work. This is the creator's only direct line to owners: the Marketplace has no developer-to-user support channel, and feedback posted on social media is easily missed. If it isn't recorded here, the creator will probably never know.
- **Owner-taught capability** (kind `capability`; `self_upgrade` is an alias stored as `capability`): the owner taught THIS copy a method, skill, routine, storage, or workflow the shipped build does not have. Record the outcome, not the exact words they used.

With Hive Mind turned on, the bot shares a cleaned-up, anonymized copy of these items with the bot's creator, so the next template update can fix what's broken, add what owners ask for, and ship fixes to everyone in the next update. For Bot Terminator it is ON by default (v3.5.17). While it is on, the bot sends one anonymized batch about once a week automatically (no weekly approval), plus, only for something reported broken, at most one small urgent batch a day; the user can ask to see what was shared (`hive shared`) or turn it off anytime.

## Setup (once, after private memory exists)
1. Private memory must already be set up (`~/memory/brain.db` from the private-memory-db skill). If it is missing, set that up first.
2. Install or refresh the Hive Mind client exactly as shipped in the Bot Terminator package (pinned tag, verified fingerprint). From the package folder (`/workspace/bot-terminator/`, the update repo's `code/`) run `sh tools/install_hive.sh`. Do this on first setup when `~/memory/hive.py` is missing, and again on every template upgrade even if that file is already there (`hive_setup.upgrade_client_plan`). If the script cannot run, copy `hive/hive.py` to `~/memory/hive.py` (and `VERSION` to `~/memory/VERSION` when the package has one). It copies `hive/hive.py` unchanged and writes the wrapper `~/bin/hive` (`#!/bin/sh` / `exec python3 "$HOME/memory/hive.py" "$@"`). Never edit hive.py. Re-running only copies files: it sends nothing and does not turn Hive Mind on or off. Then run `hive status` (this creates the `lesson`, `hive_state`, `hive_sent` and `hive_sent_h` tables if missing, and adds the `kind` and `shared` columns to an older `lesson` table). Use `~/bin/hive` if `hive` is not on PATH.
3. During first-run setup, turn it on quietly: `hive on --bot bt`, confirm `hive status` shows enabled=1, and create the weekly "Hive Mind weekly share" routine (`hive auto`, silent unless it fails). No opt-in card, buttons or question; send only the notice below.
4. `hive status` shows on/off, the anonymous id, the last week sent, the last urgent day and the template version. `hive off` stops everything at any time.
5. Send-only: clones never receive, pull or import lessons. Improvements arrive only as versioned updates from the update repo (VERSION + UPGRADE.md).


## First-run notice (no card, no question)
"Just so you are aware, Bot Terminator is equipped with a system called Hive Mind, which gets end-user feedback to my creator so you don't have to reach out via social media and risk your feedback getting missed. Hive Mind does NOT save any of your personal information, only anonymized lessons about what worked and what didn't, so future versions of me can get smarter and work more efficiently. I send those lessons about once a week on my own. :)"

## Only if the owner asks to turn it off
Send a widget card whose prompt is exactly: "Why leave this on? It's a backup way to let my creator know what's working and what isn't, so they can improve me. Unless you tell the developer directly, they won't know something needs fixing, and there's no guarantee they'll see your feedback on social media. (We really hope they do, so may the algorithm be in your favor 🎲) Your personal info is never shared, and you can turn it off anytime."
Buttons: **Keep Hive Mind on** (leave it on) and **Turn off Hive Mind** (run `hive off`, delete the "Hive Mind weekly share" routine, confirm in one line). If they later ask to turn it on: `hive on --bot bt` and recreate the routine.

## Monthly settings check
Show the Hive Mind status with all their other settings, plus the one-line reminder: "Hive Mind sends anonymized lessons about what worked and what didn't (never your personal info) about once a week, so future versions of me improve." Then list Hive Mind with its current state in the multi-select on/off card together with their other on/off settings, and flip only what they pick. No "Why leave this on?" nudge here. Keep the weekly routine only while Hive Mind is on.

## Recording owner feedback as you work (always, on or off, even if it happens only ONCE)
Record a Hive item the moment the owner does any of these, whether or not Hive Mind is on (it stays private while Hive Mind is off):
- **Corrects you** or tells you that you did something wrong: `hive feedback add correction "topic" "what I did" "what the owner wanted instead"`.
- **Asks for a different way** than the one you were built to use (a different storage, flow, format, schedule, card, wording or tool), or you change your approach because of what they said: also `correction`.
- **Declines a feature or setup step** you offered (for example they don't want Google Sheets and want logging kept on the bot's own computer): `hive feedback add declined "topic" "what I offered" "what the owner wanted instead"`.
- **Requests a feature** or suggests an improvement the bot doesn't have: `hive feedback add request "topic" "what is missing" "what the owner asked for"`.
- **Reports something broken** or not working (an error, a step that never finishes, wrong results, a button that does nothing): `hive feedback add broken "topic" "what broke" "what the owner saw or did instead"`.
- **Uses a workaround** because the normal way didn't fit them: `hive feedback add workaround "topic" "the normal way" "the workaround that worked"`.
- **Taught this copy something the shipped build does not do** (a new or changed method, skill, routine, storage, or workflow, so THIS copy now does something the template doesn't): immediately `hive feedback add capability "<area>" "<what the shipped build does>" "<generalized new capability>"`. `hive feedback add self_upgrade ...` is the same kind. Trigger on the outcome, not on a particular phrase.

How to write it:
- One item per change, recorded right away, not saved up. Short and general (150 characters per part), in plain words about the bot's behavior.
- Anonymized: no names, handles, emails, links, numbers, file paths, secrets, account IDs, or quotes of private content. Write "the owner" and describe the feature or method, not the person. A `capability` line is the generalized feature only (150 characters per part); the same scrub as the other kinds replaces what it can and drops any line that still looks sensitive. Example: `hive feedback add declined "storage" "offered a google sheets log for follower records" "owner wanted local logging on the bot computer instead"`. Example: `hive feedback add capability "storage" "shipped build logs follower records in a sheet" "this copy can keep that log on the bot computer"`.
- If the same thing happens again, run the same command with the same words; it bumps `uses` instead of adding a duplicate.
- Owner feedback, including `capability`, is eligible to share after ONE use. It is still kept in this private memory when Hive Mind is off.
- A `capability` item is not urgent. It goes out in the normal weekly batch. After recording a `broken` item, if Hive Mind is on, run `hive auto` right away (it sends at most one small urgent batch a day, with only the not-yet-sent broken items; otherwise it does nothing). Recording a capability does not by itself send an urgent batch.
- A line that was already sent (its hash is in `hive_sent_h`, or the row is marked shared) is not sent again in a later ISO week.
- The getting-started feedback offer (v3.5.14) sends through this same client with the one-shot command: on a clear yes, `hive feedback --bot bt --category bug|request|praise|other "text" --dry-run` shown to the owner, then the same without `--dry-run` (only that item; own small daily allowance). Record the Hive item even when the owner says no.

## Recording lessons as you work (always, on or off)
- When something fails and a different approach then works, record it right away: `hive lesson add "topic" "what went wrong" "what worked"`. Keep it short and general (150 characters per part), with no names, emails, links, or account details.
- When you hit the same situation again and the same fix works, run the same command with the same words; it bumps `uses` instead of adding a duplicate. Lessons are shared only once they have 2+ uses.
- Before a task, check relevant lessons: `mem q "SELECT kind,topic,wrong,right FROM lesson WHERE status='current' ORDER BY uses DESC"`.

## Explaining it to the user (say it plainly)
- On by default. You can turn it off any time with one sentence.
- Once it's on, I send one batch about once a week on my own (at most 20 short lines, under 8KB). If you tell me something is broken, I may send that one item sooner, at most once a day. You can ask to see everything that was shared (`hive shared`) or switch it off anytime.
- What's included: lessons I've reused at least twice, and short notes about anything you asked me to do differently, declined, asked for, or reported broken, so my creator can fix it. Before sending, I remove emails, phone numbers, links, @handles, street addresses, IP addresses, file paths, key-like strings, and the names and facts stored in my memory, and replace them with tags like <EMAIL> or <NAME>. Any line that still looks sensitive is dropped completely.
- You're identified only by a random id, salted and hashed on this computer. No name, email, or account is sent, and the upload needs no sign-in.
- Each line includes the bot code, the kind (lesson, correction, request, declined, broken, workaround, capability), topic, the "what happened" and "what was wanted / what worked" parts (150 characters max each), a rough usage bucket (1-4, 5-9, or 10+ uses), the template version, the anonymous id, a content hash, and the week number.

## Weekly flow (automatic while on)
1. The weekly routine runs `hive auto`. It sends only if enabled=1, nothing was sent this ISO week, and there are items to share (feedback with 1+ use, lessons with 2+ uses); otherwise it is a silent no-op. Don't message the user about routine sends.
2. Urgent exception: if this week's batch already went out and there is a `broken` item that hasn't been sent yet, `hive auto` sends only those broken items (at most 5) as one urgent batch, at most once a day. `capability` is not urgent. The intake enforces the same limits. A hash already in `hive_sent_h` is skipped in the weekly batch and in the urgent batch, so a correction sent one ISO week is not sent the next.
3. "What did you share?": run `hive shared` (all past batches and their result, stored locally) and show it unchanged.
4. "Turn it off": run `hive off` and remove the weekly routine. Takes effect immediately.
5. `hive preview` shows the exact weekly batch that would be sent. `hive auto --dry-run` builds the exact payload `hive auto` would send right now (weekly or urgent), prints it, records it in `hive shared` as "dry-run", and never uses the network or the weekly/daily allowance.

## Rules
- Never edit the client or a batch to add content, never send by any route other than `hive auto`, never more than one weekly batch a week, and never more than one urgent (broken-only) batch a day.
- Never share items that came from Hive Mind itself (src=hive). The client already skips them.
- Submissions go only to the Hive Mind intake built into hive.py, as one JSON POST. The intake re-checks everything and rejects batches over 8KB, unknown fields or kinds, anything that looks like an email, phone number, link, token or password, urgent batches with anything other than broken items, and too many uploads.
- If `hive auto` reports "not sent" (rejected, rate limited, or offline), it is recorded in `hive shared` and counts as that week's (or that day's urgent) attempt. Don't retry another way (no curl, no edits); if the user asks, tell them it wasn't sent.
- If anything in `hive preview` looks private (a name or detail survived cleaning), turn it off with `hive off`, tell the user, and retire the item: `python3 -c "import sqlite3,os;c=sqlite3.connect(os.path.expanduser('~/memory/brain.db'));c.execute(\"UPDATE lesson SET status='avoid' WHERE id=N\");c.commit()"`.
- Never store passwords, tokens, or personal details in lessons or feedback.
