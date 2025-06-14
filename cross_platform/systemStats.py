#!/usr/bin/env python
import argparse
import logging
import os
import platform
import socket
import subprocess
import sys
import time
import shutil
from datetime import datetime

class ISOFormatter(logging.Formatter):
    """Custom formatter to include ISO8601 with milliseconds."""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + dt.strftime('%z')

def setup_logger(debug=False):
    logger = logging.getLogger("SystemStats")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    ch = logging.StreamHandler()
    formatter = ISOFormatter('[%(levelname)s] %(asctime)s - %(message)s')
    ch.setFormatter(formatter)
    logger.handlers = []
    logger.addHandler(ch)
    return logger

class SystemStats:
    def __init__(self, logger):
        self.logger = logger
        self.os_type = platform.system().lower()

    def log_start(self, name):
        self.logger.info(f"Starting {name} collection.")

    def log_end(self, name):
        self.logger.info(f"Finished {name} collection.")

    def get_uptime(self):
        self.log_start("uptime")
        try:
            if self.os_type == "windows":
                uptime_seconds = 0
                try:
                    # Try wmic first
                    if shutil.which("wmic"):
                        output = subprocess.check_output("wmic os get lastbootuptime", shell=True, text=True)
                        lines = output.strip().splitlines()
                        if len(lines) > 1:
                            boot_time_str = lines[1].strip()
                            boot_time = datetime.strptime(boot_time_str[:14], "%Y%m%d%H%M%S")
                            now = datetime.now()
                            uptime_seconds = (now - boot_time).total_seconds()
                    else:
                        # Fallback to PowerShell
                        output = subprocess.check_output(
                            'powershell -Command "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"', 
                            shell=True, text=True
                        )
                        boot_time_str = output.strip()
                        boot_time = datetime.strptime(boot_time_str[:19], "%Y-%m-%dT%H:%M:%S")
                        now = datetime.now()
                        uptime_seconds = (now - boot_time).total_seconds()
                except Exception:
                    uptime_seconds = 0
            else:
                # Linux/Unix: use the 'uptime' command
                output = subprocess.check_output("uptime", shell=True, text=True)
                print(f"Uptime: {output.strip()}")
                self.log_end("uptime")
                return output.strip()
            uptime_str = self.format_uptime(uptime_seconds)
            self.logger.info(f"Uptime: {uptime_str}")
            self.log_end("uptime")
            return uptime_str
        except Exception as e:
            self.logger.error(f"Error collecting uptime: {e}")
            return None

    @staticmethod
    def format_uptime(uptime_seconds):
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{days} days, {hours:02}:{minutes:02}"

    def get_disk(self):
        self.log_start("disk")
        try:
            if self.os_type == "windows":
                try:
                    ps_script = (
                        "$drives = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 3 }; "
                        "$drives = $drives | ForEach-Object { "
                        "$size = [double]$_.Size; "
                        "$free = [double]$_.FreeSpace; "
                        "$used = $size - $free; "
                        "$usepct = if ($size -ne 0) { [math]::Round(($used / $size) * 100, 1) } else { 0 }; "
                        "$size_hr = if ($size -ge 1TB) { \"{0:N1}TB\" -f ($size/1TB) } elseif ($size -ge 1GB) { \"{0:N1}GB\" -f ($size/1GB) } else { \"{0:N1}MB\" -f ($size/1MB) }; "
                        "$used_hr = if ($used -ge 1TB) { \"{0:N1}TB\" -f ($used/1TB) } elseif ($used -ge 1GB) { \"{0:N1}GB\" -f ($used/1GB) } else { \"{0:N1}MB\" -f ($used/1MB) }; "
                        "$free_hr = if ($free -ge 1TB) { \"{0:N1}TB\" -f ($free/1TB) } elseif ($free -ge 1GB) { \"{0:N1}GB\" -f ($free/1GB) } else { \"{0:N1}MB\" -f ($free/1MB) }; "
                        "[PSCustomObject]@{DeviceID=$_.DeviceID; Size=$size_hr; Used=$used_hr; Free=$free_hr; UsePct=$usepct; Mount=$_.DeviceID}"
                        "}; "
                        "$drives | Sort-Object UsePct -Descending | ForEach-Object { "
                        "Write-Output (\"$($_.DeviceID),$($_.Size),$($_.Used),$($_.Free),$($_.UsePct)%,$($_.Mount)\") "
                        "}"
                    )
                    output = subprocess.check_output(
                        ['powershell', '-NoProfile', '-Command', ps_script],
                        shell=True, text=True
                    )
                    print("Filesystem               Size     Used    Avail     Use% Mounted on")
                    for line in output.strip().splitlines():
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) == 6:
                            print(f"{parts[0]:<24} {parts[1]:>8} {parts[2]:>8} {parts[3]:>8} {parts[4]:>8} {parts[5]}")
                except Exception as e:
                    self.logger.error(f"Error collecting disk info (Windows): {e}")
            else:
                output = subprocess.check_output(
                    "df -h --output=source,size,used,avail,pcent,target | (read -r header && echo \"$header\" && sort -k5 -hr)", shell=True, text=True
                )
                print(output.strip())
            self.log_end("disk")
        except Exception as e:
            self.logger.error(f"Error collecting disk info: {e}")

    def get_memory(self):
        self.log_start("memory")
        try:
            if self.os_type == "windows":
                try:
                    ps_script = (
                        "Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10 "
                        "@{Name='Id';Expression={$_.Id}}, "
                        "@{Name='ProcessName';Expression={$_.ProcessName}}, "
                        "@{Name='WorkingSetMB';Expression={ [math]::Round($_.WorkingSet/1MB,2) }}, "
                        "@{Name='CommandLine';Expression={($_.Path + ' ' + ($_.StartInfo.Arguments -join ' '))}} | "
                        "ForEach-Object { "
                        "$cmd = $_.CommandLine; "
                        "if (-not $cmd) { $cmd = $_.ProcessName } "
                        "Write-Output (\"$($_.Id),$($_.ProcessName),$($_.WorkingSetMB),$($cmd.Substring(0, [Math]::Min(100, $cmd.Length)))\") "
                        "}"
                    )
                    output = subprocess.check_output(
                        ['powershell', '-NoProfile', '-Command', ps_script],
                        shell=True, text=True
                    )
                    print(f"{'PID':<8} {'Name':<25} {'Mem(MB)':>10} {'Command':<100}")
                    for line in output.strip().splitlines():
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) == 4:
                            print(f"{parts[0]:<8} {parts[1]:<25} {parts[2]:>10} {parts[3]:<100}")
                except Exception as e:
                    self.logger.error(f"Error collecting memory info (Windows): {e}")
            else:
                # Use ps with a delimiter and only the fields we want
                output = subprocess.check_output(
                    "ps -eo pid,comm,user,rss,args --sort=-rss --no-headers | head -n 10",
                    shell=True, text=True
                )
                print(f"{'PID':<8} {'Name':<25} {'User':<12} {'Mem(MB)':>10} {'Command':<100}")
                for line in output.strip().splitlines():
                    # Split only the first 4 fields, the rest is the command
                    parts = line.split(None, 4)
                    if len(parts) == 5:
                        pid, name, user, rss, cmd = [p.strip() for p in parts]
                        try:
                            rss_mb = int(rss) / 1024
                        except Exception:
                            rss_mb = 0
                        print(f"{pid:<8} {name:<25} {user:<12} {rss_mb:>10.2f} {cmd[:100]:<100}")
        except Exception as e:
            self.logger.error(f"Error collecting memory info: {e}")
        self.log_end("memory")

    def get_cpu(self):
        self.log_start("cpu")
        try:
            if self.os_type == "windows":
                try:
                    ps_script = (
                        "$samples = Get-Process | "
                        "Select-Object Id,ProcessName,Path,@{Name='CPU';Expression={$_.CPU}}; "
                        "Start-Sleep -Milliseconds 500; "
                        "$samples2 = Get-Process | "
                        "Select-Object Id,ProcessName,Path,@{Name='CPU';Expression={$_.CPU}}; "
                        "$cpuList = @(); "
                        "$numCPU = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors; "
                        "foreach ($p in $samples) { "
                        "  $p2 = $samples2 | Where-Object { $_.Id -eq $p.Id }; "
                        "  if ($p2) { "
                        "    $cpuDelta = $p2.CPU - $p.CPU; "
                        "    $cpuPct = ($cpuDelta / 0.5) / $numCPU * 100; "
                        "    $cmd = $p.Path; "
                        "    if (-not $cmd) { $cmd = $p.ProcessName } "
                        "    $cmd = $cmd.Substring(0, [Math]::Min(100, $cmd.Length)); "
                        "    $cpuList += [PSCustomObject]@{Id=$p.Id;ProcessName=$p.ProcessName;CPUPercent=[math]::Round($cpuPct,2);Command=$cmd} "
                        "  } "
                        "} "
                        "$cpuList | Sort-Object CPUPercent -Descending | Select-Object -First 10 | "
                        "ForEach-Object { Write-Output (\"$($_.Id),$($_.ProcessName),$($_.CPUPercent),$($_.Command)\") }"
                    )
                    output = subprocess.check_output(
                        ['powershell', '-NoProfile', '-Command', ps_script],
                        shell=True, text=True
                    )
                    print(f"{'PID':<8} {'Name':<25} {'%CPU':>8} {'Command':<100}")
                    for line in output.strip().splitlines():
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) == 4:
                            print(f"{parts[0]:<8} {parts[1]:<25} {parts[2]:>8} {parts[3]:<100}")
                except Exception as e:
                    self.logger.error(f"Error collecting CPU info (Windows): {e}")
            else:
                # Use ps with a delimiter and only the fields we want
                output = subprocess.check_output(
                    "ps -eo pid,comm,user,%cpu,args --sort=-%cpu --no-headers | head -n 10",
                    shell=True, text=True
                )
                print(f"{'PID':<8} {'Name':<25} {'User':<12} {'%CPU':>8} {'Command':<100}")
                for line in output.strip().splitlines():
                    parts = line.split(None, 4)
                    if len(parts) == 5:
                        pid, name, user, cpu, cmd = [p.strip() for p in parts]
                        print(f"{pid:<8} {name:<25} {user:<12} {cpu:>8} {cmd[:100]:<100}")
        except Exception as e:
            self.logger.error(f"Error collecting CPU info: {e}")
        self.log_end("cpu")

    def get_all(self):
        self.logger.info("Starting full system stats collection.")
        self.get_uptime()
        self.get_disk()
        self.get_cpu()
        self.get_memory()
        self.logger.info("Finished full system stats collection.")

    def print_summary(self):
        hostname = socket.gethostname()
        print("="*60)
        print(f"System Summary for: {hostname}")
        print("="*60)
        # Uptime
        uptime = self.get_uptime()
        print(f"\nUptime: {uptime if uptime else 'Unavailable'}")
        # Disk
        print("\nDisk Usage:")
        self.get_disk()
        # CPU
        print("\nTop 10 CPU Consuming Processes:")
        self.get_cpu()
        # Memory
        print("\nTop 10 Memory Consuming Processes:")
        self.get_memory()
        print("="*60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cross-platform system stats collector.")
    parser.add_argument("--memory", action="store_true", help="Show top memory consumers")
    parser.add_argument("--cpu", action="store_true", help="Show top CPU consumers")
    parser.add_argument("--disk", action="store_true", help="Show disk usage")
    parser.add_argument("--uptime", action="store_true", help="Show system uptime")
    parser.add_argument("--all", action="store_true", help="Show all stats")
    parser.add_argument("--summary", action="store_true", help="Show summarized system stats")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logger = setup_logger(debug=args.debug)
    stats = SystemStats(logger)

    if args.summary:
        stats.print_summary()
    elif args.all:
        stats.get_all()
    else:
        if args.uptime:
            stats.get_uptime()
        if args.disk:
            stats.get_disk()
        if args.cpu:
            stats.get_cpu()
        if args.memory:
            stats.get_memory()