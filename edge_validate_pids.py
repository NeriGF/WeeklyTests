import json
import re
import sys
from typing import Any, Dict, List, Tuple, Optional

import requests

SCOPE = "lrm.priceTesting.overviewScreen.productIds"

def split_streaming_json(raw: bytes) -> List[Dict[str, Any]]:
    """
    Edge/Konductor streaming responses may contain multiple JSON objects separated by NULL (\x00).
    This returns a list of decoded JSON objects.
    """
    parts = [p for p in raw.split(b"\x00") if p.strip()]
    out = []
    for p in parts:
        out.append(json.loads(p.decode("utf-8")))
    return out

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
            out.append(f"⟦ZW{o:04X}⟧")  # zero-width
        else:
            out.append(ch)
    return "".join(out)

def extract_decision_product_ids(records: List[Dict[str, Any]], scope: str) -> Tuple[List[str], Dict[str, Any]]:
    """
    Find personalization:decisions record(s) and extract product_ids for the given scope.
    Returns (product_ids, decision_metadata).
    Raises if not found.
    """
    for rec in records:
        for h in rec.get("handle", []):
            if h.get("type") != "personalization:decisions":
                continue
            for decision in h.get("payload", []):
                if decision.get("scope") != scope:
                    continue
                # Find JSON content item with { product_ids: [...] }
                for item in decision.get("items", []):
                    data = item.get("data", {})
                    content = data.get("content")
                    if isinstance(content, dict) and "product_ids" in content and isinstance(content["product_ids"], list):
                        return content["product_ids"], decision
    raise RuntimeError(f"No product_ids found for scope '{scope}'. (Either no decisions delivered or different response shape.)")

def whitespace_healthcheck(pids: List[str]) -> List[str]:
    issues = []
    for p in pids:
        if p != p.strip():
            issues.append(f"PID has leading/trailing whitespace: {show_invisibles(p)}")
        if re.search(r"[\u00A0\u200B\u200C\u200D\uFEFF]", p):
            issues.append(f"PID contains invisible unicode: {show_invisibles(p)}")
    return issues

