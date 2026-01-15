from pathlib import Path
import json

# Repo root = parent of /pipeline
PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = PROJECT_ROOT / "config" / "paths.json"
if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")

_paths = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

RUNTIME_ROOT = Path(_paths["runtime_root"])

# Standard runtime locations (authoritative)
INCOMING_RAW = RUNTIME_ROOT / "incoming" / "raw"
WORK_AI = RUNTIME_ROOT / "work" / "ai"
ASSETS_FINAL = RUNTIME_ROOT / "assets" / "final"
QC_NEEDS_REVIEW = RUNTIME_ROOT / "qc" / "needs_review"
OUTGOING_READY = RUNTIME_ROOT / "outgoing" / "ready_to_upload"
LOGS = RUNTIME_ROOT / "logs"
