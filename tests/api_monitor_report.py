# -*- coding: utf-8 -*-
"""
Issue reporting for the daily API monitor – turns the result JSONs of both
test jobs into one tracking issue (label api-monitor) via gh.

Cases (design decision 8):
  * any FAIL/DRIFT, no open issue yet -> create it
  * open issue, changed fingerprint (sorted names of non-OK checks,
    stored in an HTML comment in the issue body) -> comment + update body
  * open issue, identical fingerprint -> do nothing
  * every check OK, open issue -> close it with a comment
  * no FAIL/DRIFT but some UNAVAILABLE -> leave the issue as it is
  * a job without its result file counts as one FAIL named after the job

Runs only for schedule/workflow_dispatch on the default branch (the
workflow guards it, the script trusts its inputs). Issue text is Czech,
not hard-wrapped (GitHub GFM re-flows anyway).

Dry run: API_MONITOR_DRY_RUN=1 prints the gh commands instead of
executing them, and does not touch GitHub. Existing-issue input for
local testing: API_MONITOR_EXISTING_ISSUE=<number> (simulate an open
issue; the search is skipped).

Usage inside the reporting job:

    python3 tests/api_monitor_report.py <results-dir> <run-url>

The deployed digiarchiv version is read from the deployed-version check
in the contract results.

Exit code: 0 always – a reporting problem must not mask the test results
(the job's conclusion is already decided by the test jobs).
"""

import json
import os
import subprocess  # nosec B404 - volá jen gh se seznamem argumentů
import sys

LABEL = "api-monitor"
FINGERPRINT_MARK = "<!-- api-monitor-fingerprint"

RESULTS_DIR = sys.argv[1] if len(sys.argv) > 1 else "results"
RUN_URL = sys.argv[2] if len(sys.argv) > 2 else ""
# Filled in main() from the deployed-version check of the contract test
VERSION = ""

DRY = os.environ.get("API_MONITOR_DRY_RUN") == "1"
EXISTING_ISSUE = os.environ.get("API_MONITOR_EXISTING_ISSUE", "")
# Test hook: stands in for the body of the existing issue, so the
# identical-fingerprint case can be exercised without GitHub
EXISTING_BODY = os.environ.get("API_MONITOR_EXISTING_BODY", "")

JOBS = ["api_contract", "plugin_live"]


def gh(args, input_text=None):
    """Runs gh (or prints the command in a dry run)."""
    cmd = ["gh"] + args
    if DRY:
        shown = " ".join(cmd)
        if input_text:
            shown += f"  <<'EOF'\n{input_text}EOF"
        print(f"[dry-run] {shown}")
        return None
    return subprocess.run(  # nosec B603 B607
        cmd, input=input_text, text=True, capture_output=True, check=False
    )


def load_checks():
    """One list of check dicts; a missing result file is a FAIL."""
    checks = []
    missing = []
    for job in JOBS:
        path = os.path.join(RESULTS_DIR, f"results-{job}.json")
        if not os.path.exists(path):
            missing.append(job)
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            checks.extend(data)
        except (OSError, ValueError) as e:
            missing.append(job)
            print(f"cannot read {path}: {e}")
    for job in missing:
        # A crashed script or an image pull failure – the run is broken
        # even though no check had the chance to fail
        checks.append({
            "name": f"job {job}",
            "status": "FAIL",
            "detail": "job did not produce its result file",
            "url": "",
        })
    return checks


def find_open_issue():
    """Number of the open issue with the api-monitor label, or None."""
    if EXISTING_ISSUE:
        return EXISTING_ISSUE
    res = gh(["issue", "list", "--label", LABEL, "--state", "open",
              "--json", "number", "--limit", "1"])
    if res is None:
        return None
    if res.returncode != 0:
        print(f"issue search failed: {res.stderr}")
        return None
    try:
        issues = json.loads(res.stdout)
    except ValueError:
        return None
    return str(issues[0]["number"]) if issues else None


def fingerprint(checks):
    """Sorted names of the FAIL/DRIFT checks – the issue identity.

    UNAVAILABLE is left out on purpose: a flaky endpoint next to a real
    break would otherwise change the fingerprint and add a comment on
    every run.
    """
    return ",".join(sorted(
        c["name"] for c in checks if c["status"] in ("FAIL", "DRIFT")))


