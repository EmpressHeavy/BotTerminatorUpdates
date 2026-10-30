"""Bridge so the package's REAL write_rows_to_sheet code runs against a sheet reached through another channel
(e.g. an agent's Google Sheets connector) instead of google-api-python-client.

BridgeService implements the calls the writer makes:
  values().get(...).execute()    -> {"values": <rows you read from the real sheet>}
  values().append(...).execute() -> records the call (range, valueInputOption, insertDataOption, values); you then
                                    perform that SAME values.append on the real sheet with the connector (e.g.
                                    append_rows parseInput=true insertRows=true) and feed the response back with
                                    set_append_response() if you want start_row in the writer's result.
Nothing here contacts Google by itself. Used for the 2026-10-16 real-sheet run and the opt-in integration test.
"""
from __future__ import annotations

import csv
import io


def rows_from_csv(text: str) -> list[list[str]]:
    """CSV from a connector read -> rows; trailing empty rows trimmed like the Sheets API does."""
    rows = [list(r) for r in csv.reader(io.StringIO(text or ""))]
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    return rows


class BridgeService:
    def __init__(self, existing_rows):
        self.existing = [list(r) for r in existing_rows]
        self.bodies = []      # legacy batchUpdate bodies (unused by the current writer)
        self.appends = []     # values.append calls made by the writer
        self.append_response = {}
        self._op = None

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, spreadsheetId, range):
        self._op = "get"; return self

    def append(self, spreadsheetId, range, valueInputOption, insertDataOption, body):
        self._op = "app"
        self.appends.append({"range": range, "valueInputOption": valueInputOption,
                             "insertDataOption": insertDataOption, "values": body["values"]})
        return self

    def batchUpdate(self, spreadsheetId, body):
        self._op = "upd"; self.bodies.append(body); return self

    def execute(self):
        if self._op == "app":
            return self.append_response
        return {"values": self.existing} if self._op == "get" and self.existing else {}
