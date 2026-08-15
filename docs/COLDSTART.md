# Macross 30 × RPCS3 32:9 项目 — 冷启动 Handoff（2026-08-15 深夜）

> 给全新会话/未来的自己：读完这一份即可上手。编年日志在 `docs/HANDOFF.md`，烘焙器考据在 `docs/BAKER_FINDING.md`，事故编年在 `docs/FINAL_HANDOFF.md`。

## 0. 一句话现状

**3D / HUD / 文字 32:9 全部落地并实机验证，日常可玩。唯一开放问题：通讯场景监视器头像横向缩半（混画写出器 0x5e5ea4）——三版门控补丁均告失败，已回滚到"脸缩但其余全对"的全补丁状态。**

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

已知残留（全部 cosmetic，可正常通关）：冲刺运动模糊一条分割线（Next Path I）、通讯场景头像缩半（Next Path II）、Dead FIFO 偶发（激战 ~25min 一次，ZCULL 守卫保证它只留日志不弹窗）。

## 3. 血泪雷区（每条都是真炸过的）

- **`dev_hdd0\game\BLJS10184_INSTALL` 覆盖目录是最高危物品**：游戏加载资源先探它再读光盘。周末实验包（data.dat 变体十几个 + shaders.dat）在里面插队，导致机库 `vector<T> too long` 自杀 + `Game data is corrupted`。已整体改名 `BLJS10184_INSTALL.off` 隔离，游戏从光盘重装了原版。**pack 工具实验后必须清理这里，否则它对一切模拟器、一切补丁状态生效，怎么 A/B 都洗不清自己。**
- **输入配置**：脚本开车需要 `config\input_configs\active_input_configurations.yml` = AutoTest（键盘映射：X=Cross、Return=Start、W/S/A/D=左摇杆）；用户手柄玩要改回 Default。
- **GDB stub（127.0.0.1:2345）**：gdb 客户端断开即 stub 线程死，**下次连接必须重启模拟器**；断点命中后必须**解析停止回复里的 thread 并 Hg 过去**，否则读到的是 main_thread 的寄存器（全是别人的）。
- **截图**：uw_gameview.ps1 的 PrintWindow 对 Vulkan 窗口**常拿陈旧帧**；全屏独占时 uw_desktop.ps1 也瞎。**要拿真帧就切窗口模式**（专属配置 Miscellaneous 里把 fullscreen 改 false，验完改回）。
- **着色器预载**：换过游戏数据后首次启动，775+ 管线对象预载，"Compiling 0/N" 可能几分钟不动——不是死了，是在编。

## 4. 开放问题一：冲刺残影分割线（Next Path I）

机制已查明（BAKER_FINDING 附录 D）：运动模糊走 0x822 dummy-quad 合成路径（slot12 共享表 @0x81eb1e04，发射器 0x9b1d8），不经 36 个已补丁写出函数，无函数可摘。路线：build2 运行时按 quad 宽门控（RPCS3_UW_HUD 链），或 build2 日志法定 0x822 写表者（tex==0x027b0000 时记录写表 CPU PC）。**别恢复 7 个 quad+UV 变体补丁（缝换黑影），别再摘 0x5exxxx 函数（摘一个少一块 UI）。**

## 5. 开放问题二：通讯场景头像缩半（Next Path II，本轮主战场）

**机制（全部实机验证）**：

- 头像与九宫格对话框底座、座舱 HUD 底座共用写出器 `0x5e5ea4`（混画）。4 个调用点：`0x4c210`/`0x4c9ec`/`0x4ca60`（九宫格对话框类）+ `0x79674`（元素装配点）
- 角点公式 `(px/A)·fS − fS`：**fS=0.5 → px/(2A)−0.5（居中 16:9 带）；fS=1.0 → px/A−1 = 原式（全宽）**。头像要 1.0（监视器 3D 投影叠加层，帧缓冲坐标系）；一切底座/HUD 要 0.5
- 通道机制（已验证可用）：洞例程算 fS → r12 → 写出器 nop（`0x5e5f08`）stw 到 `writer_frame+0x88` → 种子槽（`0x5e5fcc`）`lfs f11, 0x88(r1)`。全程唯一调用 `0x5bba04` 只碰 r3

**三版失败实录**：

- **v1（x1>1280 判帧缓冲 quad）**：失败——**底座也是帧缓冲坐标**（x1 一样超 1280），一刀切冤杀全部底座。坐标数值上头像/底座不可分
- **v2（LR 低16==0x9678 判 0x79674）**：失败 + 低级 bug——`cntlzw` 相等得 32、不等得 17-20，漏写 `srwi` 导致对话框 fS≈0.77-0.81，菜单全飞。**`cntlzw` 永远不是布尔值**
- **v3（修好的 LR 判别）**：Load Save/菜单底座完美恢复，但**座舱 HUD 底座全飞**——`0x79674` 装配点同时服务头像和座舱 HUD，1.0 把 HUD 拉成全宽

**当前认知**：0x79674 至少服务"要 0.5 的座舱 HUD"；头像走哪条路**尚未实锤**（0x79674 或九宫格类）。下一步必须拿到现场数据再定判别器，候选：

1. **quad 宽度窗**：头像 ≈ 监视器宽（估 600-1000px），HUD 表盘小（100-500），对话框宽（1500+）——w∈[600,1200] 给 1.0，其余 0.5
2. **UV 跨度**：头像用角色整图（UV≈[0,1]），HUD/九宫格用图集子矩形（UV 跨度小）——r7 指向的 UV 块可查
3. **场景标志**：通讯场景与飞行场景互斥，找内存里的场景标志位

**取证工具（已备好，吸取教训修过）**：`tools\uw_writer_trace2.py`——GDB 断 `0x7009c4`（0x5e5ea4 唯一跳板），解析停止线程后读 LR + r4 八坐标 + r6/r7（色/UV 指针）。用法：游戏**完全进场景后**再启动它（预载期启动只会空转）；每次连接前**重启模拟器**（gdb 线程一次性）。采集目标：飞行场景（HUD quad 宽度/UV 实测）+ 通讯场景（头像 quad 实测），然后定阈值。洞例程放 `0x8defd4`（25 零词区，lis 扫描确认无引用），空间管够。

**回滚单位**：`patches\patch_iso_full.yml` = 无门控全补丁（脸缩，其余全对）。洞例程与通道的词表见 build2 `patches\patch.yml` 的 git 历史（分发仓 commit c051d69 的 v3 版，已撤）。

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
