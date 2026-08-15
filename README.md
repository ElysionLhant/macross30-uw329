# Macross 30 (BLJS10184) — RPCS3 32:9 Ultrawide Patch & Toolkit

English summary at the bottom / 英文摘要在文末。

Macross 30（超时空要塞30 连接银河的歌声，BLJS10184）在 **RPCS3 v0.0.32-16803** 上的 32:9（7680×2160）超宽屏补丁，以及打出这套补丁所用的全套逆向工具链。

**当前效果（全部实机验证）**：

- 3D 投影原生 32:9（主相机矩阵 m00 减半，0.974→0.487）
- HUD / 菜单 / 文字全部原生居中到中央 16:9 区（CPU 烘焙补丁，不是拉伸）
- 影片为 16:9 预渲染，保持拉伸（无解，片源就是 16:9 的）
- 已知残留：冲刺（加速）时运动模糊边缘有一条分割线，见下文「下一段路」

---

## 安装

1. 必须用 RPCS3 **v0.0.32-16803**（新版放不了本作的影片，见 RPCS3 issue #17485）
2. `patches/patch.yml` 放进 rpcs3 的 `patches/`；`patches/config_BLJS10184.yml` 放进 `config/custom_configs/`（里面 VFS 路径改成你自己的游戏目录）
3. 补丁管理器启用；GPU 设置勾 **Stretch To Display Area**；**必须全屏玩**（窗口模式横向压缩是预期现象）
4. PPU 补丁在 LLVM recompiler 下同样生效；不要用解释器（0.08 fps，纯粹调试用途）

---

## 核心考据：这套补丁是怎么想出来的

给后来人：以下每一节都是卡了很久才打通的关节，按这个顺序读可以少踩我们踩过的坑。完整编年日志在 `docs/HANDOFF.md`，写出函数全考据在 `docs/BAKER_FINDING.md`（附录 A-D），冷启动交接在 `docs/COLDSTART.md`。

### 1. 3D 宽屏：别碰投影矩阵，碰它的原料

