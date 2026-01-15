from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\GLSCLP\config")
EBAY = ROOT / "ebay"
SCHEMA = EBAY / "schema"

REQUIRED_FILES = [
    ROOT / "paths.json",
    ROOT / "naming_rules.json",
    ROOT / "thresholds.json",
    EBAY / "title_rules.json",
    EBAY / "policies.json",
    EBAY / "store_categories.json",
    SCHEMA / "index.json",
    SCHEMA / "global_defaults.json",
]

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)


def load_json(path: Path) -> dict:
    if not path.exists():
        fail(f"MISSING FILE: {path}")
        return {}
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        fail(f"EMPTY FILE: {path}")
        return {}
    try:
        return json.loads(txt)
    except Exception as e:
        fail(f"INVALID JSON: {path} :: {e}")
        return {}


def main() -> int:
    # 1) Required files
    for p in REQUIRED_FILES:
        load_json(p)

    # 2) Schema index → category file resolution
    index = load_json(SCHEMA / "index.json")
    cats = index.get("categories")
    if not isinstance(cats, dict):
        fail("schema/index.json missing 'categories' object")
    else:
        for cat_id, cfg in cats.items():
            f = cfg.get("file")
            if not f:
                fail(f"Category {cat_id} has no 'file' defined")
                continue
            cat_path = SCHEMA / f
            if not cat_path.exists():
                fail(f"Category {cat_id} references missing file: {f}")
            else:
                load_json(cat_path)

    # 3) Policies sanity
    policies = load_json(EBAY / "policies.json")
    profile = policies.get("active_profile")
    profiles = policies.get("profiles", {})
    if profile not in profiles:
        fail("policies.json active_profile not found in profiles")

    # 4) Title rules sanity
    title = load_json(EBAY / "title_rules.json")
    if "order" not in title:
        fail("title_rules.json missing 'order'")
    if "max_len" not in title:
        fail("title_rules.json missing 'max_len'")

    # 5) Hard-fail if scaffolding remains
    template = SCHEMA / "cat_BASE_TEMPLATE.json"
    if template.exists():
        fail("Scaffolding file present: cat_BASE_TEMPLATE.json (delete it)")

    # ---- RESULT ----
    if FAILURES:
        print("\nCONFIG VALIDATION FAILED\n")
        for f in FAILURES:
            print(f" - {f}")
        print("\nABORTING RUN.\n")
        return 1

    print("\nCONFIG VALIDATION PASS\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
