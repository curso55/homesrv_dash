#!/usr/bin/env python3
import os
import shutil
import subprocess
from datetime import datetime

# ANSI Colors for formatting
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def get_uptime():
    """Reads system uptime from /proc/uptime to avoid heavy shell parsing."""
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m"
    except Exception:
        return "Unknown"


def get_cpu_temp():
    """Reads core CPU temperature from sysfs."""
    try:
        # Standard thermal zone 0 is usually the CPU package
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_raw = float(f.read().strip())
        temp_c = temp_raw / 1000.0

        if temp_c < 55:
            return f"{GREEN}{temp_c:.1f}°C{RESET}"
        elif temp_c < 75:
            return f"{YELLOW}{temp_c:.1f}°C{RESET}"
        return f"{RED}{temp_c:.1f}°C{RESET}"
    except Exception:
        return f"{YELLOW}N/A{RESET}"


def check_os_updates():
    """Checks for pending APT updates and reboot requirements."""
    reboot_pending = os.path.exists("/var/run/reboot-required")

    updates, security = 0, 0
    try:
        # Querying the same apt-check helper used by the system MOTD login banner
        result = subprocess.run(
            ["/usr/lib/update-notifier/apt-check"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Output comes out to stderr as 'regular_updates;security_updates'
        output = result.stderr.strip()
        if ";" in output:
            parts = output.split(";")
            updates = int(parts[0])
            security = int(parts[1])
    except Exception:
        pass

    return {
        "reboot": reboot_pending,
        "total_updates": updates,
        "security_updates": security,
    }


def draw_bar(pct, width=20):
    """Generates a text-based resource usage bar."""
    filled = int(width * (pct / 100))
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)

    if pct < 60:
        color = GREEN
    elif pct < 85:
        color = YELLOW
    else:
        color = RED
    return f"{color}[{bar}]{RESET} {pct:.1f}%"


def main():
    # Gather Host Information
    uptime_str = get_uptime()
    cpu_temp_str = get_cpu_temp()
    apt_info = check_os_updates()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Fetch CPU/RAM load metrics
    load1, _, _ = os.getloadavg()
    cpu_cores = os.cpu_count() or 1
    cpu_pct = min(100.0, (load1 / cpu_cores) * 100)

    # Memory parsing
    mem_pct, mem_str = 0.0, "Unknown"
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        total = int([x for x in lines if "MemTotal" in x][0].split()[1])
        avail = int([x for x in lines if "MemAvailable" in x][0].split()[1])
        used = total - avail
        mem_pct = (used / total) * 100
        mem_str = f"{used / 1024 / 1024:.1f}G / {total / 1024 / 1024:.1f}G"
    except Exception:
        pass

    # Root Disk Storage
    total_d, used_d, _ = shutil.disk_usage("/")
    disk_pct = (used_d / total_d) * 100
    disk_str = f"{used_d / (2**30):.1f}G / {total_d / (2**30):.1f}G"

    # Print Dashboard layout
    os.system("clear")
    print(f"{BOLD}{CYAN}===================================================={RESET}")
    print(f"{BOLD} homesrv CENTRAL COMMAND DASHBOARD {RESET}".center(52))
    print(f" As of: {now}   |   Uptime: {uptime_str}".center(52))
    print(f"{BOLD}{CYAN}===================================================={RESET}\n")

    # Render OS / Reboot Banner Alerts if applicable
    if apt_info["reboot"]:
        print(
            f"{BOLD}{RED}  [!] REBOOT REQUIRED (Kernel/System Updates Pending) [!]{RESET}\n"
        )
    elif apt_info["total_updates"] > 0:
        print(
            f"{BOLD}{YELLOW}  [*] OS Updates Pending: {apt_info['total_updates']} ({apt_info['security_updates']} Security){RESET}\n"
        )

    print(f"{BOLD}{BLUE}[ HOST MACHINE STATUS ]{RESET}")
    print(f"  CPU Load: {draw_bar(cpu_pct)}  (Temp: {cpu_temp_str})")
    print(f"  Memory:   {draw_bar(mem_pct)}  ({mem_str})")
    print(f"  Storage:  {draw_bar(disk_pct)}  ({disk_str})")
    print(f"\n{BOLD}{CYAN}===================================================={RESET}")


if __name__ == "__main__":
    main()