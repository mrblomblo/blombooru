import os
import subprocess
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from ..auth import require_admin_mode
from ..config import settings

router = APIRouter(prefix="/api/system", tags=["system"])

def is_git_available() -> tuple[bool, str]:
    """Check if git repo is available and properly configured"""
    try:
        # Check if git is installed
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        
        # Check if in a git repo
        subprocess.run(
            ["git", "rev-parse", "--git-dir"], 
            check=True, 
            capture_output=True,
            text=True
        )
        
        # Check if a remote is configured
        subprocess.run(
            ["git", "remote", "get-url", "origin"],
            check=True,
            capture_output=True
        )
        
        return True, ""
    except subprocess.CalledProcessError as e:
        if "not a git repository" in e.stderr.decode() if e.stderr else "":
            return False, "Not running in a git repository. If you're using Docker, rebuild the image with: docker compose up --build --no-cache"
        return False, f"Git is not properly configured: {e.stderr.decode() if e.stderr else str(e)}"
    except FileNotFoundError:
        return False, "Git is not installed"
    except Exception as e:
        return False, f"Unable to access git: {str(e)}"

class UpdateStatus(BaseModel):
    current_hash: str
    latest_dev_hash: str
    latest_stable_tag: Optional[str] = None
    update_available: bool
    current_branch: str
    requirements_changed: bool
    notices: List[str]
    changelog: List[dict]

@router.get("/update/check", response_model=UpdateStatus)
async def check_update_status(current_user: dict = Depends(require_admin_mode)):
    """Check for available updates"""
    git_available, error_msg = is_git_available()
    if not git_available:
        raise HTTPException(status_code=503, detail=error_msg)
    
    try:
        subprocess.run(["git", "fetch"], check=True, capture_output=True)

        current_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        current_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        latest_dev_hash = subprocess.check_output(["git", "rev-parse", "origin/main"]).decode().strip()
        try:
            latest_stable_tag = subprocess.check_output(["git", "describe", "--tags", "--abbrev=0", "origin/main"]).decode().strip()
        except subprocess.CalledProcessError:
            latest_stable_tag = None

        changelog = []
        try:
            log_output = subprocess.check_output(["git", "log", "--pretty=format:%h|%B<END>", f"HEAD..origin/main"]).decode()
            if log_output:
                commits = log_output.split('<END>')
                for commit_str in commits:
                    if not commit_str.strip():
                        continue
                    parts = commit_str.split('|', 1)
                    if len(parts) >= 2:
                        commit_hash = parts[0].strip()
                        full_msg = parts[1].strip()
                        msg_lines = full_msg.split('\n', 1)
                        subject = msg_lines[0].strip()
                        body = msg_lines[1].strip() if len(msg_lines) > 1 else ""
                        
                        changelog.append({
                            "hash": commit_hash,
                            "subject": subject,
                            "body": body
                        })
        except subprocess.CalledProcessError:
            pass

        update_available = current_hash != latest_dev_hash
        requirements_changed = False
        notices = []
        try:
            diff_output = subprocess.check_output(["git", "diff", "--name-only", "HEAD", "origin/main"]).decode()
            if "requirements.txt" in diff_output:
                requirements_changed = True
                notices.append("Python dependencies have changed. You may need to run `docker compose up --build -d` or `pip install -r requirements.txt` (in the venv).")
            
            if "docker-compose.yml" in diff_output:
                notices.append("Docker Compose configuration has changed. You may need to run `docker compose up --build -d`.")
                
        except subprocess.CalledProcessError:
            pass

        return UpdateStatus(
            current_hash=current_hash,
            latest_dev_hash=latest_dev_hash,
            latest_stable_tag=latest_stable_tag,
            update_available=update_available,
            current_branch=current_branch,
            requirements_changed=requirements_changed,
            notices=notices,
            changelog=changelog[:50]
        )

    except Exception as e:
        print(f"Error checking for updates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check for updates: {str(e)}")

@router.post("/update/perform")
async def perform_update(
    target: dict, 
    current_user: dict = Depends(require_admin_mode)
):
    """Perform update"""
    git_available, error_msg = is_git_available()
    if not git_available:
        raise HTTPException(status_code=503, detail=error_msg)
    
    target_type = target.get("target", "dev") # "dev" or "stable"
    
    try:
        commands = []
        if target_type == "stable":
            latest_tag = subprocess.check_output(["git", "describe", "--tags", "--abbrev=0", "origin/main"]).decode().strip()
            commands = [
                ["git", "fetch"],   
                ["git", "checkout", latest_tag]
            ]
        else:
            commands = [
                ["git", "checkout", "main"],
                ["git", "pull"]
            ]
             
        output_log = []
        for cmd in commands:
            process = subprocess.run(cmd, check=True, capture_output=True, text=True)
            output_log.append(f"$ {' '.join(cmd)}")
            output_log.append(process.stdout)
            if process.stderr:
                 output_log.append(process.stderr)
                 
        return {"success": True, "log": "\n".join(output_log), "message": "Update successful. Please restart Blombooru to apply the changes!"}

    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {e.cmd}\nStdout: {e.stdout}\nStderr: {e.stderr}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=f"Update failed: {e.stderr}")
    except Exception as e:
        print(f"Update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
