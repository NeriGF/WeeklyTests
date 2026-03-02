import json
import uuid
import datetime as dt
import re
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import requests

SCOPE = "lrm.priceTesting.overviewScreen.productIds"


# -----------------------------
# Helpers
# -----------------------------
def utc_now_iso_z() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def split_streaming_json(raw: bytes) -> List[Dict[str, Any]]:
    parts = [p for p in raw.split(b"\x00") if p.strip()]
    return [json.loads(p.decode("utf-8")) for p in parts]

def show_invisibles(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if ch == " ":
            out.append("␠")
        elif ch == "\t":
            out.append("⇥")
        elif ch == "\n":
            out.append("↩")
        elif ch == "\r":
            out.append("␍")
        elif o == 0x00A0:
            out.append("⍽")  # NBSP
        elif o in (0x200B, 0x200C, 0x200D, 0xFEFF):
            out.append(f"⟦ZW{o:04X}⟧")
        else:
            out.append(ch)
    return "".join(out)

def hygiene_issues(pids: List[str]) -> List[str]:
    issues = []
    for p in pids:
        if p != p.strip():
            issues.append(f"leading/trailing whitespace: {show_invisibles(p)}")
        if re.search(r"[\u00A0\u200B\u200C\u200D\uFEFF]", p):
            issues.append(f"invisible unicode: {show_invisibles(p)}")
    return issues

def extract_scope_result(records: List[Dict[str, Any]], scope: str) -> Tuple[List[str], Dict[str, Any]]:
    """
    Returns (product_ids, decision_payload)
    """
    for rec in records:
        for h in rec.get("handle", []):
            if h.get("type") != "personalization:decisions":
                continue
            for decision in h.get("payload", []):
                if decision.get("scope") != scope:
                    continue
                for item in decision.get("items", []):
                    data = item.get("data", {})
                    content = data.get("content")
                    if isinstance(content, dict) and isinstance(content.get("product_ids"), list):
                        return content["product_ids"], decision
    return [], {}

def decision_activity_experience(decision: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    sd = decision.get("scopeDetails", {}) or {}
    act = (sd.get("activity", {}) or {}).get("id")
    exp = (sd.get("experience", {}) or {}).get("id")
    return act, exp

def apply_case(base: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Minimal overrides per case: country, build_id, logged_in/out.
    Generates fresh _id + timestamp.
    """
    b = deepcopy(base)

    now = utc_now_iso_z()
    b["events"][0]["xdm"]["timestamp"] = now
    b["events"][0]["xdm"]["_id"] = str(uuid.uuid4()).upper()

    tgt = b["events"][0]["data"]["__adobe"]["target"]
    tgt["appStoreCountryCode"] = case["appStoreCountryCode"]
    tgt["a.build_id"] = case["build_id"]

    ident = b.setdefault("xdm", {}).setdefault("identityMap", {})
    if case.get("logged_in", True):
        # keep adobeGUID if present in base
        pass
    else:
        ident.pop("adobeGUID", None)

    return b


# -----------------------------
# Expectations
# -----------------------------
def matches(rule_when: Dict[str, Any], case: Dict[str, Any]) -> bool:
    for k, v in rule_when.items():
        if case.get(k) != v:
            return False
    return True

def validate_expected(rules: List[Dict[str, Any]], case: Dict[str, Any], delivered: List[str]) -> Tuple[bool, str]:
    applicable = [r for r in rules if matches(r.get("when", {}), case)]
    if not applicable:
        return True, "no expectation rule matched"

    delivered_set = set(delivered)
    for r in applicable:
        for option in r.get("expect_any_of", []):
            if set(option) == delivered_set:
                return True, "matched expected"
    return False, f"expected one of: {applicable[0].get('expect_any_of')}"


# -----------------------------
# Diffing
# -----------------------------
def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text())

def diff_latest(prev: Optional[Dict[str, Any]], curr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produces a structured diff:
    - scenario changes in activity/experience/pids
    - new activities detected
    """
    out = {"changed": [], "new_activities": [], "summary": {}}

    prev_cases = {c["name"]: c for c in (prev.get("cases", []) if prev else [])}
    curr_cases = {c["name"]: c for c in curr.get("cases", [])}

    prev_acts = set(prev.get("activities_seen", []) if prev else [])
    curr_acts = set(curr.get("activities_seen", []))

    for act in sorted(curr_acts - prev_acts):
        out["new_activities"].append(act)

    for name, c in curr_cases.items():
        p = prev_cases.get(name)
        if not p:
            out["changed"].append({"name": name, "type": "new_case", "current": c})
            continue

        changed_fields = {}
        for key in ["activityId", "experienceId", "product_ids", "hygiene_issues", "expectation_ok"]:
            if p.get(key) != c.get(key):
                changed_fields[key] = {"from": p.get(key), "to": c.get(key)}

        if changed_fields:
            out["changed"].append({"name": name, "type": "changed", "fields": changed_fields})

    out["summary"] = {
        "total_cases": len(curr_cases),
        "failed_cases": sum(1 for c in curr_cases.values() if not c.get("ok", False)),
        "new_activities_count": len(out["new_activities"]),
        "changed_cases_count": len(out["changed"]),
    }
    return out


# -----------------------------
# Main
# -----------------------------
def main():
    repo_root = Path(__file__).resolve().parents[1]

    platform = os.environ.get("PLATFORM", "ios")
    base_path = repo_root / "config" / f"base_request_{platform}.json"
    matrix_path = repo_root / "config" / f"matrix_{platform}.json"
    expected_path = repo_root / "config" / f"expected_{platform}.json"

    results_dir = repo_root / "results"
    history_dir = results_dir / "history"
    results_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    base = json.loads(base_path.read_text())
    matrix = json.loads(matrix_path.read_text())
    expected = json.loads(expected_path.read_text())

    url = matrix["edge_url"]
    cases = matrix["cases"]
    rules = expected.get("rules", [])

    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    run_ts = utc_now_iso_z()
    run_id = run_ts.replace(":", "").replace("-", "")

    latest: Dict[str, Any] = {
        "platform": platform,
        "runTimestamp": run_ts,
        "edge_url": url,
        "cases": [],
        "activities_seen": [],
    }

    activities_seen = set()
    all_ok = True

    for c in cases:
        name = c["name"]
        req_body = apply_case(base, c)

        case_result: Dict[str, Any] = {
            "name": name,
            "inputs": {
                "appStoreCountryCode": c["appStoreCountryCode"],
                "build_id": c["build_id"],
                "logged_in": bool(c.get("logged_in", True)),
            },
            "ok": False,
            "activityId": None,
            "experienceId": None,
            "product_ids": [],
            "hygiene_issues": [],
            "expectation_ok": True,
            "expectation_msg": "",
            "error": "",
        }

        try:
            r = requests.post(url, headers=headers, json=req_body, timeout=30)
            r.raise_for_status()
            records = split_streaming_json(r.content)

            pids, decision = extract_scope_result(records, SCOPE)
            act, exp = decision_activity_experience(decision)

            case_result["activityId"] = act
            case_result["experienceId"] = exp
            case_result["product_ids"] = pids

            if act:
                activities_seen.add(str(act))

            issues = hygiene_issues(pids)
            case_result["hygiene_issues"] = issues

            ok_exp, msg = validate_expected(rules, {
                "appStoreCountryCode": c["appStoreCountryCode"],
                "build_id": c["build_id"],
                "logged_in": bool(c.get("logged_in", True)),
            }, pids)
            case_result["expectation_ok"] = ok_exp
            case_result["expectation_msg"] = msg

            # Determine OK
            ok = True
            if not pids:
                ok = False
                case_result["error"] = "No product_ids delivered for scope"
            if issues:
                ok = False
            if not ok_exp:
                ok = False
            case_result["ok"] = ok
            if not ok:
                all_ok = False

        except Exception as e:
            case_result["error"] = str(e)
            case_result["ok"] = False
            all_ok = False

        latest["cases"].append(case_result)

    latest["activities_seen"] = sorted(activities_seen)

    latest_path = results_dir / "latest.json"
    prev = load_json(latest_path)
    latest_path.write_text(json.dumps(latest, indent=2, sort_keys=True))

    # Save to history
    history_path = history_dir / f"{platform}_{run_id}.json"
    history_path.write_text(json.dumps(latest, indent=2, sort_keys=True))

    # Diff
    diff = diff_latest(prev, latest)
    diff_path = results_dir / "diff.json"
    diff_path.write_text(json.dumps(diff, indent=2, sort_keys=True))

    # Exit code for CI
    if all_ok:
        print("✅ ALL OK")
        raise SystemExit(0)
    else:
        print("❌ FAILURES DETECTED")
        raise SystemExit(2)

if __name__ == "__main__":
    main()