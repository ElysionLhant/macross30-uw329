# UW_VP_OFFSET.md — Macross 30 HUD 2D VP 反汇编与 X 居中偏移来源

分析对象：`uw_capture.pkl`（及 capture2/3/4 交叉验证）+ `shaders.dat` 内 .cgb + `eboot_mem.bin`。
工具（本目录，可重跑）：`uw_vp_scan.py`（槽位扫描）、`uw_vp_disasm.py`（VP 反汇编器，按 rpcs3 `RSXVertexProgram.h` 位域）、`uw_vp_window.py`（fifo 区间详查）、`uw_cgb_find.py`（.cgb 字节定位）、`uw_vp_fields.py`（逐字段解码）。

## 0. 结论速览

- **偏移不在微码立即数里——RSX VP 指令集根本没有浮点立即数字段**（128 位指令的操作数只能是 v[]/R/c[] 寄存器，能编码的只有 swizzle/取负/槽号）。X 偏移必然来自某个常量槽。
- X 偏移源 = **常量槽 466 的 x 分量取负**（`-c466.x`，当前值 `1.0`），在 HUD 2D 着色器 `vs_ScreenToClipspace*.cgb` 的最后一条 MAD 里。缩放源 = `c466.y / c467.x`，c467 即命名 uniform **"ScreenSize"**（.cgb 资源表 `res=0x01d3=467`，名字字符串在内）。
- **补丁点（GPU 侧，4 个 cgb 文件各 2 字节）**：
  1. 解压后偏移 **0xAB**：`E0 → F8`（末条 MAD 加数 swizzle `.xxxx → .wxxx`，把 X 偏移改指 c466.w）
  2. 解压后偏移 **0xCC**：`00 00 00 00 → 3F 00 00 00`（c466.w 嵌入默认值 0.0 → 0.5）
  - 效果（配合你已把有效宽度改成 2560）：`ndc.x = px·(2/2560) − 0.5`，内容 [0,1280] → NDC [−0.5,+0.5] = UV [0.25,0.75]，**居中**；Y、Z、W 完全不动。
  - **不要**只把 c466.x 改成 0.5：该 MAD 的加数同时喂 X 和 Y，改 c466.x 会把整个 UI 抬高 +0.5 NDC（详见 §3）。
- 若 cgb 补丁实测无效 → 说明该 pass 的 c466 由 CPU 显式上传或 HUD 走 CPU 烘焙直通路径；备选补丁点在 EBOOT，见 §5。

## 1. 关键背景澄清

- trace 里的 `TRANSFORM_PROGRAM x24` = **24 个 32 位字 = 6 条指令**（每指令 4 字），且那段（capture 开头 @584）是 3D 程序（DP4 投影矩阵），不是 HUD。真正的 HUD 2D VP 是 **9 条指令**（vs_ScreenToClipspace，0x90 字节微码）。
- 4 份 capture 里 slot 467 的 `{1/1280, 1/720, 0, 0}` / `{2/1280, 2/720, 0, 0}` 上传，**全部喂给 3D pass 和后期直通 pass，没有任何一份喂给位置缩放**：
  - 3D 大程序（66–96 条指令）：`R.x = c467.x; R.y = -c467.y` → 输出为 texcoord 变体（o[12]/o[13]），即**屏幕空间纹理的 UV 缩放**（1/宽, −1/高）。
  - 后期/字体直通小程序（2–4 条）：`o[0].zw = c467.xxxx / .xxxy`（z=深度, w=1）或 `o[1] = c467`（**逐元素颜色/alpha**，如 {1,1,1,0.5} 淡入淡出）。
  - 实证：全部 4 份 capture 中，没有任何 draw 在 c467=缩放值时使用 ≤20 条指令的程序（扫描脚本结果 = 0）。
- 这解释了你的两个实测：改 c467 的 **z/w 槽无效**（所有消费者只读 .x/.y）；改 1/1280→1/2560 UI 变窄（你改的常数池同时喂 CPU 侧烘焙/上传路径，见 §5）。

