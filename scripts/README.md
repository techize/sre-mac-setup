# Bitbucket workspace cloner

A small Python utility to list and clone all repositories from specific Bitbucket Cloud project(s) in a workspace.

## Prereqs

- Python 3.9+
- Environment variables set:
  - `BB_WORKSPACE` (e.g. `sportpursuit`)
  - Preferred: `BITBUCKET_USERNAME` (your Atlassian account email) and `BITBUCKET_API_TOKEN`
  - Alternatively: `BITBUCKET_ACCESS_TOKEN` (workspace/project/repo access token)
  - Legacy fallback: `BB_USERNAME` and `BB_APP_PASSWORD`

## Install deps

```bash
pip3 install -r requirements.txt
```

## Usage

```bash
# List repos in DEVOPS
python3 clone_bitbucket_projects.py --projects DEVOPS --dest ~/repos --list

# Dry-run clone
python3 clone_bitbucket_projects.py --projects DEVOPS --dest ~/repos --dry-run

# Clone multiple projects
python3 clone_bitbucket_projects.py --projects DEVOPS,PLATFORM --dest ~/repos

# Nightly sync: fast-forward main/master only and print a report
python3 clone_bitbucket_projects.py --projects DEVOPS --dest ~/repos \
  --sync-default --report text

# JSON report (for tooling)
python3 clone_bitbucket_projects.py --projects DEVOPS --dest ~/repos \
  --report json
```

## Notes

- Uses SSH clone URLs when available; ensure your SSH key is configured for Bitbucket.
- If a repo folder already exists, the script will fetch/prune instead of recloning.
- --sync-default only fast-forwards main/master if behind; it will not push, merge, or modify diverged/ahead repos. It reports:
  - default branch ahead/behind relative to origin
  - dirty working tree status
  - branches with unpushed commits (ahead of their upstream)

### Cron example

Pipe a text report to email daily:

```bash
0 3 * * * cd /path/to/sre-mac-setup/scripts && \
  BB_WORKSPACE=sportpursuit BITBUCKET_USERNAME=you@company.com BITBUCKET_API_TOKEN=*** \
  /usr/bin/python3 clone_bitbucket_projects.py --projects DEVOPS --dest ~/repos --sync-default --report text \
  | mail -s "DEVOPS repo sync report" you@company.com
```
Or use the wrapper script (recommended):

```bash
MAIL_TO=you@company.com PROJECTS=DEVOPS DEST=$HOME/repos \
  /path/to/sre-mac-setup/scripts/nightly_repo_sync.sh
```

Add to crontab to run at midnight:

```bash
0 0 * * * MAIL_TO=you@company.com PROJECTS=DEVOPS DEST=$HOME/repos \
  /path/to/sre-mac-setup/scripts/nightly_repo_sync.sh >> $HOME/Library/Logs/repo-sync-cron.log 2>&1
```

Create ~/.bitbucket_env to hold credentials (do not commit this file):

```bash
export BB_WORKSPACE=sportpursuit
export BITBUCKET_USERNAME=you@company.com
export BITBUCKET_API_TOKEN=xxxxx
```
