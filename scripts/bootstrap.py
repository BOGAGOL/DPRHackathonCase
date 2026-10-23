import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
subprocess.run([sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"], check=True)
subprocess.run([sys.executable, "scripts/manage.py", "grants"], check=True)
