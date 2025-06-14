#!/usr/bin/env python3

import argparse
import logging
import os
import requests
import sys
import time
from urllib.parse import urlparse
from datetime import datetime, timedelta

url_radarr = ""
url_sonarr = ""
apikey_radarr = ""
apikey_sonarr = ""
check_int = 300

class MonitorMediaServer:
    def __init__(self, url_radarr, url_sonarr, apikey_radarr, apikey_sonarr, check_int=300, debug=False):
        self.url_radarr = url_radarr
        self.url_sonarr = url_sonarr
        self.apikey_radarr = apikey_radarr
        self.apikey_sonarr = apikey_sonarr
        self.check_int = check_int

        self.logger = logging.getLogger("MediaChecker")
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        ch = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        ch.setFormatter(formatter)
        self.logger.handlers = []
        self.logger.addHandler(ch)

    @staticmethod
    def obfuscate(s, show=4):
        """Show the first and last `show` characters, obfuscate the middle."""
        if not s or len(s) <= show * 2:
            return '*' * len(s) if s else '***'
        return s[:show] + '*' * (len(s) - show * 2) + s[-show:]

    @staticmethod
    def obfuscate_url(url, show_ip=3, show_port=0):
        """
        Show the first and last `show_ip` characters of the IP/host,
        hide the first 3 of the port, and leave the endpoint intact.
        """
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            # Show first 3 and last 3 chars of IP/host, obfuscate the rest
            if len(host) <= show_ip * 2:
                ob_host = '*' * len(host)
            else:
                ob_host = host[:show_ip] + '*' * (len(host) - show_ip * 2) + host[-show_ip:]
            # Obfuscate the first 3 of the port, show the rest
            port = parsed.port
            ob_port = ''
            if port:
                port_str = str(port)
                if len(port_str) <= 3:
                    ob_port = ':' + '*' * len(port_str)
                else:
                    ob_port = ':' + '*' * 3 + port_str[3:]
            path = parsed.path
            return f"{parsed.scheme}://{ob_host}{ob_port}{path}"
        except Exception:
            return "***"

    @staticmethod
    def format_uptime(start_time_str):
        try:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ")
            now = datetime.utcnow()
            uptime = now - start_time
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            if days > 0:
                return f"{days} days, {hours:02}:{minutes:02}"
            else:
                return f"{hours:02}:{minutes:02}"
        except Exception:
            return "unknown"

    def check_service(self, name, url, api_key):
        headers = {"X-Api-Key": api_key}
        api_url = f"{url}/api/v3/system/status"
        if self.logger.level <= logging.DEBUG:
            log_url = api_url
            log_key = api_key
        else:
            log_url = self.obfuscate_url(api_url)
            log_key = self.obfuscate(api_key)
        self.logger.info(f"Calling {name} API: {log_url} with API key: {log_key}")
        try:
            self.logger.debug(f"Sending GET to {api_url} with headers {headers}")
            response = requests.get(api_url, headers=headers, timeout=10)
            self.logger.debug(f"Received response from {name} ({response.status_code}): {response.text}")
            if response.status_code == 200:
                self.logger.info(f"{name} API call successful.")
                try:
                    data = response.json()
                    version = data.get("version", "unknown")
                    start_time = data.get("startTime", None)
                    uptime_str = self.format_uptime(start_time) if start_time else "unknown"
                    return True, version, start_time, uptime_str
                except Exception as jsonParsingError:
                    self.logger.error(f"Failed to parse {name} status JSON: {jsonParsingError}")
                    return True, "unknown", None, "unknown"
            else:
                self.logger.error(f"{name} API call failed, status {response.status_code}: {response.text}")
                return False, None, None, None
        except requests.exceptions.RequestException as apiConnectionError:
            self.logger.error(f"Error contacting {name}: {apiConnectionError}")
            return False, None, None, None

    def log_result(self, service, result_tuple):
        result, version, start_time, uptime_str = result_tuple
        if result:
            self.logger.info(f"{service} (v{version}) is UP. Started: {start_time}, Uptime: {uptime_str}")
        else:
            self.logger.error(f"{service} is DOWN.")

    def check_all(self):
        radarr_result = self.check_service("Radarr", self.url_radarr, self.apikey_radarr)
        sonarr_result = self.check_service("Sonarr", self.url_sonarr, self.apikey_sonarr)
        self.log_result("Radarr", radarr_result)
        self.log_result("Sonarr", sonarr_result)
        return radarr_result[0] and sonarr_result[0]

    def run(self, daemon=False, interval=None):
        interval = interval or self.check_int
        if daemon:
            self.logger.info("Running in daemon mode.")
            try:
                while True:
                    self.check_all()
                    time.sleep(interval)
            except KeyboardInterrupt:
                self.logger.info("Stopped by user.")
                sys.exit(0)
        else:
            success = self.check_all()
            sys.exit(0 if success else 1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check availability of services.")
    parser.add_argument("--radarr-url", default=None, help="Radarr base URL")
    parser.add_argument("--sonarr-url", default=None, help="Sonarr base URL")
    parser.add_argument("--radarr-token", default=None, help="Radarr API token")
    parser.add_argument("--sonarr-token", default=None, help="Sonarr API token")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode")
    parser.add_argument("--interval", type=int, default=300, help="Interval in seconds for daemon mode")

    args = parser.parse_args()

    # cli option
    radarr_url = args.radarr_url if args.radarr_url else os.getenv("url_radarr", url_radarr)
    sonarr_url = args.sonarr_url if args.sonarr_url else os.getenv("url_sonarr", url_sonarr)
    radarr_token = args.radarr_token if args.radarr_token else os.getenv("apikey_radarr", apikey_radarr)
    sonarr_token = args.sonarr_token if args.sonarr_token else os.getenv("apikey_sonarr", apikey_sonarr)

    monitor = MonitorMediaServer(
        url_radarr=radarr_url,
        url_sonarr=sonarr_url,
        apikey_radarr=radarr_token,
        apikey_sonarr=sonarr_token,
        check_int=args.interval,
        debug=args.debug
    )
    monitor.run(daemon=args.daemon, interval=args.interval)

