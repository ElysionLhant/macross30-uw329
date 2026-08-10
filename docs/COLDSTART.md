# Macross 30 × RPCS3 32:9 项目 — 冷启动 Handoff（2026-08-10 深夜）

> 给全新会话/未来的自己：读完这一份即可上手。细节考据在 `docs/HANDOFF.md`（编年日志）。

## 0. 一句话现状

**3D 32:9 已稳（日常可玩）；刚完成对 pack 数据文件的 LAYO 宽屏补丁（812+266 处原位修改，已写盘带备份），尚未实机验证——下次开机第一件事就是测它。**

## 1. 环境速查

- 机器：9800X3D / RTX 5090 / 31.5GB RAM / Win11 / 5120×1440（32:9）屏（VirtualScreen 报告值；物理 7680×2160 也是 32:9）
- 游戏（用户的盘，勿删）：`C:\Users\Elysion\Desktop\MACROSS\BLJS10184-[日版-超时空要塞30 连接银河的歌声-射击类]\`（JB 格式）
- 日常模拟器：`Downloads\rpcs3-v0.0.32-16803\` — **玩用这个**。已含预置安装数据（`dev_hdd0\game\BLJS10184_INSTALL\`，USRDIRdata junction 绕过两个 RPCS3 bug；PARAM.SFO CATEGORY=GD）+ 固件 + 存档实体
- 新版模拟器：`Downloads\rpcs3-v0.0.37-18022\` — 跑别的游戏；**放不了 Macross 30 影片**（issue #17485）
- 定制源码/构建：`桌面\rpcs3-src`（commit ff84e7c6，26 子模块齐；含 EPERM 竞态补丁+27 诊断点+UW hook 等未提交改动）+ `rpcs3-src\build2\`（实验构建，**非日常**）
- 仓库/工具：`桌面\UW32_Macross30\`（tools\、data\、docs\、patches\）；`桌面\uw_venv`（pymem/capstone Python 环境，勿动路径）
- 代理：Clash @ 127.0.0.1:7890（GitHub/LunarG 走它；pypi 用清华镜像）

## 2. 日常玩用配置（已验证稳定）

官方 16803 + 专属配置（VFS 指盘、Core: All Timers + RPCS3 Scheduler、Write Color Buffers）+ `patches\patch.yml` 7 条（6 处 3D 投影 frsp→fadds + 0xabde80 惰性项）+ patch_config.yml 启用。效果：3D 投影正确 32:9（m00=0.487）；UI/影片 16:9 拉伸属预期。**必须全屏玩**（窗口模式会横向压缩是正常的；专属配置已设开机全屏）。放片稳定性：补丁版 10/10 验收过；EPERM 竞态补丁在 build2 源码里，官方目录行为照旧（Trace 日志勿开，会掩盖竞态且拖慢）。

## 3. pack LAYO 补丁（现役=排除版，实机干净）+ HUD 居中进展

**现役文件状态**（均实机验证干净）：
- `data.dat` = selective（排除 cockpit+dialog.ark，313 ark 宽度 2560 化）
- `data2.dat` = cockpitin（cockpit/hud 全补丁 2560 化，安全）
- `shaders.dat` = 原件（cgbfix 变体已证伪退役：HUD 不用 vs_ScreenToClipspace）
- 备份 `.bak` 完好；回滚 `python data/uw_pack_patch.py --restore-from-bak`

**校验雷区（永久排除）**：dialog.ark、mechroom_develop.ark、quest_clear 目录——这三家有逐资源字节级校验，动了就弹 "Game data is corrupted"。

**HUD 居中状态（2026-08-11 凌晨定案）**：
- 三个偏移候选全部证伪（shader 立即数 / EBOOT vec4 0xab1f18 / LAYO 平移）——驾驶舱 HUD 位置是 CPU 烘焙代码每帧现算，不读 LAYO 坐标
- 下轮两条引线：A. 逐 pass 视口偏移（从 data/uw_capture.pkl 挖 HUD pass 的 VIEWPORT_OFFSET，640→1280 即居中）；B. 烘焙函数本体（0xb0b90 上传环的 TOC 跳板后真身 0x62988c 族）
- 分析报告：data/UW_VP_OFFSET.md；工具：uw_vp_disasm.py（VP 反汇编）、uw_pack_center640.py（元素平移）、uw_cgb_fix.py

## 3b. tile1/2（彩虹源）进展

- 链已实锤：gcm init（开机 5.5s）→ sys_rsx_context_attribute(0x300) ← 表面管理器 0x574da8(w,h)，pitch=w×4
- 1280 来源 = tier 预设（特效档位表），待定位（下轮：0x575690/0x575a60 族的参数来源，或断 0x574da8 记录全部 15 tile 调用序列）
- 注意：tile 配置在开机 5.5s 完成，GDB 断点必须 ~4s 内部署（见 HANDOFF.md 对应节）

## 4. 若验证不顺利的排查序

- 图层没变 2560 → 确认加载的是被打补丁的 data.dat 实体（junction 拓扑：`旧版\dev_hdd0\game\BLJS10184_INSTALL` 是 junction → `rpcs3-src\build\bin\...` 实体）
- 彩虹仍在但 pitch=0x2800 → 是显示面仍 1280（谎报/li 没开）：B 路线需显示面也 2560（RPCS3_UW_329=1 或 li 组，见 HANDOFF.md）
- 启动即崩 → 先回滚确认是补丁引起；查 uw_pack_patch.log
- 画面正常但 UI 仍 16:9 → 说明 UI 层不在已改 LAYO 集内，记录现象再议（35 处 rect 待定项）

## 5. 工具速查（UW32_Macross30\）

- `tools\uw_measure.py` — tile pitch + 主相机 m00（判定用；ASLR 自动找基址）
- `tools\uw_harness.sh <official|build2> [out.png]` — 一键 boot→导航→3D 截图
- `data\uw_pack_re.py` — pack 解析/提取（info|list|extract|scan|layos|hashcheck）；`data\UW_PACK_RE.md` — 格式文档
- `data\uw_pack_patch.py` — LAYO 补丁器（--dry-run/--apply/--restore-from-bak）
- `tools\uw_gdb_trace.py` — GDB 断点采集（用法见下「雷区」）
- `tools\uw_guest.py / uw_findbase.py / uw_poke_desc.py` — 客体内存 dump/探基址/戳描述体
- `tools\uw_rrc_parse.py / uw_rrc_trace.py` — RSX 抓包解析

## 6. 雷区（全是实测换来的，别再踩）

- **v11/v12 li 2560 补丁组（0x57fd78/0x580158/0x5ac19c/0x5ac648/0x5ad560/0x3f388c）间歇崩溃**（视频初始化窗口，0x575484），已退役；build2\patches\patch.yml 是实验残留，**别当日常**
- **EBOOT 控制流类补丁=禁区**：bl 重定向到代码洞必崩 JIT（HLE hook、trace cave 均已证伪）；只做 in-place 数据流补丁（li/frsp/值替换）
- **GDB 断点**：仅 `PPU Decoder: Interpreter (static)` 下可用（0.0.32 无 fast）；**一次 rpcs3 启动=一次 GDB 会话**（断连即死需重启）；continue 只有 vCont；GDB Server 默认 127.0.0.1:2345
- **patch.yml 格式**：serial 具体则 title 必须具体；Patch 与 Games 同级；app_version 是序列 `[ All ]`；patch_config.yml 放 config\ 子目录（无 Games 层）；**不写注释行**
- **日志 level 保持 ≤4**（Trace=6 会 100% 掩盖 EPERM 竞态且慢）
- 杀 rpcs3 后等 ~10-25s 死透再启动，否则新实例自杀
- PowerShell 脚本含 CJK 路径需 BOM；启动用 bash 直起 `(./rpcs3.exe "路径" &)`
- MSBuild 并行参数在 Git Bash 用 `-m` 不用 `/m`；cmake 用 VS2022 全路径（见 HANDOFF.md）
- build2 源码 git 状态：大量未提交定制（EPERM 补丁、诊断点、cellGcmSetTileInfo UW hook、cellVideoOut RPCS3_UW_329 开关）——别 checkout 掉

## 7. 路线全景（为什么现在是 pack 补丁）

3D 投影（fadds，已通）→ 显示面 2560（谎报/li，已通）→ **图层 2560（LAYO 文件补丁，本次待验）** → UI 正解（HUD 居中，shader 立即数问题，最后做）。tile1/2 深度/雾效层的 1280 来源经全排除（21 li 立即数/谎报/模式表/工厂 GDB 断点/427 描述体活戳/结构体拷贝）后锁定数据文件，遂逆向 pack——若本次验证通过，B 路线（原生 32:9）基本闭环；剩余只有 HUD 居中与 137 张 1280×720 DDS 纹理内容级重制（可选）。

## 8. 会话礼仪（对这个项目）

- git 操作（commit/push）须用户明确同意；游戏文件/盘/备份一律勿删
- 改配置/补丁后先在 handoff 记一笔再跑实验；实验用 harness 无人值守循环
- handoff 双份同步：`UW32_Macross30\docs\HANDOFF.md` 与桌面根 `HANDOFF.md`（内容一致）
