import os
import subprocess
import sys
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_admin_mode
from ..config import APP_VERSION, settings

router = APIRouter(prefix="/api/system", tags=["system"])

GITHUB_REPO = "mrblomblo/blombooru"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"
CONFIG_ASSET_NAMES = {"docker-compose.yml", "example.env", "docker-compose.shared-tags.yml"}
GITHUB_TIMEOUT = 10

def is_running_in_docker() -> bool:
    """Check if the application is running in a Docker container"""
    if os.path.exists("/.dockerenv"):
        return True
    
    if os.path.exists("/proc/self/cgroup"):
        try:
            with open("/proc/self/cgroup", "r") as f:
                return "docker" in f.read()
        except Exception:
            pass
    
    return False

def detect_deployment_type() -> str:
    """Detect how the application is deployed.

    Returns one of:
        - "ghcr": running in a pre-built GHCR Docker image
        - "docker_local": running in a locally-built Docker container
        - "local": running directly via Python (no Docker)
    """
    if is_running_in_docker():
        return "ghcr" if os.environ.get("BUILD_ENV", "local") == "ghcr" else "docker_local"
    return "local"

def parse_version(version_str: str) -> tuple:
    """Parse a version string like 'v1.36.2' or '1.36.2' into a tuple of ints."""
    cleaned = version_str.lstrip("v").strip()
    try:
        return tuple(int(p) for p in cleaned.split("."))
    except (ValueError, AttributeError):
        return (0,)

def github_get(path: str, params: dict = None) -> requests.Response:
    """Make a GET request to the GitHub API with standard headers and timeout."""
    url = f"{GITHUB_API_BASE}{path}" if path.startswith("/") else path
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    return requests.get(url, headers=headers, params=params, timeout=GITHUB_TIMEOUT)

class ReleaseInfo(BaseModel):
    tag: str
    name: str
    body: str
    url: str

class CommitInfo(BaseModel):
    hash: str
    message: str

class UpdateStatus(BaseModel):
    current_version: str
    latest_version: str
    update_available: bool
    release_url: Optional[str] = None
    compare_url: Optional[str] = None
    releases: List[ReleaseInfo] = []
    commits: List[CommitInfo] = []
    notices: List[str] = []
    config_files_changed: bool = False
    changed_config_files: List[str] = []
    asset_urls: dict = {}
    deployment_type: str = "local"

@router.get("/update/check", response_model=UpdateStatus)
async def check_update_status(current_user: dict = Depends(require_admin_mode)):
    """Check for available updates via the GitHub Releases API."""
    deployment = detect_deployment_type()

    try:
        resp = github_get("/releases/latest")
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise HTTPException(
                status_code=429,
                detail="GitHub API rate limit exceeded (60 requests/hr for unauthenticated users). Please try again later or add a GITHUB_TOKEN to your .env file.",
            )
        elif resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub API returned {resp.status_code}: {resp.text[:200]}",
            )

        latest_release = resp.json()
        latest_tag = latest_release.get("tag_name", "")
        latest_version = latest_tag.lstrip("v")

        current_version = APP_VERSION.lstrip("v")
        update_available = parse_version(latest_version) > parse_version(current_version)

        asset_urls = {}
        for asset in latest_release.get("assets", []):
            name = asset.get("name", "")
            if name in CONFIG_ASSET_NAMES:
                asset_urls[name] = asset.get("browser_download_url", "")

        notices: List[str] = []
        if update_available and deployment == "ghcr":
            notices.append("admin.update.ghcr_notice")
        elif update_available and deployment == "docker_local":
            notices.append("admin.update.docker_local_notice")

        releases: List[ReleaseInfo] = []
        if update_available:
            try:
                all_resp = github_get("/releases", params={"per_page": 100})
                if all_resp.status_code == 200:
                    for rel in all_resp.json():
                        rel_tag = rel.get("tag_name", "")
                        rel_ver = parse_version(rel_tag)
                        cur_ver = parse_version(current_version)
                        if rel_ver > cur_ver:
                            releases.append(
                                ReleaseInfo(
                                    tag=rel_tag,
                                    name=rel.get("name", rel_tag),
                                    body=rel.get("body", ""),
                                    url=rel.get("html_url", ""),
                                )
                            )
                    # Sort newest first
                    releases.sort(key=lambda r: parse_version(r.tag), reverse=True)
            except Exception as e:
                pass

        commits: List[CommitInfo] = []
        changed_config_files: List[str] = []
        compare_url = None
        if update_available:
            try:
                compare_resp = github_get(
                    f"/compare/v{current_version}...{latest_tag}"
                )
                if compare_resp.status_code == 200:
                    compare_data = compare_resp.json()
                    compare_url = compare_data.get("html_url")
                    for c in compare_data.get("commits", []):
                        commits.append(
                            CommitInfo(
                                hash=c.get("sha", "")[:7],
                                message=c.get("commit", {})
                                .get("message", "")
                                .split("\n")[0],
                            )
                        )
                    # Detect config file changes from actually modified files
                    for f in compare_data.get("files", []):
                        fname = f.get("filename", "")
                        if fname in CONFIG_ASSET_NAMES:
                            changed_config_files.append(fname)
            except Exception as e:
                pass

        config_files_changed = bool(changed_config_files)

        if update_available and config_files_changed:
            notices.append("admin.update.config_files_changed")

        # Filter asset_urls to only include actually changed config files
        if config_files_changed:
            asset_urls = {k: v for k, v in asset_urls.items() if k in changed_config_files}
        else:
            asset_urls = {}

        return UpdateStatus(
            current_version=f"v{current_version}",
            latest_version=f"v{latest_version}",
            update_available=update_available,
            release_url=latest_release.get("html_url"),
            compare_url=compare_url,
            releases=releases,
            commits=commits[:100],
            notices=notices,
            config_files_changed=config_files_changed,
            changed_config_files=changed_config_files,
            asset_urls=asset_urls,
            deployment_type=deployment,
        )

    except HTTPException:
        raise
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to reach GitHub API: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to check for updates: {str(e)}"
        )

