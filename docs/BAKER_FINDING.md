# BAKER_FINDING.md — HUD/UI 顶点烘焙器定位与补丁（2026-08-15，纯静态分析）

## 结论（已字节级验证）

**烘焙器 = f32 四边形顶点写出函数族**。代表函数 **`0x5e5ea4`**（每绘制调用一次）：

1. `bl 0x5bba04` 读显示参数（w@+8、h@+0xc，即 handoff 记录的 45 调用者 getter）
2. `lfs f12, 0x599c(r2)`（**TOC1+0x599c = 0xad7058，值 0.5**，已验证 `0x3F000000`）
3. `obj+4 = W×0.5`、`obj+8 = H×0.5`（0x5e5f54/0x5e5f60 fmuls → stfs）
4. 每角点（4 个）：
   - `ndc_x = (px − W·0.5)/(W·0.5)`（fsubs + fdivs，0x5e5fd0/0x5e5fe4 等）
   - `ndc_y = −(py − H·0.5)/(H·0.5)`（fdivs + fneg）
   - `stfs` 写出 **2×f32** 位置（顶点缓冲 0x40 字节 = 4 顶点 × 16B，匹配抓包 **0x1032 族 stride-16 2×f32**）

即公式 `ndc_x = px·(2/W) − 1`，缩放常量 = **K=0.5（@0xad7058）×运行时 W（cellVideoOut 派生）**——正是"无静态 51.2/32767 常量"的原因：缩放 = 数据常量 K × 运行时宽度，除法在烘焙点现场完成。

**同族写出函数**（同一 K 常量、同一公式，均经 `0x5bba04` 取 W/H）：
`0x5e8b5c`（x,y,w,h 形参版）、`0x5e953c`、`0x5e9a70`、`0x5e9f68`、`0x5ea548`、`0x5eaba4`，以及 0x5e26d0–0x5e7ed8 大簇内更多变体（共 96 个 fdivs→fneg→stfs 签名命中）。调用方：`0x5e5ea4` 经跳板 `0x7009c4` 被 4 处调用（0x4c210=九宫格对话框类、0x4c9ec/0x4ca60=同类分支、0x79674=另一元素装配点）。

## 本轮证伪/排除（勿再重查）

- **0x4cc28 环（lead 1）**：九宫格对话框类的**第二阶段** int 转换环——对象内浮点（设计 px 截断值）→ fctiwz → s16 栈缓冲 → `0x4c048` 转回浮点 → 喂给 `0x5e5ea4`。无缩放，缩放在其上游对象初始化/本写出函数。
- **0xb0aac 上传父函数（lead 2）**：渲染状态应用器（纹理/常量上传），记录 +0xc 字段是常量记录指针，非顶点烘焙。
- **0x5c0d50 族（lead 3）**：显示参数结构体 +0x2738/+0x2740/+0x2748 三组 {值, 1/值} 对（0x5c0d98/0x5c0d18/0x5c0d58 三个设置器，守卫 1e-4/10000），**全部 getter 只喂 shader 常量上传**（0x628610/0x628940/0x62988c），非 CPU 烘焙缩放源。+0x2740→+0x2738 的模式切换拷贝在 0x356a88。
- 43 个 fctiwz 候选站点：逐一核验常量（1048576.0/128.0/1.0/clamp/视口 NDC→px/进度×MAX），全非位置烘焙。
- `lwbrx`（LAYO LE 关键帧假设）：全二进制仅 2 命中，均为栈存储，无关。
- VMX 烘焙（vctsxs/vpkshss/stvx）：命中全在 0x99xxxx–0xa5xxxx 错位数据区，假阳性。

## 补丁（patch.yml，PPU be32，addr=guest vaddr）

### 目标补丁：x 映射 [−1,1]→[−0.5,0.5]（16:9 居中、比例正确，y 不动）

原理：`ndc' = 0.5·ndc`。逐角点把 `(px−A)/A` 改为 `(px/A)·0.5 − 0.5`（fmsubs 融合乘加，f11=0.5 在分配调用**之后**由 TOC 重载种子，规避 JIT 调用链对 f12 的易失风险；腾挪 `mr r10, r27` 槽位，corner-2 的指针改用 r25——r10 在 0x5e6020 会被重置，生命周期已核验无冲突）。

```yaml
# HUD bake center: writer 0x5e5ea4, x -> 0.5*(px/A - 1) => [-.5,.5]
- [ be32, 0x5e5fcc, 0xc162599c ]  # mr r10, r27      -> lfs f11, 0x599c(r2)   # f11 = 0.5（调用后种子）
- [ be32, 0x5e5fd0, 0xedad0024 ]  # fsubs f13,f13,f0 -> fdivs f13, f13, f0    # px/A
- [ be32, 0x5e5fe4, 0xedad5af8 ]  # fdivs f13,f13,f0 -> fmsubs f13, f13, f11, f11  # *0.5 - 0.5
- [ be32, 0x5e6008, 0xc5b90008 ]  # lfsu f13, 8(r10) -> lfsu f13, 8(r25)      # r10 初始化槽被征用
- [ be32, 0x5e601c, 0xc0190004 ]  # lfs f0, 4(r10)   -> lfs f0, 4(r25)        # pos[1].y 跟随 r25
- [ be32, 0x5e600c, 0xedad6024 ]  # fsubs f13,f13,f12-> fdivs f13, f13, f12
- [ be32, 0x5e6010, 0xedad5af8 ]  # fdivs f13,f13,f12-> fmsubs f13, f13, f11, f11
- [ be32, 0x5e603c, 0xedad6024 ]  # fsubs f13,f13,f12-> fdivs f13, f13, f12
- [ be32, 0x5e6040, 0xedad5af8 ]  # fdivs f13,f13,f12-> fmsubs f13, f13, f11, f11
- [ be32, 0x5e606c, 0xec006824 ]  # fsubs f0, f0, f13 -> fdivs f0, f0, f13
- [ be32, 0x5e6070, 0xec005af8 ]  # fdivs f0, f0, f13 -> fmsubs f0, f0, f11, f11
```

