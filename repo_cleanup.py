#!/usr/bin/env python3
"""
Repo Cleanup: find & remove generated artifacts (safe by default)

Scans the *current* Git repository (or CWD if no repo found) for common
ephemeral folders/files like:
  - Terraform: .terraform/, .terragrunt-cache/, *.tfplan, crash logs
  - Node/JS: node_modules/, dist/, build/, .next/, coverage/
  - Python: __pycache__/, .pytest_cache/, .mypy_cache/, .ruff_cache/, .tox/, *.pyc
  - Java/Gradle/Rust: target/, .gradle/, build/
  - Misc: .DS_Store, Thumbs.db, editor swap files

It EXCLUDES potentially critical things like Terraform state/lock files.
Optional "risky" items (off by default): venv/, .venv/, .idea/, .vscode/, .devcontainer/

Usage:
  python repo_cleanup.py               # dry-run scan (safe targets only)
  python repo_cleanup.py --yes         # prompt + delete on 'y' (safe targets)
  python repo_cleanup.py --include-risky
  python repo_cleanup.py --yes --include-risky
  python repo_cleanup.py --only "Terraform,Node/JS"
  python repo_cleanup.py --exclude-glob "dist,build"

Exit codes: 0 success, 1 error
"""
import argparse
import fnmatch
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# -------- Rules (category, risk[safe|risky], type[dir|file], pattern-on-basename) --------

RULES = [
    # Terraform
    ("Terraform", "safe",  "dir",  ".terraform"),
    ("Terraform", "safe",  "dir",  ".terragrunt-cache"),
    ("Terraform", "safe",  "file", "*.tfplan"),
    ("Terraform", "safe",  "file", "crash.log"),
    ("Terraform", "safe",  "file", "crash.*.log"),

    # Node / JS
    ("Node/JS",   "safe",  "dir",  "node_modules"),
    ("Node/JS",   "safe",  "dir",  "dist"),
    ("Node/JS",   "safe",  "dir",  "build"),
    ("Node/JS",   "safe",  "dir",  ".next"),
    ("Node/JS",   "safe",  "dir",  ".nuxt"),
    ("Node/JS",   "safe",  "dir",  ".turbo"),
    ("Node/JS",   "safe",  "dir",  ".parcel-cache"),
    ("Node/JS",   "safe",  "dir",  "coverage"),

    # Python
    ("Python",    "safe",  "dir",  "__pycache__"),
    ("Python",    "safe",  "dir",  ".pytest_cache"),
    ("Python",    "safe",  "dir",  ".mypy_cache"),
    ("Python",    "safe",  "dir",  ".ruff_cache"),
    ("Python",    "safe",  "dir",  ".ipynb_checkpoints"),
    ("Python",    "safe",  "dir",  ".tox"),
    ("Python",    "safe",  "file", "*.pyc"),
    ("Python",    "safe",  "file", "*.pyo"),

    # Java/Gradle/Rust/General build
    ("Build",     "safe",  "dir",  "target"),
    ("Build",     "safe",  "dir",  ".gradle"),

    # OS/editor junk
    ("Misc",      "safe",  "file", ".DS_Store"),
    ("Misc",      "safe",  "file", "Thumbs.db"),
    ("Misc",      "safe",  "file", "*.swp"),
    ("Misc",      "safe",  "file", "*.swo"),

    # Risky/Optional (off by default)
    ("Dev env",   "risky", "dir",  "venv"),
    ("Dev env",   "risky", "dir",  ".venv"),
    ("Dev env",   "risky", "dir",  "env"),
    ("Dev env",   "risky", "dir",  ".idea"),
    ("Dev env",   "risky", "dir",  ".vscode"),
    ("Dev env",   "risky", "dir",  ".devcontainer"),
]

# Explicitly *not* deleting: terraform.tfstate, terraform.tfstate.backup, .terraform.lock.hcl, *.tfvars


def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    s = float(n)
    for u in units:
        if s < 1024 or u == units[-1]:
            return f"{s:.1f} {u}"
        s /= 1024


def find_git_root(start: Path) -> Path:
    p = start.resolve()
    while True:
        if (p / ".git").is_dir():
            return p
        if p.parent == p:
            return start.resolve()  # fall back to CWD
        p = p.parent


