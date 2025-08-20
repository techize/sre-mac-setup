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

        # Sync mode (fast-forward pull only for main/master) and report
        python3 clone_bitbucket_projects.py --projects DEVOPS --dest ~/repos \
            --sync-default --report text
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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


def git_clone_or_update(repo: dict, dest_dir: Path, dry_run: bool = False, do_fetch: bool = True) -> None:
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
        # Update remote URL and optionally refresh origin (fast)
        if dry_run:
            print(f"[DRY RUN] git -C {target} remote set-url origin {clone_url}")
            print(f"[DRY RUN] git -C {target} remote update -p -q origin")
            return
        subprocess.run(["git", "-C", str(target), "remote", "set-url", "origin", clone_url], check=False)
        if do_fetch:
            # Fast update of remote refs without fetching every remote/branch
            subprocess.run(["git", "-C", str(target), "remote", "update", "-p", "-q", "origin"], check=False)
        return

    # Ensure parent directory
    target.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"[DRY RUN] git clone {clone_url} {target}")
        return
    subprocess.run(["git", """clone""", "-q", clone_url, str(target)], check=True)


def run(cmd: List[str], cwd: Optional[Path] = None, check: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")  # avoid hangs on credentials
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check, capture_output=True, text=True, env=env)


def branch_exists(repo_dir: Path, branch: str) -> bool:
    res = run(["git", "show-ref", "--verify", f"refs/heads/{branch}"], cwd=repo_dir)
    return res.returncode == 0


def remote_branch_exists(repo_dir: Path, branch: str, remote: str = "origin") -> bool:
    res = run(["git", "ls-remote", "--heads", remote, branch], cwd=repo_dir)
    return bool(res.stdout.strip())


def current_branch(repo_dir: Path) -> str:
    res = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    return res.stdout.strip()


def ahead_behind(repo_dir: Path, local_ref: str, remote_ref: str) -> Tuple[int, int]:
    res = run(["git", "rev-list", "--left-right", "--count", f"{local_ref}...{remote_ref}"], cwd=repo_dir)
    if res.returncode != 0 or not res.stdout.strip():
        return (0, 0)
    left, right = res.stdout.strip().split()
    return int(left), int(right)


def list_ahead_branches(repo_dir: Path) -> List[Tuple[str, int]]:
    res = run(["git", "for-each-ref", "refs/heads", "--format=%(refname:short) %(upstream:short)"], cwd=repo_dir)
    ahead: List[Tuple[str, int]] = []
    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] == "":
            continue
        local = parts[0]
        upstream = parts[1]
        a, _b = ahead_behind(repo_dir, local, upstream)
        if a > 0:
            ahead.append((local, a))
    return ahead


def is_dirty(repo_dir: Path) -> bool:
    res = run(["git", "status", "--porcelain"], cwd=repo_dir)
    return bool(res.stdout.strip())


def detect_default_branch(repo_dir: Path, remote: str = "origin") -> Optional[str]:
    # Ask remote for its HEAD symref, fallback to main/master existence
    res = run(["git", "ls-remote", "--symref", remote, "HEAD"], cwd=repo_dir)
    for line in res.stdout.splitlines():
        # format: ref: refs/heads/main\tHEAD
        if line.startswith("ref:") and "HEAD" in line:
            ref = line.split()[1] if "\t" not in line else line.split("\t")[0].split()[-1]
            if ref.startswith("refs/heads/"):
                return ref.split("/", 2)[-1]
    # Fallback checks
    if remote_branch_exists(repo_dir, "main", remote):
        return "main"
    if remote_branch_exists(repo_dir, "master", remote):
        return "master"
    return None


def update_remote_branch(repo_dir: Path, branch: str, remote: str = "origin") -> None:
    # Fetch only the specific branch's remote tracking ref
    run(["git", "fetch", "-q", remote, f"refs/heads/{branch}:refs/remotes/{remote}/{branch}"], cwd=repo_dir)


