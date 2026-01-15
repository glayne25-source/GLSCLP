import sys
from pathlib import Path

# Ensure repo root is on Python path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.paths import (
    RUNTIME_ROOT,
    INCOMING_RAW,
    LOGS,
)

print("Runtime root:", RUNTIME_ROOT)
print("Incoming:", INCOMING_RAW)
print("Logs:", LOGS)
