# RPCS3 / Macross 30 调试与定制构建 Handoff（2026-08-08 深夜）

> **冷启动入口：`docs/COLDSTART.md`（2026-08-10 深夜起，新会话先读它）**


## 玩家环境
- 机器：AMD 9800X3D / RTX 5090 / 31.5GB RAM / Win11 26200 / 显示器 7680×2160（32:9 双宽屏）
- 手柄：DualSense Edge（蓝牙），RPCS3 Pads → Player1 Handler 选 DualSense
- 代理：Clash @ 127.0.0.1:7890（pip 走它会断 SSL，用清华镜像；git/curl 走它很快）
- Python 3.10 + 桌面 uw_venv（pymem、aqtinstall 已装）

## 今日支线1：Windows 蓝屏（已结论）
- 14:55 硬死机（Kernel-Power 41, BugcheckCode=0）；20:40 蓝屏 0x1A MEMORY_MANAGEMENT 子类型 0x61941（页表保留位被写坏）
- dump 分析结论：出事时进程 = PsPcSdkSttTts（PlayStation PC SDK 语音组件），栈上有 EasyAntiCheat_EOS；游戏《漫威斗魂 MARVEL Tokon Fighting Souls》（Sony发行/Arc System Works开发，8/6 首发口碑炸锅）首发已知问题。历史上还有两次 0x10E 显存蓝屏 + nvlddmkm TDR。内存大概率清白；若**不玩该游戏也死机**再查 XMP/MemTest86。
- 桌面遗留：kd_out4.txt（分析全文）、080826-14562-01.dmp（转储副本）
- 符号：C:\Symbols（pdb 存储结构）+ C:\SymbolsFlat（ntkrnlmp.pdb/ntoskrnl.exe 平铺）；微软服务器直连下不动符号时用 curl 手动按 RSDS 索引下载
- WinDbg/kd 路径：C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\kd.exe

## 今日主线：Macross 30 (BLJS10184) on RPCS3

