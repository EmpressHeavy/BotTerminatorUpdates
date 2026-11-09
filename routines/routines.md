# Bot Terminator routines (generic)

All times are in the owner's own time zone ({{OWNER_TIME_ZONE}}). Exact prompts: `routine-prompts.md` (monthly) and `weekly-update-check.md`; the others are defined step by step in `skills/bot-terminator-getting-started/SKILL.md` (section named in each row) and use the code in `code/`.

| # | Routine | When | Created | Default |
|---|---|---|---|---|
| 1 | Daily scan | daily at the owner's scan time (setup card, `new_user.SETUP_QUESTIONS`) | setup step 8 | on (owner picks time) |
| 2 | Inactive mutuals card | daily, with the scan | setup | on (card only; nothing removed unless marked) |
| 3 | Terminate reminder ("Hey, want to terminate some bots?") | daily or weekly (chosen weekday) at the owner's chosen time; one-off "Remind me later" follow-ups | setup cadence cards / monthly check-in via `terminate_reminder.set_reminder` | **off** |
| 4 | List returns check | daily, only if list checks are on | setup | **off** |
| 5 | Weekly backup file | weekly, only if backup = "Send me the file" (`records.download_reminder`, sends only when something changed) | setup backup card | owner's backup choice |
| 6 | Backup re-ask | each session start while backup is `pending` (`records.backup_reminder`) | setup | until a backup is chosen |
| 7 | Hive Mind weekly share (`MEM_DB=<path> hive auto`, silent unless it fails) | weekly | setup (Hive Mind on by default); deleted if the owner turns Hive Mind off, recreated if turned back on | **on** |
| 8 | Monthly settings check-in | 1st of month, 10:00 AM (`0 10 1 * *`) | setup | on |
| 9 | Weekly Bot Terminator update check | Sunday 10:00 AM (`0 10 * * 0`) | setup / UPGRADE step 7; re-created monthly | **always on, no off switch** |
