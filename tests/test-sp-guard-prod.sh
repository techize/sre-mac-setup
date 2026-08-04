#!/usr/bin/env bash
# Test harness for sp-guard-prod. Builds a throwaway git repo per case.
# Usage: test-sp-guard-prod.sh /path/to/sp-guard-prod
set -uo pipefail

GUARD="${1:?usage: $0 /path/to/sp-guard-prod}"
GUARD="$(cd "$(dirname "$GUARD")" && pwd)/$(basename "$GUARD")"
PROTECTED="deployment/helm_charts/jenkins/values.production.yaml"

pass=0; fail=0

# mkrepo: fresh git repo with one committed baseline file
mkrepo() {
  local d; d="$(mktemp -d)"
  git -C "$d" init -q 2>/dev/null
  git -C "$d" config user.email t@t.local
  git -C "$d" config user.name t
  git -C "$d" checkout -q -b main 2>/dev/null
  mkdir -p "$d/$(dirname "$PROTECTED")"
  echo "base: 1" > "$d/$PROTECTED"
  echo "other" > "$d/unrelated.txt"
  git -C "$d" add -A >/dev/null
  git -C "$d" commit -qm base >/dev/null
  echo "$d"
}

# check <name> <expected_exit> <actual_exit>
check() {
  if [ "$2" = "$3" ]; then
    printf '  PASS  %-58s (exit %s)\n' "$1" "$3"; pass=$((pass+1))
  else
    printf '  FAIL  %-58s expected %s, got %s\n' "$1" "$2" "$3"; fail=$((fail+1))
  fi
}

run() { # run in dir, with env, capture exit
  local d="$1"; shift
  ( cd "$d" && env "$@" bash "$GUARD" >/dev/null 2>&1 ); echo $?
}

echo "Testing: $GUARD"
echo

# T1: nothing staged at all -> must pass (nothing to guard)
d=$(mkrepo)
check "T1 nothing staged -> allow" 0 "$(run "$d" X=1)"
rm -rf "$d"

# T2: protected default file staged -> must BLOCK
d=$(mkrepo)
echo "changed: 2" > "$d/$PROTECTED"
git -C "$d" add "$PROTECTED" >/dev/null
check "T2 protected default staged -> block" 1 "$(run "$d" X=1)"
rm -rf "$d"

# T3: unrelated file staged -> must pass
d=$(mkrepo)
echo "changed" > "$d/unrelated.txt"
git -C "$d" add unrelated.txt >/dev/null
check "T3 unrelated file staged -> allow" 0 "$(run "$d" X=1)"
rm -rf "$d"

# T4: .sp-guard.yml declares a path, that path staged -> must BLOCK
d=$(mkrepo)
printf 'protected:\n  - unrelated.txt\n' > "$d/.sp-guard.yml"
echo "changed" > "$d/unrelated.txt"
git -C "$d" add unrelated.txt >/dev/null
check "T4 .sp-guard.yml path staged -> block" 1 "$(run "$d" X=1)"
rm -rf "$d"

# T5: ALLOW_PROD_VALUES=1 override -> must pass even with protected staged
d=$(mkrepo)
echo "changed: 2" > "$d/$PROTECTED"
git -C "$d" add "$PROTECTED" >/dev/null
check "T5 ALLOW_PROD_VALUES=1 override -> allow" 0 "$(run "$d" ALLOW_PROD_VALUES=1)"
rm -rf "$d"

# T6: release/ branch -> must pass even with protected staged
d=$(mkrepo)
git -C "$d" checkout -q -b release/1.0
echo "changed: 2" > "$d/$PROTECTED"
git -C "$d" add "$PROTECTED" >/dev/null
check "T6 release/ branch -> allow" 0 "$(run "$d" X=1)"
rm -rf "$d"

# T7: explicit path argument staged -> must BLOCK
d=$(mkrepo)
echo "changed" > "$d/unrelated.txt"
git -C "$d" add unrelated.txt >/dev/null
e=$( cd "$d" && bash "$GUARD" unrelated.txt >/dev/null 2>&1; echo $? )
check "T7 explicit arg staged -> block" 1 "$e"
rm -rf "$d"

# T8: regex safety - '.' in a protected path must not match any char
d=$(mkrepo)
mkdir -p "$d/deployment/helm_charts/jenkins"
echo "decoy" > "$d/deployment/helm_charts/jenkins/valuesXproductionXyaml"
git -C "$d" add -A >/dev/null; git -C "$d" commit -qm decoy >/dev/null
echo "changed" > "$d/deployment/helm_charts/jenkins/valuesXproductionXyaml"
git -C "$d" add "deployment/helm_charts/jenkins/valuesXproductionXyaml" >/dev/null
check "T8 dots are literal, decoy path -> allow" 0 "$(run "$d" X=1)"
rm -rf "$d"

# T9: protected path absent from repo, nothing staged -> allow (no crash under set -e)
d=$(mktemp -d)
git -C "$d" init -q; git -C "$d" config user.email t@t.local; git -C "$d" config user.name t
git -C "$d" checkout -q -b main 2>/dev/null
echo hi > "$d/a.txt"; git -C "$d" add -A >/dev/null; git -C "$d" commit -qm base >/dev/null
check "T9 default path absent from repo -> allow" 0 "$(run "$d" X=1)"
rm -rf "$d"

# T10: .sp-guard.yml with FLUSH-LEFT list items -> must BLOCK
d=$(mkrepo)
printf 'protected:\n- unrelated.txt\n' > "$d/.sp-guard.yml"
echo "changed" > "$d/unrelated.txt"
git -C "$d" add unrelated.txt >/dev/null
check "T10 .sp-guard.yml flush-left item -> block" 1 "$(run "$d" X=1)"
rm -rf "$d"

# T11: .sp-guard.yml quoted item with trailing comment -> must BLOCK
d=$(mkrepo)
printf 'protected:\n  - "unrelated.txt"   # keep me safe\n' > "$d/.sp-guard.yml"
echo "changed" > "$d/unrelated.txt"
git -C "$d" add unrelated.txt >/dev/null
check "T11 .sp-guard.yml quoted + comment -> block" 1 "$(run "$d" X=1)"
rm -rf "$d"

# T12: .sp-guard.yml present but the staged file is NOT listed -> allow
d=$(mkrepo)
printf 'protected:\n  - some/other/file.yaml\n' > "$d/.sp-guard.yml"
echo "changed" > "$d/unrelated.txt"
git -C "$d" add unrelated.txt >/dev/null
check "T12 .sp-guard.yml unlisted file -> allow" 0 "$(run "$d" X=1)"
rm -rf "$d"

# T13: .sp-guard.yml overrides defaults - protected default staged, not listed -> allow
d=$(mkrepo)
printf 'protected:\n  - unrelated.txt\n' > "$d/.sp-guard.yml"
echo "changed: 2" > "$d/$PROTECTED"
git -C "$d" add "$PROTECTED" >/dev/null
check "T13 .sp-guard.yml replaces defaults -> allow" 0 "$(run "$d" X=1)"
rm -rf "$d"

# T14: a later key ends the protected block
d=$(mkrepo)
printf 'protected:\n  - unrelated.txt\nother:\n  - %s\n' "$PROTECTED" > "$d/.sp-guard.yml"
echo "changed: 2" > "$d/$PROTECTED"
git -C "$d" add "$PROTECTED" >/dev/null
check "T14 keys after protected: are not paths -> allow" 0 "$(run "$d" X=1)"
rm -rf "$d"

echo
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
