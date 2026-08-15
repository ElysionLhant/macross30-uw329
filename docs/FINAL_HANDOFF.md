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
2. **彩虹边缘**——tile1/2（深度/雾 RT）的 1280 来源在 tier 预设表，未定位。
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

## 存档点

- 分发仓：`github.com/ElysionLhant/macross30-uw329`（README 英文门面，docs 中文档案）
- 本地日常工作补丁：`rpcs3-src/build2/bin/patches/patch.yml`（与分发仓同步，Author: "ElysionLhant & Kimi"）
- 备份：`patch.yml.bak_family`（35 族全量未摘状态，考古用）

两个周末，一台 7680×2160 的屏幕，一个本来没打算被人超宽的游戏。值。