数学核验（W=1280，A=640）：px=0→−0.5，px=1280→+0.5；y 保持 (py−360)/360 → [−1,1] 满高。JIT 缓存需重启游戏生效。

### 覆盖范围与风险（务必读）

- **只覆盖 0x5e5ea4 一个写出函数**（0x1032 stride-16 f32 族及其 4 个调用方：对话框九宫格类、0x79674 装配点）。同族其它写出函数（0x5e8b5c/0x5e953c/0x5e9a70/0x5e9f68/0x5ea548/0x5eaba4 等）需按同一模式逐个打补丁才能全覆盖；未打的部分 HUD 元素仍拉伸（类似 v2 的部分生效）。
- **s16 族（0x1022/0x822）不经此函数**，本补丁对其无效（0x822 位置在 slot12 共享浮点表，烘焙点未定位）。
- **勿与 center640 包补丁叠加**（菜单会二次平移）。
- fmsubs 与 fdivs+fmuls 的舍入差异在 s16/f32 顶点精度下不可见。
- 角点 1 的 f11 种子在 `bl 0x574190`（分配器）**之后**加载（0x5e5fcc），不依赖任何跨调用浮点寄存器；r2=TOC1 在分配链中被保存/恢复（已核验 0x574190→…→0x8ddcac 导入存根均有 `ld r2, 0x28(r1)` 恢复）。

### 备选单数据补丁（全局但**左锚定**，用于先行验证机制）

```yaml
# HUD bake scale: K 0.5 -> 1.0 (all writers using TOC1+0x599c) => ndc [−1,0]
- [ be32, 0xad7058, 0x3f800000 ]
```

效果：所有读 K 的写出函数 ndc_x = px/W − 1 ∈ [−1,0]——比例正确但贴左半屏（公式结构 (px−A)/A 恒过 −1，单改 K 无法居中，已数学证明）。验证机制成立后再上 11 词居中补丁。

## 现场验证清单（实机）

1. 先打备选单数据补丁（0xad7058→1.0）：预期 HUD/对话框 2D 元素收缩到左半、比例正常 → 证实该写出族覆盖范围。
2. 换 11 词补丁：预期被 0x5e5ea4 服务的元素居中（对话框/通讯框最易观察）。
3. 若仍有元素拉伸：记录其抓包顶点格式（0x1432/0x1022/0x822），对应写出函数按同模式补打；0x822 共享浮点表烘焙点另查（候选：每帧写 float 表的函数，读 0x5bba04 + 0xad7058 K）。

## 关键地址备忘

- 写出函数族代表：`0x5e5ea4`（另 `0x5e8b5c` x/y/w/h 版）
- 缩放常量：`0xad7058`（TOC1+0x599c，0.5）
- 显示参数 getter：`0x5bba04`（w@+8、h@+0xc）
- 跳板：`0x7009c4`（→0x5e5ea4，TOC 切换）
- 调用点：0x4c210、0x4c9ec、0x4ca60、0x79674
- 第二阶段 int 转换：0x4cac4（0x4cc28 环）、0x4c048（s16→f32 + UV/贴图尺寸归一）
- 顶点格式参考：0x1032 = 2×f32（非 handoff 旧记的 s16；0x?22 低字节 0x22 才是 2×s16 归一化）

---

# 附录 A：写出函数族全量居中补丁（2026-08-15 II，35 函数 263 词，编码全验证）

## 机制与验证方法

族谱：全二进制 39 处 `lfs fX, 0x599c(r2)`（K=0.5）站点 = **0x5e5ea4（已打）+ 本附录 35 函数 + 2 个 blit 变体（0x5dd0e8/0x5ded54，仅搬运预烘焙块，无烘焙公式，跳过）+ 0x5dc910（A/B 设置助手，无角点，跳过）**。35 个写出函数全部确认含 `bl 0x5bba04` + `bl 0x574190` + obj+4/+8 存 A/B + 逐角点 `(px−A)/A`（x，无 fneg）/ `(py−B)/B` 取负（y，不动）。

每函数补丁构成（y 角点一律不碰）：
1. **种子**：`bl 0x574190` 后的 ABI `nop`（TOC 恢复槽，同 TOC 下为空操作）→ `lfs fS, 0x599c(r2)`（fS=0.5）。在分配调用**之后**取常量，不受调用链易失影响；fS 选自该函数种子点之后**全函数范围（含各退出路径）无任何读写**的易失浮点寄存器，且不等于任何角点的目的寄存器。
2. **每 x 角点 2 词**：`fsubs fD,fA,fT → fdivs fD,fA,fT`（px/A）；`fdivs fD,fD,fT → fmsubs fD,fD,fS,fS`（×0.5−0.5）。

特例（已逐一人工核验）：
- **滚动列表四胞胎** 0x5e39f8/0x5e3c94/0x5e3edc/0x5e4124：角点在 beq 分支后的无调用循环里，且 K 常驻非易失 **f31=0.5**（兼作 +0.5 半像素偏置）——**免种子**，每角点仅 2 词 `fmsubs f0,f0,f31,f31`。
- **循环写出器** 0x5e6580（bdnz 循环逐顶点）/ 0x5e7678（bdnz 循环每轮 4 顶点，文本字形四边形）：补丁在循环体内，一次生效全部顶点。
- **0x5eaba4** 角点 1 的 fdivs 与其 UV 计算交错，人工定位在 0x5eadf0（非自动首匹配）。
- **0x5e2568**（2 顶点线）/ 0x5e2934/0x5e2c34（3 顶点三角）/ 0x5e36f8（5 x 角点扇）/ 0x5e46b0（1 x 角点）：按实际角点数打。
- **0x5e5ea4 注**：已部署 11 词补丁（实机验证）；其后亦有 nop 槽 0x5e5f6c 可作种子（更简方案），但已验证补丁不动。

