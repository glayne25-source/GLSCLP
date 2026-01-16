from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EBAY_TITLE_MAX = 80


def _clean(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _join_tokens(tokens: List[str]) -> str:
    return _clean(" ".join([_clean(t) for t in tokens if _clean(t)]))


def _norm_optional(val: Any) -> str:
    """
    Optional field normalization:
    - False/None/"" -> missing
    - "false"/"no"/"none"/"n/a" -> missing
    - Any other string -> stripped string
    - Any other type -> missing (we don't stringify booleans/ints into titles)
    """
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


def _parse_serial_for_ebay(serial_raw: Any) -> Optional[str]:
    """
    Title serial rules:
    - Default format: "/99", "/199", etc.
    - Include leading number only if:
        a) first == 1  (e.g., 1/99)
        b) first == denom (e.g., 99/99)
    Accepts: "/99", "12/99", "099/199", "1/1", "99/99", "of99" variants.
    """
    s = _norm_optional(serial_raw)
    if not s:
        return None

    # normalize common variants: "of99" -> "/99"
    s = re.sub(r"\bof\b", "/", s, flags=re.IGNORECASE)

    # full fraction like 12/99
    m = re.search(r"(\d+)\s*/\s*(\d+)", s)
    if m:
        first = int(m.group(1))
        denom = int(m.group(2))
        if denom <= 0:
            return None
        if first == 1 or first == denom:
            return f"{first}/{denom}"
        return f"/{denom}"

    # denom-only like "/99"
    m2 = re.search(r"/\s*(\d+)", s)
    if m2:
        denom = int(m2.group(1))
        if denom <= 0:
            return None
        return f"/{denom}"

    return None


@dataclass
class TitleInputs:
    # Required (always included)
    year: str
    brand: str
    set_name: str
    player_first: str
    player_last: str
    card_number: str

    # Optional (include only if present)
    insert: str = ""
    parallel: str = ""
    auto_patch: str = ""        # "Auto" | "Patch" | "Patch Auto"
    serial_raw: Any = ""        # raw; will be normalized to "/99" etc.
    grading_company: str = ""   # PSA, BGS, SGC, CGC, etc.
    numerical_grade: str = ""   # 10, 9.5, etc.
    team_city: str = ""         # full city name, no abbreviations (assumed upstream)
    team_name: str = ""
    rookie: str = ""            # e.g. "Rookie" or "RC"


def build_ebay_title(card: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Returns: (final_title, dropped_groups)
    - dropped_groups are optional groups removed to satisfy 80-char limit.
    Raises ValueError if mandatory fields alone exceed 80 characters.
    """
    # Required fields: stringify (but clean whitespace)
    year = _clean(str(card.get("year", "")))
    brand = _clean(str(card.get("brand", "")))
    set_name = _clean(str(card.get("set", card.get("set_name", ""))))
    player_first = _clean(str(card.get("player_first", card.get("player_first_name", ""))))
    player_last = _clean(str(card.get("player_last", card.get("player_last_name", ""))))
    card_number = _clean(str(card.get("card_number", card.get("card_no", ""))))

    inp = TitleInputs(
        year=year,
        brand=brand,
        set_name=set_name,
        player_first=player_first,
        player_last=player_last,
        card_number=card_number,

        insert=_norm_optional(card.get("insert", card.get("insert_set"))),
        parallel=_norm_optional(card.get("parallel", card.get("variety"))),
        auto_patch=_norm_optional(card.get("auto_patch", card.get("auto_patch_type"))),
        serial_raw=card.get("serial", card.get("serial_number")),
        grading_company=_norm_optional(card.get("grading_company", card.get("grader"))),
        numerical_grade=_norm_optional(card.get("numerical_grade", card.get("grade"))),
        team_city=_norm_optional(card.get("team_city")),
        team_name=_norm_optional(card.get("team_name", card.get("team"))),
        rookie=_norm_optional(card.get("rookie", card.get("rc"))),
    )

    # Mandatory block (per latest spec)
    mandatory_tokens = [
        inp.year,
        inp.brand,
        inp.set_name,
        inp.player_first,
        inp.player_last,
        inp.card_number,
    ]

    serial_fmt = _parse_serial_for_ebay(inp.serial_raw) or ""

    # Optional groups in your latest token order:
    # Insert, Parallel, Auto/Patch, Serial, Grading Company, Numerical Grade, Team City, Team Name, Rookie
    group_values: Dict[str, str] = {
        "insert": _join_tokens([inp.insert]),
        "parallel": _join_tokens([inp.parallel]),
        "auto_patch": _join_tokens([inp.auto_patch]),
        "serial": _join_tokens([serial_fmt]),
        "grading_company": _join_tokens([inp.grading_company]),
        "numerical_grade": _join_tokens([inp.numerical_grade]),
        "team_city": _join_tokens([inp.team_city]),
        "team_name": _join_tokens([inp.team_name]),
        "rookie": _join_tokens([inp.rookie]),
    }

    include_order = [
        "insert",
        "parallel",
        "auto_patch",
        "serial",
        "grading_company",
        "numerical_grade",
        "team_city",
        "team_name",
        "rookie",
    ]

    # Build initial title
    tokens = mandatory_tokens[:]
    for k in include_order:
        if group_values.get(k):
            tokens.append(group_values[k])

    title = _join_tokens(tokens)

    # 80-char enforcement drop priority:
    # Drop lowest priority first. (Grading fields aren't specified in your priority list, so they drop low.)
    drop_priority = [
        "team_city",
        "team_name",
        "numerical_grade",
        "grading_company",
        "parallel",
        "insert",
        "serial",
        "auto_patch",
        "rookie",
    ]

    dropped: List[str] = []
    if len(title) > EBAY_TITLE_MAX:
        active = dict(group_values)  # copy
        for k in drop_priority:
            if len(title) <= EBAY_TITLE_MAX:
                break
            if active.get(k):
                active[k] = ""
                dropped.append(k)

                rebuilt = mandatory_tokens[:]
                for kk in include_order:
                    if active.get(kk):
                        rebuilt.append(active[kk])
                title = _join_tokens(rebuilt)

    if len(title) > EBAY_TITLE_MAX:
        raise ValueError(
            f"Mandatory fields exceed {EBAY_TITLE_MAX} chars after drops. "
            f"Title='{title}' ({len(title)} chars)"
        )

    return title, dropped


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python title_builder.py <card.json>")
        return 2

    p = Path(sys.argv[1])
    card = json.loads(p.read_text(encoding="utf-8"))

    title, dropped = build_ebay_title(card)
    print(title)
    if dropped:
        print("\n[DROPPED]", ",".join(dropped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
