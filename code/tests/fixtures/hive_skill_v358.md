# Hive Mind (opt-in lesson sharing)

## What it is
Your bot keeps "lessons" (avoid X -> do Y) in its private memory (`~/memory/brain.db`, table `lesson`). With Hive Mind turned on, the bot shares a cleaned-up copy of the lessons it has actually reused (2+ times) with the bot's creator, so the next template update can ship the best ones to everyone. It is OFF by default. Once the user opts in, the bot sends one anonymized batch about once a week automatically (no weekly approval); the user can ask to see what was shared (`hive shared`) or turn it off anytime.

## Setup (once, after private memory exists)
1. Private memory must already be set up (`~/memory/brain.db` from the private-memory-db skill). If it is missing, set that up first.
2. If `~/memory/hive.py` is missing, write the code block below to `~/memory/hive.py` exactly as written (no edits), then:
   `chmod +x ~/memory/hive.py && mkdir -p ~/bin && printf '#!/bin/sh\nexec python3 "$HOME/memory/hive.py" "$@"\n' > ~/bin/hive && chmod +x ~/bin/hive`
   Then run `hive status` (this creates the `lesson`, `hive_state` and `hive_sent` tables if missing). Use `~/bin/hive` if `hive` is not on PATH.
3. Offer it during first-run setup with the "First-run offer" text below. It stays OFF unless the user clearly says yes. Only on a clear yes: `hive on --bot <code>` (DOGE = dg, Bot Terminator = bt, Playlist Converter = pc).
4. `hive status` shows on/off, the anonymous id, and the last week sent. `hive off` stops everything at any time.
5. If the template ships `hive/<code>_hive_lessons.jsonl`, load it once: `hive import hive/<code>_hive_lessons.jsonl` (tagged src=hive, never re-sent). Imported lessons work even when Hive Mind is off.