**编码验证（零失误）**：263 词全部经 capstone 双向核验——原址原词与预期指令逐字相符（fsubs/fdivs/nop 语义匹配），新词反汇编与目标指令一致（fdivs XO=18、fmsubs XO=28、frC 在 bits10-6、lfs opcode 48）。脚本 %TEMP%\uw_family_encode.py，产物 %TEMP%\uw_family_patches.txt。

## 覆盖声明与注意

- 补丁只改各函数 x 角点映射 `[-1,1]→[-0.5,0.5]`；y 角点、UV/属性流、z 深度（0x5a10=-2.5 等）均未动。
- 滚动四胞胎的 +0.5 半像素偏置随 x 一并缩放（公式内，行为正确）。
- 仍不覆盖：s16 族（0x1022/0x822）与 0x822 slot12 共享浮点表烘焙点（非本公式族）。
- 若实机仍见个别元素拉伸：抓包确认其顶点格式与绘制 pass，反查其写出函数是否在本族 39 站点之外（可能是不经 0x599c K 的变体），按同模式补打。

## 全量 patch.yml 条目（35 函数）
### fn 0x5e2568 (3 words)
- [ be32, 0x5e2638, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e26b8, 0xedad0024 ]  # fsubs f13, f13, f0  ->  fdivs f13, f13, f0
- [ be32, 0x5e26bc, 0xedad5af8 ]  # fdivs f13, f13, f0  ->  fmsubs f13, f13, f11, f11

