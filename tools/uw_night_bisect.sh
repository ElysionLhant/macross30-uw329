#!/bin/bash
# 夜间批量二分: 每个 li1280 候选单独一轮 (v7 五处常驻), 记录 tile pitch/崩溃/截图
set -u
cd /c/Users/Elysion/Desktop/UW32_Macross30/tools
CANDS=(0x0005f9c4 0x0005fa24 0x0005fbac 0x000e6728 0x000f4bf8 0x000fdf08 0x0011a9ac 0x0011aa14 0x0011ade8 0x0011ae50 0x001ccd3c 0x003f388c)
LOG=/c/Users/Elysion/Desktop/cycle_log.txt
echo "=== night bisect start $(date) ===" >> "$LOG"
for c in "${CANDS[@]}"; do
  echo ">>> testing $c" >> "$LOG"
  bash uw_cycle.sh "$c" "bisect_$c" >> "$LOG" 2>&1
  echo "--- done $c $(date)" >> "$LOG"
done
echo "=== night bisect complete $(date) ===" >> "$LOG"
