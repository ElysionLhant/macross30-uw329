#!/bin/bash
# Macross30 放片复现自动化测试
# 用法: ./movie_test.sh <rpcs3目录> <次数>
# 判定: 每次启动后等 100 秒, grep 日志:
#   cellVdecStartSeq 出现且无 error 0x80010009 => PASS
#   error 0x80010009 出现 => FAIL(EPERM)
#   都没有 => TIMEOUT
set -u
DIR="$1"
N="${2:-5}"
GAME='C:\Users\Elysion\Desktop\MACROSS\BLJS10184-[日版-超时空要塞30 连接银河的歌声-射击类]'
PASS=0; FAIL=0; TMO=0
for i in $(seq 1 "$N"); do
  LOG="$DIR/RPCS3.log"
  [ -f "$LOG" ] && mv "$LOG" "$LOG.bak"
  (cd "$DIR" && ./rpcs3.exe --no-gui "$GAME" > /dev/null 2>&1 &)
  sleep 150
  powershell -NoProfile -Command "Get-Process rpcs3 -ErrorAction SilentlyContinue | Stop-Process -Force" 2>/dev/null
  sleep 3
  EPERM=$(grep -c "error 0x80010009" "$LOG" 2>/dev/null); EPERM=${EPERM:-0}
  VDEC=$(grep -c "cellVdecStartSeq" "$LOG" 2>/dev/null); VDEC=${VDEC:-0}
  TRAP=$(grep -a "EPERM_TRAP" "$LOG" 2>/dev/null | head -3)
  if [ "$EPERM" -gt 0 ]; then
    echo "run $i: FAIL (EPERM)  trap: $TRAP"
    FAIL=$((FAIL+1))
  elif [ "$VDEC" -gt 0 ]; then
    echo "run $i: PASS (movie playing)"
    PASS=$((PASS+1))
  else
    echo "run $i: TIMEOUT/UNKNOWN"
    TMO=$((TMO+1))
  fi
  cp "$LOG" "$DIR/movie_test_run$i.log" 2>/dev/null
done
echo "==== PASS=$PASS FAIL=$FAIL TIMEOUT=$TMO ===="
