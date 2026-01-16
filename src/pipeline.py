# C:\GLSCLP\src\pipeline.py
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Local module
from title_builder import build_ebay_title

ROOT = Path(__file__).resolve().parents[1]

SCHEMA_PATH = ROOT / "config" / "ebay" / "schema" / "cat_261328.json"
GLOBALS_PATH = ROOT / "config" / "ebay" / "schema" / "global_defaults.json"
ENFORCED_PATH = ROOT / "config" / "ebay" / "enforced_requirements" / "cat_261328.json"


# ----------------------------
# Utils
# ----------------------------
def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def norm_optional(val: Any) -> str:
    if val is None or val is False:
        return ""
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return ""
        if s.lower() in {"false", "no", "none", "n/a", "na"}:
            return ""
        return s
    return ""


def strip_hash(s: str) -> str:
    s = (s or "").strip()
    return s[1:].strip() if s.startswith("#") else s


def serial_denominator_only_no_slash(serial: Any) -> str:
    s = norm_optional(serial)
    if not s:
        return ""
    s = s.lower().replace("of", "/")
    # "/99" or "12/99"
    if "/" in s:
        parts = s.split("/")
        if len(parts) >= 2 and parts[-1].strip().isdigit():
            return str(int(parts[-1].strip()))
        return ""
    return str(int(s)) if s.isdigit() else ""


def get_player_name(card: Dict[str, Any]) -> str:
    pf = (card.get("player_first") or card.get("player_first_name") or "").strip()
    pl = (card.get("player_last") or card.get("player_last_name") or "").strip()
    return f"{pf} {pl}".strip()


# ----------------------------
# Schema helpers (names only, v1)
# ----------------------------
def schema_aspect_names(schema: Any) -> set:
    names = set()
    if isinstance(schema, list):
        for a in schema:
            if isinstance(a, dict) and a.get("name"):
                names.add(str(a["name"]))
    return names


