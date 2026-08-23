#!/usr/bin/env python3
"""
Checks for available updates on the host (apt packages, Unbound, Pi-hole,
and Docker container images) and writes a single status.json consumed by
the Homepage "Updates" dashboard group via its Custom API widget.

Nothing here installs or changes anything -- read-only checks only.
"""
import json
import re
import subprocess
import tempfile
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

STATUS_DIR = "/home/curso/homesrv_webstack/config/homepage/update-status"
STATUS_FILE = os.path.join(STATUS_DIR, "status.json")
ENV_FILE = "/home/curso/homesrv_webstack/config/homepage/.env"
PIHOLE_URL = "http://localhost:8080"


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def check_os():
    out = run(["apt", "list", "--upgradable"]).stdout
    pkgs = []
    for line in out.splitlines():
        if not line or line.startswith("Listing..."):
            continue
        name = line.split("/", 1)[0]
        if name != "unbound":
            pkgs.append(name)
    count = len(pkgs)
    status_text = "✅ Up to date" if count == 0 else f"⬆️ {count} update(s) available"
    return {"count": count, "packages": pkgs, "status_text": status_text}


def check_unbound():
    out = run(["apt-cache", "policy", "unbound"]).stdout
    installed = re.search(r"Installed:\s*(\S+)", out)
    candidate = re.search(r"Candidate:\s*(\S+)", out)
    installed = installed.group(1) if installed else "unknown"
    candidate = candidate.group(1) if candidate else "unknown"
    update_available = candidate not in ("(none)", "unknown") and installed != candidate
    status_text = "⬆️ Update available" if update_available else "✅ Up to date"
    return {
        "installed": installed,
        "candidate": candidate,
        "update_available": update_available,
        "status_text": status_text,
    }


def check_unbound_stats():
    out = run(["unbound-control", "stats_noreset"])
    if out.returncode != 0:
        err = out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "unknown error"
        if "Permission denied" in err:
            status_text = "🔒 curso not in 'unbound' group"
        else:
            status_text = f"⚠️ Check failed ({err.split(':')[-1].strip()[:40]})"
        return {"available": False, "status_text": status_text}

    stats = {}
    for line in out.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        stats[key] = value

    try:
        queries = int(float(stats.get("total.num.queries", 0)))
        cachehits = int(float(stats.get("total.num.cachehits", 0)))
        uptime_s = float(stats.get("time.up", 0))
        hit_rate = round((cachehits / queries) * 100, 1) if queries else 0.0
        uptime_text = f"{int(uptime_s // 86400)}d {int((uptime_s % 86400) // 3600)}h"
        return {
            "available": True,
            "queries": queries,
            "cache_hit_rate": hit_rate,
            "uptime_text": uptime_text,
            "status_text": f"✅ {hit_rate}% cache hit",
        }
    except (ValueError, ZeroDivisionError) as e:
        return {"available": False, "status_text": f"⚠️ Parse failed ({type(e).__name__})"}


def check_pihole():
    key = None
    try:
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith("HOMEPAGE_VAR_PIHOLE_KEY="):
                    key = line.strip().split("=", 1)[1]
                    break
    except OSError:
        pass

    if not key:
        return {"status_text": "❓ No API key configured"}

    sid = None
    try:
        auth_body = json.dumps({"password": key}).encode()
        auth_req = urllib.request.Request(
            f"{PIHOLE_URL}/api/auth",
            data=auth_body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(auth_req, timeout=10) as resp:
            sid = json.loads(resp.read())["session"]["sid"]

        ver_req = urllib.request.Request(f"{PIHOLE_URL}/api/info/version", headers={"sid": sid})
        with urllib.request.urlopen(ver_req, timeout=10) as resp:
            v = json.loads(resp.read())["version"]

        components = {}
        any_update = False
        for comp in ("core", "web", "ftl"):
            local = v[comp]["local"]["version"]
            remote = v[comp]["remote"]["version"]
            outdated = local != remote
            comp_status_text = f"⬆️ {local} → {remote}" if outdated else f"✅ {local}"
            components[comp] = {
                "local": local,
                "remote": remote,
                "update_available": outdated,
                "status_text": comp_status_text,
            }
            any_update = any_update or outdated

        status_text = "⬆️ Update available" if any_update else "✅ Up to date"
        return {"components": components, "update_available": any_update, "status_text": status_text}
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError) as e:
        return {"status_text": f"⚠️ Check failed ({type(e).__name__})"}
    finally:
        if sid:
            try:
                del_req = urllib.request.Request(
                    f"{PIHOLE_URL}/api/auth", headers={"sid": sid}, method="DELETE"
                )
                urllib.request.urlopen(del_req, timeout=5)
            except Exception:
                pass


def check_docker():
    ps = run(["docker", "ps", "--format", "{{.Names}}|{{.Image}}"]).stdout.strip()
    checked = 0
    outdated = []
    for line in ps.splitlines():
        if "|" not in line:
            continue
        name, image = line.split("|", 1)

        pull = run(["docker", "pull", image], timeout=300)
        if pull.returncode != 0:
            # not a pullable registry image (e.g. a locally built container) -- skip
            continue
        checked += 1

        running_id = run(["docker", "inspect", name, "--format", "{{.Image}}"]).stdout.strip()
        new_id = run(["docker", "image", "inspect", image, "--format", "{{.Id}}"]).stdout.strip()
        if running_id and new_id and running_id != new_id:
            outdated.append(name)

    count = len(outdated)
    status_text = "✅ Up to date" if count == 0 else f"⬆️ {count} update(s) available"
    return {"checked": checked, "count": count, "outdated": outdated, "status_text": status_text}


def main():
    unbound = check_unbound()
    unbound["stats"] = check_unbound_stats()

    status = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "os": check_os(),
        "unbound": unbound,
        "pihole": check_pihole(),
        "docker": check_docker(),
    }

    os.makedirs(STATUS_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=STATUS_DIR)
    with os.fdopen(fd, "w") as f:
        json.dump(status, f, indent=2)
    os.chmod(tmp_path, 0o644)
    os.replace(tmp_path, STATUS_FILE)


if __name__ == "__main__":
    main()
