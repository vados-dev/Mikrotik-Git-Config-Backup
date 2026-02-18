"""
Git operations for the MikroTik config backup server.

Handles repo initialisation on startup and commit+push on every change.
"""

import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_PATH = Path("/data/repo")


def _run(
    cmd: list[str],
    check: bool = True,
    use_repo_cwd: bool = True,
) -> subprocess.CompletedProcess:
    """Run a subprocess command, optionally from within REPO_PATH."""
    result = subprocess.run(
        cmd,
        cwd=REPO_PATH if use_repo_cwd else None,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command {cmd} failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _authenticated_url(url: str) -> str:
    """Inject the PAT into an HTTPS remote URL (held in memory, never written to disk)."""
    pat = os.environ.get("GIT_PAT", "")
    if pat and url.startswith("https://"):
        return f"https://{pat}@{url[len('https://'):]}"
    return url


def _configure_repo():
    """Set local git identity inside the repo."""
    _run(["git", "config", "user.name", os.environ.get("GIT_USER_NAME", "MikroTik Backup")])
    _run(["git", "config", "user.email", os.environ.get("GIT_USER_EMAIL", "backup@localhost")])


def initialise_repo():
    """
    Called once at startup. Ensures /data/repo is a valid git repo
    pointing at the configured remote.
    """
    REPO_PATH.mkdir(parents=True, exist_ok=True)

    repo_url = os.environ.get("GIT_REPO_URL", "").strip()
    if not repo_url:
        raise ValueError("GIT_REPO_URL environment variable is not set")

    branch = os.environ.get("GIT_BRANCH", "main")

    if (REPO_PATH / ".git").exists():
        logger.info("Repo already initialised at %s", REPO_PATH)
        _configure_repo()
        return

    logger.info("Attempting to clone %s ...", repo_url)
    clone_result = subprocess.run(
        ["git", "clone", "--branch", branch, _authenticated_url(repo_url), str(REPO_PATH)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )

    if clone_result.returncode == 0:
        logger.info("Clone successful")
        _configure_repo()
        return

    # Clone failed — remote is likely empty. Init locally and wire up the remote.
    logger.warning(
        "Clone failed (rc=%d): %s — initialising empty local repo instead",
        clone_result.returncode,
        clone_result.stderr.strip(),
    )
    subprocess.run(["git", "init", "-b", branch, str(REPO_PATH)], check=True, capture_output=True)
    _run(["git", "remote", "add", "origin", repo_url])
    _configure_repo()
    logger.info("Empty repo initialised with remote origin")


def commit_and_push(router_name: str, file_label: str) -> bool:
    """
    Stage all changes, check whether anything actually changed, and if so
    commit and push.

    Returns True if a commit was made, False if nothing changed.
    """
    _run(["git", "add", "."])

    if _run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return False

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    fmt = os.environ.get(
        "COMMIT_MESSAGE_FORMAT",
        "backup: {router_name} config updated at {timestamp}",
    )
    message = fmt.format(router_name=router_name, timestamp=timestamp, file=file_label)
    _run(["git", "commit", "-m", message])
    logger.info("Committed: %s", message)

    branch = os.environ.get("GIT_BRANCH", "main")
    repo_url = os.environ.get("GIT_REPO_URL", "")

    _run(["git", "remote", "set-url", "origin", _authenticated_url(repo_url)])
    try:
        _run(["git", "push", "origin", branch])
        logger.info("Pushed to origin/%s", branch)
    finally:
        _run(["git", "remote", "set-url", "origin", repo_url])

    return True
