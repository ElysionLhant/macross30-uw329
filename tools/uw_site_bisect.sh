#!/bin/bash
# 用法: uw_site_bisect.sh "0 1 2 3"   — 只启用指定序号的调用点补丁，跑 25s 判崩/活
set -u
DT=/c/Users/Elysion/Desktop
BIN="$DT/rpcs3-src/build2/bin"
EBOOT='C:\Users\Elysion\Desktop\MACROSS\BLJS10184-[日版-超时空要塞30 连接银河的歌声-射击类]\PS3_GAME\USRDIR\EBOOT.BIN'

# 14 个调用点: 地址:编码(bl 0x8dc8ac)
SITES=(
"0x00584178 0x48358735" "0x00586a98 0x48355e15" "0x005876d8 0x483551d5"
"0x005a88dc 0x48333fd1" "0x005ac1ac 0x48330701" "0x005ac658 0x48330255"
"0x005acbbc 0x4832fcf1" "0x005ad0b0 0x4832f7fd" "0x005ad570 0x4832f33d"
"0x005af708 0x4832d1a5" "0x005b02e0 0x4832c5cd" "0x005bfc9c 0x4831cc11"
"0x005bfdc4 0x4831cae9" "0x005d40a8 0x48308805"
)

SEL="${1:-all}"
{
cat <<'HDR'
Version: 1.2

PPU-15a011c611e0a0a1fedff55159bc26336db4dfd7:
  "32:9 Ultrawide (7680x2160)":
    Games:
      "Macross 30":
        "BLJS10184": [ All ]
    Author: Kimi
    Notes: "bisect"
    Patch Version: 1.0
    Patch:
      - [ be32, 0x00ad5328, 0x40638e39 ]
      - [ be32, 0x0057fd78, 0x38000a00 ]
      - [ be32, 0x00580158, 0x38000a00 ]
      - [ be32, 0x005ac19c, 0x38000a00 ]
      - [ be32, 0x005ac648, 0x38000a00 ]
      - [ be32, 0x005ad560, 0x38000a00 ]
      - [ be32, 0x003f388c, 0x38000a00 ]
      - [ be32, 0x008dc8ac, 0x4bce32b0 ]
      - [ be32, 0x008dc8b0, 0x60000000 ]
      - [ be32, 0x008dc8b4, 0x60000000 ]
      - [ be32, 0x008dc8b8, 0x60000000 ]
HDR
if [ "$SEL" = "all" ]; then
  for s in "${SITES[@]}"; do echo "      - [ be32, $s ]"; done
elif [ "$SEL" = "none" ]; then
  :
else
  for i in $SEL; do echo "      - [ be32, ${SITES[$i]} ]"; done
fi
} > "$BIN/patches/patch.yml"

taskkill //F //IM rpcs3.exe > /dev/null 2>&1
for i in $(seq 1 20); do sleep 1; tasklist //FI "IMAGENAME eq rpcs3.exe" 2>/dev/null | grep -q rpcs3 || break; done
sleep 2
cd "$BIN" && (RPCS3_UW_329=1 ./rpcs3.exe "$EBOOT" > /dev/null 2>&1 &)
sleep 40
C=$(grep -c "Access violation" RPCS3.log)
P=$(grep -c "sceNpTrophyRegisterContext" RPCS3.log)
echo "sel=[$SEL] crash=$C progress=$P"
taskkill //F //IM rpcs3.exe > /dev/null 2>&1
exit 0
