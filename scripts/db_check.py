import os
import sqlite3

path = os.environ["COURSEBOX_BACKUP_SOURCE"]
connection = sqlite3.connect(path)
try:
    result = connection.execute("PRAGMA quick_check").fetchone()[0]
finally:
    connection.close()
raise SystemExit(0 if result == "ok" else 1)