def fast_forward_default(repo_dir: Path, default_branch: str, dry_run: bool = False) -> Tuple[str, Optional[str]]:
    """Fast-forward update the default branch from origin only.

    Returns (action, error). action in {"pulled", "up-to-date", "skipped"}
    """
    # Ensure remote tracking ref for default branch is up to date
    update_remote_branch(repo_dir, default_branch)

    cur = current_branch(repo_dir)
    a, b = ahead_behind(repo_dir, default_branch, f"origin/{default_branch}")
    if a > 0 and b == 0:
        return "skipped", None  # local ahead, don't modify
    if a > 0 and b > 0:
        return "skipped", None  # diverged, report only
    if a == 0 and b == 0:
        return "up-to-date", None

    # Local is behind only; update default branch
    if dry_run:
        if cur == default_branch:
            print(f"[DRY RUN] git -C {repo_dir} pull --ff-only origin {default_branch}")
        else:
            print(f"[DRY RUN] git -C {repo_dir} fetch origin {default_branch}:{default_branch}")
        return "pulled", None

    if cur == default_branch:
        res = run(["git", "pull", "--ff-only", "origin", default_branch], cwd=repo_dir)
        if res.returncode != 0:
            return "skipped", res.stderr.strip() or res.stdout.strip()
        return "pulled", None
    else:
        # Update local branch without switching (fast-forward only)
        res = run(["git", "fetch", "-q", "origin", f"{default_branch}:{default_branch}"], cwd=repo_dir)
        if res.returncode != 0:
            return "skipped", res.stderr.strip() or res.stdout.strip()
        return "pulled", None


def summarize_repo(repo: dict, dest_dir: Path, perform_pull: bool, dry_run: bool = False) -> Dict:
    slug = repo["slug"]
    path = dest_dir / slug
    summary: Dict = {
        "name": repo.get("name"),
        "slug": slug,
        "path": str(path),
        "default_branch": None,
        "current_branch": None,
        "ahead_main": 0,
        "behind_main": 0,
        "dirty": False,
        "ahead_branches": [],
        "action": None,
        "error": None,
    }

    if not path.exists():
        # Will be cloned by outer loop; report as such
        summary["action"] = "to-clone"
        return summary

    default = detect_default_branch(path)
    summary["default_branch"] = default
    cur = current_branch(path)
    summary["current_branch"] = cur

    if default:
        # Only update remote tracking ref if we are performing a pull; otherwise use locally-known info
        if perform_pull:
            update_remote_branch(path, default)
        a, b = ahead_behind(path, default, f"origin/{default}") if branch_exists(path, default) else (0, 0)
        summary["ahead_main"], summary["behind_main"] = a, b
        if perform_pull:
            action, err = fast_forward_default(path, default, dry_run=dry_run)
            summary["action"], summary["error"] = action, err
        else:
            summary["action"] = "checked"
    else:
        summary["action"] = "no-default-branch"

    summary["dirty"] = is_dirty(path)
    summary["ahead_branches"] = [
        {"branch": bname, "ahead": ahead}
        for (bname, ahead) in list_ahead_branches(path)
    ]

    return summary


def main():
    parser = argparse.ArgumentParser(description="Clone Bitbucket repos by project key, with optional sync/report")
    parser.add_argument("--projects", required=True, help="Comma-separated project keys, e.g. DEVOPS,PLATFORM")
    parser.add_argument("--dest", required=True, help="Destination directory for clones")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--list", action="store_true", help="Only list repositories and exit")
    parser.add_argument("--sync-default", action="store_true", help="Fast-forward pull only for main/master if behind (no pushes, no merges)")
    parser.add_argument("--report", choices=["text", "json"], help="Print a repo sync report in the chosen format")
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

    # Clone missing repos and adjust remotes for existing ones (skip heavy fetching here)
    for r in repos:
        git_clone_or_update(r, dest_dir, dry_run=args.dry_run, do_fetch=False)

    # Build report if requested or syncing
    if args.report or args.sync_default:
        summaries = []
        for r in repos:
            summaries.append(summarize_repo(r, dest_dir, perform_pull=args.sync_default, dry_run=args.dry_run))

        if args.report == "json":
            print(json.dumps(summaries, indent=2))
        else:
            # Text report
            lines = ["Repo sync report:"]
            for s in summaries:
                status_bits = []
                if s["default_branch"]:
                    status_bits.append(f"{s['default_branch']}: +{s['ahead_main']}/-{s['behind_main']}")
                if s["dirty"]:
                    status_bits.append("dirty")
                if s["ahead_branches"]:
                    ahead_list = ", ".join(f"{b['branch']}(+{b['ahead']})" for b in s["ahead_branches"])
                    status_bits.append(f"unpushed: {ahead_list}")
                if s["error"]:
                    status_bits.append(f"error: {s['error']}")
                lines.append(f"- {s['slug']} [{s['action'] or 'n/a'}] " + ("; ".join(status_bits) if status_bits else "ok"))
            print("\n".join(lines))



if __name__ == "__main__":
    main()
