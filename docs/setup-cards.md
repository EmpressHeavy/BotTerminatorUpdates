# Setup cards (exact wording and options)
Generated from the shipped code (`code/src/`), so it matches what the bot sends. The getting-started skill sends them one at a time with tap buttons, in its step order. Owner-specific values appear as {{placeholders}}.

## `records.setup_card`

```json
{
  "message": "Keeping your records safe 🛡️\nI keep a record of every bot I remove for you: who got unfollowed, who's in the graveyard, and who you told me to leave alone. That record is how I keep bots from sneaking back onto your account.\nRight now it lives on my computer, which runs on SpaceXAI's servers. That's fast and private, and it doesn't touch your Google Drive or any of your files. But if something ever happened to my computer, your records could be lost. So I'd like to keep a backup copy too:\n1. GitHub backup (recommended). GitHub is a free online storage service. I'd save your records to a private folder (a \"repository\") that only you can see. It's free, uses no space on your device, and if I ever get reset I can restore everything in seconds. You'd sign in to GitHub (or make a free account) and give me access to that one private folder.\n2. Your own cloud storage or device. I can save your records as a spreadsheet file (CSV) wherever you like: your cloud storage (Google Drive, OneDrive, Dropbox, or another; I'll show a quick sign-in card and keep one folder updated), or your device (I'll send you the file to keep anywhere, including iCloud).\nHand it back to me anytime and I'll restore everything.",
  "note": "I can connect directly to most cloud drives through this app's connectors, so tell me which one you use.",
  "options": [
    "GitHub backup (recommended)",
    "My cloud storage (CSV)",
    "Send me the file (CSV)"
  ],
  "values": {
    "GitHub backup (recommended)": "github",
    "My cloud storage (CSV)": "cloud_csv",
    "Send me the file (CSV)": "download"
  }
}
```

## `records.migration_card`

```json
{
  "question": "Heads up: Bot Terminator is retiring Google Sheets for records. Sheets get bulky and slow as they grow and cost more tokens to read and write. I'm copying everything from your Sheet into your own records file here now (read only, no duplicates). Then pick where I back it up: GitHub (recommended), your cloud storage, or a file I send you. Your Sheet stays exactly where it is as your old copy; I never delete, clear or change it.",
  "options": [
    "Got it, move my records"
  ]
}
```

## `records.upgrade_card`

```json
{
  "question": "Have you used Bot Terminator before?",
  "options": [
    "Yes",
    "No",
    "Not sure"
  ]
}
```

## `terminate_reminder.card`

```json
{
  "multiSelect": false,
  "allowCustom": false,
  "prompt": "Hey, want to terminate some bots?",
  "options": [
    {
      "label": "Yes",
      "value": "Yes"
    },
    {
      "label": "Remind me later",
      "value": "Remind me later"
    },
    {
      "label": "Not today",
      "value": "Not today"
    }
  ]
}
```

## `terminate_reminder.time_card`

```json
{
  "multiSelect": false,
  "allowCustom": true,
  "prompt": "When should I ask again? Tap a time, or type one like 6:30 PM, 18:30 or in 2 hours.",
  "options": [
    {
      "label": "In 1 hour",
      "value": "in 1 hour"
    },
    {
      "label": "In 3 hours",
      "value": "in 3 hours"
    },
    {
      "label": "This evening (6:00 PM)",
      "value": "6:00 PM"
    },
    {
      "label": "Tomorrow morning (9:00 AM)",
      "value": "tomorrow 9:00 AM"
    }
  ]
}
```

## `lists_scan.scope_card`

```json
{
  "multiSelect": false,
  "allowCustom": false,
  "prompt": "Which lists should this check cover?",
  "options": [
    {
      "label": "Only lists from people I don't follow back",
      "value": "not_followed_back"
    },
    {
      "label": "Show all lists",
      "value": "all"
    }
  ]
}
```

## `new_user.SETUP_QUESTIONS`

```json
[
  "How many followers may I remove per day at most? (1-100; I suggest starting low, e.g. 10)",
  "What time should I run the daily scan? (e.g. 09:00, your time zone)",
  "Want a reminder through your front-door bot when the daily cards are ready? (yes/no; this is a ping through a different bot, separate from the chat nudge asked below)",
  "Want me to also check the X lists you've been added to and flag negative ones? (yes/no; default: no, you can turn it on any time)",
  "Want me to nudge you once a day, right here in chat, with \"Hey, want to terminate some bots?\" (yes/no; default: no. This is separate from the front-door reminder above)",
  "What time should I send it? (e.g. 18:00, your time zone; only if you said yes)",
  "Want me to back up your private Bot Terminator memory to a GitHub repo you own? (yes/no; default: no. It must be a private repo, and I use your own GitHub login; no tokens are saved anywhere)",
  "Which private repo should I use? (owner/name, e.g. yourname/bot-terminator-memory; only if you said yes)"
]
```

## `card_text`

```json
{
  "CARD_SIZE": 5,
  "REVIEW_NOTE": "Unmarked accounts will be kept in review.",
  "MARK_ALL_TERMINATION": "Mark all for termination",
  "NA": "Not available",
  "_ABOUT_KEYS": [
    "date_joined",
    "account_based_in",
    "verified",
    "id_verified",
    "username_changes",
    "connected_via"
  ],
  "LABEL_TEXT": {
    "bot": "likely bot",
    "review": "worth a closer look"
  },
  "_BOILER": [
    "unverified",
    "you follow",
    "account based in",
    "30-day activity",
    "last post date",
    "x account country"
  ]
}
```

## Cards defined in the skill text
- **Round review card:** chat message listing the round's accounts (number, x.com/@handle link, label, posts, followers, following, join date, reason), then multi-select "Round N of M: which should I terminate?" with those accounts plus "Mark all 5 for termination" (last round uses its real count). Unmarked accounts will be kept in review.
- **List cards:** 4 lists plus "Remove me from these lists" and "Keep all these lists".
- **Hive Mind (on by default, v3.5.17):** no card at setup, only the exact notice in `skills/bot-terminator-getting-started/SKILL.md` step 10. The "Why leave this on?" card (Keep Hive Mind on / Turn off Hive Mind) is shown only when the owner asks to turn it off. Monthly: Hive Mind is one row in the on/off multi-select card, no nudge.
- **Monthly check-in cards:** see `routines/routine-prompts.md`.
- There is **no** card for automatic updates (always on).
