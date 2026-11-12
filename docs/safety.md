# Safety rules

- Only the owner's own X account. No action, message or post unless the owner asked for it or their chosen mode authorizes it (Automatic Mode: marking on a card and submitting = OK; Manual Mode: an extra yes).
- Protected, never removed: accounts the owner follows, verified accounts, Always Keep, privately protected accounts, Keepers and anyone who interacted with them recently. Missing info = protected. Matched by account ID.
- Pace: one removal at a time ~10 s apart, one run at a time (lock), daily cap 1–100 chosen at setup, each removal verified on X before logging, refuse scans older than 7 days, stop for the day at the first warning or rate limit.
- The bot removes accounts itself in its box browser (signed in by the owner via the sign-in flow). Never hand the owner a TXT/DOCX/HTML report or manual removal steps; the only file is the optional CSV backup.
- Logins: the owner signs in; the bot never asks for or stores passwords, 2FA codes or tokens in chat, files, memory or logs.
- Per-owner data stays under `data/users/<user_key>/` on the owner's own bot computer; never shared or copied. GitHub backup repos must be private and the owner's own.
- Hive Mind: send-only, on by default (one notice at setup, off anytime on request), anonymized lessons only, never personal info; clones never pull lessons.
- Updates: only from github.com/EmpressHeavy/BotTerminatorUpdates; see `UPGRADE.md` guardrails. An update can never enable or perform removals, blocks, messages, posts, logins or deletions.
