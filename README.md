# Macross 30 (BLJS10184) — RPCS3 32:9 Ultrawide Patch & Toolkit

English below / 中文说明在下文。

A 32:9 ultrawide patch set for **Macross 30: Ginga o Tsunagu Utagoe (BLJS10184)** running on **RPCS3 v0.0.32-16803**, plus the full reverse-engineering toolkit used to build it: pack container tooling, RSX vertex-program disassembler, GDB breakpoint tracer, and live-memory utilities.

**State of the project**: 3D projection renders correctly at 32:9 (verified). HUD and menu text are natively centered to the middle 16:9 region (CPU quad-baker patch, verified). Movies are pre-rendered 16:9. One cosmetic leftover: a seam line on the boost motion blur.

---

## 中文

**这是什么**：Macross 30（BLJS10184）在 RPCS3 0.0.32-16803 上的 32:9 超宽屏补丁 + 全套逆向工具链。

**当前效果**：3D 投影正确 32:9（已验收）；HUD/菜单文字原生居中到中央 16:9 区（CPU 烘焙补丁，已验收）；影片为 16:9 预渲染。残留：冲刺运动模糊有一条分割线（ cosmetic ）。

### 安装（补丁）
1. 需要 RPCS3 **v0.0.32-16803**（新旧版本行为差异大，新版放不了本片，见 docs/HANDOFF.md）
2. 把 `patches/patch.yml` 与 `patches/config_BLJS10184.yml` 放到 rpcs3 目录的 `patches/` 与 `config/custom_configs/` 下（config 里的 VFS 路径按你自己的游戏位置改）
3. 补丁管理器里启用该补丁；GPU 设置勾 **Stretch To Display Area**；**必须全屏玩**（窗口模式横向压缩是正常现象）

### pack 数据补丁（LAYO 加宽，可选/实验）
`tools/uw_pack_re.py`、`uw_pack_patch.py`、`uw_pack_center640.py` 是 pack 容器（PIDX/AXL）的解析/补丁工具，可把 1280×720 的 LAYO 画布原位改 2560（排除带完整性校验的资源）。**它们只在你自己的游戏文件上操作**；本仓库不含任何游戏数据。详见 `docs/UW_PACK_RE.md`。

### 工具一览
- `uw_measure.py` — tile pitch + 主相机投影 m00 读取（pymem，自动找 ASLR 基址）
- `uw_gdb_trace.py` — RPCS3 GDB stub 断点采集（Z0 断点 + 任意寄存器 + 内存 deref）
- `uw_pack_re.py` / `uw_pack_patch.py` / `uw_pack_center640.py` — pack 逆向/补丁/元素平移
- `uw_vp_disasm.py` — RSX 顶点着色器微码反汇编器
- `uw_cgb_fix.py` — shaders.dat 内 .cgb 微码补丁器
- `uw_harness.sh` 等 — 自动化 boot→导航→3D 测试循环
- `uw_guest.py` / `uw_findbase.py` / `uw_poke_desc.py` — 客体内存 dump/探基址/活体戳

### 文档
- `docs/COLDSTART.md` — **冷启动交接**（先读它）
- `docs/HANDOFF.md` — 编年调试日志（全部考据过程）
- `docs/UW_PACK_RE.md` — pack/PIDX/AXL 格式文档
- `docs/UW_VP_OFFSET.md` — HUD 偏移的 VP 微码分析

### 已知未竟
- tile1/2（深度/雾效渲染目标）的 1280 来源：tier 预设表，待定位（彩虹源）
- 冲刺运动模糊分割线：模糊 tap 走 0x822 dummy-quad 合成路径（不经 36 个已补丁写出函数），压区/非压区边界留缝；修法需 build2 运行时按 quad 宽门控或定 0x822 烘焙器
- dialog.ark/mechroom_develop.ark/quest_clear 有逐资源完整性校验，改动会弹 "Game data is corrupted"——本工具链默认排除

### 免责
仅为学习/研究目的的游戏修改工具与补丁。不包含任何游戏数据文件；所有 pack 工具只操作用户本地合法持有的游戏副本。游戏版权归 Bandai Namco / Artdink 所有。

---

## English

### What works
- 3D projection renders native 32:9 (verified: main camera matrix m00 halved, 0.974→0.487)
- HUD/menu natively centered to the middle 16:9 region via CPU quad-baker patch (36 writer functions + text renderers, verified on hardware)
- EPERM race fix for movie playback (see HANDOFF.md)
- Full pack container reverse engineering + patching tools (PIDX/AXL format, zlib/segs compression, integrity-check exclusions mapped)

### Install
1. Use RPCS3 **v0.0.32-16803** (newer builds can't play this game's videos — issue #17485)
2. Copy `patches/patch.yml` into your rpcs3 `patches/` folder, and `config_BLJS10184.yml` into `config/custom_configs/` (edit the VFS path to your game folder)
3. Enable the patch in the patch manager, check **Stretch To Display Area**, and play in **fullscreen**

### Toolkit
- `uw_pack_re.py` — PIDX/AXL pack parser/extractor (`info|list|extract|scan|layos|hashcheck`)
- `uw_pack_patch.py` — in-place LAYO canvas widener (1280→2560) with integrity-check exclusions
- `uw_pack_center640.py` — element x-translation for HUD centering
- `uw_gdb_trace.py` — RPCS3 GDB stub breakpoint/registers tracer
- `uw_vp_disasm.py` — RSX VP microcode disassembler
- `uw_measure.py` — live tile-pitch / projection-matrix probe

### Not included
Any game data. The tools operate only on your own legally obtained copy. All rights to the game belong to Bandai Namco / Artdink.

### Roadmap (open items)
- tile1/2 depth/fog render targets: 1280 source = tier preset table (see HANDOFF.md)
- Boost motion-blur seam: blur taps go through the 0x822 dummy-quad composite path (not the 36 patched writer functions), leaving a boundary line; fix needs build2 runtime gating by quad width or locating the 0x822 baker
- Per-resource integrity check (CRC32 routine @0x653aa0) reverse engineering
