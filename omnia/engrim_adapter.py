import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, List

class EngrimAdapter:
    """
    Adapter for timgordontg/engrim (Universal Cross-Model Episodic Memory Standard).
    Provides local-first, project-scoped SQLite memory with FTS5.
    """
    
    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.db_path = self.project_dir / "engrim.db"
        self._init_db()
        
    def _init_db(self):
        """Initializes the SQLite database with FTS5 for episodic memory."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Core Episode Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                agent_id TEXT,
                intent TEXT,
                outcome TEXT,
                context_snapshot TEXT
            )
        ''')
        
        # FTS5 Virtual Table for semantic/hybrid search
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                intent,
                outcome,
                context_snapshot,
                content='episodes',
                content_rowid='id'
            )
        ''')
        
        # Sync triggers
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
                INSERT INTO episodes_fts(rowid, intent, outcome, context_snapshot)
                VALUES (new.id, new.intent, new.outcome, new.context_snapshot);
            END;
        ''')
        
        conn.commit()
        conn.close()

    def record_episode(self, agent_id: str, intent: str, outcome: str, context: Dict[str, Any]):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO episodes (agent_id, intent, outcome, context_snapshot) VALUES (?, ?, ?, ?)",
            (agent_id, intent, outcome, json.dumps(context))
        )
        conn.commit()
        conn.close()
        
    def search_memory(self, query: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT e.id, e.timestamp, e.agent_id, e.intent, e.outcome 
            FROM episodes e
            JOIN episodes_fts fts ON e.id = fts.rowid
            WHERE episodes_fts MATCH ?
            ORDER BY rank
            LIMIT 5
        ''', (query,))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

if __name__ == "__main__":
    # Test initialization
    adapter = EngrimAdapter(Path.cwd())
    print(f"[*] Engrim SQLite Adapter initialized at {adapter.db_path}")