## 2. HUD VP 微码反汇编（vs_ScreenToClipspace，9 条全）

资源：`shaders.dat → /shaders/bin/vs_ScreenToClipspace.cgb`（另有 Color/Tex/TexColor 三变体，位置数学完全相同）。
容器：`CGB\0` 头，微码在文件 +0x20，长度 0x90（BE 128 位字），尾部为常量/参数表。

```
[0] MOV  o[0].zw, c[466].zzzx                          ; o.z = c466.z (=0 深度), o.w = c466.x (=1)
[1] RCP  R0.x, c[467].xxxx                             ; R0.x = 1/ScreenSize.x
[2] RCP  R0.y, c[467].yyyy                             ; R0.y = 1/ScreenSize.y
[3] MOV  R0.z, c[466].xxxx                             ; (死代码, 被 [6] 覆盖)
[4] ADD  R0.z, c[467].yyyy, v[0]                       ; (死代码, 被 [6] 覆盖)
[5] ADD  R0.w, -v[0].yyyy, v[0]                        ; R0.w = v0.w - v0.y   (Y 翻转项)
[6] MOV  R0.z, v[0].xxxx                               ; R0.z = v0.x          (像素 X)
[7] MUL  R0.xy, R0.zwzz, R0.xyxx                       ; R0.x = v0.x/SS.x, R0.y = (v0.w-v0.y)/SS.y
[8] MAD  o[0].xy, R0.xyxx, c[466].yyyy, -c[466].xxxx END ; o.xy = R0.xy * c466.y - c466.x
```

变体差异仅在 [1]/[2] 复用 RCP 旁路写 o[1]=v[3]（顶点色）/o[7]=v[8]（UV），位置部分逐字节一致。

**X 输出公式**（c466 嵌入默认 {1.0, 2.0, 0, 0}，c467 = ScreenSize = {1280, 720}）：

```
o.x = v0.x · (c466.y / c467.x) − c466.x = px · (2/1280) − 1      [0,1280] → [−1,1] ✓
o.y = (v0.w − v0.y) · (2/720) − 1                                (Y 翻转, 与 X 无关)
o.z = c466.z = 0 ,  o.w = c466.x = 1
```

你改 1/1280→1/2560（等效 c467.x=2560）后：`o.x = px·(2/2560) − 1` → [0,1280]→[−1,0] = UV [0,0.5] **左锚定**，与实测完全吻合。居中需加性 +0.5 NDC（= +0.25 UV）。

## 3. 偏移的字节位置（patch 用）

加性偏移 = **−c466.x**，值 1.0 存在 .cgb 尾部的槽 466 嵌入默认常量块（`01d2`=466 记录后的 16 字节 `{1.0, 2.0, 0, 0}`）。
**但注意 Y 耦合**：指令 [8] 的加数 `-c466.xxxx` 同时是 X 和 Y 的偏移（o.y 也减 c466.x）。直接改 c466.x→0.5 会让 Y 整体上移 +0.5 NDC。因此采用**两字节方案**——把 X 偏移改指空闲的 c466.w：

| 文件（shaders.dat 内） | rec_idx | abs_off | dec/stored | 压缩 |
|---|---|---|---|---|
| /shaders/bin/vs_ScreenToClipspace.cgb | 26288 | 0x34f4000 | 0xfd / 0xab | zlib |
| /shaders/bin/vs_ScreenToClipspaceColor.cgb | 26289 | 0x34f4800 | 0xfd / 0xb1 | zlib |
| /shaders/bin/vs_ScreenToClipspaceTex.cgb | 26290 | 0x34f5000 | 0xfd / 0xb3 | zlib |
| /shaders/bin/vs_ScreenToClipspaceTexColor.cgb | 26291 | 0x34f5800 | 0xfd / 0xb4 | zlib |

每个文件解压后（4 个文件字节布局相同）：

