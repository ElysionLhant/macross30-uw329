# Macross 30 × RPCS3 32:9 项目 — 冷启动 Handoff（2026-08-15 深夜）

> 给全新会话/未来的自己：读完这一份即可上手。编年日志在 `docs/HANDOFF.md`，烘焙器考据在 `docs/BAKER_FINDING.md`，事故编年在 `docs/FINAL_HANDOFF.md`。

## 0. 一句话现状

**3D / HUD / 文字 32:9 全部落地并实机验证，日常可玩。通讯场景头像（含嘴型/表情动画）已由 v4 LR 类门控修复（2026-08-17，见 §5）。剩余开放问题：冲刺运动模糊分割线（Next Path I）。**

## 1. 环境速查（2026-08-15 版）

- 机器：9800X3D / RTX 5090 / Win11 / 7680×2160（32:9）屏
- 游戏（勿删）：`桌面\MACROSS\BLJS10184-[日版-超时空要塞30 连接银河的歌声-射击类]\`
- **日常模拟器 = `桌面\rpcs3-src\build2\bin\rpcs3.exe`**（定制版：0.0.32-16803 + EPERM 竞态补丁 + UW hooks + **ZCULL 关机守卫**）。桌面有 `Macross 30 (32x9).lnk` 快速启动器（图标 = 游戏 ICON0 转 ico，存于 `UW32_Macross30\assets\`）
- 官方原版备用：`Downloads\rpcs3-v0.0.32-16803\`（存档与 build2 符号链接共享；**新版 0.0.37 放不了影片，issue #17485**）
- 仓库：`桌面\macross30-uw329`（公开分发仓，github.com/ElysionLhant/macross30-uw329）+ `桌面\UW32_Macross30`（工作仓，含内存 dump/抓包，未公开）；`桌面\uw_venv`（pymem/capstone Python，勿动路径）
- 补丁本体：`rpcs3-src\build2\bin\patches\patch.yml`（242 词；与分发仓同步；`patch_iso_full.yml` 是其备份）
- 代理：Clash @ 127.0.0.1:7890

## 2. 日常玩用配置（已验证）

build2 + 专属配置（VFS 指盘；Core: LLVM + All Timers + RPCS3 Scheduler；Video: Write Color Buffers + Stretch To Display Area；Advanced: **Driver Wake-Up Delay 200µs**——20 没拦住 Dead FIFO，再犯就上 RSX FIFO Accuracy: Atomic）+ `patch.yml` 242 词。**必须全屏玩**。

已知残留（全部 cosmetic，可正常通关）：冲刺运动模糊一条分割线（Next Path I）、Dead FIFO 偶发（激战 ~25min 一次，ZCULL 守卫保证它只留日志不弹窗）。

## 3. 血泪雷区（每条都是真炸过的）

- **`dev_hdd0\game\BLJS10184_INSTALL` 覆盖目录是最高危物品**：游戏加载资源先探它再读光盘。周末实验包（data.dat 变体十几个 + shaders.dat）在里面插队，导致机库 `vector<T> too long` 自杀 + `Game data is corrupted`。已整体改名 `BLJS10184_INSTALL.off` 隔离，游戏从光盘重装了原版。**pack 工具实验后必须清理这里，否则它对一切模拟器、一切补丁状态生效，怎么 A/B 都洗不清自己。**
- **输入配置**：脚本开车需要 `config\input_configs\active_input_configurations.yml` = AutoTest（键盘映射：X=Cross、Return=Start、W/S/A/D=左摇杆）；用户手柄玩要改回 Default。
- **GDB stub（127.0.0.1:2345）**：gdb 客户端断开即 stub 线程死，**下次连接必须重启模拟器**；断点命中后必须**解析停止回复里的 thread 并 Hg 过去**，否则读到的是 main_thread 的寄存器（全是别人的）。
- **截图**：uw_gameview.ps1 的 PrintWindow 对 Vulkan 窗口**常拿陈旧帧**；全屏独占时 uw_desktop.ps1 也瞎。**要拿真帧就切窗口模式**（专属配置 Miscellaneous 里把 fullscreen 改 false，验完改回）。
- **着色器预载**：换过游戏数据后首次启动，775+ 管线对象预载，"Compiling 0/N" 可能几分钟不动——不是死了，是在编。

## 4. 开放问题一：冲刺残影分割线（Next Path I）

机制已查明（BAKER_FINDING 附录 D）：运动模糊走 0x822 dummy-quad 合成路径（slot12 共享表 @0x81eb1e04，发射器 0x9b1d8），不经 36 个已补丁写出函数，无函数可摘。路线：build2 运行时按 quad 宽门控（RPCS3_UW_HUD 链），或 build2 日志法定 0x822 写表者（tex==0x027b0000 时记录写表 CPU PC）。**别恢复 7 个 quad+UV 变体补丁（缝换黑影），别再摘 0x5exxxx 函数（摘一个少一块 UI）。**

## 5. （已解决）通讯场景头像缩半 — v4 门控定案（2026-08-17）

**结论：头像 + 表情/嘴型叠加格已全部恢复正常，实机签收。** 商店看板娘、任务内通讯对话（嘴型翻动、表情切换）均验证。

**机制**：写出器 `0x5e5ea4` 混画。取证（环形日志洞，见下）横跨商店/飞行/标题/通讯四场景的实机数据：**除头像外一切元素都走 `0x79674`**（LR=0x79678）；头像底图（`po_*.dds`/`/pk2_*.dds`）与表情格（`po_*_N.dds`）只走 `0x4c214`/`0x4c9f0`（`0x4ca64` 从未触发，同族一并罩住）。UV 跨度/宽度窗判别器均被数据证伪（标题/菜单大图全 UV；`face_l_mask.dds` 是全 UV 的 HUD 板）。

**v4 门控**（已并入主补丁，9 词洞 @0x9e2f8c）：跳板 `0x7009d0` 改道洞例程；区间判定 `(lr16 ^ 0x8000) − 0x4214 < 0x864` 选中头像类；r12 携带 fS 位（`0x3F800000`/`0x3F000000`）经 `0x5e5f08` 的 stw 落 `writer_frame+0x88`，种子槽 `0x5e5fcc` `lfs f11, 0x88(r1)` 读回。全部词经 Python 仿真 + capstone 双向核验后才上机。

**血泪教训（新）**：
- git 历史里 v1/v3 的门控词表实际构造的是 `0x3F80`（float 高 16 位但没左移）→ fS≈0 而非 1.0/0.5。**整数寄存器手搓 float 位必须 slwi/oris 进高半，且先仿真再上机**。
- r5 描述体是**池化复用**的——跨场景解读旧 r5 会拿到别的贴图名；纹理名必须场景活着时读。
- 头像是**入店/换表情时才重烘焙**的（内容不变不重画），静态画面里环形缓冲抓不到它，要蹲事件或用后台长监听。

**取证工具链**（分发仓 `tools/`）：`uw_logger_patch.yml`（日志洞补丁块，贴进 patch.yml 即启用，日常勿开）+ `uw_ring_read2.py`（单次读环，带纹理名）+ `uw_bg_watch.py`（长监听，自动找基址/断线重连）+ `uw_talk_watch.py`（蹲 0x4cxxx 重烘焙）。数据区 0xa6c000（text 尾页 21KB 零区，已验证安全）；洞 0x9e2f8c（596B 零岛）。

**回滚**：`rpcs3-src\build2\bin\patches\patch.yml.pre-v4.bak` = 无门控全补丁（脸缩其余全对）。

## 6. 工具速查（UW32_Macross30\）

- `tools\uw_writer_trace2.py` — 混画取证 GDB 断点（用法见 §5）
- `tools\postkey.ps1` — 向游戏窗投递按键（配 AutoTest 输入；X=Cross、Return=Start、W/S/A/D=摇杆）
- `tools\uw_desktop.ps1 / uw_gameview.ps1` — 截图（雷区见 §3）
- `data\eboot_mem.bin` — EBOOT 解密镜像（capstone skipdata 反汇编用）；客体内存基址 `0x400000000`
- PPC A-form 备忘：**frC 在 bits 10-6，frB 在 bits 15-11**；fdivs XO=18 / fmsubs XO=28 / fmuls XO=25（opcode 59）；frsp/fmr/带 Rc 的注意 opcode 63/字段序；lwz opcode **32**（35 是 lbzu）

## 7. 编年索引

- `docs\FINAL_HANDOFF.md` — 两个周末收官 + 事故编年（Dead FIFO / ZCULL / 覆盖目录 / 彩虹 / 混画三败）
- `docs\HANDOFF.md` — 全部调试编年（含失败路线）
- `docs\BAKER_FINDING.md` — 烘焙器全考据（附录 A-D）
- `docs\publishing\` — Reddit/PSXPlace/B站 发布稿
