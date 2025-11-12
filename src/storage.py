
# storage.py
import sqlite3, json, time
from typing import Dict, Any, List

class SQLiteStore:
    def __init__(self, path: str = "wq_graph.db"):
        self.conn = sqlite3.connect(path)
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS snapshots(
            ts INTEGER, round_idx INTEGER, state_json TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS leaderboard(
            ts INTEGER, expr TEXT, settings_json TEXT, score REAL, comment TEXT
        )""")
        self.conn.commit()

    def save_snapshot(self, round_idx: int, state: Dict[str, Any]):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO snapshots VALUES(?,?,?)",
                    (int(time.time()), round_idx, json.dumps(state)))
        self.conn.commit()

    def load_latest_snapshot(self) -> Dict[str, Any]:
        cur = self.conn.cursor()
        row = cur.execute("SELECT state_json FROM snapshots ORDER BY ts DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else {}

    def add_leaderboard(self, expr: str, settings: Dict[str, Any], score: float, comment: str = ""):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO leaderboard VALUES(?,?,?,?,?)",
                    (int(time.time()), expr, json.dumps(settings), score, comment))
        self.conn.commit()

    def top_k(self, k: int = 5) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        rows = cur.execute("SELECT expr, settings_json, score, ts FROM leaderboard ORDER BY score DESC LIMIT ?", (k,)).fetchall()
        return [{"expr": r[0], "settings": json.loads(r[1]), "score": r[2], "ts": r[3]} for r in rows]
