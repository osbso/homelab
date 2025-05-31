#!/usr/bin/env python3

import requests
import argparse
import logging
import sys
import time
import os

url_radarr = os.getenv("url_radarr")
url_sonarr = os.getenv("url_sonarr")
apikey_radarr = os.getenv("RADARR_API_KEY")
apikey_sonarr = os.getenv("SONARR_API_KEY")
CHECK_INTERVAL = 300

logger = logging.getLogger("MediaChecker")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
ch.setFormatter(formatter)
logger.addHandler(ch)

def check_service(name, url, api_key):
    headers = {"X-Api-Key": api_key}
    api_url = f"{url}/api/v3/system/status"
    logger.info(f"Calling {name} API: {api_url}")
    try:
        logger.debug(f"Sending GET request to {api_url} with headers {headers}")
        response = requests.get(api_url, headers=headers, timeout=10)
        logger.debug(f"Received response from {name} ({response.status_code}): {response.text}")
        if response.status_code == 200:
            logger.info(f"{name} API call successful.")
            return True
        else:
            logger.error(f"{name} API call failed with status {response.status_code}: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error contacting {name}: {e}")
        return False

def run_checks(args):
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled.")

    def log_result(service, result):
        if result:
            logger.info(f"{service} is UP.")
        else:
            logger.error(f"{service} is DOWN.")

    def check_all():
        radarr_ok = check_service("Radarr", args.radarr_url, args.radarr_token)
        sonarr_ok = check_service("Sonarr", args.sonarr_url, args.sonarr_token)
        log_result("Radarr", radarr_ok)
        log_result("Sonarr", sonarr_ok)
        return radarr_ok and sonarr_ok

    if args.daemon:
        logger.info("Running in daemon mode. Press Ctrl+C to exit.")
        try:
            while True:
                check_all()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")
            sys.exit(0)
    else:
        success = check_all()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check availability of Radarr and Sonarr services.")
    parser.add_argument("--radarr-url", default=url_radarr, help="Radarr base URL")
    parser.add_argument("--sonarr-url", default=url_sonarr, help="Sonarr base URL")
    parser.add_argument("--radarr-token", default=apikey_radarr, help="Radarr API token")
    parser.add_argument("--sonarr-token", default=apikey_sonarr, help="Sonarr API token")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode")
    parser.add_argument("--interval", type=int, default=CHECK_INTERVAL, help="Interval in seconds for daemon mode")

    args = parser.parse_args()
    run_checks(args)