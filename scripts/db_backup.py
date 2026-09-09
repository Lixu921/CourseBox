import os
import sqlite3


source_path = os.environ["COURSEBOX_BACKUP_SOURCE"]
target_path = os.environ["COURSEBOX_BACKUP_TARGET"]
source = sqlite3.connect(source_path)
target = sqlite3.connect(target_path)
try:
    source.backup(target)
finally:
    target.close()
    source.close()
