-- Bot Terminator records (v3.5.0): the main local store for one owner's scans, removals, graveyard and allowlist.
-- One file per owner: data/users/<user_key>/terminator.db. Starts empty. History tables are append-only
-- (triggers refuse UPDATE/DELETE); a change is a new row (e.g. allowlist op='remove', removals action='restored').
CREATE TABLE IF NOT EXISTS followers(user_id TEXT PRIMARY KEY, handle TEXT, first_seen TEXT, score REAL, reasons TEXT, last_seen TEXT);
CREATE TABLE IF NOT EXISTS removals(id INTEGER PRIMARY KEY, user_id TEXT, handle TEXT,
  action TEXT NOT NULL CHECK(action IN ('removed','blocked','listed','restored')), at TEXT NOT NULL, batch TEXT, result TEXT,
  UNIQUE(user_id, handle, action, at));
CREATE TABLE IF NOT EXISTS graveyard(id INTEGER PRIMARY KEY, user_id TEXT, handle TEXT, added_at TEXT NOT NULL, reason TEXT,
  event TEXT DEFAULT 'REMOVED', UNIQUE(user_id, handle, added_at, event));
CREATE TABLE IF NOT EXISTS allowlist(id INTEGER PRIMARY KEY, user_id TEXT, handle TEXT, added_at TEXT NOT NULL,
  op TEXT NOT NULL DEFAULT 'add' CHECK(op IN ('add','remove')), UNIQUE(user_id, handle, added_at, op));
CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, at TEXT NOT NULL, count INTEGER);
CREATE TABLE IF NOT EXISTS candidates(id INTEGER PRIMARY KEY, scan_id TEXT NOT NULL, user_id TEXT NOT NULL, handle TEXT NOT NULL,
  label TEXT, reasons TEXT, score REAL, UNIQUE(scan_id, user_id, handle));
CREATE TABLE IF NOT EXISTS scan_metrics(id INTEGER PRIMARY KEY, scan_id TEXT NOT NULL, metric TEXT NOT NULL, value TEXT,
  UNIQUE(scan_id, metric));
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, at TEXT NOT NULL, event TEXT NOT NULL, detail TEXT,
  UNIQUE(at, event, detail));
-- v3.5.5: full-fidelity copy of the owner's old Google Sheet (every tab, every column, every row, link formulas kept).
CREATE TABLE IF NOT EXISTS sheet_tabs(id INTEGER PRIMARY KEY, tab TEXT NOT NULL, position INTEGER, header_row INTEGER,
  headers TEXT, preamble TEXT, row_count INTEGER, imported_at TEXT NOT NULL, UNIQUE(tab));
CREATE TABLE IF NOT EXISTS sheet_rows(id INTEGER PRIMARY KEY, tab TEXT NOT NULL, row_num INTEGER NOT NULL, cells TEXT NOT NULL,
  formulas TEXT, imported_at TEXT NOT NULL, UNIQUE(tab, row_num));
CREATE VIEW IF NOT EXISTS current_allowlist AS
  SELECT a.user_id, a.handle, a.added_at FROM allowlist a
  WHERE a.op='add' AND a.id = (SELECT max(b.id) FROM allowlist b WHERE coalesce(b.user_id,'')||'|'||lower(coalesce(b.handle,''))
                                = coalesce(a.user_id,'')||'|'||lower(coalesce(a.handle,'')));
CREATE TRIGGER IF NOT EXISTS removals_no_update BEFORE UPDATE ON removals BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS removals_no_delete BEFORE DELETE ON removals BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS graveyard_no_update BEFORE UPDATE ON graveyard BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS graveyard_no_delete BEFORE DELETE ON graveyard BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS allowlist_no_update BEFORE UPDATE ON allowlist BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS allowlist_no_delete BEFORE DELETE ON allowlist BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS scans_no_update BEFORE UPDATE ON scans BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS scans_no_delete BEFORE DELETE ON scans BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS candidates_no_update BEFORE UPDATE ON candidates BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS candidates_no_delete BEFORE DELETE ON candidates BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS scan_metrics_no_update BEFORE UPDATE ON scan_metrics BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS scan_metrics_no_delete BEFORE DELETE ON scan_metrics BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS sheet_tabs_no_update BEFORE UPDATE ON sheet_tabs BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS sheet_tabs_no_delete BEFORE DELETE ON sheet_tabs BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS sheet_rows_no_update BEFORE UPDATE ON sheet_rows BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS sheet_rows_no_delete BEFORE DELETE ON sheet_rows BEGIN SELECT RAISE(ABORT, 'append-only'); END;
