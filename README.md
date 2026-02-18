# MikroTik Git Config Backup

A Docker server that receives your MikroTik router's config on a schedule, and commits it to a git repository whenever something changes.

The router runs a script that exports its config and POSTs it to the server. The server strips the auto-generated timestamp header, checks if anything actually changed, and commits + pushes if so. If nothing changed, it does nothing.

---

## Setup

### 1. Create a private git repository

GitHub, GitLab, Gitea — anything works. Copy the HTTPS clone URL.

### 2. Create a Personal Access Token

Go to https://github.com/settings/personal-access-tokens/new and create a fine-grained token with:
- **Repository access** → your backup repo only
- **Repository permissions → Contents** → Read and write

### 3. Configure and start the server

Edit the `environment:` block in `docker-compose.yml`, then:

```bash
docker compose up -d
```

The container clones the repo on first start and stores the working tree in `./repo_data`.

### 4. Install the RouterOS script

Edit the three variables at the top of `router-scripts/mikrotik-backup.rsc` and add it to the router under **System → Scripts**. Test it with `/system script run git-backup`, then schedule it under **System → Scheduler**.

---

## Configuration

All settings are in the `environment:` block in `docker-compose.yml`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ROUTER_AUTH_TOKEN` | Yes | — | Bearer token the router sends. Generate with `openssl rand -hex 32`. |
| `GIT_REPO_URL` | Yes | — | HTTPS remote repo URL (`https://...`). |
| `GIT_PAT` | Yes | — | Personal Access Token. |
| `GIT_BRANCH` | No | `main` | Branch to commit to. |
| `GIT_USER_NAME` | No | `MikroTik Backup` | Git commit author name. |
| `GIT_USER_EMAIL` | No | `backup@localhost` | Git commit author email. |
| `COMMIT_MESSAGE_FORMAT` | No | `backup: {router_name} config updated at {timestamp}` | Supports `{router_name}` and `{timestamp}`. |
| `LISTEN_PORT` | No | `8080` | Also update the `ports:` mapping if you change this. |

