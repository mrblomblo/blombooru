import os
import subprocess
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from ..auth import require_admin_mode
from ..config import settings

router = APIRouter(prefix="/api/system", tags=["system"])

def is_running_in_docker() -> bool:
    """Check if the application is running in a Docker container"""
    if os.path.exists("/.dockerenv"):
        return True
    
    if os.path.exists("/proc/self/cgroup"):
        try:
            with open("/proc/self/cgroup", "r") as f:
                return "docker" in f.read()
        except:
            pass
    
    return False

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
            return False, "Not running in a git repository. If you're using Docker, rebuild the image with: docker compose up --build"
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
    remote_url: Optional[str] = None

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
            remote_url = subprocess.check_output(["git", "remote", "get-url", "origin"]).decode().strip()
        except subprocess.CalledProcessError:
            remote_url = None

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
        
        if is_running_in_docker():
            notices.append("Running in Docker: The built-in updater cannot be used from within a Docker container. To update, run 'git pull' on the host machine, then 'docker compose down && docker compose up --build -d' in the project root folder.")
        
        try:
            diff_output = subprocess.check_output(["git", "diff", "--name-only", "HEAD", "origin/main"]).decode()
            if "requirements.txt" in diff_output:
                requirements_changed = True
                if not is_running_in_docker():
                    notices.append("Python dependencies have changed. The updater will automatically install them when you update.")
            
            if "docker-compose.yml" in diff_output or "Dockerfile" in diff_output:
                if not is_running_in_docker():
                    notices.append("Docker configuration has changed. If you plan to use Docker, you will need to rebuild with 'docker compose up --build -d'.")

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
            changelog=changelog[:50],
            remote_url=remote_url
        )

    except Exception as e:
        print(f"Error checking for updates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check for updates: {str(e)}")

@router.post("/update/perform")
async def perform_update(
    target: dict, 
    current_user: dict = Depends(require_admin_mode)
):
    """Perform update and automatically handle dependencies"""
    git_available, error_msg = is_git_available()
    if not git_available:
        raise HTTPException(status_code=503, detail=error_msg)
    
    in_docker = is_running_in_docker()
    if in_docker:
        raise HTTPException(
            status_code=400, 
            detail="Cannot update from within Docker container. Please run 'git pull' on the host machine, then 'docker compose down && docker compose up --build -d' in the project root folder."
        )
    
    target_type = target.get("target", "dev") # "dev" or "stable"
    
    try:
        current_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
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
        
        new_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()        
        requirements_changed = False
        docker_files_changed = False
        post_update_actions = []
        
        if current_hash != new_hash:
            try:
                diff_output = subprocess.check_output(
                    ["git", "diff", "--name-only", current_hash, new_hash]
                ).decode()
                
                if "requirements.txt" in diff_output:
                    requirements_changed = True
                
                if "docker-compose.yml" in diff_output or "Dockerfile" in diff_output:
                    docker_files_changed = True
                    
            except subprocess.CalledProcessError:
                pass
        
        # Handle dependencies automatically when running locally, not in Docker
        if requirements_changed:
            output_log.append("\n=== Python Dependencies Changed ===")
            output_log.append("Installing updated dependencies...")
            
            # Try to install dependencies
            try:
                base_dir = subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"]
                ).decode().strip()
                requirements_path = os.path.join(base_dir, "requirements.txt")
                
                if os.path.exists(requirements_path):
                    install_process = subprocess.run(
                        ["pip", "install", "-r", requirements_path],
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout
                    )
                    
                    output_log.append(f"$ pip install -r {requirements_path}")
                    output_log.append(install_process.stdout)
                    if install_process.stderr:
                        output_log.append(install_process.stderr)
                    
                    if install_process.returncode == 0:
                        output_log.append("Dependencies installed successfully!")
                        post_update_actions.append(
                            "Dependencies were automatically installed. Please restart Blombooru to apply the changes."
                        )
                    else:
                        output_log.append("Failed to install dependencies automatically.")
                        post_update_actions.append(
                            f"WARNING: Automatic dependency installation failed. Please manually run 'pip install -r {requirements_path}' and restart Blombooru. You will need to run said command in the venv you created for Blombooru."
                        )
                else:
                    post_update_actions.append(
                        "WARNING: requirements.txt not found. Please manually install dependencies."
                    )
                    
            except subprocess.TimeoutExpired:
                output_log.append("Dependency installation timed out.")
                post_update_actions.append(
                    "WARNING: Automatic dependency installation timed out. Please manually run 'pip install -r requirements.txt' and restart Blombooru. You will need to run said command in the venv you created for Blombooru."
                )
            except Exception as e:
                output_log.append(f"Error installing dependencies: {str(e)}")
                post_update_actions.append(
                    f"WARNING: Could not automatically install dependencies. Please manually run 'pip install -r requirements.txt' and restart Blombooru. You will need to run said command in the venv you created for Blombooru."
                )
        
        if docker_files_changed:
            output_log.append("\n=== Docker Configuration Changed ===")
            output_log.append("Note: Docker configuration files have changed.")
            post_update_actions.append(
                "INFO: Docker configuration has changed. If you plan to run in Docker, rebuild with 'docker compose up --build -d'."
            )
        
        if post_update_actions:
            message = "\n\n".join(post_update_actions)
        else:
            message = "Update successful. Please restart Blombooru to apply the changes!"
                 
        return {
            "success": True, 
            "log": "\n".join(output_log), 
            "message": message,
            "actions_taken": {
                "git_updated": True,
                "dependencies_installed": requirements_changed,
                "needs_restart": True
            }
        }

    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {e.cmd}\nStdout: {e.stdout}\nStderr: {e.stderr}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=f"Update failed: {e.stderr}")
    except Exception as e:
        print(f"Update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