# ----------------------------
# Build item specifics
# ----------------------------
def build_item_specifics(
    card: Dict[str, Any],
    globals_defaults: Dict[str, Any],
    enforced: Dict[str, Any],
) -> Dict[str, Any]:
    """
    v1 rules:
      - globals_defaults inject always
      - enforced derivations + conditional mappings
      - no allowed-values validation yet (next step)
    """
    item: Dict[str, Any] = {}

    # 1) Start with globals (flat dict of aspect->value)
    # globals_defaults is expected to be a plain dict of aspect->value
    for k, v in globals_defaults.items():
        item[k] = v

    # 2) Copy obvious direct fields if present (typed or dropdown)
    # (No guessing; only pass through if non-empty)
    direct_map = {
        "Player/Athlete": card.get("player_athlete") or card.get("Player/Athlete") or get_player_name(card),
        "Manufacturer": card.get("Manufacturer") or card.get("brand"),
        "Set": card.get("Set") or card.get("set") or card.get("set_name"),
        "Team": card.get("Team") or card.get("team_name") or card.get("team"),
        "Season": card.get("Season") or card.get("year"),
        "Year Manufactured": card.get("Year Manufactured") or card.get("year"),
        "Parallel/Variety": card.get("Parallel/Variety") or card.get("parallel"),
        "Features": card.get("Features"),
        "Insert Set": card.get("Insert Set") or card.get("insert_set") or card.get("insert"),
        "Autographed": card.get("Autographed") or card.get("autographed"),
        "Professional Grader": card.get("Professional Grader") or card.get("grading_company") or card.get("grader"),
        "Grade": card.get("Grade") or card.get("grade") or card.get("numerical_grade"),
        "Card Thickness": card.get("Card Thickness"),
        "Event/Tournament": card.get("Event/Tournament"),
        "League": card.get("League"),
        "Card Name": card.get("Card Name"),
        "Card Number": card.get("Card Number") or card.get("card_number"),
        "Print Run": card.get("Print Run"),
        "Signed By": card.get("Signed By"),
        "Autograph Authentication": card.get("Autograph Authentication"),
        "Autograph Authentication Number": card.get("Autograph Authentication Number"),
        "Autograph Format": card.get("Autograph Format"),
        "California Prop 65 Warning": card.get("California Prop 65 Warning"),
        "Sport": card.get("Sport") or card.get("sport"),
        "Type": card.get("Type"),
    }

    # normalize booleans/false strings to blank for optional fields
    for aspect, raw in direct_map.items():
        if aspect == "Features":
            # features can be list or string; accept list; blank otherwise
            if isinstance(raw, list) and raw:
                item[aspect] = [str(x).strip() for x in raw if str(x).strip()]
            elif isinstance(raw, str) and raw.strip():
                item[aspect] = raw.strip()
        else:
            s = norm_optional(raw)
            if s:
                item[aspect] = s

    # 3) Apply enforce/derive rules (from enforced_requirements)
    dae = enforced.get("derive_and_enforce", {})
    if isinstance(dae, dict):
        for target, rule in dae.items():
            if not isinstance(rule, dict):
                continue
            src = rule.get("from")
            xform = rule.get("transform")

            val = ""
            if src == "player_name":
                val = get_player_name(card)
            elif src == "card_number":
                val = str(card.get("card_number", "")).strip()
            elif src == "serial_number":
                val = str(card.get("serial_number", "")).strip()
            elif src == "year":
                val = str(card.get("year", "")).strip()

            if xform == "strip_hash":
                val = strip_hash(val)
            elif xform == "serial_denominator_only_no_slash":
                val = serial_denominator_only_no_slash(val)

            if val:
                item[target] = val

    # 4) Conditional aspects (Sport->League/Event, thickness default/exception, Prop65 blank)
    ca = enforced.get("conditional_aspects", {})
    sport = (item.get("Sport") or "").strip()

    if isinstance(ca, dict):
        # Prop 65 explicit blank
        if "California Prop 65 Warning" in ca:
            item["California Prop 65 Warning"] = ""

        # League / Event mappings
        for k in ("League", "Event/Tournament"):
            if k in ca and isinstance(ca[k], dict) and sport:
                rules = ca[k].get("rules", [])
                if isinstance(rules, list):
                    for r in rules:
                        when = r.get("when", {})
                        if isinstance(when, dict) and when.get("Sport") == sport:
                            v = norm_optional(r.get("value"))
                            if v:
                                item[k] = v
                            break

        # Card Thickness default unless Memorabilia feature
        if "Card Thickness" in ca and isinstance(ca["Card Thickness"], dict):
            if not norm_optional(item.get("Card Thickness")):
                default = norm_optional(ca["Card Thickness"].get("default"))
                if default:
                    item["Card Thickness"] = default

            feats = item.get("Features", [])
            feats_text = " ".join(feats) if isinstance(feats, list) else str(feats)
            if "Memorabilia" in feats_text:
                item["Card Thickness"] = ""

    # 5) Autograph dependencies (No -> blanks; Yes -> set Signed By/Auth/etc.)
    ar = enforced.get("autograph_rules", {})
    if isinstance(ar, dict) and isinstance(ar.get("Autographed"), dict):
        blk = ar["Autographed"]
        auto = norm_optional(item.get("Autographed"))
        if auto.lower() == "no":
            when_no = blk.get("when_no", {})
            if isinstance(when_no, dict):
                for k, v in when_no.items():
                    item[k] = v
        elif auto.lower() == "yes":
            when_yes = blk.get("when_yes", {})
            if isinstance(when_yes, dict):
                # Signed By = player name (override allowed)
                sb = when_yes.get("Signed By")
                if isinstance(sb, dict) and sb.get("from") == "player_name":
                    item["Signed By"] = get_player_name(card)

                aa = when_yes.get("Autograph Authentication")
                if isinstance(aa, dict) and "value" in aa:
                    item["Autograph Authentication"] = aa["value"]

                # Always blank auth number per your lock
                item["Autograph Authentication Number"] = ""

                # Autograph Format: never allow Cut (policy). If present and not allowed -> blank.
                af = when_yes.get("Autograph Format")
                if isinstance(af, dict):
                    allowed = af.get("allowed_by_policy", [])
                    current = norm_optional(item.get("Autograph Format"))
                    if current and allowed and current not in allowed:
                        item["Autograph Format"] = ""

    # 6) Parallel default [Base]
    pvr = enforced.get("parallel_variety_rules", {})
    if isinstance(pvr, dict):
        if not norm_optional(item.get("Parallel/Variety")):
            item["Parallel/Variety"] = pvr.get("default", "[Base]")

    # 7) Features default Base Set if missing
    fr = enforced.get("features_rules", {})
    if isinstance(fr, dict):
        feats = item.get("Features")
        if not feats:
            item["Features"] = fr.get("default_if_none_detected", ["Base Set"])

    # 8) Print Run: if serial present, enforce derived denominator
    # (even if UI allows typing; your lock says derived)
    serial_raw = card.get("serial_number")
    denom = serial_denominator_only_no_slash(serial_raw)
    if denom:
        item["Print Run"] = denom

    # 9) Insert Set passthrough if present (typed/custom)
    ins = norm_optional(card.get("insert_set") or card.get("insert"))
    if ins:
        item["Insert Set"] = ins

    return item


# ----------------------------
# Main
# ----------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="GLSCLP Pipeline (no eBay push).")
    ap.add_argument("--in", dest="in_path", required=True, help="Input card JSON path")
    ap.add_argument("--out", dest="out_path", default="", help="Optional output JSON path")
    args = ap.parse_args()

    card_path = Path(args.in_path)
    if not card_path.exists():
        print(f"Input file not found: {card_path}", file=sys.stderr)
        return 1

    card = load_json(card_path)
    schema = load_json(SCHEMA_PATH)
    globals_defaults = load_json(GLOBALS_PATH)
    enforced = load_json(ENFORCED_PATH)

    # Title (from title_builder.py)
    title, dropped = build_ebay_title(card)

    # Item specifics
    item_specifics = build_item_specifics(card, globals_defaults, enforced)

    # Minimal schema-aware check (names only; values validation is next)
    allowed_names = schema_aspect_names(schema)
    unknown_names = sorted([k for k in item_specifics.keys() if k not in allowed_names])
    # Keep unknowns in _debug for now (don’t delete silently)
    # You can flip this to an error later.
    payload: Dict[str, Any] = {
        "category_id": "261328",
        "title": title,
        "item_specifics": item_specifics,
        "_debug": {
            "input": card,
            "dropped_title_groups": dropped,
            "unknown_item_specific_names": unknown_names,
        },
    }

    # Always stdout
    print(dump_json(payload))

    # Optional file output (auto-create folders)
    if args.out_path:
        out_path = Path(args.out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(dump_json(payload), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
