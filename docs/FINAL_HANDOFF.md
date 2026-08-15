# FINAL HANDOFF — 两个周末的收官与交接

> 写给六个月后的我们，也写给任何想接着干的人。
> 2026-08 上旬，两个周末。第一天面对着左 1/3 的 HUD 觉得全是硬骨头，最后一天看着文字收进底座。
> —— ElysionLhant & Kimi

## 最终状态（实机验证通过，可正常游玩）

- **3D**：原生 32:9。原料法：宽度转换 `frsp→fadds`（5 处）+ 静态宽高比表 `@0xad5328`。思路致谢 [@wagrenier](https://github.com/wagrenier) 的星海补丁。
- **HUD**：36 个 f32 四边形写出函数（0x5e5ea4 + 35 族）逐角点改 `ndc_x = px/(2A) − 0.5`，居中且不变形。
- **文字**：`0x1a1244`/`0x1a1a54` 同公式；批量环把 UV v 除数 texH 从 f12 挪到 f13，保住 f12=K=0.5。
- **豁免**：7 个 quad+UV 变体（混画全屏特效）保持原始，黑影因此消失。
- **载体**：标准 `patch.yml`（be32），LLVM 下生效。分发仓：https://github.com/ElysionLhant/macross30-uw329
- **环境**：RPCS3 **v0.0.32-16803 钉死**（新版放不了影片，issue #17485）+ build2 定制版（日常工作目录 `rpcs3-src/build2`）+ Stretch To Display Area + 全屏。

## 未竟事项（按价值排序，起始点都已写死）

1. **冲刺残影分割线**——README「The Next Path」+ BAKER_FINDING 附录 D。模糊走 0x822 dummy-quad 路径（共享表 `@0x81eb1e04`，发射器 `0x9b1d8`），不经已补丁的 36 函数。正道 = build2 运行时按 quad 宽门控（`RPCS3_UW_HUD` 钩子链）；侦察 = tex==`0x027b0000` 的 0x822 绘制时记录写表 CPU PC。**别恢复那 7 个变体，别再摘 0x5exxxx 函数。**
2. ~~彩虹边缘~~ **已随路线退役**——彩虹是 li 1280→2560 组（B 路线）把表面 VP 拉得比 tile pitch 还宽的产物；现装的 fadds 原料法不动表面宽度，**没有彩虹**。tile1/2 tier 预设表只有谁想复活 li 路线时才需要找。
3. **pack 完整性校验**——CRC32 @0x653aa0，dialog.ark 等三个资源改不了（弹 "Game data is corrupted"）。

## 文档地图（按阅读顺序）

1. 本文件 —— 5 分钟版
2. `README.md` —— 技术考据主体（英文）；「How the patch works」四节是最有含金量的部分
3. `docs/COLDSTART.md` —— 环境/工具冷启动
4. `docs/BAKER_FINDING.md` —— 烘焙器全考据（附录 A：35 族清单；B：文字渲染器；C：RSX 抓包法；D：模糊链终判）
5. `docs/HANDOFF.md` —— 编年日志，含所有失败路线（失败也是路标）
6. `docs/publishing/` —— Reddit / PSXPlace / B站 发布稿

## 回来接着干之前必须想起来的事

- **客体内存基址** `0x400000000`；pymem 读 base+vaddr 验证补丁是否生效。
- 反汇编用 capstone **`skipdata=True`**，否则遇数据即停。
- PPC A-form：**frC 在 bits 10-6，frB 在 bits 15-11**；fdivs XO=18 / fmsubs XO=28 / fmuls XO=25，opcode 59；frsp 是 opcode 63。
- 改循环内代码前**先画寄存器生命周期**；volatile 寄存器跨 `bl` 必须反汇编整条调用链确认零 FP 写。
- **别碰 `li 1280→2560` 立即数补丁组**——随机万花筒（布局多路径），v11 已弃。
- 别乱开 `RPCS3_UW_HUD/PROBE/WATCH/RACE` 这几个 env，日常配置保持干净。
- PPU 解释器 0.08fps 只用于调试，日常 LLVM。
- 静态补丁最小粒度 = 整个函数（每角点 2 指令位，无 code cave）；混画函数只能取舍或上模拟器侧门控。
- 工作仓 `UW32_Macross30`（本地，含 117MB 内存 dump 与抓包）未公开；分析脚本与文档已全部并入分发仓。

## 已处理的崩溃/事故（别重复查）

- **主局：RSX Dead FIFO**——FIFO 里出现 `call 0x0`：RSX 消费者读到了 PPU 还没写完的命令（rpcs3 已知竞态类，非本补丁引起）。两次发作均在激战 ~25 分钟处。缓解阶梯：每游戏配置 `Driver Wake-Up Delay` 20→**200µs**（20 已证不够）→ `RSX FIFO Accuracy: Atomic`。
- **次局：退出时 ZCULL_control 析构崩（host AV @base+0x7438f0）**——关机路径遍历已损坏的 MMIO 锁定页表（`RSXZCULL.cpp:23`），上游 master 代码相同（未修）。已在 build2 源码加 SEH 守卫（`unlock_pages_guarded`），**实机验证**：Dead FIFO 后的关机只留两行日志不再弹窗。重编方法：VS2022 自带 cmake（不在 PATH）`--build build2 --config Release --target rpcs3`。
- **"Game data is corrupted" / "vector<T> too long" 闪退**——**周末实验包在覆盖目录插队**：`dev_hdd0/game/BLJS10184_INSTALL/USRDIR/data/pack/` 里的实验 data.dat/data2.dat/shaders.dat（文件侧路线遗物）被游戏优先加载，一张坏表让机库菜单 vector 爆炸（游戏自己 abort 并 tty 打印回栈）；摘掉实验包又触发安装完整性校验弹 corrupted。**解法：整个 BLJS10184_INSTALL 隔离改名，游戏从光盘重装原版数据**。教训：文件侧实验残留比代码补丁残留更阴险，它对所有模拟器、所有补丁状态一视同仁地生效。
- **人脸缩半（通讯场景监视器头像）**——五轮二分定位：画家 = `0x5e5ea4`，但它同时给 LAYO 对话框（需居中）和帧缓冲空间头像（原公式即正确）打工，**混画**。**已修（门控种子，10 词）**：角点 `(px/A)·fS−fS` 在 fS=0.5 是居中、fS=1.0 是原式；判别 = **LR 低16位 == 0x9678**（头像唯一来路 0x79674；坐标数值分不开——底座也是帧缓冲 quad，x1>1280 一刀切会把底座冤杀，v1 因此失败）。跳板 `0x7009d0` 尾分支改道 `0x8defd4` 洞（25 零词区，lis 扫描确认无引用）；r12 通道落 `writer_frame+0x88` 由 nop（`0x5e5f08`）写、种子槽（`0x5e5fcc`）读，中间唯一调用 `0x5bba04` 只碰 r3。**血泪坑**：`cntlzw` 后忘了 `srwi`——相等得 32、不等得 17-20，直接 slwi 让对话框 fS≈0.77-0.81 全部飞出屏幕（v2 黑屏菜单的元凶）；`cntlzw` 永远不是布尔值。验证：Load Save/道具菜单/机库标签全部正确。**剩**：用户看通讯场景（脸+底座同屏）签收。

## 存档点

- 分发仓：`github.com/ElysionLhant/macross30-uw329`（README 英文门面，docs 中文档案）
- 本地日常工作补丁：`rpcs3-src/build2/bin/patches/patch.yml`（与分发仓同步，Author: "ElysionLhant & Kimi"）
- 备份：`patch.yml.bak_family`（35 族全量未摘状态，考古用）

两个周末，一台 7680×2160 的屏幕，一个本来没打算被人超宽的游戏。值。