### 游戏文件（用户自己的盘，完整，勿删）
- 玩用：`C:\Users\Elysion\Desktop\MACROSS\BLJS10184-[日版-超时空要塞30 连接银河的歌声-射击类]\`（JB 文件夹格式，EBOOT.BIN 是加密 SELF，RPCS3 自动解密）
- 备份 ISO：`桌面\PS3\Macross 30 - Ginga o Tsunagu Utagoe (Japan).iso`（16.3GB，RPCS3 不能直接读 ISO）

### 两个模拟器
- `Downloads\rpcs3-v0.0.37-18022-9c93ec0b_win64_msvc\` — 新版，跑别的 PS3 游戏用。**不能跑 Macross 30**（现行版影片完全放不了，GitHub issue #17485）
- `Downloads\rpcs3-v0.0.32-16803\` — 旧版，Macross 30 专用。已含迁移好的固件 dev_flash、游戏安装数据（见下）

### 已做的修复（旧版目录内）
1. `dev_hdd0\game\BLJS10184_INSTALL\` — 手动预置安装数据绕过两个 RPCS3 bug：
   - RPCS3 cellGameContentPermit 返回路径无尾斜杠 → 游戏拼出 `USRDIRdata/...`；另有 `USRDIR//data` 双斜杠路径
   - 做法：数据实体在 `USRDIR\data\`（15GB），`USRDIRdata` 是 Junction → `USRDIR\data`；两种拼法都能命中
2. `BLJS10184_INSTALL\PARAM.SFO` 偏移 352：CATEGORY 由 DG 改为 GD（安装数据要求 GD，否则游戏判损毁）
3. 专属配置 `config\custom_configs\config_BLJS10184.yml`：
   ```yaml
   VFS:
     /dev_bdvd/: C:/Users/Elysion/Desktop/MACROSS/BLJS10184-[日版-超时空要塞30 连接银河的歌声-射击类]/
   Core:
     Sleep Timers Accuracy: All Timers
     Thread Scheduler Mode: RPCS3 Scheduler
   Video:
     Write Color Buffers: true
   ```
   （RPCS3 Scheduler 把放片成功率从 ~50% 提到 ~75%；All Timers 单独无效）
4. `GuiConfigs\CurrentSettings.ini` 里 `level=6`（Trace 日志）——**开着 Trace 放片 100% 成功**（海森堡 bug，证实竞态），但拖慢游戏，定制版修好后改回 4

### 放片卡死的根因（已确诊机制）
- 失败签名：游戏 tty 打印 `error 0x80010009`（CELL_EPERM）→ `error 0x806107FF` → `openStream() failed (0x80010005)` → 黑屏死
- 时机：libsail 的 _libsail-control 线程创建完 _libsail-adec_copy / _libsail-vdec_copy（挂起态）后 ~0.5ms 内
- 上游 issue：GitHub RPCS3#17485（新版完全放不了片；旧版偶发卡死）、论坛 tid=180736

### 2026-08-09 凌晨进展（定案）
- **真凶实锤**：对照组复现失败时，失败前 0.5ms 有 `EPERM_TRAP cond#1: sys_cond_signal_to(): target thread is not waiting on this cond`（_libsail-control → main_thread 0x1000000）。竞态：控制线程发信号时主线程还没入队，RPCS3 直接 EPERM，真机时序永远先入队。
- **补丁状态**：v1 曾撤回（build1 native 构建上出现 Dead FIFO 疑似相关，但 build1 无补丁也崩过一次 → 归因到 native 指令集）。**build2（native OFF）已重新打入同一补丁（sys_cond_signal_to 有界重试 40×25µs）**，EXIT=0，冒烟验证中。
- **最终交付**：build2 = 官方 0.0.32-16803 + 27 诊断点 + 竞态补丁 + 32:9 开关（RPCS3_UW_329），native OFF。**补丁版对照配置 10/10 全过，达成验收**。生效配置已恢复为缓解版（双保险）。
- **3D 自动化导航未竟**：游戏标题/attract 循环刁钻（Start 进 intro、X 跳过、PRESS START 窗口短），键盘注入能进 intro 但未能稳定进主菜单；留给用户手动 2 分钟。注意：一次菜单加载片也触发了 EPERM 黑屏 → 证明补丁必要性不限于开场。
- 晨报：`UW32_Macross30\docs\晨报_Macross30_RPCS3.md`（含用户操作指引）。
- 自动化复现测试：缓解配置（RPCS3 Scheduler+All Timers）5/5 PASS；对照（默认 Core）4/5。**注意：日志 Trace 级会完全掩盖竞态（海森堡 bug），测试必须 level≤4**；首启欢迎框会卡死 --no-gui 启动（需 infoBoxEnabledWelcome=false）。
- 测试脚本 `movie_test.sh <rpcs3目录> <轮数>`（判定 cellVdecStartSeq vs error 0x80010009）；插桩 27 点 grep `EPERM_TRAP`。
- savestate 对本游戏不可用：保存时 cellSysutil.cpp:119 `ensure(!registered)` 崩（有未清 sysutil 回调）。
- **32:9 新路线**：cellVideoOut.cpp `_IntGetResolutionInfo` 720p 分支已加环境变量开关 `RPCS3_UW_329` → 谎报 2560×720（原生 32:9 宽高比，游戏自建宽 FOV）。尚未编译验证。HUD/影片预期仍 16:9。
- 键盘自动化：`config\input_configs\global\AutoTest.yml`（Keyboard handler，方向键+X=确认+Return=Start），切换用 active_input_configurations.yml（`global: AutoTest`；用户手柄配置是 `Default`=DualSense，改完记得改回）；`send_key.ps1 -Key X` 发送按键（SetForegroundWindow+SendInput）。
- 数据拓扑：BLJS10184_INSTALL 实体在 `build\bin\dev_hdd0\game\`（内含 USRDIRdata junction → USRDIR\data）；旧版 16803 同位置是 junction 指过来。savedata 实体在旧版，两个 build 目录都是 junction 指过去。**换 build 目录只需跑 `migrate_build2.ps1` 模式的 junction 装配**。
- build2 额外需要：Qt 插件目录（platforms/styles/multimedia/tls）+ OpenAL32.dll + GuiConfigs（persistent_settings.dat + CurrentSettings.ini 含欢迎框关闭）→ 见 `migrate_build2.ps1`。

### 定制版构建（进行中）
- 源码：`桌面\rpcs3-src`（commit ff84e7c6，26 子模块齐）
- 环境：VS2022 Community（MSVC 14.44，自带 CMake 3.31）、Qt 6.6.3 @ C:\Qt\6.6.3\msvc2019_64（aqt 安装，Multimedia 用 --modules 补的）、Vulkan SDK 1.3.290.0 @ C:\VulkanSDK（1.3.268.0 已被官方下架，用 290 无碍）
- 配置命令（关键坑全在这）：
  ```
  cmake -B build -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release \
    -DUSE_NATIVE_INSTRUCTIONS=ON -DUSE_SYSTEM_ZLIB=OFF -DUSE_SYSTEM_OPENAL=OFF \
    -DBUILD_LLVM=ON -DCMAKE_PREFIX_PATH="C:/Qt/6.6.3/msvc2019_64"
  ```
  坑：USE_SYSTEM_ZLIB/OPENAL 默认 ON 会找不到；Qt 找的是 CMAKE_PREFIX_PATH 不是 Qt6_DIR/QTDIR；BUILD_LLVM=ON 会从源码编 LLVM（首次编译 40~90min）
- 编译：`cmake --build build --config Release --target rpcs3 -- -m -v:m`（注意 Git Bash 会把 /m 转成 M:/，必须用 -m）
- 当前状态：原版编译中（任务 bash-w12rlvsi）；EPERM 插桩由子代理在源码树准备（eperm_instrument.diff），编译完成后：打插桩→增量编译→复现→定位→真补丁→再编→实测
- 补丁思路：EPERM 候选点统一"遇 EPERM 先 yield 重试一次"，真机语义无损

### 32:9 超宽屏手术（长期项目，用户明确要正经方案）
- 已确认：游戏无存量的 16:9 float/double 常量（全内存扫描只命中一张无关查找表），宽高比是动态计算的
- 已找到：91 个每帧重算的活投影矩阵（m11/m00=1.7778, m32≈-1 特征），地址池在 host 0x56xxxxxx 段（见 uw_proj.txt）；100Hz 注射会把游戏扎崩（证明是活数据，但注射法不可行）
- 工具（已全部入仓 `桌面\UW32_Macross30\tools\`，大文件在 `data\`，截图在 `screenshots\`）：
  - uw_venv（pymem 环境，留桌面不动，venv 路径绝对化）
  - uw_scan.py / uw_hits*.txt — 早期扫描（跳过了大区域，结论无效注意）
  - **uw_guest.py** — PS3 客体内存转储（基址 0x700000000，32GB 保留区，提交块散落其中）。`python uw_guest.py dump guest.bin 1024`
  - 后续计划：dump 客体内存 → 离线找投影计算代码（PPC 大端，EBOOT text 在 guest 0x10000 附近）→ 定位宽高比除法 → 做 PPU patch 或 rpcs3 侧补丁

### 32:9 进展（2026-08-09 上午）
- 谎报分辨率路线证伪（RPCS3_UW_329）：帧缓冲变宽但 3D 视口写死，内容压缩进左半；随后游戏卡死。该 env 开关仍在代码里（cellVideoOut.cpp），默认不启用。
- 客体内存基址：`uw_findbase.py` 找 "BLJS10184" 锚点反推（实测 host base 0x400000000；**每局 ASLR 会变，用脚本重查**）。
- guest 0x10000 = 解密后 EBOOT.ELF（\x7fELF 头可见）。dump 工具 uw_guest.py（改 BASE 为实测值后用）。
- **关键线索**：全镜像仅两处相邻 {u32 1280, u32 720}：guest 0x20A50 与 0x20A60，周边是 pitch=0x1400 的表面描述符。无 16:9 float、无 FOV 弧度常量。
- 试金石工具 `uw_poke_res.py`（apply=改 2560×720 / restore=还原 / 无参=只读），**需在 3D 场景中执行**，基址先按当局的 findbase 结果校准。
- **试金石结果（2026-08-09 上午）**：两处 {1280,720}（guest 0xB93FC8 / 0xD4CF04，会话间地址稳定）在运行中改 2560×720 无视觉变化；启动后 15s 早注入同样无效 → 该值不是 3D 视口来源，可能只是表面分配记录。**运行时改 guest 值导致过一次 Dead FIFO**——后续 poke 需谨慎、先备份。
- 已证伪路线汇总：谎报分辨率（RPCS3_UW_329）、表面描述符注入、float 常量扫描（无 16:9/FOV 常量）。
- 剩余正经路线：反汇编 EBOOT 找投影构建代码（可用 Ghidra + SELF/ELF loader，dump 已能拿到）；或从活矩阵池反查写入者。

### 32:9 突破（2026-08-09 上午，补丁已备待重启验证）
- **纠正旧结论**：16:9 float 常量其实存在（早期全内存扫描跳区漏报）：0x3FE38E39 在 guest 0xad5328（与 4/3@0xad532c、π/2@0xad5330 组成宽高比表）、0xb07a70、0xb08170。
- **EBOOT 解析**：guest 0x10000 = ELF64 PPC64 BE，PH0 代码 0x10000-0xa5bd68（RX），PH1 数据 0xa70000-0xd96080（RW）。节头被 bss 覆盖不可用；双 TOC=0xad16bc/0xac1ba0。dump 工具：`python uw_guest.py`（BASE 改 0x400000000）；已 dump `eboot_mem.bin`（offset=vaddr-0x10000，存于仓库 `data\`）。
- **投影链**（tan 分派函数 0x657520 共 5 个调用点）：aspect 主流来源是**整数 w/h 转 float 相除**（fcfid），宽度在 `frsp` 后 `fdivs fX, fW, fH`。5 处：0x5655c8 / 0x566a74 / 0x57fdf4 / 0x5801d4（都 `frsp f2,f13` 后调通用构建器 0x5bce60）、0x56677c（内联 `frsp f30,f13`）。宽高/高来自显示参数结构体（getter 0x5bba04 = base+0x14，w@+8 h@+0xc，45 个调用者共用，**不可改数据**）。
- **补丁方案**（单指令，不碰视口/表面/HUD）：上述 frsp → `fadds fX, f13, f13`（宽度×2 → aspect 32:9）；另数据补丁 0xad5328: 0x3FE38E39→0x40638E39。
- **已部署**：`patches\patch.yml` + `patch_config.yml`（Enabled），PPU hash=PPU-15a011c611e0a0a1fedff55159bc26336db4dfd7（从 RPCS3.log 抓）。patch 偏移=guest vaddr（已查 bin_patch.cpp:2199 确认 min_addr=0）。专属配置已加 `Stretch To Display Area: true`（3D 需拉伸铺满；HUD/影片随之拉伸属预期）。
- **验证脚本**：`uw_watch_matrix.py`——主相机矩阵 @0xb94260（m00 0.974→应 0.487）、变焦组 @0x303b0d10（1.533→应 0.767）、表 @0xad5328。**需重启游戏生效**（JIT 缓存，运行时改码无效——0x56677c 热补丁测试无变化属 JIT 陈旧，未证伪）。
- **2026-08-09 中午：32:9 补丁验证通过**。`PAT: Applied patch (<- 6)` 全打上；m00：主相机 0.974279→0.487139、变焦组 1.533110→0.766555、表→3.555556；引擎内 3D 演算画面正常。
- **用法（重要）**：Stretch 生效后**必须全屏**——窗口模式 16:9 下画面被横向压缩是正常现象（宽 FOV 挤进窄窗口）；全屏到 32:9 屏才恢复正常比例。全屏快捷键 Alt+Enter（mw/gw_toggle_fullscreen 默认）。专属配置已加 `Miscellaneous: Start games in fullscreen mode: true` 开机直进全屏。实测当前屏幕为 5120×1440（VirtualScreen 报告值），同为 32:9，补丁比例 3.5556 不变。
- **patch.yml 格式坑**（0.0.32 实测）：serial 为具体值时 title 也必须具体（不能 title=具体 serial=All）；Author/Notes/Patch 与 Games **同级**；serial 下是 app_version 的**序列** `[ All ]`。启用文件 `patch_config.yml` 放 **config/** 子目录（不是根目录），层级 = hash→补丁名→title→serial→app_version→Enabled（**没有 Games 层**）。
- **操作坑**：taskkill 后 16803 退出要 ~24s（退出段还会 segfault，属正常）；没死透就重启新实例会自杀。杀→轮询确认死透→再启动。
- 其他活矩阵（telescopic m00=51.1 组 @0x33c2xxxx）来源未明，若重启后未变 32:9 再追。（重启后该组未观察到影响）
- 分析工具：`uw_verify.py`（常量+矩阵扫描）、`uw_poke_aspect.py`（表 poke）、`uw_shot.ps1`（窗口截图）、`uw_cpu.ps1`。
- 桌面窗口置顶/置前工具：focus.ps1（SetWindowPos TOPMOST + MoveWindow 100,100）；send_key.ps1 发键（X=Cross, Return=Start）。（均在 `UW32_Macross30\tools\`）
- 注意：HUD/菜单是 16:9 布局，3D 拉宽后 HUD 错位预期内；影片是预渲染 16:9 没救

### UI 修复进展（2026-08-09 下午，部分生效）
- **RSX Capture 解析完毕**（`data\uw_capture.pkl` / `data\uw_fifo_trace.txt`）：HUD = CPU 烘焙 2D short 顶点 + 每批次 TRANSFORM_CONSTANT 上传缩放向量到 slot 467(0x1d3)。RRC 格式要点：VLE 变长计数；tile_state=432B（zcull_info 是 6×u32 不是 7）；replay_commands=(header,val)+ms_vle+u64×2 流。
- **NDC 缩放源（字节级实锤）**：显示模式表 @0xb07a10 = {0x3A4CCCCD(1/1280), 0x3AB60B61(1/720), 0, 0}，与抓包上传值逐字节一致；B 模式镜像 @0xb08110。{2/1280}=0x3ACCCCCD 在 0x8df288/0x8df4c0/0x8dfa18。**常量备忘：1/1280=0x3A4CCCCD、1/720=0x3AB60B61、2/1280=0x3ACCCCCD、2/720=0x3B360B61**（早期手算的 0x39D1B718/0x3A888889 是错的，害两次扫描空报）。
- **UI 补丁 v2（已部署 15 处）**：1/1280→1/2560(0x39CCCCCD) @0xb07a10/0xb08110；2/1280→2/2560 @3 处；另 vec4.z→0.25（0xb07a18/0xb08118）+ {0.5625,0.5}槽→0.25（0xb07a34/0xb08134）为无效遗留。效果：**UI 比例恢复正常，但左锚定**（[0,1280]→[0,0.5] UV，shader 无中心偏移数据槽）。
- **居中尝试失败**：vec4.z=0→0.25 无效；0.5→0.25 槽无效 → 中心偏移是 shader 内嵌立即数。真居中需改 VP 微码（抓包里有 TRANSFORM_PROGRAM 二进制）或顶点烘焙代码。3D 投影元素（瞄准环、距离标记）不受 UI 补丁影响，位置正确。
- **UI 补丁 v2 已回滚**：实测对话框/通讯文字仍拉伸（0xb07a10 只喂部分 2D 元素，座舱罩图被压左属副作用）→ 效果不完整，patch.yml 回滚为 **6 处 3D 验证版**；15 处实验版存于仓库 `patches\uw_patch_15entries_wip.yml`。UI 正解在下轮：VP 微码中心偏移 or 顶点烘焙代码（通信对话框的缩放源未找到，可能运行时计算）。

### UI 再战突破（2026-08-09 下午 v3）
- **翻案**：早期手算常量 0x39D1B718/0x3A888889 全错。正确值：**1/1280=0x3A4CCCCD、1/720=0x3AB60B61、2/1280=0x3ACCCCCD、2/720=0x3B360B61**（抓包上传值逐字节吻合）。
- **{1/1280,1/720} 静态副本共 3 处**：0xabde80（TOC2 -0x3D20 可达，4 个代码引用）、0xb07a10、0xb08110。**活内存 272 处命中**（0x373xxxxx = 每帧常量池暂存）。
- **对话框缩放源实锤 = 0xabde80**：代码 @0xb0b90 `lfs f0,-0x3d20(r2); lfs f13,-0x3d1c(r2)` 构建 {1/1280,1/720,0,0} 栈向量 → bl 0x700bc4 上传，与抓包 slot467 上传一致。另有 lwz 引用 @0x7de320/0x7df9e4。
- **UI v3 补丁**：0xabde80 → 1/2560 (0x39CCCCCD)。**后经用户实测+同帧 A/B 对比证伪**：对话框纹丝不动——0xabde80 族 `{W,1/W}` 是**贴图 UV/尺寸描述**（0x5c0d50 证实读对象字段），与位置缩放无关。该补丁保留在官方 patch.yml 中（惰性无害）。
- VP 微码为引擎运行时拼装（rodata 里是 COLO/oColor/EXCOORD0 元数据+参数，无二进制本体）；顶点双槽（0:2×short 位置, 8:2×short UV, stride 8, 0x40/sprite；12: 共享浮点表）。
- 显示模式表族：0xb079e0={1/720,2/720}、0xb07a30={0.5625,0.5}、0xb07a70={16/9,2.0}、0xb08130={0.5625,2/3}、0xb08170={16/9,1.5}。
- **启动教训**：无 BOM 的 .ps1 里 CJK 路径被 PowerShell 按 GBK 读成乱码（`日版`→`鏃ョ増`），RPCS3 报 Invalid file 起不来（uw_launch.ps1 因此废弃）；用 bash 直接 `(./rpcs3.exe "路径" &)` 启动（UTF-8 argv 正常）。杀进程 taskkill //F //IM rpcs3.exe，死透 ~10-25s。
- 工具链新增：uw_rrc_parse.py（RRC→pkl）、uw_rrc_trace.py（FIFO 跟踪）、uw_desktop.ps1（全屏截图）、uw_cpu.ps1。
- **HUD 位置缩放结论**：HUD 位置 = CPU 逐帧烘焙 NDC short（顶点 type2 归一化），缩放源既非 3 张静态表也非每帧堆池（290 处 {1/1280}、16 处 {2/1280} 试戳均无 HUD 变化，后者只炸出红色特效已还原）；显示尺寸整数**静态文件 0 处**（全部运行时从 cellVideoOut 查）→ boot 期数据补丁无法改 2D 画布，正解 = 路线 B。

### 路线 B（谎报分辨率原生 2560）机制全图（2026-08-09 下午，差最后一环）
- **工具链**：build2（定制版 = 官方 16803 + EPERM 竞态补丁 + RPCS3_UW_329 谎报开关 + 27 诊断点）。启动：`cd build2/bin && RPCS3_UW_329=1 ./rpcs3.exe "<EBOOT路径>"`（bash 启动，勿用 ps1）。
- **B 路线验证序列**：
  - v4（仅表补丁）：3D 全黑+1/4 屏。抓包①：主表面 SURF_CLIP=2560（谎报生效），但主 pass VP/裁剪=1280。
  - v5（8 对 {720.0,1280.0} 浮点→2560.0）：3D+UI 收紧中央 1280 带（比例正确）。抓包②：主 pass VP 仍 1280 → **那 8 对不是主视口源**（@420 pass 有效而已）。
  - v6（li1280→2560 @0x57fd78/0x580158）：VP 变 2560 但渲染目标 pitch 仍 1280 → **彩虹条纹**（VP 宽度 > 表面行距）。
- **硬编码链（已确诊）**：渲染上下文 w/h 存于 r31+0x994/+0x998，初始化点 `li 1280 @0x57fd78`（C pass）、`li 1280 @0x580158`（D pass）；投影宽高比 = fcfid(r27+0x994 / r27+0x998)（**fadds 补丁正是加倍此路径**）。表面创建函数 `0x5bfb5c(w,h,?)` 有 **14 个调用者**，li(1280,720) 配对喂参的确认 3 处：0x5ac19c / 0x5ac648 / 0x5ad560；主 3D 渲染目标（抓包 tile1/2 pitch=0x1400=1280px）= 其中之一，**待下轮指认**（逐一二分）。显示面 tile9/10/11 pitch=0x2800（2560，谎报已生效）。
- **B 路线剩余步骤**：指认主 RT 的 0x5bfb5c 调用者 → li 1280→2560 → 若还有错位再查 scissor/深度面。成功后：表面 2560（谎报）+ VP/投影/UI 全跟随（硬编码点已齐）→ 撤 fadds 与视口浮点补丁，原生 32:9。
- **回滚路径**：玩官方 16803 + 7 补丁（6 处 3D + 0xabde80 惰性项），一切照旧。build2 的 patches/patch.yml 是 v6 实验版，勿用于日常。

### 路线 B 终局（2026-08-09 午后）：图层族结构，暂缓
- **v7**（5 li：视口 2 + 分配 3）：UI 干净正确但左半 + 3D 彩虹。
- **v8**（+3 个 1280.0f 单点浮点）：无效。**v9**（二分批次1 四处 li）：撞非宽度字段，模拟器 segfault（0x7536c0），批次撤回。
- **B 真实结构（确诊）**：游戏 = **几十个 1280×720 特效/UI 图层分别渲染再合成**。表面描述体（活内存读到的名字）：pose_ob_dialogue / pose_dialogue_cursor_off / sankaku_b / cap_obj / caption1 / enemy_guage_ace / own_barrier_gauge / black_back / rsrt_ob_dialogue2 / stay_dialogue_flame_s2 / LAYOUT0 等，全部 {0x500,0x2D0}+pitch 0x1400。彩虹 = 图层族 1280 行距合成到 2560 显示面的全面错位。
- **结论**：完成 B 需把几十处图层分配初始化全部 2560 化，盲改必崩（已验证），逐一定位成本几十轮。工程上**不划算，暂缓**。若重启此项目：从描述体反查分配代码（描述体地址池 0x34603xxx/0x32f4xxxx/0x3466xxxx，抓包 tile1/2 = 主场景层）。
- 显示侧 {0xA00,0x2D0} 描述体（0xb93fc8 / 0xd4cf04）= cellVideoOut 派生（谎报生效证据），非图层。

### B 路线 v7-v10 补记（2026-08-09 晚）
- **已证实：UI 画布宽度跟随渲染上下文字段变**（v6/v7 的 li 1280→2560 @0x57fd78/0x580158 让 UI 收紧）。所以 UI 与 3D 视口/投影**共用**该字段——B 路线只剩 tile pitch 一环。
- v8（3 个 1280.0f 单点浮点）无效；v9（批次1 四处 li）撞非宽度字段 segfault；v10（0x5d40d0 + 0x620650 + 0x6207e0，排除视频模式表 0x5f28a0）仍彩虹。
- **表面创建链**：0x5bfb5c(w,h,?) 工厂 → 0x5be3c8 存 w@+0x54/h@+0x58（+sth +0x48/+0x4a）。14 调用者中 3 处 li(1280,720) 已试（非主场景 tile1/2 的创建者）；struct 驱动的 0x5a88dc（r31+0x4c/+0x50）是主嫌疑，其初始化点未找到（无 li→stw 直连，可能间接/间接调用）。
- **live 反查线索**：gcm 上下文 tile 数组 @0x1020ae0（tile1=0x02030001/0x036a0000/0x1400），访问全经指针无静态 xref。
- **83 个 {1280,720}+(-1@-0x20) 渲染上下文候选活体戳 w→2560：HUD 无变化**——但 UI 是**创建时一次性烘焙**，戳对已建元素无效；暂停菜单重开也不变 → 该 83 个不是 UI 画布源。
- **下一轮正解**：build2 加 RSX 侧插桩——NV4097 表面/tile 命令写入 pitch=0x1400 时记录（FIFO get 地址/时间戳），反查游戏侧创建点；或者干脆给 cellGcmSetTile 包装函数的 EBOOT 地址做断点日志。GDB stub 无内存 watchpoint（只支持软件断点 Z0）。
- 视频模式表 @0x5f28a0 是雷（720p/1080p/小尺寸枚举表，v9 崩溃元凶嫌疑）。

### 自动化迭代设施（2026-08-09 深夜，已验证可用）
- **按键病灶**：SetForegroundWindow 被前台锁拦截 + SendInput 进不了 Qt handler → **PostMessage(WM_KEYDOWN/UP) 直投游戏窗口**（无需焦点），且必须 AutoTest(键盘) 配置激活。工具 `postkey.ps1`（桌面）/ `tools\uw_gameview.ps1`（置前+截游戏窗）。
- **导航时序（实测破解）**：boot ~85s → Return(skip OP) → 4s → Return ×3(2s 间隔，踩 PRESS START 短窗) → 8s → X ×2(2s 间隔) → 15s 读档载入 → 3D。封装 `tools\uw_harness.sh <official|build2> [out.png]`（bash 版——ps1/cmd 版有 CJK 路径编码坑，已弃 ps1 版）。
- **迭代循环 `tools\uw_cycle.sh "<追加 li1280 站点>" <label>`**：重写 build2 patch.yml（v7 五处常驻 + 追加）→ harness → `uw_measure.py`（自动找 ASLR 基址+读 tile pitch+主相机 m00）→ 崩溃计数 → 追加到桌面 cycle_log.txt。
- **ASLR 注意**：基址会变（本夜实测 0x300000000，非 0x400000000），一律用 uw_measure.py/uw_findbase.py 先探。
- **当前状态（v11a/b）**：m00=0.487139（32:9 投影已通过 谎报+li 原生达成），tile1/2 pitch 仍 0x1400（彩虹源未除），tile9/10=0x2800（显示面正常）。UI 左锚定（v7 效果），居中问题待 3D 原生后处理。
- **渲染目标对象实证**：tile1/2 对应对象 @0x305aa998/0x309a3e28（活内存），含 "DepthVs"/fog 字样 = 深度/雾效延迟渲染目标；名称来自数据文件非 EBOOT。对象布局：hw w@+0x48、h@+0x4a、w@+0x54、h@+0x58。
- **夜间任务**：`uw_night_bisect.sh` 批量单点试 12 个 li1280 候选（每候选独立一轮），结果记 cycle_log.txt；若无一命中 → 下一轮上 RSX 插桩（build2 在 NV4097 tile 写入处记日志反查）。

### 夜间二分结果（2026-08-09 21:30-21:53，12 候选全灭）
- 当夜 14 轮迭代全自动无人值守跑完（harness+cycle+bisect 闭环首次通宵实战）。
- 12 个 li(1280,720) 候选（0x5f9c4/0x5fa24/0x5fbac/0xe6728/0xf4bf8/0xfdf08/0x11a9ac/0x11aa14/0x11ade8/0x11ae50/0x1ccd3c/0x3f388c）逐一单测：**tile1/2 pitch 全守 0x1400，无崩溃**。加上此前已试的 5+3+3 处，**21 个 li 对全部排除**。
- **结论**：主场景渲染目标（tile1/2 = 深度/雾效层）**不走任何 li(1280,720) 立即数**——dims 来自 struct/计算路径（struct 驱动 caller 0x5a88dc 的 r31+0x4c/+0x50 初始化点仍未找到），或按固定 720p 特效档位分配（这解释了全部宽度补丁落空）。
- **下一步（唯一正路）**：build2 加插桩——在 RSX 表面/tile 配置（nv4097 或 rsx 表面绑定）处，pitch==0x1400 时记录上下文（FIFO get + 时间戳 + 可能的话 PPU PC），反查创建点；或在 0x5bfb5c 工厂入口做 PPU 断点+打印（GDB stub 只有软件断点但可用：断 0x5bfb5c 读 r4/r5/LR 逐层回溯调用者）。另一路：反汇编 0x5a88dc 的上游（找 +0x4c/+0x50 的 stw 源，允许跨函数 memcpy/计算链）。
- keep-awake 已失效（ps 退出即释放，无残留）。harness/cycle/bisect 脚本均在 `UW32_Macross30\tools\`，cycle_log.txt 在桌面。

### 自读档工作流（2026-08-09 傍晚，导航待用户示范）
- **目标**：kill → boot → 读档 → 3D HUD 截图 的一键循环 harness，用于 B 路线（图层分配族）自主迭代。
- **存档**：SAVEDATA_01 = 1-3 ハンター試験（LV1, 1h10m）；SAVEDATA_00 = 序章空白。计划：让用户在 SAVEDATA_00 覆盖存一个开战点。
- **输入配置**：`config\input_configs\active_input_configurations.yml` 切 `AutoTest`（键盘：X=Cross, C=Circle, Z=Square, V=Triangle, Return=Start, Space=Select, WASD=左摇杆, 方向键=D-pad）即恢复用户 DualSense（Default）。改前备份 .bak。
- **导航实测（build2，放片补丁全程无卡）**：boot → Start 跳 intro → 标题卡（暗底）→ Start 无反应 → attract 循环（每 ~2:07 一部片，日志见 _libsail-control 线程轮换）→ X/C 只是快进 attract。**PRESS START 窗口极短且只在 intro 刚结束瞬间**；Start 连发 10 次也未进主菜单。**结论：键盘时序还没抄对，等用户手动示范一次（逐秒截屏记录），再写死进 harness**。（**注：当夜深夜已自行破解**，时序见上文「自动化迭代设施」导航时序条；本节保留作时间线记录，勿再等项目示范。）
- **用户口述流程**：播片 Start 跳过 → 主界面 Start → load（Circle 确认）→ 读档界面 X X → 进 3D。
- send_key.ps1 已验证可达游戏（X/C 有反应）；uw_desktop.ps1 全屏截图可用。

### 快照（Savestate）玩法（用户已会）
- Utilities → Create Savestate 随存；Boot Savestate 复活；过场景前存一个

### 操作备忘（这机器上反复踩过的坑）
- PowerShell 在 Bash 里 $_ 会被吞：写 .ps1 再执行
- cmd /c 带 mklink 等引号参数在 Bash 里会乱：用 New-Item -ItemType Junction
- Minidump 目录要管理员：Start-Process -Verb RunAs 提权拷贝
- GitHub raw/API、LunarG：走 clash；pypi：走 tuna 镜像
- MSBuild 并行参数在 Git Bash 里用 -m 不用 /m

### B 路线攻坚（2026-08-10，GDB 断点路线打通，采集进行中）
- **目标**：指认 tile1/2（1280×720 深度/雾效 RT）的工厂创建调用点（B 路线最后一环）。
- **已证伪路线（勿再试）**：
  - HLE hook（改 cellGcmSetTileInfo 签名+代码洞 bl/bctrl 到 HLE 区/PRX 跳板）：JIT 下全部挂死——**跨模块直跳/间接跳 HLE 在 JIT 下不可行**。
  - 客体 trace buffer cave 三版（含寄存器全保护）+ 纯 trampoline cave（语义零影响）：**单点也崩** → 调用点重定向（bl cave→b 工厂）本身在当前 JIT+patch 组合下即致崩，崩在下游无关代码（0x575484 结构体初始化写野指针）。
  - GDB 软断点在 LLVM 下被 ppu_breakpoint 直接拒绝；**0.0.32 只有 "Interpreter (static)"/"Recompiler (LLVM)" 两个解码器**（无 fast）。
- **重要纠错**：昨晚 v11 基线（7 条 li 2560 补丁组）**本身会在视频初始化窗口间歇崩溃**（0x575484，读 0x8/写野址，随机恢复）；零补丁 6/6 全稳。日常官方 16803 的 6 条 fadds 补丁不受影响。
- **打通的路线（GDB stub，实测可用）**：
  - 专属配置加 `PPU Decoder: Interpreter (static)`（仅它支持断点；rpcs3 退出会重写并裁掉与全局一致的行，注意复查）。全局 config.yml 保持 LLVM。
  - GDB Server 默认监听 127.0.0.1:2345（misc.gdb_server）。**一次 rpcs3 启动 = 一次 GDB 会话**：客户端断连 gdb 线程即死，必须重启 rpcs3。continue 只有 vCont（无裸 'c'）；连接即暂停，`vCont;c` 恢复。
  - 客户端 `tools/uw_gdb_trace.py`（标准 RSP，Z0 断点，命中读 r3-r6/LR/CIA，去重+过滤 0x5b02e4 刷屏点）。
  - 静态解释器极慢（OP 低帧数属预期）；其下 RSX FIFO 偶发 recover 崩溃，重启再跑。
- **已得数据**：
  - 工厂签名实锤：`0x5bfb5c(r3=对象ptr, r4=w, r5=h, r6)`（旧记 (w,h,?) 有误，w 在 r4）。
  - 首个 1280×720 开机显示面：间接调用 `0x1ccc30` → wrapper `0x700514`（切 TOC）→ 尾跳工厂（**间接调用 bl 扫描扫不到**）。
  - 59× 1×1 = 0x5b02e4（dummy 刷屏）；64×64 = 0x586a9c。
  - 14 直调点 arg 来源静态图：3 处 li(1280,720)（0x5ac1ac/0x5ac658/0x5ad570，夜二分已排除）；寄存器驱动 3 处：**0x5876d8(r28/r27)、0x5a88dc(r4/r5 透传上级)、0x5d40a8(r29/r28)**；0x5bfc9c/0x5bfdc4 在工厂体内；其余小尺寸 li。
  - tile1/2 创建者将在 0x5876d8/0x5a88dc/0x5d40a8/间接点中产生；正在静态解释器+断点进 3D 采集（任务 bash-1p4in6wm）。
- **现场状态**：build2 专属配置=Interpreter (static)（**玩用前改回 LLVM 或删行**）；patch_config.yml.off（补丁全关）；patches/patch.yml=单点探测残留（玩前恢复仓库版）；源码含 cellGcmSetTileInfo UW hook（LR==0x8dc8c4 惰性分支，可留）。新工具：uw_gdb_trace.py / uw_single_site.py / uw_trace_read.py。

### B 路线攻坚续（2026-08-10 午后，结构体维度源锁定）
- **live 采集结果（静态解释器+断点，boot→主菜单）**：工厂调用仅 2 类——开机显示面 1280×720（间接点 0x1ccc30）与 64×64（0x586a9c）。**主菜单阶段不创建场景表面**，tile1/2 要等任务/3D 加载（本轮未到，导航时序在解释器下没踩准）。
- **静态反汇编突破（dim 源锁定，无需运行时）**：两个寄存器驱动调用点读**同一结构体布局**：
  - func@0x587668（site 0x5876d8）：`lwz r28, 0x4c(r29)` / `lwz r27, 0x50(r29)`，r29=入参 r4（结构体）
  - func@0x5a887c（site 0x5a88dc）：`lwz r5, 0x50(r31)` / `lwz r4, 0x4c(r31)`，r31=入参 r4（结构体）
  - **w/h 来自结构体字段 +0x4c/+0x50**（与 handoff 旧记 r31+0x994/+0x998 是不同结构体）。下一个环节：找这两个函数的调用者（多为间接），拿到结构体实例，反查 +0x4c/+0x50 的 stw 初始化点（允许跨函数 memcpy/计算链）。
  - func@0x5d404c（site 0x5d40a8）：w/h = 入参 r4/r5 直传，追其调用者即可。
- **下一步（两路并行）**：① 静态：反查 +0x4c/+0x50 初始化点（eboot_mem.bin 在 data\）；② live：重启 rpcs3（一次启动=一次 GDB 会话）跑 uw_gdb_trace.py 5bfb5c 200 2400，导航用口述流程（Start→load Circle→XX）进任务看 tile1/2 命中（其 r3 对象可对照旧记录 0x305aa998/0x309a3e28 家族的 DepthVs/fog 描述体）。
- **现场**：bash-1p4in6wm 可能仍在跑（静态解释器，低帧数正常，直接关 rpcs3 即可）。build2 专属配置含 `PPU Decoder: Interpreter (static)`——**日常玩前删该行或改回 Recompiler (LLVM)**（会被 rpcs3 重写配置时裁掉，复查）。patch_config.yml.off=补丁全关；patches/patch.yml=单点探测残留（uw_single_site.py 生成，玩前恢复仓库版）。采集日志 data\uw_gdb_trace.log。
- **40 分钟采集窗口结果**：仅 hit#0/#1 两条（boot 显示面 + 64×64），主菜单阶段无任何场景表面创建；按键导航在静态解释器下未踩进 PRESS START 窗口，3D 未到达。下次采集建议：先用 savestate 或手动把游戏停在主菜单/读档点再挂断点，跳过解释器下慢慢摸导航。

### B 路线攻坚三（2026-08-10 夜：调研 + 来源排除清单定稿）
- **调研结论**：
  - 开发商 = **Artdink 自研**（非万代本社引擎；同技术世代候选：Dragon Ball Z: Battle of Z (PS3/2014)、SAO: Lost Song (PS3/2015)）。
  - 参考方法论（用户 Downloads\GamePatches-SO6 (2).zip = Lyall 模板）：分辨率点补丁 + FOV mid-hook + **RT 创建点强制分辨率** + HUD 单点修 + 已知问题类目（截屏纹理错位）。RPCS3 宽屏教程（Margen67 tid=199065）= Big Endian 浮点扫描法（我们已覆盖并超出）。
  - **关键认知修正**：显示面 2560 不需要谎报——v11 的 li 补丁组自己就能让 tile9/10=0x2800（2026-08-10 实测无谎报也成立）；谎报只剩显示侧其它消费者需要。
- **tile1/2 宽度/pitch 来源·全排除清单**（每一个都实测/静态验证过）：21 处 li(1280,720) 立即数；显示模式查询（谎报）；视频模式表 720p 项（0x5f28a0 单点 1280→2560，无变化）；li 0x1400 pitch 常量（12 处全非 tile）；工厂 0x5bfb5c（GDB 断点实玩 3D 零 RT 命中——**工厂签名实为 (r3=对象, r4=w, r5=h)**，且 tile1/2 不走它）；427 个 {0x500,0x2D0}+pitch 描述体活体戳（绑定后不重建，无效）；pack 数据文件明文（全零，压缩/编码）；li→stw 与 context→descriptor 拷贝（静态扫描零）；0x9b1d8 FIFO 提交函数（实玩 25min 零调用——init 专用或非此路径）。
- **幸存理论（按优先级）**：① dims 来自**压缩数据文件**（pack .dat 需解格式：无明文名字、无 {0x500,0x2D0} 明文对）；② 计算路径（非 li、非查表、非拷贝的算术链，如位运算/移位派生）。
- **v12 实验记录（已退役）**：9 条补丁（v7 base + 0x5876b4/0x5a88c4 强制 li 2560）→ 3D 崩坏（神秘几何体、瞄准环/距离标跑最右、缺物件）；曾出现"彩虹突然消失"未解现象（疑场景不再启用雾效合成）；log 5 次 access violation。**v11/v12 li 2560 补丁组证为不稳定源（视频初始化窗口间歇崩）**。
- **GDB 路线工具链（已验证可用）**：专属配置 `PPU Decoder: Interpreter (static)`（0.0.32 仅此支持断点）+ GDB Server 127.0.0.1:2345（默认开）。**一次 rpcs3 启动 = 一次 GDB 会话**（断连即死需重启）；continue 只有 vCont；客户端 tools\uw_gdb_trace.py（Z0 断点+任意寄存器采集+去重过滤）。
- **下一步候选**：① 逆向 pack .dat 容器格式（找压缩块里的描述体记录）；② 活体内存里对 DepthVs/fog 对象（0x305axxxx/0x309axxxx 家族）做 +0x54/+0x58 字段戳 + 关卡重载触发重建；③ 收兵维持官方 16803 + 6 补丁日常。
- **现场**：build2 patch.yml = v12 残留（玩前恢复仓库版）；patch_config.yml 启用中（玩前关）；专属配置已无解释器行（全局 LLVM 生效）；官方 16803 未动。新工具：uw_gdb_trace.py、uw_poke_desc.py、uw_single_site.py、uw_trace_read.py。

### HUD 攻坚与完整性校验（2026-08-10 深夜 II，用户主导排障）
- **实验矩阵结论（每轮实机验证）**：
  - rebuildtest（dialog.ark 内容零改动、仅压缩流 level6 重压）：**弹 corrupt** → dialog.ark 存在**逐资源完整性校验**（压缩字节级敏感）；nowloading.ark 同操作不弹 → 校验非全量覆盖。
  - dialogonly（dialog.ark 加宽 6 头+2 元素）：弹 corrupt ×2 → 即触发源。
  - tinyonly（nowloading.ark 加宽）：干净 → 补丁机制无辜。
  - 全排除版（cockpit+dialog 排除）：干净复测过。
  - **cockpitin（data2 全补丁含 hud.ark 107 头+4 元素）：corrupt=0、SPU 崩=0** → cockpit/hud 2560 化安全！早期"SPU 崩+corrupt"全是 dialog.ark 一条链。
  - face_dummy 探测在**原始未补丁下也是常态**（基线 108 次，游戏良性探测，旧推断"加宽才探测"已翻案）。
- **corrupt 触发链（GDB 断点实锤）**：spawn helper 0x64e528 ← 0x64e56c（弹框函数）← 6 个调用点（0x62d168/0x62d1e8/0x62ec18/0x62ecd4/0x634658/0x6347c4），共同守卫 = **0x643f90 资源装载器**（认 "segs" 魔数分派）返回非零 → 弹 CorruptDialog（线程 func 0x64e450，OPD 0xab1670）。
- **分类器 0x55a0c8（w==0x500 早退）已证伪**——不是分屏触发点。
- **完整性校验待办**：EBOOT 0x653b40 有 CRC32 slice-by-4 例程（表签名命中 0x8d49c4/0xd6a8bc）；下一步找其调用者与期望值存放处，确定校验覆盖清单与算法参数 → 补丁后重算 → dialog.ark 可重新纳入。
- **Pierre84 恶魔之魂 32:9 UI 补丁分析**（用户提供，BLUS30443）：3 点 = R 浮点（数据）+ L 立即数（lis）+ stw；**UI quad 左右边对称外扩**（L=-640,R=1920，中心保持 640）——内容随边界外扩而居中。对照：我们 v2 只改缩放（1/1280→1/2560）所以左锚；正确做法是扩边界/烘焙偏移，不是动缩放。
- **horkrux DeS 32:9 补丁**（wiki）：同族（anchors BLUS30443），论坛/维基均被 Cloudflare 拦截，经用户直贴获得内容。
- **现场**：data.dat=selective（排除 cockpit+dialog，干净）；data2.dat=cockpitin（全补丁含 hud.ark，干净）；data.dat.bak/data2.dat.bak 原件备份；变体 data.dat.dialogonly/tinyonly/rebuildtest、data2.dat.cockpitin 在 pack 目录旁。官方 patch.yml 现为 9 条（7 条日常 + 2 条分类器试验 0x55a0dc/0x55a154——**已证伪，可删**）。新工具：uw_pack_rebuild.py（纯重建变体生成器）。RPCS3 论坛/维基直连+archive 均被 Cloudflare/429 拦截，r.jina.ai 亦被挡——内容靠搜索摘要+用户直贴。

### B 路线联调实录（2026-08-10 深夜 III：tile1/2 排除 LAYO，HUD 居中思路定案）
- **谎报只在 build2 有效**（cellVideoOut 定制补丁），官方 16803 设 RPCS3_UW_329 无效（实测 tile9/10=0 无变化）。
- **B 路线当前最优配置实测**：build2 + 谎报 + v11 li 组（视口/分配 li 2560，**不含 fadds**——li 视口后宽高比原生 3.5556，fadds 会加倍）+ 文件侧 cockpitin/selective → 3D 全宽 ✓ 但 **彩虹回归**（tile1/2 仍 0x1400）、UI 全左锚。不加 li 视口组则"左半 16:9 + 右半黑"。
- **tile1/2 来源最终排除**：LAYO 补丁不改 pitch；tile1/2 是引擎自建 RT，1280 来源疑为 **gcm init 期 tile 配置的固定值**（tile 数组只在 init 配置一次，0x9b1d8/0x9b2e0 在实玩零调用；静态搜 lis/lwz/stw/addi/addi 0xae0 各模式均未定位写入者）。
- **HUD 居中定案（Pierre84 思路）**：HUD 保持 1280 设计尺寸，元素 x 统一 +640 平移 → 3D 投影中心与 HUD 中心在画布 x=1280 重合，瞄准/指向不脱钩。工具 `data\uw_pack_center640.py`（dx 可调），变体 `data2.dat.center640` 已产出（4845 处关键帧平移，仅 x 改动），**待测**（需配合：显示 2560 + HUD 处于 1280 画布的状态下才能看到居中效果——当前 v11 组 UI 全左锚说明 HUD 画布跟随渲染上下文，先做 B 路线视口/上下文修复再测）。
- **元素记录格式**（子代理双证）：LAYO 头格式串 "32c2s8i3i"；元素记录 "i4c2i32c8i"（0x50 定长，无位置字段）；**位置在轨迹段关键帧块（0x00140034 打头），块内 +0x14=x +0x18=y（i32 LE 画布坐标）**，无锚点标志。
- **截图工具注意**：uw_gameview.ps1 可能抓陈旧帧/错窗口（连续多张字节级相同即为中招）；游戏没卡，以日志 TTY/log 活动为准。
- **现行文件状态**：data.dat=selective（排除 cockpit+dialog，md5 ad6884a8…）、data2.dat=cockpitin（md5 21b78028…）、两者.bak 备份完好；变体备齐（dialogonly/tinyonly/rebuildtest/cockpitin/center640）。官方 patch.yml 已回 7 条日常。

### tile1/2 来源追击（2026-08-11 凌晨：链到层级派发，强推失败已回滚）
- **tile 配置路径实锤**（GDB 断点）：gcm init（开机 ~5.5s，**早于一切断点部署窗口，这就是此前 0x9b1d8/0x5bfb5c 断点全miss的原因**）经 `sys_rsx_context_attribute(package_id=0x300)` 配 15 个 tile；游戏侧入口 = cellGcmSetTileInfo 调用点 0x5754ac（pitch 取结构体 +0x10）← tile 设置函数 **0x574da8(r4=w, r5=h)**，**pitch = w×4 计算得出**。
- **GDB 抓到**：0x574da8 被以 (1280,720) 调用两次（LR=0x575988/0x575bd8），均来自 0x575xxx 表面管理器族（按 tier 派发，0x58 步长描述体数组）。
- **强推实验（已回滚）**：0x575964/0x575ba4 强制 r4=0xA00 → 显示 tile pitch 崩成 0x200、tile1/2 仍 0x1400、全屏平铺万花筒。证明这两个调用点是共享通道（显示面也走），且 tile1/2 的 1280 在更上游（tier 预设表）。
- **剩余正路**：找 tier 预设表（特效档位的 1280 来源）——0x575690/0x575a60 族的 r3/r6/r7 参数来源；或给 0x574da8 下断点逐次记录全部 15 tile 的 (w,h) 调用序列对照 tier。
- **方法论沉淀**：GDB 断点必须 4s 内部署（tile 配置 5.5s 即发生）；栈回溯 mem 读在 dbg_pause 下不可靠（待修）；build2 patch.yml 混入 GBK 字节，python 编辑需 encoding='gbk' 或 errors='ignore'。
- **截图工具**：uw_gameview.ps1 在全屏/窗口切换期会抓陈旧帧（字节级相同即中招）；用户直贴截图最可靠。

### HUD 居中攻坚（2026-08-11 凌晨 II：三个偏移候选全证伪，两条引线留给下轮）
- **证伪清单**（实机验证过）：
  1. shader 立即数路线：HUD 2D 着色器曾被认为是 vs_ScreenToClipspace{,Color,Tex,TexColor}.cgb（X = px·(2/w) − c466.x），cgbfix 变体（shaders.dat 4 个 cgb 各 2 字节，末条 MAD 加数 swizzle 改指 c466.w=0.5）——**实机零变化**。原因：capture 显示 2D 绘制全是 CPU 烘焙 NDC 直通（o[0].xy=v0.xy），该 shader 在实机 capture 中零命中，根本没被用。
  2. EBOOT vec4 0xab1f10={1/1280,−1/720,−1.0}（0xab1f18 改 −0.5）——零变化，非活偏移。
  3. LAYO 元素 x+640 平移——只对菜单类界面有效（通用界面正确居中过），**驾驶舱 HUD 不读 LAYO 坐标**（代码每帧现算）。
- **方法论结论**：驾驶舱 HUD 位置 = CPU 烘焙代码逐帧从运行时显示参数计算，全部"数据表/文件坐标"路线无效；正解必须落在烘焙代码（或逐 pass 视口状态）。
- **两条引线**（下轮起点）：
  A. **视口偏移**：capture 里 HUD pass VIEWPORT_OFFSET=640（=1280/2）；谎报 2560 下若不变 1280，则 640→1280 即居中。从 `data\uw_capture.pkl`（111MB，uw_rrc_parse.py 可读）挖 HUD pass 的 VIEWPORT/WINDOW_OFFSET 值即可验证。
  B. **烘焙函数本体**：0xb0b90 上传环调用的 0x700bc4/0x7006e4 等是 TOC 跳板（addis r2,+1; addi −0x4e4; b），真身 0x62988c/0x5c0d50 等——继续拆即到 NDC 公式。
- **新工具/产物**：uw_vp_disasm.py（通用 RSX VP 反汇编器）、uw_cgb_fix.py（cgb 补丁器）、UW_VP_OFFSET.md（VP 分析报告）、data2.dat.center640/center640full、data.dat.center640（x 平移变体族，菜单类有效）。
- **现场**：pack 现役 = selective(data.dat) + cockpitin(data2.dat) + shaders 原件，全部实机干净；官方 16803 日常配置未动；build2 patch.yml = v11 7 条（实验残留，勿当日常）。
