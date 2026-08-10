#!/bin/bash
# 夜间二分迭代器: ./uw_cycle.sh "0xADDR1 0xADDR2 ..." label
# 基础 = v7 五处(li 1280->2560) + 表补丁; 参数为追加的 li1280 站点
set -u
EXTRA="$1"
LABEL="${2:-cycle}"
PATCH='/c/Users/Elysion/Desktop/rpcs3-src/build2/bin/patches/patch.yml'
DT=/c/Users/Elysion/Desktop

python3() { /c/Users/Elysion/Desktop/uw_venv/Scripts/python.exe "$@"; }

python3 - "$PATCH" "$EXTRA" <<'PYEOF'
import sys
patch_path, extra = sys.argv[1], sys.argv[2].split()
base = '''Version: 1.2

PPU-15a011c611e0a0a1fedff55159bc26336db4dfd7:
  "32:9 Ultrawide (7680x2160)":
    Games:
      "Macross 30":
        "BLJS10184": [ All ]
    Author: Kimi
    Notes: "32:9 route B cycle: use with RPCS3_UW_329=1 (build2)."
    Patch Version: 1.0
    Patch:
      - [ be32, 0x00ad5328, 0x40638e39 ]
      - [ be32, 0x0057fd78, 0x38000a00 ]
      - [ be32, 0x00580158, 0x38000a00 ]
      - [ be32, 0x005ac19c, 0x38000a00 ]
      - [ be32, 0x005ac648, 0x38000a00 ]
      - [ be32, 0x005ad560, 0x38000a00 ]
'''
for a in extra:
    if a and a != 'none':
        base += '      - [ be32, %s, 0x38000a00 ]\n' % a
open(patch_path, 'w', encoding='utf-8').write(base)
print('patch.yml written with extras:', extra)
PYEOF

cd "$DT/UW32_Macross30/tools"
bash uw_harness.sh build2 "cycle_$LABEL.png" > /dev/null 2>&1
# 测量
M=$(python3 uw_measure.py 2>&1)
CRASH=$(grep -acE "SIGSEGV|Dead FIFO|Fatal Error" /c/Users/Elysion/Desktop/rpcs3-src/build2/bin/RPCS3.log 2>/dev/null || echo 0)
{
  echo "=== cycle $LABEL (extras: $EXTRA) ==="
  echo "$M"
  echo "crash_lines=$CRASH"
} | tee -a "$DT/cycle_log.txt"
