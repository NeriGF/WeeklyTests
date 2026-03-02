import json
import os
from pathlib import Path
import requests

def main():
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        print("No SLACK_WEBHOOK_URL set; skipping Slack post.")
        return

    repo_root = Path(__file__).resolve().parents[1]
    latest = json.loads((repo_root / "results" / "latest.json").read_text())
    diff = json.loads((repo_root / "results" / "diff.json").read_text())

    platform = latest.get("platform", "ios")
    ts = latest.get("runTimestamp", "")
    summary = diff.get("summary", {})

    title = f"Target PID Matrix — {platform.upper()} — {ts}"
    lines = []
    lines.append(f"*{title}*")
    lines.append(f"Cases: {summary.get('total_cases')} | Failed: {summary.get('failed_cases')} | New activities: {summary.get('new_activities_count')} | Changed cases: {summary.get('changed_cases_count')}")

    # New activities
    new_acts = diff.get("new_activities", [])
    if new_acts:
        lines.append("")
        lines.append(f"*New activityIds detected:* {', '.join(new_acts)}")

    # Changed cases details (limit to avoid spam)
    changed = diff.get("changed", [])
    if changed:
        lines.append("")
        lines.append("*Changes:*")
        for item in changed[:10]:
            name = item.get("name")
            typ = item.get("type")
            if typ == "new_case":
                lines.append(f"• `{name}` (new case)")
                continue
            fields = item.get("fields", {})
            # focus on the key fields
            if "product_ids" in fields:
                frm = fields["product_ids"]["from"]
                to = fields["product_ids"]["to"]
                lines.append(f"• `{name}` product_ids changed:")
                lines.append(f"   from: {frm}")
                lines.append(f"   to:   {to}")
            elif "activityId" in fields or "experienceId" in fields:
                lines.append(f"• `{name}` activity/experience changed: {fields}")
            else:
                lines.append(f"• `{name}` changed: {list(fields.keys())}")

        if len(changed) > 10:
            lines.append(f"… plus {len(changed) - 10} more")

    # Failures details
    failed_cases = [c for c in latest.get("cases", []) if not c.get("ok", False)]
    if failed_cases:
        lines.append("")
        lines.append("*Failures:*")
        for c in failed_cases[:10]:
            name = c["name"]
            act = c.get("activityId")
            exp = c.get("experienceId")
            err = c.get("error") or ""
            exp_ok = c.get("expectation_ok")
            exp_msg = c.get("expectation_msg")
            hygiene = c.get("hygiene_issues") or []
            lines.append(f"• `{name}` act={act} exp={exp}")
            if err:
                lines.append(f"   error: {err}")
            if not exp_ok:
                lines.append(f"   expectation: {exp_msg}")
            if hygiene:
                lines.append(f"   hygiene: {hygiene}")

        if len(failed_cases) > 10:
            lines.append(f"… plus {len(failed_cases) - 10} more")

    payload = {"text": "\n".join(lines)}
    r = requests.post(webhook, json=payload, timeout=15)
    r.raise_for_status()
    print("Posted Slack message.")

if __name__ == "__main__":
    main()