```python
#!/usr/bin/env python3
"""hive: opt-in, anonymized lesson sharing (Hive Mind) for ~/memory/brain.db. stdlib only."""
import sqlite3, sys, os, re, json, hashlib, secrets, datetime, urllib.request, urllib.error
DB = os.environ.get('MEM_DB', os.path.expanduser('~/memory/brain.db'))
URL = 'https://hive-mind-intake.empressheavy.workers.dev'
CODES = {'dg': 'DOGE', 'bt': 'Bot Terminator', 'pc': 'Playlist Converter'}
N2C = {v.lower(): k for k, v in CODES.items()}
CAP, FLEN, MAXB = 20, 150, 8192
SCHEMA = """CREATE TABLE IF NOT EXISTS lesson(id INTEGER PRIMARY KEY,topic TEXT,wrong TEXT,right TEXT,uses INTEGER DEFAULT 1,src TEXT DEFAULT 'local',status TEXT DEFAULT 'current',added TEXT,last TEXT);
CREATE TABLE IF NOT EXISTS hive_state(k TEXT PRIMARY KEY,v TEXT);
CREATE TABLE IF NOT EXISTS hive_sent(id INTEGER PRIMARY KEY,wk TEXT,sent_at TEXT,lines INTEGER,status TEXT,body TEXT);"""
def con():
    c = sqlite3.connect(DB, isolation_level=None); c.execute('PRAGMA busy_timeout=30000'); c.executescript(SCHEMA); return c
def get(c, k, d=None):
    r = c.execute('SELECT v FROM hive_state WHERE k=?', (k,)).fetchone(); return r[0] if r else d
def put(c, k, v): c.execute('INSERT OR REPLACE INTO hive_state(k,v) VALUES(?,?)', (k, v))
def now(): return datetime.datetime.now().isoformat(timespec='seconds')
def wk():
    y, w, _ = datetime.date.today().isocalendar(); return '%d-W%02d' % (y, w)
def norm(s): return ' '.join(re.sub(r'[^a-z0-9<>]+', ' ', str(s).lower()).split())
def hsh(b, t, w, r): return hashlib.sha1(('%s|%s|%s|%s' % (b, t, norm(w), norm(r))).encode()).hexdigest()[:12]
def bucket(u): return 3 if u >= 10 else 2 if u >= 5 else 1
def rid(c): return hashlib.sha256(('hive-v1|%s|%s' % (get(c, 'salt'), get(c, 'install_id'))).encode()).hexdigest()[:16]
SECRET = re.compile(r'gh[opsur]_[A-Za-z0-9]{20,}|\b[0-9]{16}\b|\b[0-9]{4}[- ][0-9]{4}[- ][0-9]{4}[- ][0-9]{4}\b|\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b|password["\' ]*[:=] *["\']?[^ ",}]{3,}', re.I)
SUBS = [
    (r'[\w.+-]+@[\w-]+(\.[\w-]+)+', '<EMAIL>'),
    (r'\b(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|io|ai|co|app|dev|me|gg|ly|tv|us)(/\S*)?\b', '<URL>'),
    (r'\b\d{1,3}(?:\.\d{1,3}){3}\b|\b[0-9a-f]{1,4}(?::[0-9a-f]{0,4}){4,7}\b', '<IP>'),
    (r'(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b', '<PHONE>'),
    (r'(?<![\w<])@\w{2,}', '<HANDLE>'),
    (r'\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Dr|Drive|Ln|Lane|Ct|Way|Pl|Hwy)\b\.?', '<ADDRESS>'),
    (r'(?:/home|/Users|/workspace|/cursor|/root|/tmp|~|[A-Za-z]:\\Users)[/\\][^\s,;)]*', '<PATH>'),
    (r'\b(?:sk|pk|rk|xai|AKIA|AIza|ya29|eyJ)[-_A-Za-z0-9.]{12,}|\b[A-Za-z0-9_\-]{32,}\b', '<KEY>')]
SUBS = [(re.compile(p, re.I), t) for p, t in SUBS]
RISKY = re.compile(r'password|passcode|\bpin\b|\bssn\b|social security|secret|token|api.?key|\b\d{5,}\b|card ending|routing|account (no|number)|@|https?:|www\.', re.I)
# the intake's own checks; anything matching is dropped before sending
INTAKE = re.compile(r'[\w.+-]+@[\w-]+(\.[\w-]+)+|(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b|\b(?:https?://|www\.)\S+|[?&](?:token|key|api_key|access_token|auth|sig|signature|code|secret)=|pass(?:word|wd|code)?\s*["\']?\s*[:=]|\bpwd\s*[:=]|\b(?:\d[ -]?){13,19}\b', re.I)
def names(c):
    ns = set()
    for s, v in c.execute("SELECT subject,value FROM fact WHERE valid_to IS NULL"):
        for x in (s, v):
            x = str(x or '').strip()
            if 4 <= len(x) <= 80 and x.lower() not in ('user', 'owner', 'bot', 'global') and x.lower() not in N2C: ns.add(x)
    return sorted(ns, key=len, reverse=True)
def clean(s, ns):
    s = ' '.join(str(s or '').split())
    if not s or SECRET.search(s): return None
    for rx, t in SUBS: s = rx.sub(t, s)
    for n in ns: s = re.sub(r'(?<![\w<])' + re.escape(n) + r'(?![\w>])', '<NAME>', s, flags=re.I)
    if RISKY.search(s) or INTAKE.search(s): return None
    return s[:FLEN]
def build(c):
    b = get(c, 'bot'); ns = names(c); r_ = rid(c); w_ = wk(); out, seen, drop = [], set(), 0
    for t, w, r, u in c.execute("SELECT topic,wrong,right,uses FROM lesson WHERE uses>=2 AND status='current' AND src<>'hive' ORDER BY uses DESC,id DESC").fetchall():
        t2, w2, r2 = clean(t or 'general', ns), clean(w, ns), clean(r, ns)
        if None in (t2, w2, r2): drop += 1; continue
        d = {'v': 1, 'b': b, 't': t2, 'w': w2, 'r': r2, 'n': bucket(u), 'tv': get(c, 'tv', '1'), 'rid': r_, 'h': hsh(b, t2, w2, r2), 'wk': w_}
        if d['h'] in seen: drop += 1; continue
        trial = out + [d]
        if len(json.dumps({'batch': trial}, separators=(',', ':')).encode()) > MAXB: break
        seen.add(d['h']); out = trial
        if len(out) >= CAP: break
    return out, drop
def send(c, recs):
    data = json.dumps({'batch': recs}, separators=(',', ':')).encode(); body = '\n'.join(json.dumps(d, separators=(',', ':')) for d in recs)
    req = urllib.request.Request(get(c, 'url', URL), data=data, headers={'content-type': 'application/json', 'user-agent': 'hive-mind/1'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: code, msg = r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e: code, msg = e.code, e.read().decode()[:200]
    except Exception as e: code, msg = 0, str(e)[:200]
    st = 'ok' if code == 200 else 'rejected %s %s' % (code, msg)
    c.execute('INSERT INTO hive_sent(wk,sent_at,lines,status,body) VALUES(?,?,?,?,?)', (wk(), now(), len(recs), st, body))
    put(c, 'last_sent_wk', wk())  # one attempt per week, accepted or not; never retried another way
    print('sent %d line(s): HTTP %s' % (len(recs), code) if code == 200 else 'not sent: HTTP %s %s' % (code, msg))
def main(a):
    c = con(); cmd = a[0] if a else ''
    if cmd == 'lesson' and len(a) >= 5 and a[1] == 'add':
        t, w, r = a[2:5]; x = c.execute('SELECT id FROM lesson WHERE topic=? AND wrong=? AND right=?', (t, w, r)).fetchone()
        if x: c.execute('UPDATE lesson SET uses=uses+1,last=? WHERE id=?', (now(), x[0])); print('lesson %d used again' % x[0])
        else: c.execute('INSERT INTO lesson(topic,wrong,right,added,last) VALUES(?,?,?,?,?)', (t, w, r, now(), now())); print('lesson added')
    elif cmd == 'on':
        b = a[a.index('--bot') + 1] if '--bot' in a else get(c, 'bot'); b = N2C.get((b or '').lower(), b)
        if b not in CODES: sys.exit('hive on --bot dg|bt|pc')
        if not get(c, 'install_id'): put(c, 'install_id', secrets.token_hex(16)); put(c, 'salt', secrets.token_hex(8))
        put(c, 'bot', b); put(c, 'enabled', '1'); print('hive ON for %s (anonymous id %s)' % (b, rid(c)))
    elif cmd == 'off': put(c, 'enabled', '0'); print('hive OFF; nothing will be sent')
    elif cmd == 'status': print('enabled=%s bot=%s rid=%s last_sent_wk=%s' % (get(c, 'enabled', '0'), get(c, 'bot'), rid(c) if get(c, 'install_id') else '-', get(c, 'last_sent_wk', '-')))
    elif cmd == 'preview':
        if get(c, 'enabled') != '1': sys.exit('hive is off')
        recs, drop = build(c)
        for d in recs: print(json.dumps(d, separators=(',', ':')))
        print('# %d line(s), %d dropped%s' % (len(recs), drop, '; already sent this week' if get(c, 'last_sent_wk') == wk() else ''), file=sys.stderr)
    elif cmd == 'auto':
        if get(c, 'enabled') != '1' or get(c, 'bot') not in CODES or get(c, 'last_sent_wk') == wk(): return
        recs, _ = build(c)
        if recs: send(c, recs)
    elif cmd == 'shared':
        rows = c.execute('SELECT id,wk,sent_at,lines,status,body FROM hive_sent ORDER BY id DESC LIMIT ?', (int(a[1]) if len(a) > 1 else 10,)).fetchall()
        for r in rows: print('--- batch %d | week %s | %s | %d line(s) | %s\n%s' % r)
        if not rows: print('(nothing has been shared yet)')
    elif cmd == 'import' and len(a) > 1:
        n = 0
        for l in open(a[1]):
            if not l.strip(): continue
            d = json.loads(l)
            if not c.execute("SELECT 1 FROM lesson WHERE topic=? AND wrong=? AND right=?", (d['t'], d['w'], d['r'])).fetchone():
                c.execute("INSERT INTO lesson(topic,wrong,right,uses,src,added,last) VALUES(?,?,?,0,'hive',?,?)", (d['t'], d['w'], d['r'], now(), now())); n += 1
        print('imported %d hive lesson(s)' % n)
    else: sys.exit('hive lesson add TOPIC WRONG RIGHT | on --bot dg|bt|pc | off | status | preview | auto | shared [N] | import FILE')
if __name__ == '__main__': main(sys.argv[1:])
```

