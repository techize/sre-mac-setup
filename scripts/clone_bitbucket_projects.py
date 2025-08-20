#!/usr/bin/env python3
"""
Clone all repositories from Bitbucket Cloud workspace filtered by project keys.

Authentication (preferred):
- BITBUCKET_USERNAME (Bitbucket/Atlassian account email) and BITBUCKET_API_TOKEN: use Basic auth per Atlassian docs.

Other supported methods:
- BITBUCKET_ACCESS_TOKEN: Bearer token (Workspace/Project/Repo access token) with repository:read and project:read.
- BB_USERNAME and BB_APP_PASSWORD (App Password) – legacy basic auth.

Required env var:
- BB_WORKSPACE: Bitbucket workspace slug (e.g. sportpursuit)

Usage examples:
    # Single project (token-based auth)
    python3 clone_bitbucket_projects.py --projects DEVOPS --dest ~/repos

    # Multiple projects
    python3 clone_bitbucket_projects.py --projects DEVOPS,PLATFORM --dest ~/repos

    # Dry run
    python3 clone_bitbucket_projects.py --projects DEVOPS --dest ~/repos --dry-run
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import requests

BITBUCKET_API = "https://api.bitbucket.org/2.0"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def get_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        eprint(f"Missing env var: {name}")
        sys.exit(2)
    return val


def get_auth_context() -> Tuple[Optional[Tuple[str, str]], dict]:
    """Return (basic_auth_tuple_or_None, headers_dict) depending on env vars.

    Priority:
    1) BITBUCKET_ACCESS_TOKEN -> Bearer token header
    2) BB_USERNAME + BB_APP_PASSWORD -> Basic auth
    """
    # 1) New API token flow (Basic auth with username:token)
    api_user = os.environ.get("BITBUCKET_USERNAME")
    api_token = os.environ.get("BITBUCKET_API_TOKEN")
    if api_user and api_token:
        return (api_user, api_token), {}

    # 2) Bearer token flow (Workspace Access Token)
    token = os.environ.get("BITBUCKET_ACCESS_TOKEN")
    if token:
        return None, {"Authorization": f"Bearer {token}"}

    username = os.environ.get("BB_USERNAME")
    app_password = os.environ.get("BB_APP_PASSWORD")
    if username and app_password:
        return (username, app_password), {}

    eprint("Missing authentication. Set BITBUCKET_USERNAME and BITBUCKET_API_TOKEN, or BITBUCKET_ACCESS_TOKEN, or BB_USERNAME and BB_APP_PASSWORD.")
    sys.exit(2)


def iter_paginated(url: str, auth: Optional[tuple], headers: Optional[dict], params: Optional[dict] = None):
    params = params or {}
    while url:
        r = requests.get(url, auth=auth, headers=headers, params=params, timeout=30)
        if r.status_code in (401, 403):
            eprint(
                "Bitbucket API returned %s. Ensure your token has repository:read and project:read and is a Workspace Access Token."
                % r.status_code
            )
        r.raise_for_status()
        data = r.json()
        yield from data.get("values", [])
        url = data.get("next")
        params = None  # next already contains the query


def list_repos(workspace: str, projects: Iterable[str], auth: Optional[tuple], headers: Optional[dict]) -> List[dict]:
    projects_set = {p.strip().upper() for p in projects if p.strip()}
    url = f"{BITBUCKET_API}/repositories/{workspace}"
    repos: List[dict] = []
    for repo in iter_paginated(url, auth, headers, params={"pagelen": 100}):
        proj = (repo.get("project") or {}).get("key", "").upper()
        if projects_set and proj not in projects_set:
            continue
        repos.append(repo)
    return repos


def git_clone_or_update(repo: dict, dest_dir: Path, dry_run: bool = False) -> None:
    name = repo["name"]
    slug = repo["slug"]
    project_key = repo.get("project", {}).get("key", "")
    # Prefer SSH if available, else HTTPS
    ssh_link = next((l["href"] for l in repo.get("links", {}).get("clone", []) if l.get("name") == "ssh"), None)
    https_link = next((l["href"] for l in repo.get("links", {}).get("clone", []) if l.get("name") == "https"), None)

    # Construct HTTPS with credentials for read-only if user prefers HTTPS; SSH is cleaner if keys are set
    clone_url = ssh_link or https_link
    if not clone_url:
        eprint(f"No clone URL for {name} ({slug})")
        return

    target = dest_dir / slug
    if target.exists():
        # Fetch updates
        if dry_run:
            print(f"[DRY RUN] git -C {target} fetch --all --prune")
            return
        subprocess.run(["git", "-C", str(target), "remote", "set-url", "origin", clone_url], check=False)
        subprocess.run(["git", "-C", str(target), "fetch", "--all", "--prune"], check=False)
        return

    # Ensure parent directory
    target.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"[DRY RUN] git clone {clone_url} {target}")
        return
    subprocess.run(["git", """clone""", clone_url, str(target)], check=True)


def main():
    parser = argparse.ArgumentParser(description="Clone Bitbucket repos by project key")
    parser.add_argument("--projects", required=True, help="Comma-separated project keys, e.g. DEVOPS,PLATFORM")
    parser.add_argument("--dest", required=True, help="Destination directory for clones")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--list", action="store_true", help="Only list repositories and exit")
    args = parser.parse_args()

    workspace = get_env("BB_WORKSPACE")
    auth, headers = get_auth_context()

    projects = [p.strip() for p in args.projects.split(",") if p.strip()]
    dest_dir = Path(os.path.expanduser(args.dest)).resolve()

    try:
        repos = list_repos(workspace, projects, auth, headers)
    except requests.HTTPError as e:
        eprint(f"Failed to list repositories: {e}")
        sys.exit(1)
    if args.list:
        print(json.dumps([
            {
                "name": r.get("name"),
                "slug": r.get("slug"),
                "project": (r.get("project") or {}).get("key"),
                "ssh": next((l["href"] for l in r.get("links", {}).get("clone", []) if l.get("name") == "ssh"), None),
                "https": next((l["href"] for l in r.get("links", {}).get("clone", []) if l.get("name") == "https"), None),
            }
            for r in repos
        ], indent=2))
        return

    for r in repos:
        git_clone_or_update(r, dest_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
