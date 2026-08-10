#!/bin/bash
# Macross 30 一键测试循环 (bash 版, UTF-8 路径安全)
# 用法: ./uw_harness.sh build2 [outname]   或   ./uw_harness.sh official
set -u
TARGET="${1:-build2}"
OUT="${2:-harness_result.png}"
EBOOT='C:\Users\Elysion\Desktop\MACROSS\BLJS10184-[日版-超时空要塞30 连接银河的歌声-射击类]\PS3_GAME\USRDIR\EBOOT.BIN'
DT=/c/Users/Elysion/Desktop
PK() { powershell -NoProfile -ExecutionPolicy Bypass -File "$DT/postkey.ps1" "$@" > /dev/null; }

if [ "$TARGET" = "official" ]; then
  DIR='/c/Users/Elysion/Downloads/rpcs3-v0.0.32-16803'
else
  DIR='/c/Users/Elysion/Desktop/rpcs3-src/build2/bin'
fi

# 1) kill & wait
taskkill //F //IM rpcs3.exe > /dev/null 2>&1
dead=0
for i in $(seq 1 45); do
  sleep 2
  if ! tasklist //FI "IMAGENAME eq rpcs3.exe" 2>/dev/null | grep -q rpcs3; then dead=1; break; fi
done
[ "$dead" = "1" ] || { echo "FATAL: rpcs3 won't die"; exit 1; }
sleep 3

# 2) launch (bash 传 UTF-8 argv)
if [ "$TARGET" = "build2" ]; then
  cd "$DIR" && (RPCS3_UW_329=1 ./rpcs3.exe "$EBOOT" > /dev/null 2>&1 &)
else
  cd "$DIR" && (./rpcs3.exe "$EBOOT" > /dev/null 2>&1 &)
fi
echo "launched ($TARGET), waiting boot+movie..."

# 3) boot + intro
sleep 85

# 4) 导航: Return x4 -> X x2
PK -Key Return; sleep 4
PK -Key Return; sleep 2
PK -Key Return; sleep 2
PK -Key Return
echo "menu sequence sent, waiting load screen..."
sleep 8
PK -Key X; sleep 2
PK -Key X
echo "load confirmed, waiting level load..."

# 5) 截图
sleep 15
powershell -NoProfile -ExecutionPolicy Bypass -File "$DT/UW32_Macross30/tools/uw_desktop.ps1" -Out "$OUT"
echo "DONE -> $OUT"