## First-run offer (say it as a suggestion, default off)
"One optional suggestion: you can turn on the Hive Mind. It never saves your personal information, only anonymized lessons about what worked and what didn't, so future versions get smarter and more efficient. Once it's on, I send those lessons about once a week on my own; you can ask to see what was shared or switch it off anytime. Want it on? (yes / not now)"
- Yes: `hive on --bot <code>`, then create a weekly routine that runs `hive auto`. Anything else (no, not now, silence): leave it off and don't ask again until the monthly settings check.

## Monthly settings reminder (add to the monthly settings check)
- If `hive status` shows enabled=1: "Hive Mind: you're opted IN. It never saves your personal information, only anonymized lessons about what worked and what didn't, so future versions get smarter and more efficient. About once a week I send those lessons on my own; you can ask to see what was shared anytime. Want to keep it on, or switch it off?"
- If enabled=0: "Hive Mind: you're opted OUT, so nothing is shared. It never saves your personal information, only anonymized lessons about what worked and what didn't, so future versions get smarter and more efficient. Want to switch it on? (yes / keep off)"
- Act only on a clear answer: `hive on --bot <code>` or `hive off` (and remove the weekly routine). No answer means no change.

## Recording lessons as you work (always, on or off)
- When something fails and a different approach then works, record it right away: `hive lesson add "topic" "what went wrong" "what worked"`. Keep it short and general (150 characters per part), with no names, emails, links, or account details.
- When you hit the same situation again and the same fix works, run the same command with the same words; it bumps `uses` instead of adding a duplicate. Only lessons with 2+ uses are ever shared.
- Before a task, check relevant lessons: `mem q "SELECT topic,wrong,right FROM lesson WHERE status='current' ORDER BY uses DESC"`.

