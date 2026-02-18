"""
MikroTik Git Config Backup — HTTP server

Receives router config files via POST, diffs against the previous version,
and commits + pushes any changes to a git repository.
"""

import hmac
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from git_ops import REPO_PATH, commit_and_push, initialise_repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# One lock so concurrent uploads don't race on git operations
_git_lock = threading.Lock()


def _get_required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return value


def _verify_token(request: Request) -> None:
    """Raise 401 if the Bearer token is missing or wrong."""
    expected = _get_required_env("ROUTER_AUTH_TOKEN")
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    provided = auth_header[len("Bearer "):]
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _strip_rsc_header(body: bytes) -> bytes:
    """
    Remove the auto-generated RouterOS header block from an RSC export.

    RouterOS prepends lines like:
        # 2026-02-19 10:34:29 by RouterOS 7.20.8
        # software id = ITTQ-AHUF
        # model = RB5009UG+S+
        # serial number = HFH094R5XVS

    The timestamp changes on every export, which would create a spurious commit
    even when the actual config has not changed. Stripping the entire leading
    comment block keeps the diff meaningful.
    """
    lines = body.decode("utf-8", errors="replace").splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return "".join(lines[i:]).encode("utf-8")
    return body


class _SuppressHealthLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uvicorn configures its loggers during startup, so the filter must be
    # added here — after uvicorn is ready — not at module import time.
    logging.getLogger("uvicorn.access").addFilter(_SuppressHealthLogs())
    logger.info("Initialising git repository ...")
    initialise_repo()
    logger.info("Repository ready. Server starting.")
    yield


app = FastAPI(
    title="MikroTik Git Config Backup",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.get("/health")
async def health():
    """Liveness probe — returns 200 when the server is up."""
    return {"status": "ok"}


@app.post("/backup/config")
async def backup_config(request: Request):
    """
    Receive the router's plain-text RSC export.

    The router POSTs the raw file body with:
        Authorization: Bearer <ROUTER_AUTH_TOKEN>

    The RouterOS timestamp header is stripped before diffing so it never
    triggers a spurious commit. The file is saved as <ROUTER_NAME>.rsc.
    """
    _verify_token(request)

    router_name = request.headers.get("X-Router-Name", "router")
    body = await request.body()

    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty body")

    body = _strip_rsc_header(body)
    dest = REPO_PATH / f"{router_name}.rsc"

    with _git_lock:
        dest.write_bytes(body)
        committed = commit_and_push(router_name=router_name, file_label="config")

    if committed:
        logger.info("Config change committed for router %r", router_name)
        return JSONResponse({"committed": True}, status_code=status.HTTP_200_OK)

    logger.debug("Config unchanged for router %r — nothing to commit", router_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("LISTEN_PORT", "8080"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