> 本节的思路致谢 **[@wagrenier](https://github.com/wagrenier)**——"改宽度原料而非投影公式"的解法来自他的星海（Star Ocean）系列补丁，本作 3D 部分能解得这么顺，是因为在他的作业里见过同一个坑。

症状是 32:9 下 3D 被压扁。常规定位是找投影矩阵的 m00/tan(fov)，但本作的投影是**每帧现算**的：

- `aspect = (float)w / (float)h`，其中 w/h 来自**整数到浮点的 fcfid 转换**，再 `frsp` 收成单精度
- 把各处宽度转换的 `frsp fX, f13` 改成 `fadds fX, f13, f13`（宽度×2），aspect 就从 16:9 变成 32:9，下游所有投影构建自动正确
- 另有一路标量构建器走**静态宽高比常量表** `@0xad5328`，把里面的 16/9 (0x3FE38E39) 改成 32/9 (0x40638E39)

教训：**改输入比改公式安全**。投影矩阵在内存里每次重新构建，盯着矩阵本身永远追不到源头；盯它的操作数一次到位。

### 2. HUD 居中：找"写出函数"，别找常量

症状：32:9 下全部 HUD 挤在屏幕左 1/3。

HUD 顶点是 **CPU 逐角点烘焙**的 f32 四边形，写出代码是一个**函数族**（通用 2D 类的 vtable，共 36 个写出函数 + 2 个文字渲染器）。每个函数的模式一模一样：

```
每绘制读 0x5bba04 的运行时 W/H（所以没有任何静态常量可搜！）
A = W * K,  K = 0.5（常量 @0xad7058, TOC1+0x599c）
ndc_x = (px - A) / A      // px ∈ [0,1280] 设计坐标
ndc_y = -(py - B) / B
```

32:9 下运行时 W=3840，A=1920，px∈[0,1280] 被映射到 [-1, -1/3]——这就是"左 1/3"的成因。**搜 51.2 / 32767 / 1280 之类的常量全是死路**，因为宽度是运行时读的，必须找写出函数本身。

居中的改法（每个 x 角点只动 2 条指令，y 不碰）：

```ppc
# 原始:  fsubs f13, f13, fA   ; px - A
#        fdivs f13, f13, fA   ; / A
# 改后:  fdivs f13, f13, fA   ; px / A
#        fmsubs f13, f13, fS, fS ; (px/A)*0.5 - 0.5  =  px/(2A) - 0.5
```

合成结果 `px/(2A) - 0.5`：设计坐标 [0,1280] 恰好映射到 NDC [-0.5, 0.5]，即中央 16:9 区，且**宽高比不被拉伸**（x 缩放系数与 y 一致）。fS=0.5 的种子用函数里现成的 `nop` 槽放一条 `lfs fS, 0x599c(r2)`。

PPC A-form 编码要点（踩过坑）：**frC 在 bits 10-6，frB 在 bits 15-11**；fdivs XO=18、fmsubs XO=28、fmuls XO=25（opcode 都是 59）；`fmsubs(a,b,c) = a*b - c`。frsp/frsqrte 等是 opcode **63** 不是 59。

### 3. 全屏特效必须豁免：UI 和特效共用同一个 vtable

36 个写出函数里有一小撮**不只画 UI，还画全屏特效 quad**（冲刺拖影的黑带来源）。这些 quad 的设计坐标本来就横跨全屏，居中补丁把它们压进中央带 = 一条黑色拖影。

处理：**7 个 quad+UV 变体（0x5e48ac/0x5e4bc8/0x5e4ee0/0x5e51f8/0x5e5510/0x5e5828/0x5e5b7c）整体不打补丁**，保持原始 `(px-A)/A`——对全屏 quad 来说原式在任何宽高比下都正确。

教训：**静态补丁的最小粒度是整个函数**。一个函数混画 UI 和特效时，内联按宽度豁免做不到（每角点只剩 2 条指令位，fsel 需要 3 条，JIT 下也没有 code cave），只能整函数取舍，或者上模拟器侧运行时门控（见「下一段路」）。

### 4. 文字渲染器：寄存器生命周期比公式难

文字不走上面 36 个函数，走 `0x1a1244`（单精灵）和 `0x1a1a54`（批量精灵 bdnz 环），用另一套 K 常量（@0xac18a4, TOC2-0x2fc）。公式改法相同，但批量环里有个暗坑：

- 环内 `f12` 加载 K=0.5 之后，被一条 `frsp f12, f7`（UV 的 v 除数 texH 的 int→float 转换）**撞碎**——texW/texH 是环不变的，编译器却每轮重算
- 解法：把 texH 挪窝——`frsp f12,f7` 改成 `frsp f13,f7`，两条 UV v 除法 `fdivs f10,f10,f12` / `fdivs f8,f8,f12` 改吃 f13。f13 本来就是每角点 `lfs` 重载的 scratch，时机上无冲突；f12 于是全程保 K
- **敢用 f12 的前提是确认它跨 `bl` 存活**：整条调用链（0x8daf08 跳板 → 0x574190 → memcpy 系工具函数）反汇编确认**全程零 FP 写**才行。volatile 寄存器想当然是会死人的

教训：批量环的记录推进指针是 `r31`（`addi r31,r31,0x20`）。早前一版补丁偷 `clrldi` 槽位放种子、补偿错了寄存器，文字被压成一条竖线。**改环内代码前，先把每个寄存器的生命周期画完**。

### 5. 工程环境（RPCS3 特制 build2）

- 补丁载体就是标准 `patch.yml`（be32 词），LLVM 下生效，不用改模拟器
- PPU 补丁地址 = EBOOT 解密后的 vaddr（本仓 `tools/` 里有 dump/反汇编设施，capstone 记得开 `skipdata`，否则遇数据即停）
- **一组 `li 1280→2560` 立即数补丁会随机"万花筒"**（布局走了多条路径），已弃用；v11 li 组同理，日常别开
- 活体内存基址实测 `0x400000000`（pymem 读 base+vaddr 可验证补丁是否生效）

---

## 下一段路（冲刺残影分割线）— 起始点写死在这里

**症状**：加速/冲刺时 3D 残影上有一条竖直分割线。其余全部正常，游戏完全可玩。

**已查明（附录 D，不用再查）**：

- 运动模糊 = 3 个 pass × 7 tap，采样主显示纹理 `0x027b0000`；着色器 VP 本地地址低 24 位 `0xf3d181 / 0x7b01 / 0xabf81`（**运行时分配**，EBOOT 无字面值，静态搜不到）
- 三个 pass 全部走 **0x822 dummy-quad 合成路径**：slot0 全零、slot12 是共享浮点表 **`@0x81eb1e04`**；发射器在 `0x9b1d8`（含 `0x9b420`/`0x9b7f8` 两处 ori 0x822 格式命令）
- 这条路径**不经过**已打补丁的 36 个写出函数（那些产 0x1032/0x1432 真顶点，slot0 非零）。模糊链本身没被压缩，**没有更多函数可摘**——再摘只会把 UI 一起带走
- 那条缝 = 全屏模糊区与其它内容的边界，**不是**还有一个模糊写出器被压着

**两条可行路线**：

1. **（正道）build2 模拟器侧运行时门控**：在已建的 `RPCS3_UW_HUD` 钩子链上，按当次绘制 quad 的宽度判断——≈全屏宽就跳过居中、UI 宽才收。这是唯一能"特效全屏 + UI 居中"两全的做法，代价是改模拟器代码 + 重编。
2. **（侦察）定位 0x822 烘焙器**：用附录 C 末尾的 build2 日志法——在 tex==0x027b0000 的 0x822 绘制时记录写 slot12 表的 CPU PC，一次实测定案。定到写表者之后，要么单独豁免，要么发现它本就该全屏而结案。

**别做的事**：恢复那 7 个 quad+UV 变体的补丁（会用缝换回黑影）；继续摘 0x5exxxx 函数（摘一个少一块 UI）。

---

## 工具链

- `uw_measure.py` — tile pitch + 主相机投影 m00 活体读取（pymem，自动找 ASLR 基址）
- `uw_gdb_trace.py` — RPCS3 GDB stub 断点采集（Z0 断点 + 任意寄存器 + 内存 deref）
- `uw_vp_disasm.py` / `uw_vp_*.py` — RSX 顶点着色器微码反汇编 / 抓包绘制挖掘
- `uw_pack_re.py` / `uw_pack_patch.py` / `uw_pack_center640.py` — pack 容器（PIDX/AXL）解析/补丁/LAYO 加宽（只操作你自己的游戏文件；带完整性校验的资源会弹 "Game data is corrupted"，默认排除）
- `uw_cgb_fix.py` — shaders.dat 内 .cgb 微码补丁器
- `uw_harness*.sh` / `postkey.ps1` — 自动化 boot→导航→3D 测试循环、按键注入
- `uw_guest.py` / `uw_findbase.py` / `uw_poke_desc.py` — 客体内存 dump/探基址/活体戳

## 文档

- `docs/COLDSTART.md` — 冷启动交接（先读它）
- `docs/HANDOFF.md` — 编年调试日志（全部过程，含失败路线）
- `docs/BAKER_FINDING.md` — HUD 烘焙器全考据（附录 A：35 族清单；B：文字渲染器；C：RSX 抓包法；D：模糊链终判）
- `docs/UW_PACK_RE.md` — pack/PIDX/AXL 格式文档
- `docs/UW_VP_OFFSET.md` — HUD 偏移的 VP 微码分析

## 已知未竟（除分割线外）

- tile1/2（深度/雾效渲染目标）的 1280 来源：tier 预设表，待定位（彩虹边缘源）
- dialog.ark / mechroom_develop.ark / quest_clear 的逐资源完整性校验（CRC32 @0x653aa0）逆向

## 致谢

- **[@wagrenier](https://github.com/wagrenier)** — 星海（Star Ocean）系列补丁的作者。3D 宽屏"改原料不改公式"的思路学自他的作业，特此致谢。

## 免责

仅为学习/研究目的的游戏修改工具与补丁。不包含任何游戏数据文件；所有 pack 工具只操作用户本地合法持有的游戏副本。游戏版权归 Bandai Namco / Artdink 所有。

---

## English summary

A 32:9 (7680×2160) ultrawide patch for **Macross 30 (BLJS10184)** on **RPCS3 v0.0.32-16803**, plus the reverse-engineering toolkit used to build it.

**What works (all verified on hardware)**: native 32:9 3D projection; HUD, menus and text natively centered to the middle 16:9 region via CPU quad-baker patches; movies stay stretched 16:9 (pre-rendered). One cosmetic leftover: a seam line on the boost motion blur.

**Key techniques** (full write-up in the Chinese sections above and `docs/`):

- *3D*: aspect ratio is computed per-frame from integer width via `fcfid`/`frsp`; changing `frsp fX,f13` to `fadds fX,f13,f13` doubles the width at the source. Patch the ingredients, not the matrix.
- *HUD*: vertex data is CPU-baked per corner by a family of 36 quad-writer functions reading runtime W/H from `0x5bba04` (`ndc = (px - W/2)/(W/2)`). Centering = 2 instructions per x-corner: `fsubs→fdivs` then `fdivs→fmsubs(f,f,0.5,0.5)`, yielding `px/(2A) - 0.5`. No static constants exist — find the writers, not the numbers.
- *Fullscreen effects exemption*: 7 quad+UV variants also draw fullscreen effects and are left unpatched (patching them squashes effects into a black band). Static PPC patches can only gate at whole-function granularity.
- *Text renderer*: `0x1a1244`/`0x1a1a54` batch loop clobbers `f12` (=K) with a UV divisor `frsp`; fix relocates texH to `f13`. Verify the whole call tree is FP-write-free before relying on a volatile register across `bl`.
- *Next path (boost-blur seam)*: blur taps use the `0x822` dummy-quad composite path (shared float table `@0x81eb1e04`, emitter `0x9b1d8`), not the 36 patched writers. Fix = emulator-side runtime gating by quad width (build2 `RPCS3_UW_HUD` hook chain), or locate the table writer via build2 logging on draws with tex==`0x027b0000`. Do not re-patch the 7 variants (trades seam for black band) and do not strip more writer functions (eats UI).

Requires RPCS3 v0.0.32-16803 exactly (newer builds can't play this game's videos — issue #17485). Enable the patch, check **Stretch To Display Area**, play fullscreen. No game data included; tools operate only on your own legally obtained copy. All rights to the game belong to Bandai Namco / Artdink.

**Credits**: 3D widening approach ("patch the width source, not the projection formula") learned from [@wagrenier](https://github.com/wagrenier)'s Star Ocean patch work — thanks!