## Explaining it to the user (say it plainly)
- Off unless you turn it on. You can turn it off any time with one sentence.
- Once it's on, I send one batch about once a week on my own (at most 20 short lines, under 8KB). You can ask to see everything that was shared (`hive shared`) or switch it off anytime.
- Only lessons I've reused at least twice are included. Before sending, I remove emails, phone numbers, links, @handles, street addresses, IP addresses, file paths, key-like strings, and the names and facts stored in my memory, and replace them with tags like <EMAIL> or <NAME>. Any line that still looks sensitive is dropped completely.
- You're identified only by a random id, salted and hashed on this computer. No name, email, or account is sent, and the upload needs no sign-in.
- Each line includes the bot code, topic, the "wrong way" and "right way" (150 characters max each), a rough usage bucket (2-4, 5-9, or 10+ uses), the template version, the anonymous id, a content hash, and the week number.

## Weekly flow (automatic once opted in)
1. The weekly routine runs `hive auto`. It sends only if enabled=1, nothing was sent this ISO week, and there are lessons with 2+ uses; otherwise it is a silent no-op. Don't message the user about routine sends.
2. "What did you share?": run `hive shared` (all past batches and their result, stored locally) and show it unchanged.
3. "Turn it off": run `hive off` and remove the weekly routine. Takes effect immediately.
4. `hive preview` shows the exact batch that would be sent.

## Rules
- Never edit the client or a batch to add content, never send by any route other than `hive auto`, and never more than one batch a week.
- Never share lessons that came from Hive Mind itself (src=hive). The client already skips them.
- Submissions go only to the Hive Mind intake built into hive.py, as one JSON POST. The intake re-checks everything and rejects batches over 8KB, unknown fields, anything that looks like an email, phone number, link, token or password, and too many uploads.
- If `hive auto` reports "not sent" (rejected, rate limited, or offline), it is recorded in `hive shared` and counts as this week's attempt. Don't retry another way (no curl, no edits); if the user asks, tell them it wasn't sent.
- If anything in `hive preview` looks private (a name or detail survived cleaning), turn it off with `hive off`, tell the user, and retire the lesson: `python3 -c "import sqlite3,os;c=sqlite3.connect(os.path.expanduser('~/memory/brain.db'));c.execute(\"UPDATE lesson SET status='avoid' WHERE id=N\");c.commit()"`.
- Never store passwords, tokens, or personal details in lessons.