def path_size(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        total = 0
        for dp, dn, fn in os.walk(p, onerror=lambda e: None):
            for f in fn:
                try:
                    total += (Path(dp) / f).stat().st_size
                except Exception:
                    pass
        return total
    except Exception:
        return 0


def build_rule_index(include_risky: bool, only_cats: List[str]) -> Tuple[List[Tuple], List[Tuple]]:
    selected = []
    for cat, risk, typ, pat in RULES:
        if only_cats and cat not in only_cats:
            continue
        if risk == "risky" and not include_risky:
            continue
        selected.append((cat, risk, typ, pat))
    dir_rules = [r for r in selected if r[2] == "dir"]
    file_rules = [r for r in selected if r[2] == "file"]
    return dir_rules, file_rules


def should_exclude_by_glob(path: Path, exclude_globs: List[str]) -> bool:
    if not exclude_globs:
        return False
    name = path.name
    for g in exclude_globs:
        if fnmatch.fnmatch(name, g) or fnmatch.fnmatch(str(path), g):
            return True
    return False


def scan(root: Path, include_risky: bool, only_cats: List[str], exclude_globs: List[str]) -> Dict[str, Dict]:
    dir_rules, file_rules = build_rule_index(include_risky, only_cats)
    matches: Dict[str, Dict] = {}
    chosen_dirs: List[Path] = []

    def add_item(cat: str, p: Path):
        if should_exclude_by_glob(p, exclude_globs):
            return
        bucket = matches.setdefault(cat, {"items": [], "size": 0})
        # Avoid adding nested items if a parent dir is already selected
        for parent in p.parents:
            if parent in chosen_dirs:
                return
        bucket["items"].append(p)

    # Walk and match
    for dp, dirnames, filenames in os.walk(root):
        dp_path = Path(dp)

        # do not traverse .git
        dirnames[:] = [d for d in dirnames if d != ".git"]

        # Match directory rules by basename
        to_prune = set()
        for d in list(dirnames):
            for cat, risk, typ, pat in dir_rules:
                if fnmatch.fnmatch(d, pat):
                    full = dp_path / d
                    add_item(cat, full)
                    chosen_dirs.append(full)
                    to_prune.add(d)
                    break
        # Don't walk into matched dirs
        if to_prune:
            dirnames[:] = [d for d in dirnames if d not in to_prune]

        # Match file rules by basename
        for f in filenames:
            for cat, risk, typ, pat in file_rules:
                if fnmatch.fnmatch(f, pat):
                    full = dp_path / f
                    add_item(cat, full)
                    break

    # Compute sizes
    for cat, data in matches.items():
        uniq = []
        seen = set()
        for p in data["items"]:
            if p not in seen:
                uniq.append(p)
                seen.add(p)
        data["items"] = uniq
        total = 0
        for p in uniq:
            total += path_size(p)
        data["size"] = total
    return matches


def summarize(matches: Dict[str, Dict]) -> Tuple[str, int, int]:
    lines = []
    total_items = 0
    total_bytes = 0
    cats_sorted = sorted(matches.items(), key=lambda kv: kv[1]["size"], reverse=True)
    for cat, data in cats_sorted:
        count = len(data["items"])
        size = data["size"]
        total_items += count
        total_bytes += size
        lines.append(f"- {cat}: {count} item(s), {human_size(size)}")
    summary = "\n".join(lines) if lines else "No removable items found."
    return summary, total_items, total_bytes


def delete_all(matches: Dict[str, Dict]) -> Tuple[int, List[str]]:
    freed = 0
    errors: List[str] = []

    # Flatten all items and sort by path length (longest first) to remove deep paths first
    all_items: List[Path] = []
    for data in matches.values():
        all_items.extend(data["items"])
    all_items = sorted(set(all_items), key=lambda p: len(str(p)), reverse=True)

    for p in all_items:
        try:
            freed += path_size(p)
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
        except Exception as e:
            errors.append(f"{p}: {e}")
    return freed, errors


def main():
    parser = argparse.ArgumentParser(description="Find and remove generated artifacts from the current repo.")
    parser.add_argument("--yes", action="store_true",
                        help="Skip dry-run and prompt to delete everything found.")
    parser.add_argument("--include-risky", action="store_true",
                        help="Include optional directories like venv/, .vscode/, .idea/.")
    parser.add_argument("--only", type=str, default="",
                        help="Comma-separated list of categories to include (e.g. 'Terraform,Node/JS').")
    parser.add_argument("--exclude-glob", type=str, default="",
                        help="Comma-separated glob(s) to exclude (matched against name or full path).")
    args = parser.parse_args()

    only_cats = [c.strip() for c in args.only.split(",") if c.strip()]
    exclude_globs = [g.strip() for g in args.exclude_glob.split(",") if g.strip()]

    repo_root = find_git_root(Path.cwd())
    print(f"Scanning: {repo_root}")

    matches = scan(repo_root, include_risky=args.include_risky, only_cats=only_cats, exclude_globs=exclude_globs)
    summary, total_items, total_bytes = summarize(matches)

    print("\nSummary by category:")
    print(summary)
    print(f"\nTotal: {total_items} item(s), {human_size(total_bytes)}\n")

    # Show top items (largest first)
    if total_items:
        all_items = []
        for cat, data in matches.items():
            for p in data["items"]:
                all_items.append((p, data))
        # recompute sizes per item for sorting
        item_sizes = [(p, path_size(p)) for (p, _) in all_items]
        item_sizes.sort(key=lambda t: t[1], reverse=True)

        print("Largest items:")
        for p, sz in item_sizes[:20]:
            print(f"  {human_size(sz):>8}  {p}")
        print()

    if total_items == 0:
        sys.exit(0)

    # Prompt
    if args.yes:
        reply = input(f"Delete ALL of the above ({human_size(total_bytes)})? [y/N]: ").strip().lower()
    else:
        print("Dry run only. Re-run with --yes to enable deletion.")
        reply = input("Proceed to delete ALL found items now? [y/N]: ").strip().lower()

    if reply in ("y", "yes"):
        freed, errors = delete_all(matches)
        print(f"\nDeleted. Space freed: {human_size(freed)}")
        if errors:
            print("\nSome items failed to delete:")
            for e in errors:
                print(f"  - {e}")
        sys.exit(0 if not errors else 1)
    else:
        print("Aborted. Nothing was deleted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
