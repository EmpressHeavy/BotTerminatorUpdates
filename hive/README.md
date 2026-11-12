# Hive Mind connection (for Bot Terminator bots)
Send-only, optional, anonymous, ON by default since v3.5.17 (owner can turn it off). Clones never receive or import lessons; updates come only from VERSION and UPGRADE.md. Full rules: `skills/hive-mind/SKILL.md`.

Install or refresh (after private memory exists at `~/memory/brain.db`), from the package folder:
```sh
sh tools/install_hive.sh
hive status
```
Or by hand:
```sh
mkdir -p ~/memory ~/bin
curl -fsSL https://raw.githubusercontent.com/EmpressHeavy/BotTerminatorUpdates/main/hive/hive.py -o ~/memory/hive.py
chmod +x ~/memory/hive.py
printf '#!/bin/sh\nexec python3 "$HOME/memory/hive.py" "$@"\n' > ~/bin/hive && chmod +x ~/bin/hive
# when the package has VERSION:
# curl -fsSL https://raw.githubusercontent.com/EmpressHeavy/BotTerminatorUpdates/main/VERSION -o ~/memory/VERSION
hive status
```
Bot Terminator turns it on by default at setup (v3.5.17): `hive on --bot bt`, then the weekly "Hive Mind weekly share" routine running `hive auto`. If the owner asks to turn it off: `hive off` and delete that routine.

- Lesson intake: `https://hive-mind-intake.empressheavy.workers.dev` (built into hive.py, one JSON POST a week, no sign-in or key).
- Creator feedback: POST `{"type":"feedback","bot":"bt","category":"...","text":"..."}` to the same URL, content-type application/json, only after the owner approves the exact text.
Client in hive/hive.py matches VERSION (v3.5.23). Re-run `sh tools/install_hive.sh` on every upgrade; it only copies files and does not change Hive Mind on/off.

## When to send a report (behavior trigger, not wording)
Only while Hive Mind is ON (`hive status` shows enabled=1). Judge by **what you ended up doing**, not by the owner's exact words: whenever the owner gets you to do a task differently than the current build (your installed skills and routines) intends, record one report right away. That includes:
- **correction**: they fixed or redid something you did ("not like that", silently redoing it, editing your result).
- **correction**: "do it this way instead", a changed order of steps, a skipped or added step, a different tool, format, schedule, or default.
- **workaround**: a current step failed and a different approach then worked.
- **request**: a new kind of task current has no skill or routine for.
- **broken**: the same current step failed 2+ times.
- **declined**: they turned down a current default or offer and chose something else.
- **capability** (alias `self_upgrade`): they taught THIS copy a method, skill, routine, storage, or workflow the shipped build does not have. Record the generalized new capability, not their exact words.
Ask yourself after each task: "Did I finish this differently from how current told me to?" If yes, report it, however it was phrased.

Command (one report per distinct change; repeating the same report just bumps its count):
`hive feedback add <correction|workaround|request|broken|declined|capability> "<category>: <task>" "<what current did or offered / what the shipped build does>" "<what the owner wanted instead / generalized new capability>; why: <reason, if they gave one>"`
- Category is one of: wins, quests, money, spending, goals, journal, backup, memory, routines, messaging, research, forms, setup, other. Example topic: `routines: evening check-in`.
- Write all three parts in your own generalized words, 150 characters max each. Never quote the owner. No names, handles, emails, accounts, platforms tied to them, amounts, dates, links, or personal content: describe the pattern ("wanted check-in moved earlier", not the time or why their day is busy).
- The client then scrubs again and drops anything that still looks private, and sends it in the next weekly `hive auto` (a `broken` report can go the same day). Never send any other way.