| dec 偏移 | 原字节 | 新字节 | 含义 |
|---|---|---|---|
| **0xAB** | `E0` | `F8` | 指令[8] d2 低字节：src2 swizzle `.xxxx→.wxxx`（已用反汇编器往返验证） |
| **0xCC** | `00 00 00 00` | `3F 00 00 00` | c466.w 嵌入默认 0.0 → 0.5（BE float） |

结果：`o.x = px·(2/c467.x) − c466.w`，`o.y = … − c466.x`（不变），`o.z = c466.z = 0`（不变），`o.w = c466.x = 1`（不变）。
c466.w 在该 shader 内无任何其他引用，安全。

重打包与 .ark 流程相同：`zlib.compress(dec, 9)` 已验证与游戏压缩器**字节级一致**（4 个文件均已复验），stored 变小（0xab→~0xab），落在原 0x800 对齐槽内，只改记录 stored 字段，零级联。

## 4. capture 内全部 VP 程序类型（对照）

| 类型 | 条数 | o[0].x 来源 | c467 角色 |
|---|---|---|---|
| 3D 物件（大程序） | 64–96 | DP4(v0, c264..267) 矩阵 | {c467.x, −c467.y} → texcoord 缩放 |
| 天空盒 | 9/19 | DP4/DPH(v0, c256..259) | 颜色/雾参数 |
| 后期/字体直通 | 2–4 | **v0.xy 直通**（CPU 烘焙 NDC） | z/w={1,0} 或 逐元素颜色 |
| **HUD 2D（vs_ScreenToClipspace）** | 9 | **v0.x·(c466.y/c467.x) − c466.x** | ScreenSize（RCP 取倒数） |

注意：vs_ScreenToClipspace 在 4 份 capture 里**一次都没执行**（字节级搜索 0 命中）——capture 抓的是 3D 战斗场景，LAYO/菜单 2D pass 不在其中。capture 里能看到的 2D draw（字体、fade quad）全是 CPU 烘焙 NDC 直通。

## 5. 风险与备选

- **主要不确定性**：c466={1,2,0,0} 是 .cgb 嵌入默认值。若引擎对该 pass 显式上传 c466（capture 里其他 pass 确实有逐批上传 c466 的先例，如 {1,0,0,0}），则 cgb 补丁不生效。EBOOT 内**没有** `{1,2,0,0}` vec4 明文（已全扫），所以显式上传也只能是代码逐字段构造——这种情况下 cgb 默认大概率就是生效值。
- **判定测试**：打上 cgb 补丁跑一次。HUD 居中 → 完事。无变化 → HUD 走 CPU 烘焙直通路径，转用下面的 EBOOT 备选。
- **EBOOT 备选补丁点**（`eboot_mem.bin` = EBOOT.ELF 文件映像，BE）：
  - `0xab1f10` = `{1/1280, −1/720, −1.0, …}` —— 全 EBOOT 唯一同时含缩放和 **−1.0 X 偏移**的 vec4。若 HUD 顶点由 CPU 烘焙（直通），偏移就是这里的 z：`file+0xab1f18` 的 `BF 80 00 00` → `BF 00 00 00`（−1→−0.5）。
  - 你改 1/2560 时动过的缩放池很可能在这几处：`0x8cf278 / 0x8cf4b0 / 0x8cfa08` = `{1/1280, −1/720, 0, 1}`，`0x8cf288 / 0x8cf4c0 / 0x8cfa18` = `{2/1280, −1/720, 0, 1}`（各 3 份镜像，可能对应不同渲染路径/分辨率分支，需一并处理）。
  - 上传源 `{1/1280, +1/720}` 明文：`0xaade80 / 0xaf7a10 / 0xaf8110`（喂 3D texcoord 的那条路径）。
- **打包层风险**：沿用你已验证的结论——同槽位写回、stored 字段同步、pack.idx 不动。zlib 重压字节级一致已复验。
- **微码编辑风险**：src2 swizzle 改动只影响本 shader 的 X 加数来源；该 shader 仅用于 2D 屏幕空间 pass，不波及 3D。
