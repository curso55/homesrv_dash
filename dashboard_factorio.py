#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import urllib.request
from datetime import datetime

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


# --- STEP 1 UTILITIES ---
def get_uptime():
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
        days, hours = int(uptime_seconds // 86400), int(
            (uptime_seconds % 86400) // 3600
        )
        minutes = int((uptime_seconds % 3600) // 60)
        return (
            f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"
        )
    except Exception:
        return "Unknown"


def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_c = float(f.read().strip()) / 1000.0
        if temp_c < 55:
            return f"{GREEN}{temp_c:.1f}°C{RESET}"
        return (
            f"{YELLOW}{temp_c:.1f}°C{RESET}"
            if temp_c < 75
            else f"{RED}{temp_c:.1f}°C{RESET}"
        )
    except Exception:
        return f"{YELLOW}N/A{RESET}"


def check_os_updates():
    reboot_pending = os.path.exists("/var/run/reboot-required")
    updates, security = 0, 0
    try:
        result = subprocess.run(
            ["/usr/lib/update-notifier/apt-check"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output = result.stderr.strip()
        if ";" in output:
            updates, security = map(int, output.split(";"))
    except Exception:
        pass
    return {
        "reboot": reboot_pending,
        "total": updates,
        "security": security,
    }


def draw_bar(pct, width=20):
    filled = max(0, min(width, int(width * (pct / 100))))
    bar = "█" * filled + "░" * (width - filled)
    color = GREEN if pct < 60 else (YELLOW if pct < 85 else RED)
    return f"{color}[{bar}]{RESET} {pct:.1f}%"


# --- STEP 2 NATIVE SERVICES UTILITIES ---
def get_systemd_status(service_name):
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        status = result.stdout.strip()
        if status == "active":
            return "UP", f"{GREEN}● RUNNING{RESET}"
        elif status == "inactive":
            return "DOWN", f"{YELLOW}○ OFFLINE{RESET}"
        return "DOWN", f"{RED}× FAILED ({status}){RESET}"
    except Exception:
        return "DOWN", f"{RED}× UNKNOWN{RESET}"


def get_pihole_stats():
    try:
        result = subprocess.run(
            ["sudo", "pihole", "api", "stats/summary"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        data = json.loads(result.stdout.strip())
        total_blocked = data.get("queries", {}).get("blocked", 0)
        return f"({total_blocked:,} blocked queries today)"
    except Exception:
        return ""


def check_jeeves_logs():
    try:
        result = subprocess.run(
            ["journalctl", "-u", "jeeves", "-n", "5", "--no-pager"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logs = result.stdout.lower()
        if "error" in logs or "exception" in logs or "traceback" in logs:
            return f" {RED}[!] Log Alert: Error Flagged{RESET}"
        return ""
    except Exception:
        return ""


# --- STEP 3 & 4 DOCKER & FACTORIO UTILITIES ---
def check_docker_daemon():
    try:
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_factorio_versions():
    """Fetches local container version and matches it against the official API stable build."""
    local_ver, stable_ver = "Unknown", "Unknown"
    try:
        # FIXED: Using the verified /opt/factorio absolute image path
        res = subprocess.run(
            ["docker", "exec", "factorio-space-age", "/opt/factorio/bin/x64/factorio", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if "Version:" in res.stdout:
            local_ver = res.stdout.split("\n")[0].split("Version:")[1].split("(")[0].strip()
    except Exception:
        pass

    try:
        # Fetching latest releases from official endpoint
        req = urllib.request.Request(
            "https://factorio.com/api/latest-releases",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            stable_ver = data.get("stable", {}).get("headless", "Unknown")
    except Exception:
        pass

    if local_ver == "Unknown" or stable_ver == "Unknown":
        return ""
    elif local_ver != stable_ver:
        return f" {YELLOW}(Update Available: v{stable_ver} | Current: v{local_ver}){RESET}"
    else:
        return f" {BLUE}(v{local_ver}){RESET}"


def get_container_status(container_name):
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        status = result.stdout.strip()
        if status == "running":
            # If it's the Factorio container, append the version string metrics
            extra_metrics = get_factorio_versions() if container_name == "factorio-space-age" else ""
            return f"{GREEN}● RUNNING{RESET}{extra_metrics}"
        elif status in ["exited", "created", "paused"]:
            return f"{YELLOW}○ OFFLINE ({status}){RESET}"
        return f"{RED}× NOT FOUND{RESET}"
    except Exception:
        return f"{RED}× ERROR{RESET}"


def main():
    # Base Host Data Metrics Gathering
    uptime_str = get_uptime()
    cpu_temp_str = get_cpu_temp()
    apt_info = check_os_updates()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    load1, _, _ = os.getloadavg()
    cpu_pct = min(100.0, (load1 / (os.cpu_count() or 1)) * 100)

    # Memory Check
    mem_pct, mem_str = 0.0, "Unknown"
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        total = int([x for x in lines if "MemTotal" in x][0].split()[1])
        avail = int([x for x in lines if "MemAvailable" in x][0].split()[1])
        mem_pct = ((total - avail) / total) * 100
        mem_str = f"{(total - avail)/1024/1024:.1f}G / {total/1024/1024:.1f}G"
    except Exception:
        pass

    # Disk Check
    total_d, used_d, _ = shutil.disk_usage("/")
    disk_pct = (used_d / total_d) * 100
    disk_str = f"{used_d / (2**30):.1f}G / {total_d / (2**30):.1f}G"

    # Screen Render
    os.system("clear")
    print(f"{BOLD}{CYAN}===================================================={RESET}")
    print(f"{BOLD} homesrv CENTRAL COMMAND DASHBOARD {RESET}".center(52))
    print(f" As of: {now}   |   Uptime: {uptime_str}".center(52))
    print(f"{BOLD}{CYAN}===================================================={RESET}\n")

    if apt_info["reboot"]:
        print(
            f"{BOLD}{RED}  [!] REBOOT REQUIRED (Kernel/System Updates Pending) [!]{RESET}\n"
        )
    elif apt_info["total"] > 0:
        print(
            f"{BOLD}{YELLOW}  [*] OS Updates Pending: {apt_info['total']} ({apt_info['security']} Security){RESET}\n"
        )

    print(f"{BOLD}{BLUE}[ HOST MACHINE STATUS ]{RESET}")
    print(f"  CPU Load: {draw_bar(cpu_pct)}  (Temp: {cpu_temp_str})")
    print(f"  Memory:   {draw_bar(mem_pct)}  ({mem_str})")
    print(f"  Storage:  {draw_bar(disk_pct)}  ({disk_str})")
    print("\n" + "-" * 52 + "\n")

    # Render Service Stack Checks
    print(f"{BOLD}{BLUE}[ NATIVE BARE-METAL SERVICES ]{RESET}")

    _, pi_status = get_systemd_status("pihole-FTL")
    pi_extra = get_pihole_stats() if "RUNNING" in pi_status else ""
    print(f"  {'Pi-hole Ad-Blocker':<20} : {pi_status} {pi_extra}")

    _, un_status = get_systemd_status("unbound")
    print(f"  {'Unbound Resolver':<20} : {un_status}")

    _, jv_status = get_systemd_status("jeeves")
    jv_extra = check_jeeves_logs() if "RUNNING" in jv_status else ""
    print(f"  {'J.E.E.V.E.S. Bot':<20} : {jv_status}{jv_extra}")

    _, mc_status = get_systemd_status("minecraft")
    print(f"  {'Minecraft Server':<20} : {mc_status}")

    print("\n" + "-" * 52 + "\n")

    # Render Docker Stack Checks
    print(f"{BOLD}{BLUE}[ DOCKER MANAGED CONTAINERS ]{RESET}")
    if check_docker_daemon():
        print(f"  {'Factorio (Space Age)':<20} : {get_container_status('factorio-space-age')}")
        print(f"  {'Calibre-Web Server':<20} : {get_container_status('calibre-web')}")
        print(f"  {'Jellyfin Media Server':<20} : {get_container_status('jellyfin')}")
    else:
        print(f"  {RED}[!] DOCKER DAEMON IS DOWN / UNRESPONSIVE [!]{RESET}")

    print(f"\n{BOLD}{CYAN}===================================================={RESET}")


if __name__ == "__main__":
    main()