### fn 0x5e2934 (7 words)
- [ be32, 0x5e2a0c, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e2a58, 0xec1f6824 ]  # fsubs f0, f31, f13  ->  fdivs f0, f31, f13
- [ be32, 0x5e2a6c, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e2a8c, 0xec1d6824 ]  # fsubs f0, f29, f13  ->  fdivs f0, f29, f13
- [ be32, 0x5e2a90, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e2ab0, 0xec1b6824 ]  # fsubs f0, f27, f13  ->  fdivs f0, f27, f13
- [ be32, 0x5e2ab4, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e2c34 (7 words)
- [ be32, 0x5e2d0c, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e2d58, 0xec1f6824 ]  # fsubs f0, f31, f13  ->  fdivs f0, f31, f13
- [ be32, 0x5e2d60, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e2d80, 0xec1d6824 ]  # fsubs f0, f29, f13  ->  fdivs f0, f29, f13
- [ be32, 0x5e2d84, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e2da4, 0xec1b6824 ]  # fsubs f0, f27, f13  ->  fdivs f0, f27, f13
- [ be32, 0x5e2da8, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e2e9c (9 words)
- [ be32, 0x5e2f64, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e2fb0, 0xec1f6824 ]  # fsubs f0, f31, f13  ->  fdivs f0, f31, f13
- [ be32, 0x5e2fcc, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e2fec, 0xec1f6824 ]  # fsubs f0, f31, f13  ->  fdivs f0, f31, f13
- [ be32, 0x5e2ff0, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e3010, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e3014, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e3034, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e3038, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e31d0 (9 words)
- [ be32, 0x5e3298, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e32e4, 0xec1f6824 ]  # fsubs f0, f31, f13  ->  fdivs f0, f31, f13
- [ be32, 0x5e32ec, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e330c, 0xec1f6824 ]  # fsubs f0, f31, f13  ->  fdivs f0, f31, f13
- [ be32, 0x5e3310, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e3330, 0xec1d6824 ]  # fsubs f0, f29, f13  ->  fdivs f0, f29, f13
- [ be32, 0x5e3334, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e3354, 0xec1d6824 ]  # fsubs f0, f29, f13  ->  fdivs f0, f29, f13
- [ be32, 0x5e3358, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e3470 (9 words)
- [ be32, 0x5e3528, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e357c, 0xedad0024 ]  # fsubs f13, f13, f0  ->  fdivs f13, f13, f0
- [ be32, 0x5e3584, 0xedad5af8 ]  # fdivs f13, f13, f0  ->  fmsubs f13, f13, f11, f11
- [ be32, 0x5e35ac, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e35b0, 0xedad5af8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f11, f11
- [ be32, 0x5e35dc, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e35e0, 0xedad5af8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f11, f11
- [ be32, 0x5e360c, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e3610, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e36f8 (11 words)
- [ be32, 0x5e37c4, 0xc0e2599c ]  # nop  ->  lfs f7, 0x599c(r2)
- [ be32, 0x5e382c, 0xec094024 ]  # fsubs f0, f9, f8  ->  fdivs f0, f9, f8
- [ be32, 0x5e3838, 0xec0039f8 ]  # fdivs f0, f0, f8  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5e3860, 0xec0c6824 ]  # fsubs f0, f12, f13  ->  fdivs f0, f12, f13
- [ be32, 0x5e3864, 0xec0039f8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5e3884, 0xed8c6824 ]  # fsubs f12, f12, f13  ->  fdivs f12, f12, f13
- [ be32, 0x5e3888, 0xed8c39f8 ]  # fdivs f12, f12, f13  ->  fmsubs f12, f12, f7, f7
- [ be32, 0x5e38a8, 0xec096824 ]  # fsubs f0, f9, f13  ->  fdivs f0, f9, f13
- [ be32, 0x5e38ac, 0xec0039f8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5e38cc, 0xed290024 ]  # fsubs f9, f9, f0  ->  fdivs f9, f9, f0
- [ be32, 0x5e38d0, 0xed2939f8 ]  # fdivs f9, f9, f0  ->  fmsubs f9, f9, f7, f7

### fn 0x5e39f8 (2 words)
- [ be32, 0x5e3c48, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e3c4c, 0xec00fff8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f31, f31

### fn 0x5e3c94 (2 words)
- [ be32, 0x5e3e90, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e3e94, 0xec00fff8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f31, f31

### fn 0x5e3edc (2 words)
- [ be32, 0x5e40d8, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e40dc, 0xec00fff8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f31, f31

### fn 0x5e4124 (2 words)
- [ be32, 0x5e4320, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e4324, 0xec00fff8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f31, f31

### fn 0x5e436c (5 words)
- [ be32, 0x5e4438, 0xc122599c ]  # nop  ->  lfs f9, 0x599c(r2)
- [ be32, 0x5e449c, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e44a0, 0xed6b4a78 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f9, f9
- [ be32, 0x5e44c0, 0xed4a6824 ]  # fsubs f10, f10, f13  ->  fdivs f10, f10, f13
- [ be32, 0x5e44c4, 0xed4a4a78 ]  # fdivs f10, f10, f13  ->  fmsubs f10, f10, f9, f9

### fn 0x5e46b0 (3 words)
- [ be32, 0x5e476c, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e47c8, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e47cc, 0xedad5af8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f11, f11

### fn 0x5e48ac (9 words)
- [ be32, 0x5e4984, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e49e0, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e49fc, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e4a1c, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e4a20, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e4a40, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e4a44, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e4a64, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e4a68, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e4bc8 (9 words)
- [ be32, 0x5e4c98, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e4cf4, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e4d10, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e4d30, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e4d34, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e4d54, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e4d58, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e4d78, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e4d7c, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e4ee0 (9 words)
- [ be32, 0x5e4fb0, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e500c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e5028, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e5048, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e504c, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e506c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e5070, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e5090, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e5094, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e51f8 (9 words)
- [ be32, 0x5e52c8, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e5324, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e5340, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e5360, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e5364, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e5384, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e5388, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e53a8, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e53ac, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e5510 (9 words)
- [ be32, 0x5e55e0, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e563c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e5658, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e5678, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e567c, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e569c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e56a0, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e56c0, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e56c4, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e5828 (9 words)
- [ be32, 0x5e58f0, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e5954, 0xedad0024 ]  # fsubs f13, f13, f0  ->  fdivs f13, f13, f0
- [ be32, 0x5e5968, 0xedad52b8 ]  # fdivs f13, f13, f0  ->  fmsubs f13, f13, f10, f10
- [ be32, 0x5e5990, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e5994, 0xedad52b8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f10, f10
- [ be32, 0x5e59c0, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e59c4, 0xedad52b8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f10, f10
- [ be32, 0x5e59f0, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e59f4, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10

### fn 0x5e5b7c (9 words)
- [ be32, 0x5e5c54, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e5cb0, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e5ccc, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e5cec, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e5cf0, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e5d10, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e5d14, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e5d34, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e5d38, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e61f8 (9 words)
- [ be32, 0x5e62d0, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e632c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e6348, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e6368, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e636c, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e638c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e6390, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e63b0, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e63b4, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e6580 (3 words)
- [ be32, 0x5e6664, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e66e0, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e66e4, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e6888 (9 words)
- [ be32, 0x5e6960, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e69bc, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e69e0, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e6a00, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e6a04, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e6a24, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e6a28, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e6a48, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e6a4c, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e6c60 (9 words)
- [ be32, 0x5e6d30, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e6d8c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e6da8, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e6dc8, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e6dcc, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e6dec, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e6df0, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e6e10, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e6e14, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e6f78 (9 words)
- [ be32, 0x5e7050, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e70ac, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e70c8, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e70e8, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e70ec, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e710c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e7110, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e7130, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e7134, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e72a0 (9 words)
- [ be32, 0x5e7378, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e73d4, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e73f8, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e7418, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e741c, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e743c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e7440, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e7460, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e7464, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e7678 (9 words)
- [ be32, 0x5e7740, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e77b0, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e77b4, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e77e4, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e77e8, 0xedad5af8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f11, f11
- [ be32, 0x5e7818, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e781c, 0xedad5af8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f11, f11
- [ be32, 0x5e784c, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e7850, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e79c8 (9 words)
- [ be32, 0x5e7a90, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e7af4, 0xedad0024 ]  # fsubs f13, f13, f0  ->  fdivs f13, f13, f0
- [ be32, 0x5e7b08, 0xedad5af8 ]  # fdivs f13, f13, f0  ->  fmsubs f13, f13, f11, f11
- [ be32, 0x5e7b30, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e7b34, 0xedad5af8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f11, f11
- [ be32, 0x5e7b60, 0xedad6024 ]  # fsubs f13, f13, f12  ->  fdivs f13, f13, f12
- [ be32, 0x5e7b64, 0xedad5af8 ]  # fdivs f13, f13, f12  ->  fmsubs f13, f13, f11, f11
- [ be32, 0x5e7b90, 0xec006824 ]  # fsubs f0, f0, f13  ->  fdivs f0, f0, f13
- [ be32, 0x5e7b94, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e7d1c (9 words)
- [ be32, 0x5e7dec, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e7e48, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e7e5c, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e7e7c, 0xec1d6824 ]  # fsubs f0, f29, f13  ->  fdivs f0, f29, f13
- [ be32, 0x5e7e80, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e7ea0, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e7ea4, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e7ec4, 0xec1d6824 ]  # fsubs f0, f29, f13  ->  fdivs f0, f29, f13
- [ be32, 0x5e7ec8, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e8b5c (9 words)
- [ be32, 0x5e8c2c, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e8c88, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e8ca4, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e8cc4, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e8cc8, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e8ce8, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e8cec, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e8d0c, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e8d10, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e953c (9 words)
- [ be32, 0x5e960c, 0xc162599c ]  # nop  ->  lfs f11, 0x599c(r2)
- [ be32, 0x5e9668, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e9688, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e96a8, 0xec1d6824 ]  # fsubs f0, f29, f13  ->  fdivs f0, f29, f13
- [ be32, 0x5e96ac, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e96cc, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e96d0, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11
- [ be32, 0x5e96f0, 0xec1d6824 ]  # fsubs f0, f29, f13  ->  fdivs f0, f29, f13
- [ be32, 0x5e96f4, 0xec005af8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f11, f11

### fn 0x5e9a70 (9 words)
- [ be32, 0x5e9b40, 0xc142599c ]  # nop  ->  lfs f10, 0x599c(r2)
- [ be32, 0x5e9b9c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e9bb8, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e9bd8, 0xec0b6824 ]  # fsubs f0, f11, f13  ->  fdivs f0, f11, f13
- [ be32, 0x5e9bdc, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e9bfc, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5e9c00, 0xec0052b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f10, f10
- [ be32, 0x5e9c20, 0xed6b6824 ]  # fsubs f11, f11, f13  ->  fdivs f11, f11, f13
- [ be32, 0x5e9c24, 0xed6b52b8 ]  # fdivs f11, f11, f13  ->  fmsubs f11, f11, f10, f10

### fn 0x5e9f68 (9 words)
- [ be32, 0x5ea100, 0xc0e2599c ]  # nop  ->  lfs f7, 0x599c(r2)
- [ be32, 0x5ea14c, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5ea174, 0xec0039f8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5ea194, 0xec096824 ]  # fsubs f0, f9, f13  ->  fdivs f0, f9, f13
- [ be32, 0x5ea198, 0xec0039f8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5ea1b8, 0xec1e6824 ]  # fsubs f0, f30, f13  ->  fdivs f0, f30, f13
- [ be32, 0x5ea1bc, 0xec0039f8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5ea1dc, 0xed296824 ]  # fsubs f9, f9, f13  ->  fdivs f9, f9, f13
- [ be32, 0x5ea1e0, 0xed2939f8 ]  # fdivs f9, f9, f13  ->  fmsubs f9, f9, f7, f7

### fn 0x5ea548 (9 words)
- [ be32, 0x5ea66c, 0xc0c2599c ]  # nop  ->  lfs f6, 0x599c(r2)
- [ be32, 0x5ea6b0, 0xec194024 ]  # fsubs f0, f25, f8  ->  fdivs f0, f25, f8
- [ be32, 0x5ea6ec, 0xec0031b8 ]  # fdivs f0, f0, f8  ->  fmsubs f0, f0, f6, f6
- [ be32, 0x5ea748, 0xec096824 ]  # fsubs f0, f9, f13  ->  fdivs f0, f9, f13
- [ be32, 0x5ea74c, 0xec0031b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f6, f6
- [ be32, 0x5ea76c, 0xec196824 ]  # fsubs f0, f25, f13  ->  fdivs f0, f25, f13
- [ be32, 0x5ea770, 0xec0031b8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f6, f6
- [ be32, 0x5ea790, 0xed296824 ]  # fsubs f9, f9, f13  ->  fdivs f9, f9, f13
- [ be32, 0x5ea794, 0xed2931b8 ]  # fdivs f9, f9, f13  ->  fmsubs f9, f9, f6, f6

### fn 0x5eaba4 (9 words)
- [ be32, 0x5ead2c, 0xc0e2599c ]  # nop  ->  lfs f7, 0x599c(r2)
- [ be32, 0x5ead90, 0xec1c6824 ]  # fsubs f0, f28, f13  ->  fdivs f0, f28, f13
- [ be32, 0x5eadf0, 0xec0039f8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5eae10, 0xec0a6824 ]  # fsubs f0, f10, f13  ->  fdivs f0, f10, f13
- [ be32, 0x5eae14, 0xec0039f8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5eae34, 0xec1c6824 ]  # fsubs f0, f28, f13  ->  fdivs f0, f28, f13
- [ be32, 0x5eae38, 0xec0039f8 ]  # fdivs f0, f0, f13  ->  fmsubs f0, f0, f7, f7
- [ be32, 0x5eae58, 0xed4a6824 ]  # fsubs f10, f10, f13  ->  fdivs f10, f10, f13
- [ be32, 0x5eae5c, 0xed4a39f8 ]  # fdivs f10, f10, f13  ->  fmsubs f10, f10, f7, f7


---

# 附录 B：菜单文字/精灵烘焙器定位与补丁（2026-08-15 III，2 函数 20 词，编码全验证）

## 定位链（实机症状 → 根因）

- **症状**：35 函数补丁后底座居中正确，但**文字仍 2 倍宽**溢出底座。
- **根因**：文字/精灵走**另一烘焙族**——`0x1a1244`（单精灵）与 `0x1a1a54`（批量精灵 bdnz 环），用**第二处 K=0.5 常量复本** `lfs fX, −0x2fc(r2)`（r2=TOC2 → **0xac18a4 = 0.5**，与 TOC1 的 0xad7058 不同址）。全二进制 174 个 TOC 可达 0.5 字中，用于 `(px−A)/A` 烘焙的只此 2 个用户。
- **结构实证**：`0x19exxx` 布局代码（含 0x19ea40/0x1a03a4 调用点）逐条写出 **0x20 步长精灵记录** `{x@0, y@4, w@8, h@0xc, u0@0x10, v0@0x14, u1@0x18, v1@0x1c}`（stfsx/stfs，计数在 obj+0x130），再经虚函数封装 `0x1a208c`（vtable+0x1c）派发绘制；`0x1a1a54` 逐记录消费**完全同构**的记录并烘焙，另带图集 UV（按贴图 w/h 归一）。`0x1a1244` 单记录版同构。
- **公式**：与已打族相同 `ndc_x = (px−A)/A`，`A = W×K`（f31）、`B = H×K`（f30）、K=0.5。
- **锚点吻合**：菜单文字 quad s16 x=−16724 = ((313.4−640)/640)×32767；`0x6452d0` = 引擎**顶点格式转换器**（s16↔f32，±32767 钳制对 @TOC1+0x6774/0x6778——handoff 旧记"32767.0 零命中"有误，实存在于 0xad7e30），f32 烘焙 → ×32767 → s16 的链路解释该 s16 观测值。
- **排除**：0xac1868（0.5）的 4 个用户（0x19ea58/0x19ec40/0x1a03bc/0x1a05a0）= 布局偏移 fmadds（×0.5 滚动/修正量），非烘焙；0xad7174 用户群 = 缓动/曲线 helper；0x6452d0 = 格式转换非烘焙。

## 可达性说明（candid）

两函数无静态 bl/b 调用者、无数据段 OPD——经对象 vtable（bctrl）动态派发，静态不可达性不可判。但结构证据强（记录格式/图集 UV/批量环/同一 K 公式），且与未打补丁的拉伸症状精确吻合。若实机文字仍不动，则文字不走这两个函数，下一轮按"0x822 族 s16 顶点缓冲写者"重查。

## patch.yml 条目（2 函数 20 词；y 角点一律不碰）

### fn 0x1a1244（单精灵写出器，4 个 x 角点；种子偷冗余 clrldi——r29 已在调用后 li 为 0，该指令语义为空）

```yaml
- [ be32, 0x1a13e4, 0xc122fd04 ]  # clrldi r29, r29, 0x38  ->  lfs f9, -0x2fc(r2)   # f9 = 0.5（r2=TOC2，调用后已恢复）
- [ be32, 0x1a13d4, 0xedadf824 ]  # fsubs f13, f13, f31    ->  fdivs f13, f13, f31   # px/A
- [ be32, 0x1a13f4, 0xedad4a78 ]  # fdivs f13, f13, f31    ->  fmsubs f13, f13, f9, f9  # *0.5 - 0.5
- [ be32, 0x1a141c, 0xedadf824 ]  # fsubs f13, f13, f31    ->  fdivs f13, f13, f31
- [ be32, 0x1a1420, 0xedad4a78 ]  # fdivs f13, f13, f31    ->  fmsubs f13, f13, f9, f9
- [ be32, 0x1a1440, 0xedadf824 ]  # fsubs f13, f13, f31    ->  fdivs f13, f13, f31
- [ be32, 0x1a1444, 0xedad4a78 ]  # fdivs f13, f13, f31    ->  fmsubs f13, f13, f9, f9
- [ be32, 0x1a1474, 0xedadf824 ]  # fsubs f13, f13, f31    ->  fdivs f13, f13, f31
- [ be32, 0x1a1478, 0xedad4a78 ]  # fdivs f13, f13, f31    ->  fmsubs f13, f13, f9, f9
```

生命周期：f9 自 0x1a13e4 起至末角点 0x1a1478 无调用、原码不用 f9（f0/f10-f13/f24-f31 占用其余）；r29 保持 0 供 0x1a14c8 使用。

### fn 0x1a1a54（批量精灵 bdnz 环，每轮 4 个 x 角点；种子 3 词含 r6 补偿）

```yaml
- [ be32, 0x1a1b88, 0xc0a2fd04 ]  # clrldi r6, r9, 0x20   ->  lfs f5, -0x2fc(r2)   # f5 = 0.5（种子）
- [ be32, 0x1a1b90, 0x8009015c ]  # lwz r0, 0x15c(r6)     ->  lwz r0, 0x15c(r9)    # r6 不再被设置，改用 r9（同值，lwz 零扩展）
- [ be32, 0x1a1cec, 0x807b0000 ]  # mr r3, r6             ->  lwz r3, 0(r27)       # r6 后续实参补偿：重读 *r27（原 r6 来源）
- [ be32, 0x1a1bc4, 0xedadf824 ]  # fsubs f13, f13, f31   ->  fdivs f13, f13, f31
- [ be32, 0x1a1bf4, 0xedad2978 ]  # fdivs f13, f13, f31   ->  fmsubs f13, f13, f5, f5
- [ be32, 0x1a1c44, 0xedadf824 ]  # fsubs f13, f13, f31   ->  fdivs f13, f13, f31
- [ be32, 0x1a1c48, 0xedad2978 ]  # fdivs f13, f13, f31   ->  fmsubs f13, f13, f5, f5
- [ be32, 0x1a1c70, 0xedadf824 ]  # fsubs f13, f13, f31   ->  fdivs f13, f13, f31
- [ be32, 0x1a1c74, 0xedad2978 ]  # fdivs f13, f13, f31   ->  fmsubs f13, f13, f5, f5
- [ be32, 0x1a1c9c, 0xedadf824 ]  # fsubs f13, f13, f31   ->  fdivs f13, f13, f31
- [ be32, 0x1a1ca0, 0xedad2978 ]  # fdivs f13, f13, f31   ->  fmsubs f13, f13, f5, f5
```

生命周期：f5 在循环前种子，循环体**无调用**直通 bdnz（逐轮有效），循环体未用 f5（f0/f7-f13 占用）；r6 的全部后续读取（0x1a1b90 上下文基址、0x1a1cec 调用实参）已分别补偿为 r9 / 重读 *r27（r27=-0x300(r2) 全局，全程有效）；count==0 的 ble 路径同样成立（r6 无需置位）。

## 编码验证（零失误）

20 词全部 capstone 双向核验：原址原词与预期指令逐字相符（fsubs/fdivs/clrldi/lwz/mr），新词反汇编与目标一致（fdivs XO=18、fmsubs XO=28 frC bits10-6、lfs opcode 48、lwz opcode 32）。脚本 %TEMP%\uw_text_encode.py。

## 预期实机效果

菜单文字/单位标签（"セーブ"、"イシップに入る"、"アイシャ・ブランシェット UF-19E[RB]" 等精灵批量绘制）x 映射 [−1,1]→[−0.5,0.5]，与已居中的底座对位；y 不动。需与 35 函数补丁 + 0x5e5ea4 补丁同时启用并重启（JIT）。

---

# 附录 C：加速拖影（boost ghost）定位 — 已确证部分 + 二分协议（2026-08-15 IV）

## 实机现象回顾
全量补丁后按加速出现"四重影/黑影拖尾"；**摘除前 16 个函数补丁后最黑部分消失** → 黑影源在这 16 个函数内。四胞胎滚动列表（0x5e39f8/0x5e3c94/0x5e3edc/0x5e4124）已单独排除。

## 已确证（离线证据）

### C1. 16 个函数 = 同一张 2D 图元 vtable 的槽位（决定性结构）
vtable 基址 **0xaad380**（TOC1=0xad16bc，60+ 槽）。被摘 16 个的槽位与语义（按函数结构归纳）：

| 槽 | 函数 | 结构类型 |
|---|---|---|
| 13 | 0x5e2568 | 2 顶点线写出器 |
| 16 | 0x5e2934 | 3 顶点三角 |
| 17 | 0x5e2c34 | 3 顶点三角变体 |
| 18 | 0x5e2e9c | 4 角 quad（x,y,w,h 形参） |
| 19 | 0x5e31d0 | 4 角 quad（成对角点） |
| 22 | 0x5e3470 | 4 角 quad（A 寄存器混合） |
| 23 | 0x5e36f8 | **5 x 角点扇形（~7 顶点）** |
| 30 | 0x5e436c | 2 x 角点 |
| 32 | 0x5e46b0 | 1 x 角点 |
| 33 | 0x5e48ac | **4 角 quad+UV** |
| 34 | 0x5e4bc8 | 4 角 quad+UV |
| 36 | 0x5e4ee0 | 4 角 quad+UV |
| 38 | 0x5e51f8 | 4 角 quad+UV |
| 40 | 0x5e5510 | 4 角 quad+UV |
| 42 | 0x5e5828 | 4 角 quad+UV |
| 43 | 0x5e5b7c | 4 角 quad+UV |

邻接槽：45 = **0x5e5ea4**（已部署补丁的九宫格/纹理 quad，用户疑点之一）。

### C2. 加速抓包（uw_boost.pkl）关键事实
- **主显示面纹理 0x027b0000（1280×720）被 21 次采样**：3 组 × 7 连续绘制，着色器 0x4f3d181 / 0x2007b01 / 0x4aabf81 各 7 次（seq 3382-3388 / 3709-3715 / 3716-3722）——**3 pass × 7 tap 运动模糊链**（加速残影的机制级实锤）。
- 这 21 个绘制全部 fmt 0x822（slot0 零 + slot12 共享浮点表），**位置 CPU 烘焙进共享表 0x81eb1e04**（全 0x822 族 2721 次绘制共用）。
- UI 图集纹理 0x6320200（1280×720，1400 次采样 = 全部 UI 合成）；tex 0x066c4200 为真实图像内容（117 次）。
- **顶点暂存缓冲在抓包快照中全部为零页**（GPU 缓存区未 dump）→ 各候选绘制（含 7-tap 模糊 tap quad）的**顶点位置离线不可读**。

### C3. 无法离线确定的部分（诚实声明）
- **不能把 7-tap 模糊 tap quad 钉到具体写出函数**：① 共享位置表 0x81eb1e04 是运行时分配地址（EBOOT 无静态引用）；② vtable 槽派发全动态（bctrl）；③ VP 着色器本地地址（0x7980/0x6781 等）为运行时分配，EBOOT 无字面值。
- 因此**无法给出"摘哪 1-3 个函数"的确定清单**——以下是按机制假设排序的二分协议。

## 机制假设与二分协议

**最可能机制**：运动模糊 pass 的 7 个全屏 tap quad 由某个 quad 写出函数烘焙（(px−A)/A）；居中补丁把 tap quad 压到中央 → 模糊只糊中央带 = "黑影/四重影"。摘除该写出器的补丁即恢复全屏模糊、且不影响 UI（UI 由其它槽绘制）。

**二分顺序（每轮实机验证"最黑部分"是否消失）**：

- **第 1 轮（首选，全屏合成 quad 候选）**：摘除槽 33-43 的 7 个 quad+UV 变体
  `0x5e48ac / 0x5e4bc8 / 0x5e4ee0 / 0x5e51f8 / 0x5e5510 / 0x5e5828 / 0x5e5b7c`
  补丁词表见附录 A 各对应 fn 块（整块删除即可，块间无共享词）。
- **第 2 轮（若 1 轮无效）**：追加摘除 `0x5e5ea4`（槽 45，附录 A 起始的 11 词块）与 `0x5e36f8`（槽 23，扇形）。
- **第 3 轮（若仍无效）**：黑影在槽 13-32（线/三角/成对）：`0x5e2568 / 0x5e2934 / 0x5e2c34 / 0x5e2e9c / 0x5e31d0 / 0x5e3470 / 0x5e436c / 0x5e46b0`。
- 命中后对半收窄到单个函数。**UI 功能核对**：摘除后检查对话框/菜单/座舱元素是否仍然居中——若某 UI 元素回到拉伸，说明该函数身兼 UI 与特效，需换"只修特效"思路（见下）。

**若目标函数身兼 UI**：则不能用摘除法，改为给该函数补丁加**条件**——这超出静态 PPU 补丁能力，需要 build2 模拟器侧按"任务态/特效态"门控（参考路线 C 的 env 门控先例）。

## 附：抓包侧下次快速定案法（可选）
在 build2 加一行日志：绘制时若 tex==0x027b0000 且为 0x822 族，记录**本次 slot12 表写入前的 CPU 返回地址**（写表代码的 PC）。该 PC 所在函数即 tap quad 烘焙器，与 vtable 槽对照即得目标函数。只需一次加速复现。

---

# 附录 D：运动模糊链写出者最终判定（2026-08-15 V）— 模糊不在已打补丁的函数里

## 判定（抓包逐槽位实证）

对加速抓包中 3 个模糊 pass（shader `0x4f3d181` / `0x2007b01` / `0x4aabf81`，各 7 tap）逐绘制读取全部 16 个顶点槽：

| pass | shader | 顶点槽格式 | 位置源 |
|---|---|---|---|
| 1 | 0x4f3d181 | slot0=0x822（零）, slot8=0x822, slot12=0x2823 | **slot12 共享浮点表 @0x81eb1e04** |
| 2 | 0x2007b01 | slot0=0x822（零）, slot3=0x1042, slot8=0x822, slot12=0x2823 | 同上 |
| 3 | 0x4aabf81 | slot0=0x822（零）, slot8=0x822, slot9=0x822, slot12=0x2823 | 同上 |

**三个 pass 全部走 0x822 合成/dummy-quad 路径**（slot0 全零 + slot12 共享浮点表），而**不是**已打补丁的 36 个写出函数（0x5e5ea4 + 35 族——那些产出 0x1032/0x1432 的 2×f32 真实顶点、slot0 非零）。

## 由此得出的关键结论

1. **运动模糊 tap quad 不被居中补丁压缩**——它们的位置由"合成/dummy 生成器 + slot12 表"烘焙，**该烘焙代码不在 36 个已打函数之内**（那些函数写 0x1032 格式，不出现在模糊链里）。
2. 被摘除的 7 个 quad+UV 变体（0x5e48ac…0x5e5b7c）所除掉的"最黑拖影"，是**另一组全屏 f32 quad（0x1032 系，已打函数产出）**——与 0x822 模糊 tap 是**不同的绘制元素**。
3. **"压区 vs 未压区"的屏幕分割线，不是"还有别的模糊写出函数被压着"**——而是：全屏模糊 tap（0x822，未打补丁、保持全屏）与已居中的 UI/内容之间的**边界**。模糊链本身没有被压，**没有更多模糊写出函数可摘**。
4. 因此：**不要再摘函数**。摘更多 0x5exxxx 只会像前 7 个一样把 UI 元素一并带走（该 vtable 是通用 2D 类，UI 与特效共用槽位）。

## 着色器→函数反查的结论（诚实）

三个模糊着色器（`0x4f3d181`/`0x2007b01`/`0x4aabf81`）**无法静态映射到写出函数**：① 它们是 0x822 dummy-quad 系统的材质状态，VP 本地地址（低 24 位 0xf3d181/0x7b01/0xabf81）为**运行时分配**，EBOOT 无字面值；② dummy 发射器 `0x9b1d8`（含 0x9b420/0x9b7f8 两处 ori 0x822 格式命令）只做 FIFO 发射，位置来自对象字段+共享表，烘焙在其上游布局代码；③ 写 slot12 表（@0x81eb1e04）的代码地址同为运行时分配，EBOOT 无静态引用。

## 分割线的处理选项（按优先级）

- **选项 A（推荐先试）**：**恢复被摘的 7 个 quad+UV 变体补丁**（它们同时画 UI）。分割线若由"UI 底座被一并摘除"造成，恢复即消失；模糊 tap 本就不受补丁影响，黑影是否回来可实测区分"黑影=变体所画的全屏 quad"vs"黑影=模糊"。
- **选项 B**：若确认黑影=变体所画全屏特效 quad、且这些变体也画 UI，则**不能摘除**，需按宽度豁免（见下）。
- **选项 C**：若要连模糊 tap 也居中（消缝），目标是 **0x822 dummy 位置烘焙器**（合成布局代码 + slot12 写者），需用附录 C 末尾的 build2 日志法（tex==0x027b0000 的 0x822 绘制时记录写表 CPU PC）一次实测定案。

## 宽度豁免样板（选项 B 的 PPC 改法，诚实标注限制）

目标：quad 宽约等于全屏（≈1280 设计 px）时保持 `(px−A)/A` 原式，小 quad 才 ×0.5−0.5。

**结论先行：内联做不到干净豁免**。每个 x 角点在已打补丁下只剩 2 条指令位（fdivs + fmsubs），`fsel` 选值需要"原始值/折半值/门控"三个寄存器（3 条指令），**没有第三条指令位**；跨角点共享的门控需要一次比较+分支跳过角点块，而角点是内联代码、无 code cave 可跳（本游戏 JIT 下 code cave 已证伪，见 handoff 2026-08-10）。

可行的最接近形式（以 `0x5e8b5c` 为例，x,y,w,h 形参版，w 在 f28）：把**每函数一次**的种子改成按 w 门控的两条，仍保每角点 2 词：

```ppc
# 原种子: lfs f10, 0x599c(r2)          # f10 = 0.5
# 改为（示意，需要 2 个额外指令位，但该处无空位——故只能整体换思路）:
lfs    f10, 0x599c(r2)                 # 0.5
# 门控不可内联 → 改为: 不用豁免, 直接把"全屏 quad 专用写出器"与其它 UI 写出器分开打补丁
```

**工程上正确的做法**（取代内联豁免）：从抓包/实机区分"该函数画的是全屏特效 quad 还是 UI quad"——若某函数**只画全屏特效**则整个不补丁（摘除）；若**混画**，则只能：① 接受分割/黑影，② 用 build2 模拟器侧按绘制宽度做运行时门控（读当次 quad 宽，≈1280 则跳过居中，可挂在已建的 RPCS3_UW_HUD 钩子链上），而非 PPU 静态补丁。
