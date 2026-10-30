"""Test helper: a 'connections' block confirmed for a current session (preflight session recheck)."""
import datetime as dt


def confirmed(session_id="test-session"):
    now = dt.datetime.now().astimezone().isoformat()
    return {"session": {"id": session_id, "started_at": now},
            "google_sheets": {"confirmed_at": now, "session_id": session_id},
            "google_drive": {"confirmed_at": now, "session_id": session_id},
            "book_read": {"read_at": now, "session_id": session_id}}
