"""
PyIDM GitHub Auto-Updater Module
Connects to GitHub Releases API to check for updates, fetch release notes,
and apply updates directly to the installed application.
"""

import os
import sys
import json
import time
import zipfile
import tempfile
import urllib.request
import urllib.parse
from typing import Dict, Optional, Tuple

import version

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = get_app_dir()
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

def get_default_download_dir() -> str:
    user_dl = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.exists(user_dl):
        return user_dl
    return os.path.abspath(".")

def load_config() -> dict:
    defaults = {
        "github_repo": version.DEFAULT_GITHUB_REPO,
        "auto_check_updates": True,
        "last_update_check": 0,
        "download_dir": get_default_download_dir(),
        "auto_categorize": True,
        "show_download_dialog": True,
        "max_concurrent_downloads": 2,
        "default_connections": 8
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    if not defaults.get("download_dir"):
        defaults["download_dir"] = get_default_download_dir()
    return defaults

def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def parse_semver(v_str: str) -> Tuple[int, ...]:
    cleaned = v_str.strip().lstrip("v").lstrip("V")
    parts = []
    for p in cleaned.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)

def is_newer_version(remote_v: str, local_v: str) -> bool:
    try:
        return parse_semver(remote_v) > parse_semver(local_v)
    except Exception:
        return False

def check_for_updates() -> Dict:
    """
    Checks GitHub Releases API for the latest release.
    Returns:
      {
        "status": "success" | "no_update" | "error",
        "current_version": str,
        "latest_version": str,
        "release_name": str,
        "release_notes": str,
        "html_url": str,
        "download_url": Optional[str],
        "error_message": Optional[str]
      }
    """
    cfg = load_config()
    repo = cfg.get("github_repo", version.DEFAULT_GITHUB_REPO).strip()

    if not repo or "/" not in repo or repo == "user/PyIDM":
        return {
            "status": "not_configured",
            "current_version": version.VERSION,
            "error_message": "GitHub repository is not configured. Set your repo in config.json or Settings."
        }

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(api_url, headers={
        "User-Agent": f"PyIDM-Updater/{version.VERSION}",
        "Accept": "application/vnd.github.v3+json"
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag = data.get("tag_name", "")
        remote_ver = tag.lstrip("v").lstrip("V")
        local_ver = version.VERSION

        # Find assets or fallback to zipball
        download_url = None
        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            if name.endswith(".zip") or name.endswith(".exe"):
                download_url = asset.get("browser_download_url")
                break

        if not download_url:
            download_url = data.get("zipball_url")

        has_update = is_newer_version(remote_ver, local_ver)

        return {
            "status": "success" if has_update else "no_update",
            "has_update": has_update,
            "current_version": local_ver,
            "latest_version": remote_ver,
            "release_name": data.get("name") or tag,
            "release_notes": data.get("body", "No release notes provided."),
            "html_url": data.get("html_url", f"https://github.com/{repo}/releases"),
            "download_url": download_url
        }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "status": "error",
                "current_version": version.VERSION,
                "error_message": f"No releases found for repository '{repo}'. Push a release or tag to GitHub first."
            }
        return {
            "status": "error",
            "current_version": version.VERSION,
            "error_message": f"GitHub API error: {e}"
        }
    except Exception as e:
        return {
            "status": "error",
            "current_version": version.VERSION,
            "error_message": f"Network or connection error: {e}"
        }

def download_and_extract_update(download_url: str, target_dir: str, progress_callback=None) -> bool:
    """Downloads updated archive and applies files over target_dir"""
    try:
        temp_zip = os.path.join(tempfile.gettempdir(), f"pyidm_update_{int(time.time())}.zip")
        
        req = urllib.request.Request(download_url, headers={
            "User-Agent": f"PyIDM-Updater/{version.VERSION}"
        })

        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(temp_zip, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0:
                        progress_callback(downloaded, total)

        # Extract files
        extract_dir = os.path.join(tempfile.gettempdir(), f"pyidm_extracted_{int(time.time())}")
        with zipfile.ZipFile(temp_zip, "r") as z:
            z.extractall(extract_dir)

        # In GitHub zipballs, files are inside a root folder like 'user-repo-hash/'
        root_items = os.listdir(extract_dir)
        source_dir = extract_dir
        if len(root_items) == 1 and os.path.isdir(os.path.join(extract_dir, root_items[0])):
            source_dir = os.path.join(extract_dir, root_items[0])

        # Copy updated files over target_dir
        import shutil
        for item in os.listdir(source_dir):
            if item.startswith(".") or item in ["dmans_db.json", "config.json"]:
                # Preserve user database and custom config!
                continue
            s = os.path.join(source_dir, item)
            d = os.path.join(target_dir, item)
            if os.path.isdir(s):
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

        # Cleanup
        try:
            os.remove(temp_zip)
            shutil.rmtree(extract_dir, ignore_errors=True)
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"[!] Update installation error: {e}")
        return False

