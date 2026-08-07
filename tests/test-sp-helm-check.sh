#!/usr/bin/env bash
# Test harness for sp-helm-check. Builds a throwaway chart per case.
# Usage: test-sp-helm-check.sh /path/to/sp-helm-check [/path/to/bash]
#
# Second argument lets the suite run against a specific bash, so the bash 3.2
# empty-array case can be exercised on macOS: test-sp-helm-check.sh ./bin/sp-helm-check /bin/bash
set -uo pipefail

CHECK="${1:?usage: $0 /path/to/sp-helm-check [/path/to/bash]}"
CHECK="$(cd "$(dirname "$CHECK")" && pwd)/$(basename "$CHECK")"
BASH_BIN="${2:-bash}"

if ! command -v helm >/dev/null 2>&1; then
  echo "helm not found in PATH; cannot test sp-helm-check" >&2
  exit 0
fi

pass=0; fail=0

# mkchart <dir> : minimal chart whose template dereferences a nested value, so it
# renders only when a values file is supplied. Mirrors jenkins sa.yaml's
# .Values.main.dockerSecretName, which is what exposed the original bug.
mkchart() {
  local d; d="$(mktemp -d)"
  mkdir -p "$d/deployment/helm_charts/jenkins/templates"
  local c="$d/deployment/helm_charts/jenkins"
  cat > "$c/Chart.yaml" <<'YAML'
apiVersion: v2
name: jenkins
version: 0.1.0
YAML
  cat > "$c/templates/sa.yaml" <<'YAML'
apiVersion: v1
kind: ServiceAccount
metadata:
  name: test
imagePullSecrets:
  - name: {{ .Values.main.dockerSecretName }}
YAML
  echo "$d"
}

addvalues() { # addvalues <repodir> <filename>
  cat > "$1/deployment/helm_charts/jenkins/$2" <<'YAML'
main:
  dockerSecretName: docker-secret
YAML
}

check() {
  if [ "$2" = "$3" ]; then
    printf '  PASS  %-58s (exit %s)\n' "$1" "$3"; pass=$((pass+1))
  else
    printf '  FAIL  %-58s expected %s, got %s\n' "$1" "$2" "$3"; fail=$((fail+1))
  fi
}

run() { # run <dir> [args...]
  local d="$1"; shift
  ( cd "$d" && "$BASH_BIN" "$CHECK" "$@" >/dev/null 2>&1 ); echo $?
}

echo "Testing: $CHECK"
echo "Using bash: $BASH_BIN ($("$BASH_BIN" --version | head -1 | sed 's/.*version //;s/ .*//'))"
echo

# T1: values.uat.yaml present -> lint must receive it and pass.
# Fails against the previous version, which linted with no values and hit a nil pointer.
d=$(mkchart); addvalues "$d" values.uat.yaml
check "T1 values.uat.yaml present -> pass" 0 "$(run "$d")"
rm -rf "$d"

# T2: no values file at all -> empty array expansion must not crash under set -u.
# The chart genuinely cannot render, so a non-zero exit is correct; what must NOT
# happen is an unbound-variable abort. Distinguished by checking stderr below.
d=$(mkchart)
out=$( cd "$d" && "$BASH_BIN" "$CHECK" 2>&1 >/dev/null )
if printf '%s' "$out" | grep -q "unbound variable"; then
  printf '  FAIL  %-58s unbound variable on empty array\n' "T2 no values file -> no unbound variable"; fail=$((fail+1))
else
  printf '  PASS  %-58s (no unbound variable)\n' "T2 no values file -> no unbound variable"; pass=$((pass+1))
fi
rm -rf "$d"

# T3: explicit --values wins over the uat default
d=$(mkchart); addvalues "$d" custom.yaml
check "T3 explicit --values -> pass" 0 \
  "$(run "$d" deployment/helm_charts/jenkins --values deployment/helm_charts/jenkins/custom.yaml)"
rm -rf "$d"

# T4: explicit -f short form
d=$(mkchart); addvalues "$d" custom.yaml
check "T4 explicit -f -> pass" 0 \
  "$(run "$d" deployment/helm_charts/jenkins -f deployment/helm_charts/jenkins/custom.yaml)"
rm -rf "$d"

# T5: both uat and uat-test present -> both passed, later wins, still lints clean
d=$(mkchart); addvalues "$d" values.uat.yaml; addvalues "$d" values.uat-test.yaml
check "T5 uat + uat-test -> pass" 0 "$(run "$d")"
rm -rf "$d"

# T6: a template error the values cannot rescue must still fail (the gate has teeth)
d=$(mkchart); addvalues "$d" values.uat.yaml
echo '{{ this is not valid go template' > "$d/deployment/helm_charts/jenkins/templates/broken.yaml"
check "T6 genuinely broken template -> fail" 1 "$(run "$d")"
rm -rf "$d"

echo
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
