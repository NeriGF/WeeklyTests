import json
import uuid
import datetime as dt
import re
import sys
from copy import deepcopy
from typing import Any, Dict, List, Tuple

import requests

SCOPE = "lrm.priceTesting.overviewScreen.productIds"

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

def extract_pids(records: List[Dict[str, Any]], scope: str) -> Tuple[List[str], Dict[str, Any]]:
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
                    if isinstance(content, dict) and "product_ids" in content and isinstance(content["product_ids"], list):
                        return content["product_ids"], decision
    return [], {}

def hygiene_issues(pids: List[str]) -> List[str]:
    issues = []
    for p in pids:
        if p != p.strip():
            issues.append(f"leading/trailing whitespace: {show_invisibles(p)}")
        if re.search(r"[\u00A0\u200B\u200C\u200D\uFEFF]", p):
            issues.append(f"invisible unicode: {show_invisibles(p)}")
    return issues
    ok, msg = validate_expected(rules, c, pids)
    if not ok:
        print("❌ EXPECTATION FAILED:", msg)
        failed = True
    else:
        print("✅ expectation OK:", msg)

def apply_case(base: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    b = deepcopy(base)

    # fresh IDs/timestamps every run (so this isn’t a stale replay)
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    b["events"][0]["xdm"]["timestamp"] = now
    b["events"][0]["xdm"]["_id"] = str(uuid.uuid4()).upper()

    tgt = b["events"][0]["data"]["__adobe"]["target"]
    tgt["appStoreCountryCode"] = case["appStoreCountryCode"]
    tgt["a.build_id"] = case["build_id"]

    # logged-in vs logged-out simulation:
    # simplest reliable lever is removing adobeGUID (anonymous)
    ident = b.setdefault("xdm", {}).setdefault("identityMap", {})
    if case.get("logged_in", True):
        # keep whatever adobeGUID exists in base
        pass
    else:
        ident.pop("adobeGUID", None)

    return b

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 run_matrix.py base_request.json matrix.json expected.json")
        sys.exit(1)

    expected = json.load(open(sys.argv[3], "r"))
    rules = expected["rules"]

    base = json.load(open(sys.argv[1], "r"))
    matrix = json.load(open(sys.argv[2], "r"))

    url = matrix["edge_url"]
    cases = matrix["cases"]

    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    print(f"Edge URL: {url}\n")

    failed = False
    for c in cases:
        body = apply_case(base, c)
        name = c["name"]

        try:
            r = requests.post(url, headers=headers, json=body, timeout=30)
            r.raise_for_status()
            records = split_streaming_json(r.content)
            pids, decision = extract_pids(records, SCOPE)

            act = (decision.get("scopeDetails", {}).get("activity", {}) or {}).get("id")
            exp = (decision.get("scopeDetails", {}).get("experience", {}) or {}).get("id")

            issues = hygiene_issues(pids)

            print(f"=== {name} ===")
            print(f"country={c['appStoreCountryCode']} build_id={c['build_id']} logged_in={c.get('logged_in', True)}")
            print(f"activityId={act} experienceId={exp}")

            if not pids:
                print("❌ No product_ids delivered (empty decisions or no matching scope).")
                failed = True
            else:
                print("product_ids:")
                for p in pids:
                    print(" -", p)

            if issues:
                print("❌ hygiene issues:")
                for i in issues:
                    print(" -", i)
                failed = True
            else:
                print("✅ hygiene OK")

            print()

        except Exception as e:
            print(f"=== {name} ===")
            print(f"❌ ERROR: {e}\n")
            failed = True

    if failed:
        sys.exit(2)
def matches(rule_when: Dict[str, Any], case: Dict[str, Any]) -> bool:
    for k, v in rule_when.items():
        if k == "build_id":
            if case.get("build_id") != v:
                return False
        elif k == "appStoreCountryCode":
            if case.get("appStoreCountryCode") != v:
                return False
        elif k == "logged_in":
            if case.get("logged_in", True) != v:
                return False
    return True

def validate_expected(rules: List[Dict[str, Any]], case: Dict[str, Any], delivered: List[str]) -> Tuple[bool, str]:
    applicable = [r for r in rules if matches(r.get("when", {}), case)]
    if not applicable:
        return True, "(no expectation rule matched)"
    delivered_set = set(delivered)

    for r in applicable:
        for option in r.get("expect_any_of", []):
            if set(option) == delivered_set:
                return True, "matched expected"
    return False, f"expected one of: {applicable[0].get('expect_any_of')}"
if __name__ == "__main__":
    main()