@router.post("/update/perform")
async def perform_update(
    target: dict,
    current_user: dict = Depends(require_admin_mode),
):
    """Perform an update.

    Only supported for 'local' (direct Python) deployments. Docker users
    are directed to use docker compose commands on the host machine.
    """
    deployment = detect_deployment_type()

    if deployment == "ghcr":
        raise HTTPException(
            status_code=400,
            detail="Cannot update from within a pre-built Docker container. "
            "Run 'docker compose up -d --pull always' on the host machine to update.",
        )

    if deployment == "docker_local":
        raise HTTPException(
            status_code=400,
            detail="Cannot update from within a locally-built Docker container. "
            "Run 'docker compose down && docker compose -f docker-compose.dev.yml up --build' on the host machine to update.",
        )

    # Direct Python (local) deployment
    try:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

        current_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], env=env
        ).decode().strip()

        try:
            resp = github_get("/releases/latest")
            if resp.status_code == 200:
                latest_tag = resp.json().get("tag_name", "")
            else:
                raise HTTPException(status_code=502, detail="Failed to fetch latest release from GitHub")
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Failed to reach GitHub API: {e}")

        commands = [
            ["git", "fetch", "--tags"],
            ["git", "checkout", latest_tag],
        ]

        output_log = []
        for cmd in commands:
            process = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
            output_log.append(f"$ {' '.join(cmd)}")
            output_log.append(process.stdout)
            if process.stderr:
                output_log.append(process.stderr)

        new_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], env=env
        ).decode().strip()

        post_update_actions = []

        # Handle changed dependencies
        if current_hash != new_hash:
            try:
                diff_output = subprocess.check_output(
                    ["git", "diff", "--name-only", current_hash, new_hash], env=env
                ).decode()

                if "requirements.txt" in diff_output:
                    output_log.append("\n=== Python Dependencies Changed ===")
                    output_log.append("Installing updated dependencies...")

                    try:
                        base_dir = subprocess.check_output(
                            ["git", "rev-parse", "--show-toplevel"], env=env
                        ).decode().strip()
                        requirements_path = os.path.join(base_dir, "requirements.txt")

                        if os.path.exists(requirements_path):
                            install = subprocess.run(
                                [sys.executable, "-m", "pip", "install", "-r", requirements_path],
                                capture_output=True,
                                text=True,
                                timeout=300,
                            )
                            output_log.append(f"$ {sys.executable} -m pip install -r {requirements_path}")
                            output_log.append(install.stdout)
                            if install.stderr:
                                output_log.append(install.stderr)

                            if install.returncode == 0:
                                output_log.append("Dependencies installed successfully!")
                                post_update_actions.append(
                                    "Dependencies were automatically installed. "
                                    "Please restart Blombooru to fully apply the changes."
                                )
                            else:
                                output_log.append("Failed to install dependencies automatically.")
                                post_update_actions.append(
                                    f"WARNING: Automatic dependency installation failed. "
                                    f"Please manually run '{sys.executable} -m pip install -r {requirements_path}' "
                                    "and restart Blombooru."
                                )
                        else:
                            post_update_actions.append(
                                "WARNING: requirements.txt not found. "
                                "Please manually install dependencies."
                            )
                    except subprocess.TimeoutExpired:
                        output_log.append("Dependency installation timed out.")
                        post_update_actions.append(
                            "WARNING: Automatic dependency installation timed out. "
                            f"Please manually run '{sys.executable} -m pip install -r {requirements_path}' "
                            "and restart Blombooru."
                        )
                    except Exception as e:
                        output_log.append(f"Error installing dependencies: {e}")
                        post_update_actions.append(
                            "WARNING: Could not automatically install dependencies. "
                            f"Please manually run '{sys.executable} -m pip install -r {requirements_path}' "
                            "and restart Blombooru."
                        )

            except subprocess.CalledProcessError:
                pass

        message = (
            "\n\n".join(post_update_actions)
            if post_update_actions
            else "Update successful. Please restart Blombooru to apply the changes!"
        )

        return {
            "success": True,
            "log": "\n".join(output_log),
            "message": message,
            "actions_taken": {
                "git_updated": True,
                "dependencies_installed": "requirements.txt" in "\n".join(output_log),
                "needs_restart": True,
            },
        }

    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {e.cmd}\nStdout: {e.stdout}\nStderr: {e.stderr}"
        raise HTTPException(status_code=500, detail=f"Update failed: {e.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