def issue_body(checks):
    """Czech GFM body with the fingerprint hidden in an HTML comment."""
    lines = []
    lines.append("Denní kontrola API (`api_monitor.yml`) našla problémy.")
    lines.append("")
    if VERSION and VERSION != "none":
        lines.append(f"Nasazená verze digiarchivu: **{VERSION}**")
        lines.append("")
    lines.append("| kontrola | stav | detail |")
    lines.append("|---|---|---|")
    for c in checks:
        if c["status"] == "OK":
            continue
        detail = str(c.get("detail", "")).replace("|", "\\|")
        lines.append(f"| {c['name']} | {c['status']} | {detail} |")
    if RUN_URL:
        lines.append("")
        lines.append(f"Běh: {RUN_URL}")
    lines.append("")
    lines.append("Lokální reprodukce:")
    lines.append("")
    lines.append("```sh")
    lines.append("uv run -q --no-project --with requests==2.34.2 "
                 "python tests/api_contract.py")
    lines.append("")
    lines.append("docker run --rm -v \"$PWD:/work:ro\" -w /work "
                 "--user \"$(id -u):$(id -g)\" -e HOME=/tmp "
                 "-e AMCR_RESULTS_DIR=/tmp/results "
                 "qgis/qgis:ltr python3 tests/api_plugin_live.py")
    lines.append("```")
    lines.append("")
    # Fingerprint must stay the last line – it is read back as-is
    lines.append(f"{FINGERPRINT_MARK}: {fingerprint(checks)} -->")
    return "\n".join(lines)


def read_fingerprint(body):
    """Extracts the fingerprint from an issue body, or None."""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith(FINGERPRINT_MARK):
            rest = line[len(FINGERPRINT_MARK):]
            # strip the ": " separator and the closing "-->"
            rest = rest[:-3].strip() if rest.endswith("-->") else rest
            return rest.lstrip(":").strip() or None
    return None


def deployed_version(checks):
    """Version string from the deployed-version check, or ""."""
    for c in checks:
        if c["name"] == "deployed-version" and c["status"] == "OK":
            return str(c.get("detail", ""))
    return ""


def main():
    global VERSION
    checks = load_checks()
    VERSION = deployed_version(checks)
    non_ok = [c for c in checks if c["status"] != "OK"]
    bad = [c for c in checks if c["status"] in ("FAIL", "DRIFT")]
    unavailable = [c for c in checks if c["status"] == "UNAVAILABLE"]
    print(f"checks: {len(checks)}, FAIL/DRIFT: {len(bad)}, "
          f"UNAVAILABLE: {len(unavailable)}")

    # The label must exist before it can be used; --force does not touch
    # an existing one with the same name
    gh(["label", "create", LABEL, "--force",
        "--description", "Denní kontrola API monitoru",
        "--color", "d93f0b"])

    if bad:
        issue = find_open_issue()
        new_fp = fingerprint(checks)
        if issue is None:
            gh(["issue", "create", "--label", LABEL, "--title",
                "API monitor: kontrola API digiarchivu selhala",
                "--body-file", "-"], input_text=issue_body(checks))
            print("issue created (or would be)")
        else:
            if EXISTING_BODY:
                old_fp = read_fingerprint(EXISTING_BODY)
            else:
                res = gh(["issue", "view", issue, "--json", "body",
                          "--jq", ".body"])
                old_fp = None
                if res is not None and res.returncode == 0:
                    old_fp = read_fingerprint(res.stdout)
            if old_fp == new_fp:
                print(f"issue #{issue}: identical fingerprint, "
                      "no new comment")
            else:
                comment = ("Stav kontrol se změnil "
                           f"(otisk: {new_fp or 'prázdný'}).\n\n"
                           + issue_body(checks))
                gh(["issue", "comment", issue, "--body-file", "-"],
                   input_text=comment)
                gh(["issue", "edit", issue, "--body-file", "-"],
                   input_text=issue_body(checks))
                print(f"issue #{issue}: comment + body updated")
    elif non_ok:
        # Only UNAVAILABLE – an outage proves neither break nor recovery
        print("only UNAVAILABLE checks, leaving the issue as it is")
    else:
        issue = find_open_issue()
        if issue is None:
            print("all checks OK and no open issue")
        else:
            comment = ("Všechny kontroly prošly, "
                       f"zavírám. {RUN_URL}".rstrip())
            gh(["issue", "close", issue, "--comment", comment])
            print(f"issue #{issue} closed with a comment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
