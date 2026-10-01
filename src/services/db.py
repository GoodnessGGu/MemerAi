import os
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join("data", "memer_intelligence.db")

class KnowledgeDatabase:
    """SQLite Database for tracking narratives, events, wallets, and token outcomes."""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self):
        # Using check_same_thread=False because it's run in async loop (we'll ensure serialized writes)
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 1. Narratives Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS narratives (
                category TEXT PRIMARY KEY,
                description TEXT,
                created_at TIMESTAMP,
                status TEXT, -- birth, growth, peak, decline, dead
                popularity REAL,
                growth_rate REAL,
                decay_factor REAL
            )
        """)
        
        # 2. Events Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                impact_score REAL,
                description TEXT,
                timestamp TIMESTAMP,
                expected_duration REAL, -- in hours
                affected_narratives TEXT -- comma-separated list
            )
        """)
        
        # 3. Wallets Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                address TEXT PRIMARY KEY,
                label TEXT,
                win_rate REAL,
                total_trades INTEGER,
                roi_mean REAL,
                roi_median REAL,
                specialization TEXT -- e.g. "AI, Meme, Sports"
            )
        """)
        
        # 4. Token Outcomes Table (For tracking outcomes & learning lifespans)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                address TEXT PRIMARY KEY,
                symbol TEXT,
                final_price REAL,
                max_multiple REAL,
                is_rug INTEGER, -- 0 or 1
                duration_hours REAL,
                timestamp TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Knowledge Database initialized at {self.db_path}")

    # --- Narrative Operations ---
    def save_narrative(self, category: str, description: str, status: str, popularity: float, growth_rate: float, decay_factor: float):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO narratives (category, description, created_at, status, popularity, growth_rate, decay_factor)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category) DO UPDATE SET
                description=excluded.description,
                status=excluded.status,
                popularity=excluded.popularity,
                growth_rate=excluded.growth_rate,
                decay_factor=excluded.decay_factor
        """, (category, description, now, status, popularity, growth_rate, decay_factor))
        conn.commit()
        conn.close()

    def get_narrative(self, category: str) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM narratives WHERE category = ?", (category,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_narratives(self) -> list:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM narratives")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # --- Event Operations ---
    def save_event(self, category: str, impact_score: float, description: str, expected_duration: float, affected_narratives: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO events (category, impact_score, description, timestamp, expected_duration, affected_narratives)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (category, impact_score, description, now, expected_duration, affected_narratives))
        conn.commit()
        conn.close()

    def get_recent_events(self, limit: int = 10) -> list:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # --- Wallet Operations ---
    def save_wallet(self, address: str, label: str, win_rate: float, total_trades: int, roi_mean: float, roi_median: float, specialization: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO wallets (address, label, win_rate, total_trades, roi_mean, roi_median, specialization)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                label=excluded.label,
                win_rate=excluded.win_rate,
                total_trades=excluded.total_trades,
                roi_mean=excluded.roi_mean,
                roi_median=excluded.roi_median,
                specialization=excluded.specialization
        """, (address.lower(), label, win_rate, total_trades, roi_mean, roi_median, specialization))
        conn.commit()
        conn.close()

    def get_wallet(self, address: str) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wallets WHERE address = ?", (address.lower(),))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    # --- Token Operations ---
    def save_token_outcome(self, address: str, symbol: str, final_price: float, max_multiple: float, is_rug: bool, duration_hours: float):
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO tokens (address, symbol, final_price, max_multiple, is_rug, duration_hours, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                final_price=excluded.final_price,
                max_multiple=excluded.max_multiple,
                is_rug=excluded.is_rug,
                duration_hours=excluded.duration_hours
        """, (address.lower(), symbol, final_price, max_multiple, int(is_rug), duration_hours, now))
        conn.commit()
        conn.close()

    def get_token_outcome(self, address: str) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tokens WHERE address = ?", (address.lower(),))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
