import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any

DB_NAME = 'sensor_data.db'
RETENTION_DAYS = 15


def get_connection() -> sqlite3.Connection:
    """Get a new SQLite connection (one per thread)."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the readings table if it doesn't exist."""
    conn = get_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            voltage REAL NOT NULL,
            current_val REAL NOT NULL,
            temperature REAL NOT NULL,
            humidity REAL NOT NULL,
            predicted_current REAL DEFAULT 0.0,
            power REAL DEFAULT 0.0,
            relay_state TEXT DEFAULT 'ON'
        )
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_readings_timestamp
        ON readings(timestamp)
    ''')

    # Relay events log table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS relay_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            predicted_current REAL DEFAULT 0.0,
            threshold REAL DEFAULT 0.0
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' initialized.")


def insert_reading(
    voltage: float,
    current_val: float,
    temperature: float,
    humidity: float,
    predicted_current: float = 0.0,
    power: float = 0.0,
    relay_state: str = 'ON'
) -> None:
    """Insert a sensor reading into the database."""
    conn = get_connection()
    conn.execute(
        '''INSERT INTO readings
           (timestamp, voltage, current_val, temperature, humidity,
            predicted_current, power, relay_state)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            voltage,
            current_val,
            temperature,
            humidity,
            predicted_current,
            power,
            relay_state,
        )
    )
    conn.commit()
    conn.close()


def insert_relay_event(
    action: str,
    reason: str,
    predicted_current: float = 0.0,
    threshold: float = 0.0
) -> None:
    """Log a relay state change event."""
    conn = get_connection()
    conn.execute(
        '''INSERT INTO relay_events
           (timestamp, action, reason, predicted_current, threshold)
           VALUES (?, ?, ?, ?, ?)''',
        (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            action,
            reason,
            predicted_current,
            threshold,
        )
    )
    conn.commit()
    conn.close()


def get_readings(hours: int = 1) -> list[dict[str, Any]]:
    """Fetch readings from the last N hours."""
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    rows = conn.execute(
        'SELECT * FROM readings WHERE timestamp >= ? ORDER BY timestamp ASC',
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_relay_events(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch recent relay events."""
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM relay_events ORDER BY timestamp DESC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def cleanup_old_data() -> int:
    """Delete data older than RETENTION_DAYS. Returns number of deleted rows."""
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
    cursor = conn.execute('DELETE FROM readings WHERE timestamp < ?', (cutoff,))
    deleted = cursor.rowcount
    # Also clean old relay events
    conn.execute('DELETE FROM relay_events WHERE timestamp < ?', (cutoff,))
    conn.commit()
    conn.close()
    if deleted > 0:
        print(f"Cleanup: deleted {deleted} rows older than {RETENTION_DAYS} days.")
    return deleted


def start_cleanup_thread() -> None:
    """Start a background daemon thread that runs cleanup every hour."""
    def _cleanup_loop() -> None:
        while True:
            try:
                cleanup_old_data()
            except Exception as e:
                print(f"Cleanup thread error: {e}")
            time.sleep(3600)  # Run every hour

    thread = threading.Thread(target=_cleanup_loop, daemon=True)
    thread.start()
    print("Background cleanup thread started (runs every hour).")


# Initialize the database on module import
init_db()
