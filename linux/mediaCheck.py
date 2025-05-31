#!/usr/bin/env python3

import argparse
import logging
import os
import requests
import sys
import time
from urllib.parse import urlparse
from datetime import datetime, timedelta

url_radarr = os.getenv("url_radarr")
url_sonarr = os.getenv("url_sonarr")
apikey_radarr = os.getenv("apikey_radarr")
apikey_sonarr = os.getenv("apikey_sonarr")
check_int = 300

logger = logging.getLogger("MediaChecker")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
ch.setFormatter(formatter)
logger.addHandler(ch)

def obfuscate(s, show=4):
    if not s:
        return '***'
    if len(s) <= show:
        return '*' * len(s)
    return '*' * (len(s) - show) + s[-show:]

def obfuscate_url(url):
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://***"
    except Exception:
        return "***"

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

def checkService(name, url, api_key):
    headers = {"X-Api-Key": api_key}
    api_url = f"{url}/api/v3/system/status"
    if logger.level <= logging.DEBUG:
        log_url = api_url
        log_key = api_key
    else:
        log_url = obfuscate_url(api_url)
        log_key = obfuscate(api_key)
    logger.info(f"Calling {name} API: {log_url} with API key: {log_key}")
    try:
        logger.debug(f"Sending GET req to {api_url} with headers {headers}")
        response = requests.get(api_url, headers=headers, timeout=10)
        logger.debug(f"Received response from {name} ({response.status_code}): {response.text}")
        if response.status_code == 200:
            logger.info(f"{name} API call successful.")
            try:
                data = response.json()
                version = data.get("version", "unknown")
                start_time = data.get("startTime", None)
                uptime_str = format_uptime(start_time) if start_time else "unknown"
                return True, version, start_time, uptime_str
            except Exception as jsonParsingError:
                logger.error(f"Failed to parse {name} status JSON: {jsonParsingError}")
                return True, "unknown", None, "unknown"
        else:
            logger.error(f"{name} API call failed with status {response.status_code}: {response.text}")
            return False, None, None, None
    except requests.exceptions.RequestException as apiConnectionError:
        logger.error(f"Error contacting {name}: {apiConnectionError}")
        return False, None, None, None

def executeChecks(args):
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled.")

    def log_result(service, result_tuple):
        result, version, start_time, uptime_str = result_tuple
        if result:
            logger.info(f"{service} (v{version}) is UP. Started: {start_time}, Uptime: {uptime_str}")
        else:
            logger.error(f"{service} is DOWN.")

    def checkAll():
        radarr_result = checkService("Radarr", args.radarr_url, args.radarr_token)
        sonarr_result = checkService("Sonarr", args.sonarr_url, args.sonarr_token)
        log_result("Radarr", radarr_result)
        log_result("Sonarr", sonarr_result)
        return radarr_result[0] and sonarr_result[0]

    if args.daemon:
        logger.info("Running in daemon mode.")
        try:
            while True:
                checkAll()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            sys.exit(0)
    else:
        success = checkAll()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check availability of services.")
    parser.add_argument("--radarr-url", default=url_radarr, help="Radarr base URL")
    parser.add_argument("--sonarr-url", default=url_sonarr, help="Sonarr base URL")
    parser.add_argument("--radarr-token", default=apikey_radarr, help="Radarr API token")
    parser.add_argument("--sonarr-token", default=apikey_sonarr, help="Sonarr API token")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode")
    parser.add_argument("--interval", type=int, default=check_int, help="Interval in seconds for daemon mode")

    args = parser.parse_args()
    executeChecks(args)