def main():
    if len(sys.argv) < 2:
        print("Usage:\n  python3 edge_validate_pids.py <EDGE_INTERACT_URL>\n")
        print("Example:\n  python3 edge_validate_pids.py 'https://adobecorp.data.adobedc.net/ee/or2/v1/interact?configId=fec951b9-...'\n")
        sys.exit(1)

    url = sys.argv[1].strip()

    # --- Paste your captured request body here (exactly what you posted) ---
    body = {
      "events": [
        {
          "xdm": {
            "eventType": "personalization.request",
            "application": { "_dc": { "language": "" } },
            "device": { "model": "iPhone14,7" },
            "_id": "2BDFFB88-51C6-4344-9748-348BD9DF14B9",
            "timestamp": "2026-03-01T06:47:21.127Z"
          },
          "data": {
            "__adobe": {
              "target": {
                "a.DailyEngUserEvent": "DailyEngUserEvent",
                "appStoreCountryCode": "USA",
                "a.ignoredSessionLength": "",
                "a.DaysSinceLastUse": "1",
                "a.Launches": "3",
                "premiumAccessType": "none",
                "a.LaunchesSinceUpgrade": "",
                "a.OSVersion": "iOS 26.2.1",
                "a.DaysSinceLastUpgrade": "",
                "a.MonthlyEngUserEvent": "",
                "a.AppID": "LrMobilePhone 11.2.2 (11.2.2.31)",
                "a.build_id": "weeklytest-high",
                "a.Resolution": "1170x2532",
                "a.PrevSessionLength": "607",
                "a.InstallDate": "",
                "a.DayOfWeek": "7",
                "a.RunMode": "Application",
                "a.DaysSinceFirstUse": "1",
                "subscriptionStatus": "subscription_expired",
                "a.CarrierName": "",
                "a.LaunchEvent": "LaunchEvent",
                "a.HourOfDay": "22",
                "a.appID": "LrMobilePhone 11.2.2 (11.2.2.31)",
                "a.UpgradeEvent": "",
                "a.InstallEvent": "",
                "a.CrashEvent": "",
                "a.DeviceName": "iPhone14,7",
                "a.locale": "en-US",
                "cachedTotalAssetCount": "0"
              }
            }
          },
          "query": {
            "personalization": {
              "schemas": [
                "https://ns.adobe.com/personalization/html-content-item",
                "https://ns.adobe.com/personalization/json-content-item",
                "https://ns.adobe.com/personalization/default-content-item",
                "https://ns.adobe.com/experience/offer-management/content-component-html",
                "https://ns.adobe.com/experience/offer-management/content-component-json",
                "https://ns.adobe.com/experience/offer-management/content-component-imagelink",
                "https://ns.adobe.com/experience/offer-management/content-component-text"
              ],
              "decisionScopes": [
                "lrm.showIntentSurvey",
                "lrm.paywallConfiguration",
                "lrm.priceTesting.overviewScreen.productIds",
                "lrm.paywallShownInPremiumFeatureSheet",
                "lrm.showFeatureDeeplinksOnPremiumSheet",
                "lrm.referralsFeb2025",
                "lrm.referralsEmergencyStopFeb2025",
                "lrm.removeMeteringTBYBTestJuly2025",
                "lrm.sendToPremiereEnabled",
                "lrm.highlightShareButtonV3",
                "lrm.sceneBalanceGlobalTrialEnd",
                "lrm.savePresetOnLists",
                "lrm.limitedTimeUnlockMAX25",
                "lrm.appTrackingTransparencyPrompt"
              ]
            }
          }
        }
      ],
      "meta": {
        "konductorConfig": {
          "streaming": { "recordSeparator": "\u0000", "lineFeed": "\n", "enabled": True }
        },
        "state": {
          "entries": [
            { "maxAge": 15552000, "value": "general=in", "key": "kndctr_9E1005A551ED61CA0A490D45_AdobeOrg_consent" },
            { "maxAge": 1800, "value": "or2", "key": "kndctr_9E1005A551ED61CA0A490D45_AdobeOrg_cluster" },
            { "maxAge": 34128000, "value": "CiY0NzE4OTc3Njk0MzYyMjU4MDU0OTA5MTQ3MzE4Mzc1Mjk4OTkwNlIQCKWjtpTKMxgBKgNPUjIwA_ABqaLiwMoz",
              "key": "kndctr_9E1005A551ED61CA0A490D45_AdobeOrg_identity"
            }
          ]
        }
      },
      "xdm": {
        "identityMap": {
          "ECID": [ { "primary": False, "authenticatedState": "ambiguous", "id": "47189776943622580549091473183752989906" } ],
          "adobeGUID": [ { "id": "26D855BE698E6CBE0A49420F@AdobeID", "authenticatedState": "authenticated", "primary": True } ]
        },
        "implementationDetails": { "name": "https://ns.adobe.com/experience/mobilesdk/ios", "environment": "app", "version": "5.7.0+5.0.3" }
      }
    }

    headers = {
        "Content-Type": "application/json",
        # Helpful to be explicit; Edge typically accepts without these too:
        "Accept": "application/json",
    }

    r = requests.post(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()

    records = split_streaming_json(r.content)
    pids, decision = extract_decision_product_ids(records, SCOPE)

    act = (decision.get("scopeDetails", {}).get("activity", {}) or {}).get("id")
    exp = (decision.get("scopeDetails", {}).get("experience", {}) or {}).get("id")

    print(f"✅ Delivered scope: {SCOPE}")
    print(f"   activityId={act} experienceId={exp}\n")

    print("Delivered product_ids:")
    for p in pids:
        print(" -", p)

    issues = whitespace_healthcheck(pids)
    if issues:
        print("\n❌ PID string hygiene issues:")
        for i in issues:
            print(" -", i)
        sys.exit(2)

    print("\n✅ No whitespace/invisible-char issues detected.")

if __name__ == "__main__":
    main()