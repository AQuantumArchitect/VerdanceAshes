#!/usr/bin/env bash
# Runs ON a Linux cloud host with a native Recoil spring-headless binary.
# Primary Verdance path is Windows remote_worker_bake.ps1 (binary parity).
# Use this only when Linux engine + BAR content are already provisioned.
set -euo pipefail

BAR_DATA_ROOT="${1:?bar data root}"
STARTSCRIPT="${2:?startscript path}"
MAP_ID="${3:?map id}"
RESULT_DIR="${4:?result dir}"
ENGINE_BIN="${5:-$BAR_DATA_ROOT/engine/spring-headless}"
TIMEOUT_SEC="${6:-3600}"

if [[ ! -x "$ENGINE_BIN" && ! -f "$ENGINE_BIN" ]]; then
  echo "spring-headless not found: $ENGINE_BIN" >&2
  exit 1
fi

RUN_STAMP=$(date +%Y%m%d_%H%M%S)
RUN_DIR="$RESULT_DIR/${MAP_ID}_${RUN_STAMP}"
mkdir -p "$RUN_DIR"
cp -f "$STARTSCRIPT" "$RUN_DIR/bake_startscript.txt"

# Headless settings: avoid icon atlas stalls.
SETTINGS="$BAR_DATA_ROOT/springsettings.cfg"
if [[ -f "$SETTINGS" ]]; then
  cp -f "$SETTINGS" "$RUN_DIR/springsettings.pre_bake.cfg"
fi
cat >> "$SETTINGS" <<'EOF'

// Verdance cloud shell-bake headless overrides
UnitIconsAsUI = 0
UnitIconDist = 99999
MinimapIconScale = 0.1
LuaUI = 0
SplashScreenDir =
EOF

echo "CLOUD BAKE (linux) map=$MAP_ID engine=$ENGINE_BIN timeout=${TIMEOUT_SEC}s"
cd "$BAR_DATA_ROOT"
set +e
timeout "${TIMEOUT_SEC}" "$ENGINE_BIN" --write-dir "$BAR_DATA_ROOT" --isolation --only-local "$STARTSCRIPT"
EXIT=$?
set -e

if [[ -f "$BAR_DATA_ROOT/infolog.txt" ]]; then
  cp -f "$BAR_DATA_ROOT/infolog.txt" "$RUN_DIR/infolog.txt"
  grep -E 'VA_SHELL_' "$RUN_DIR/infolog.txt" > "$RUN_DIR/shell_markers.txt" || true
  UNIT_COUNT=$(grep -cE 'VA_SHELL_UNIT[[:space:]]' "$RUN_DIR/shell_markers.txt" || true)
else
  UNIT_COUNT=0
fi

OK=0
if [[ "$UNIT_COUNT" -gt 0 ]]; then OK=1; fi

cat > "$RUN_DIR/result.json" <<EOF
{
  "schemaVersion": "verdance-cloud-bake-result/1.0",
  "mapId": "$MAP_ID",
  "ok": $([ "$OK" -eq 1 ] && echo true || echo false),
  "exitCode": $EXIT,
  "unitCount": $UNIT_COUNT,
  "runDir": "$RUN_DIR",
  "engine": "$ENGINE_BIN",
  "platform": "linux"
}
EOF
cp -f "$RUN_DIR/result.json" "$RESULT_DIR/${MAP_ID}_latest.json"
echo "Result units=$UNIT_COUNT ok=$OK RUNDIR=$RUN_DIR"
[[ "$OK" -eq 1 ]] || exit 2
