# UW_PACK_RE.md — Macross 30 (BLJS10184) pack 格式逆向与表面描述体原位补丁可行性

调查对象：`rpcs3-src/build/bin/dev_hdd0/game/BLJS10184_INSTALL/USRDIR/data/pack/`
工具：`uw_pack_re.py`（同目录，可重跑）。引擎：Artdink AXL（EBOOT 字符串 `f:/M30AG/program/axl/src/ark/axl_ark_renderer_arkbin.cpp`、`GArk:Layout`）。

## 0. 结论速览（三问直答）

**a. 描述体在不在 pack 里？——在。**
渲染层表面描述体记录 = `.ark` 资源里的 `ARK LAYO` 块。活内存见到的名字
（pose_ob_dialogue / enemy_guage_ace / cap_obj / caption1 / black_back / sankaku_b /
stay_dialogue_flame_s2 / LAYOUT0 / rsrt_ob_dialogue2 …）逐一对应 LAYO 块名。
dims(1280×720) 以 **LE u32 对**存于 **LAYO 块 +0x44/+0x48**
（例：`data/menu/dialog/dialog.ark` 解压后 +0x1b84/+0x1b88 = `00 05 00 00` / `d0 02 00 00`；
元素级记录再各带一份 {w,h,half_w,half_h}）。
**pitch 不以任何形式存储**——运行时按 `w × 4`(RGBA8) 计算（活内存 pitch=0x1400=1280×4，
谎报后的显示面 0x2800=2560×4，均吻合；LAYO 内及全文件无 0x1400 明文）。
.ark 文件整体经 zlib(level 9) 或 "segs" 分段 deflate 压缩存于 pack，这正是当初按
BE 明文 `00 00 05 00 00 00 02 D0` 全扫零命中的原因（压缩 + LE 存储双重掩盖）。

**b. 原位补丁同字节长度可行吗？——可行，已实测。**
`0x500→0xA00`、`0x280→0x500`(半宽) 均为 4 字节等长替换。压缩回写实测：
- zlib ark：Python `zlib.compress(dec,9)` 对原始文件**字节级一致**（游戏压缩器=zlib level 9）；
  dialog.ark 改 6 点后重压 0xd8f vs 原 stored 0xd8e（+1 字节），仍在 0x800 对齐槽(0x1000)内，
  只需同步改记录里的 stored 字段（记录表长度不变，无任何偏移级联）。
- segs ark：hud.ark 改 107 点，重建 0x6478 < 原 0x64a0；talk_window01.ark 改 23 点，
  0x7647 < 原 0x7680。直接小于原 stored，零副作用。

补丁点数量级：
- **LAYO 头 {w,h} = 1280×720：812 处**，分布在 **333 个 .ark**（data.dat 626、data2.dat 186；init/lua 0）。
- 元素级 canvas 重复 {w,h,半宽,半高}：**305 处**（另有配套的 {0x280,0x168} 半尺寸要一起改）。
- TXOS 纹理尺寸引用：8 处（**不要动**，那是 1280×720 纹理的像素尺寸）。
- 合计 LE32pair 命中 1125 = 812+305+8，与全扫一致。
- 另有 **137 张 1280×720 DDS 纹理**（segs 解出后 DDS 头 {h=720,w=1280}）——画面内容仍是 1280 宽，
  清晰化需重生成纹理，属另一件事。

**c. pack.idx 的 16 字节哈希——几乎可判定不是运行时校验。**
对 lua/init/fileset0（小文件）测试：整文件、头、记录表、名字池、各表区组合的
MD5 / SHA1[:16] **全部不匹配**；游戏 EBOOT 无 md5 字样、无逐文件小哈希表。
该值与文件内容无可计算关系 → 倾向是打包工具的**构建 GUID**。
游戏确实会按路径打开 `data/pack/pack.idx`（EBOOT 有字符串，作全局文件索引用），
但没有证据表明会校验这 16 字节。**风险低**；残余不确定性用一次实机启动即可排除
（补丁法不改任何记录/偏移，pack.idx 本身无需变动）。

## 1. PIDX 容器格式

所有 `.dat` 与 `pack.idx` 同构。魔数 `"PIDX0\0\0\0"`(8B) 后 8 个 **LE u32**：

| 字段 | 含义 |
|---|---|
| ver | .dat=1，pack.idx=9（=pack 数） |
| hsz | 头+pack条目尺寸：.dat=0x50，pack.idx=0x150 |
| nrec | 记录数 |
| f3 | 未见变化（2/1/0），疑为版本/标志 |
| recs_end | = hsz + nrec×0x18（严格成立） |
| gap_size | recs_end 到 data_start 之间的"流式 chunk 表"字节数 |
| data_start | 名字池起点 |
| pool_size | 名字池字节数 |

**记录（0x18 定长，LE）**：
- 目录 `{flag=1, name_off, n_children, first_child_idx, 0, 0}`（孩子 = 记录按下标连续区间）
- 文件 `{flag=0, name_off, f2, abs_offset, dec_size, stored_size}`
  - .dat 内 f2=0；pack.idx 内 f2 = 该文件所属 pack 路径在 idx 名字池中的偏移（即 pack 标识）
  - `stored_size==0` 或 `==dec_size` → 原始存储；否则压缩（看魔数分流，见 §2）
  - `abs_offset` 为 .dat 内绝对偏移，文件体按 **0x800 对齐**
- 树可为多根；个别文件记录不在树中（孤儿，如 data.dat 的 `m30ag_config.tbl`）

**名字池**：`data_start` 起，NUL 结尾字符串，首串为自身路径（如 `data/pack/data.dat`），
记录中的 name_off 相对池首。名字不带路径，路径由目录树拼出（如 `/data/menu/dialog/dialog.ark`）。

**gap 流式 chunk 表**（recs_end 起 gap_size 字节）：
`[u32 count][u32 off[count]]` 后接 count 条 0x14 字节记录（指向大文件内部的分段，
用于电影/流式资源）。`fileset0/1/2.dat` **没有树记录**（nrec=0），全部内容 = chunk 表 +
名字池（`gfp_po_rio` 等）+ 原始流数据；raw 全扫确认无描述体名字、无 dims 对，与 UI 无关。

各包概况：

| 文件 | nrec | 文件数 | 备注 |
|---|---|---|---|
| data.dat | 5485 | 5354 | 菜单/事件 UI、电影 gfp；描述体主战场(626 点) |
| data2.dat | 13685 | 13615 | cockpit/hud 战斗 UI(186 点)、模型/贴图 |
| fileset0/1/2 | 0 | 0 | 流式 chunk，无树，无描述体 |
| init.dat | 5 | 3 | 无命中 |
| lua.dat | 361 | 304 | lua 脚本，无 dims/名字命中 |
| shaders.dat | 26357 | 26355 | .cgb shader（部分 zlib），无命中 |
| sound.dat | 14337 | 14275 | 音频，无命中 |
| pack.idx | 60222 | 59906 | 全局合并索引：两棵树("data"+"bin")，60222 = 各包记录总和−8 个重复根 |

**pack.idx 头部 9 条 pack 条目**（0x40 起）：前 8 条各 0x20 字节
`{16 字节 GUID, u32 名字池偏移(指向该 pack 路径串尾), 0,0,0}`，第 9 条（sound.dat）只有 16 字节 GUID，
记录表紧接着从 0x150 开始。

## 2. 文件存储压缩

按 stored 区头几字节分流：

- **raw**：stored==0 或 ==dec（电影 .gfp、音频等）。
- **zlib**：`78 da` 头，单流，**level 9**（实测重压字节级复现）。多数 .ark/.tbl 走这条。
- **segs**：`"segs"` 容器，用于 .dds 贴图与大的 .ark（hud.ark、talk_window01.ark、hud_menu00.ark）：
  - 头：`"segs"` + u16be ver(=5) + u16be nseg + u32be 解压总长 + u32be 压缩总长
  - 段表 nseg×8：`{u16be comp_len, u16be dec_len(0 表示 0x10000), u16be 0, u16be src_off+1}`
  - 载荷从 `0x10+nseg*8` 按 0x10 对齐开始；每段 **raw deflate（wbits=-15, level 9）**，段间零填充
  - 解压拼接 = 原文件（dds 首字节即 `DDS `，已验证 w/h/fourcc 正确）

## 3. .ark 内部：ARK ARKF 容器

.ark 解压后为 `"ARK ARKF"` 容器，由块序列组成。块头 = 8 字节类型串 + u32le 块长 + u32le 0。
EBOOT 内块类型表 `"ARK ARKFTEXSTEX2TXOSLAYOLAY2"`；实际见到：

- `ARK TEXS`：贴图名表（u32le 个数 + u32le 名长0x20 + 名字）
- `ARK TXOS`：纹理对象记录（含纹理像素尺寸引用，1280×720 纹理有 8 处 {0x500,0x2D0}，勿动）
- `ARK LAYO`：**布局/表面描述块**（LAY2 未使用）

**LAYO 布局**（以 pose_ob_dialogue 为例，偏移相对块首）：

```
+0x00  "ARK LAYO"
+0x08  u32le 块长(不含?含头,按块链跳转即可)
+0x0c  0
+0x10  名字[0x20]  纯 ASCII, NUL 填充 ("pose_ob_dialogue")
+0x30  u32le 0x3c  / +0x34 u32le 0x78      (常量)
+0x38  u32le 标志(0xffff 或小数) / +0x3c、+0x40 小整数
+0x44  u32le W  ← 表面宽 (1280)
+0x48  u32le H  ← 表面高 (720)
+0x4c  u32le 0x50 (常量 80) / +0x50 起为锚点/参数
+0x70  元素名[0x10]（4 字节组内反序,如 "EJBO00TC" = "OBJECT00"...）
元素记录内重复出现 {W, H, W/2, H/2}（如 +0x90/+0x94/+0x98/+0x9c =
  0x500, 0x2d0, 0x280, 0x168）
```

活内存描述体名 ↔ LAYO 名对照（文件存储 dims / 活内存观察）：

| 名字 | 所在 | 文件 dims | 活内存 |
|---|---|---|---|
| pose_ob_dialogue | data.dat dialog.ark +1b40 | 1280×720 | 1280×720 ✓ |
| cap_obj / caption1 | data2.dat hud.ark +31860/+33700 | 1280×720 | ✓ |
| black_back / rsrt_ob_dialogue2 | dialog.ark +6c50/+6db0 | 1280×720 | ✓ |
| enemy_guage_ace | hud.ark +33950 | 200×64 | 1280×720 ✗ |
| sankaku_b | hud.ark +304a0 | 32×32 | 1280×720 ✗ |
| own_barrier_gauge | hud.ark +34bc0 | 140×140 | 1280×720 ✗ |
| stay_dialogue_flame_s2 | dialog.ark +7a00 | 450×124 | 1280×720 ✗ |
| LAYOUT0 | event_*/ope_i308 等 | 1280×720(多数) | ✓ |

读法：全屏层（"ob/window/caption" 类）LAYO dims=1280×720 与活内存一致；小部件层
（gauge/sankaku/cursor 类）文件里是小尺寸，活内存里挂在 1280×720 合成面上——小层应为
直接画进父面/共享面，不自建 RT。**补丁第一刀只改 812 个头部 1280×720 处是安全的；
小部件 LAYO 不要碰**。

## 4. 补丁操作指引（保持零级联）

1. `uw_pack_re.py layos` 生成清单 `uw_layo_sites.txt`（812 头部位 + 元素级位置）。
2. 对每个 ark：读出 stored → 解压（zlib 单流 / segs 分段）→
   `struct.pack_into('<I', blob, layo+0x44, 0xA00)`（需要时元素级同步改
   `+0x90:0xA00, +0x98:0x500`，半高 0x168 不动）→ 重压：
   - zlib：`zlib.compress(new, 9)`；若 ≤ 原 stored 原样写回；否则须 ≤ 0x800 对齐槽
     （slot = ceil(stored/0x800)×0x800），并把该文件记录的 stored 字段改为新长
     （记录表定长原地改，无偏移变化）。
   - segs：按 0x10000 切分逐段 raw-deflate(level 9)，重建段表（u16 偏移够用，
     现存最大 stored 0x7680 < 0x10000），总长 ≤ 原 stored 即可（实测更小）。
3. dec_size 不变、abs_offset 不变、树不变、pack.idx 不动。GUID 风险见 §0c。
4. **先备份**（本目录全部操作均未改动原 pack；正式打补丁前复制 data.dat/data2.dat）。

## 5. 产出文件

- `uw_pack_re.py` — 解析/提取/扫描/清单/哈希核对（`info|list|extract|scan|layos|hashcheck`）
- `uw_pack_scan.txt` — 全包名字/dims 模式扫描明细（1125 处 LE32pair 定位）
- `uw_layo_sites.txt` — 812 个 1280×720 LAYO 头补丁点清单（333 个 ark）
- `uw_layos.pkl` — 首轮（仅 zlib 类）LAYO 枚举缓存
- `_extract/` — 提取验证样本：dialog.ark(.dec)、dialog_text.dds(.dec)、talk_window01.ark

## 6. 补丁执行记录（2026-08-10，已落盘）

工具：`uw_pack_patch.py`（`--dry-run` / `--apply` / `--restore-from-bak`）。
备份：`pack/data.dat.bak`、`pack/data2.dat.bak`（打补丁前原样复制）。

**dry-run 核对**：头补丁点 812 ✓；元素级 canvas 305 处中 **266 处**带完整 {w,h,半宽,半高} 可改，
**39 处不匹配半尺寸、按严格规则跳过**（35 处 {x=0,y=0,1280,720} 型 rect 记录无半宽字段，
2 处在已 2560 的 LAYO 内，1 处疑为坐标，1 处尾随零）；跳过非 1280×720 小部件 LAYO 1676 个；
非 ARKF ark 0；槽位不足 0。

**apply**：data.dat 写 316 个 ark、data2.dat 写 17 个 ark（共 333）。
stored 尺寸变化：data.dat 变大 153 / 变小 54 / 等长 109；data2.dat 变大 5 / 变小 7 / 等长 5。
记录表仅 219 条记录的 stored 字段被更新（data.dat 207 + data2.dat 12），零偏移/零 pool 变化。

**roundtrip 严格验证（u32 粒度 diff vs .bak）**：
- 全部 333 个改动 ark 重新解压成功（dec 尺寸精确一致）；
- 差异只含：LAYO 头 0x500→0xA00 **812 处**、元素 w 0x500→0xA00 **266 处**、
  元素半宽 0x280→0x500 **266 处**；**非法改动 0**；
- 记录表/名字池/文件总长与 .bak 比对全部一致（除上述 219 个 stored 字段）。
- 重复执行幂等：二次 --apply 命中 0、写入 0。

**已知未动项**（如需进一步推进再议）：35 处 {0,0,1280,720} rect 型元素记录（无半宽字段，
疑为全幅背景/裁剪矩形）；137 张 1280×720 DDS 纹理（内容仍 1280 宽，需重生成）；8 处 TXOS 纹理尺寸。

回滚：`python uw_pack_patch.py --restore-from-bak`。

## 7. 排除 cockpit/hud 的重新补丁（2026-08-10，现役状态）

实机发现 cockpit/hud 的 LAYO 加宽会触发 `_L/_R` 分屏资源路径
（`hud_face_dummy_L.dds` / `hud_face_dammy_R.dds` / `face_dummy.dds`，ENOENT）
随后 SPU 几何核崩溃。这些名字**以字符串形式存在于**
`data2.dat:/data/cockpit/hud/hud.ark`（TEXS 表，+0x220 起）与
`hud_menu00.ark`（+0x240）**内部**，但**全部 9 个 pack + pack.idx 的树/名字池/原始字节中
均不存在同名文件**（解压内容搜索仅上述 2 处 TEXS 引用）——即分屏纹理是"有引用、无实体"
的未发布资源，cockpit/hud 必须保持 1280 原样。

操作：`--restore-from-bak` 还原（抽查 pose_ob_dialogue 回到 1280×720 ✓）→
`--apply --exclude cockpit --exclude /data/cockpit/hud/`（`--exclude` 可多次，
ark 路径含子串即整个跳过）。

**现役补丁点数**：
- LAYO 头 **645 处**（= 812 − 167 cockpit 相关）、元素级 **262 处**（= 266 − 4，减去的 4 处全在 hud.ark）。
- 写入 ark：data.dat 314 + data2.dat 3 = **317 个**；记录表 stored 字段更新 210 条（207+3）。
- 排除 ark（含补丁点）16 个：data.dat 的 `cockpit/movie_window/hud_moviewindow{,01}.ark`（各头 1）；
  data2.dat `cockpit/hud/` 14 个——`hud.ark`(头107+元素4)、`talk_window01.ark`(23)、
  `hud_menu00.ark`(14)、`race.ark`(7)、`course_select.ark`(2)、`hud_minimap_obj.ark`(2)、
  `hud_position.ark`(2)、`hud_wingman_order.ark`(2)、`front_attention.ark`、`hss_radar_circle.ark`、
  `hud_map_search.ark`、`hud_rescue.ark`、`inter_26.ark`、`item_icons.ark`（各 1）。
- 另有 12 个 cockpit 路径 ark 本无 1280×720 点，天然未动（排除总计 28 个 ark 与 .bak 逐字节一致）。

**roundtrip（排除版）**：排除 ark 与 .bak 逐字节一致 ✓；其余 ark 仅含
头 0x500→0xA00 ×645、元素 w ×262、半宽 0x280→0x500 ×262，非法改动 0；
记录表除 stored 字段外零差异；`ROUNDTRIP ALL OK`。

## 8. 触发源判定变体（2026-08-10 晚）

官方版弹 "Game data is corrupted"（cellGameContentErrorDialog type=100，前导
face_dummy/hud_face_dummy_L ENOENT）。为区分"整包完整性校验"vs"特定内容触发"，
新增 `--include`（只补丁路径含子串的 ark，可与 `--exclude` 叠加）与 `--file`
（显式目标，可在变体副本上打补丁）参数，生成两个单 ark 变体（均放 pack/ 内、不覆盖现役）：

| 变体 | 内容 | 补丁点 | 验证 |
|---|---|---|---|
| `pack/data.dat.dialogonly` | 原版 + 仅 `/data/menu/dialog/dialog.ark` | 头 6 + 元素 2 | ROUNDTRIP OK（其余 317 ark 与原版逐字节一致，记录仅 1 条 stored） |
| `pack/data.dat.tinyonly` | 原版 + 仅 `/data/loading/nowloading.ark` | 头 1 + 元素 1 | ROUNDTRIP OK（同上） |

tinyonly 选型说明：nowloading.ark（dec 0x1600）无 face/hud/dialog/dummy 任何引用
（TEXS 仅 nowloading_text.dds 实体纹理）；曾候选 cutin_p7_gam.ark 但 TEXS 含
cutin_face00.dds，按"face 无关"标准弃用。

当前现役状态：`data.dat` = 排除 cockpit 全补丁版（314 ark，md5 a5ad85d0…，与变体
实验前逐字节一致）、`data2.dat` = 原件（md5 == .bak）、两个变体待命实机 A/B。

## 9. dialog.ark 触发确认 + 雾效 LAYO 排查（2026-08-10 深夜）

A/B 判定：tinyonly 不炸、dialogonly 炸（corrupt ×2）→ dialog.ark 的 6 个 1280×720 LAYO
加宽是对话系统分屏路径触发源。**现役 data.dat 已重建为
`--exclude cockpit --exclude /data/menu/dialog/dialog.ark` 全补丁版**（data2.dat 保持原件）：
313 ark 写入、记录 206 条 stored-only、**头 618 + 元素 255**（较排除 cockpit 版 −6 头 −2 元素）、
非法改动 0、`ROUNDTRIP ALL OK`。

**dialog.ark 的 face 引用排查**：TEXS 纹理表只有 `stay_tx_dialogue.dds`、`dialog_text.dds`；
整个 ark 内 face/dummy/dammy 字符串**零命中**。→ face_dummy 探测**不是** dialog.ark
自身纹理引用所致，而是其 6 个 LAYO 加宽后对话渲染路径走进共享分屏代码，
间接牵出 hud 侧 `hud_face_dummy_L/dammy_R`（有引用无实体）→ ENOENT → 判损坏。

**雾效/深度渲染目标 LAYO 排查**（全 ark，LAYO 名 + 4 字节反序元素名双通道搜索
depthvs/depth/fog/zbuf/shadow/blur/effect/post/dof/bloom/ssao）：
- **1280×720 的雾效/深度类 LAYO 一个都不存在**；DepthVs/depth/zbuf/shadow/blur/bloom/ssao
  字样**全部零命中**。活内存里的 DepthVs/fog 描述体（0x305axxxx/0x309axxxx 家族）
  **不来自 pack 的 LAYO 资源**，属引擎代码路径创建（不在本补丁域内）。
- `effect` 命中 = `dev_effect`/`dev_effect0`（320×320 开发/结算特效面板，
  mechroom_develop、quest_clear_*、quest_reward_sub、race_reward、data2 race 等），
  均非 1280 层、未被补丁；ope_* 系列 LAYOUT(已 2560)内的 effect 字符串是普通元素名。
- `fog`/`dof` 命中均为更长名字里的巧合子串（mode_f_off、thrudheim、fader、
  option_menu 里的 fog 图标元素），与渲染目标无关。

**状态修订（同日后续）**：为配合 EBOOT 分类器补丁掐死 dialog.ark 触发的分屏路径的实机验证，
现役 data.dat 已回退为**仅排除 cockpit** 的全补丁版（dialog.ark 恢复打补丁）：
313→**314 ark**、头 **624**（+6）、元素 **257**（+2）、记录 207 条 stored-only、
非法改动 0、`ROUNDTRIP ALL OK`；md5 `a5ad85d05f1c49d4548adcf67694de0f`（与此前的
排除 cockpit 版逐字节一致）。data2.dat 保持原件（md5 == .bak）未动。
两个 A/B 变体（data.dat.dialogonly / data.dat.tinyonly）仍在 pack/ 内备用。

## 10. 纯重建判别变体（2026-08-11）

事实订正：**dialog.ark 与 nowloading.ark 都是 zlib(78da) 单流压缩，不是 segs**；
且对原始内容 `zlib.compress(dec,9)` 重压与原 stored **字节级一致**（两个 ark 均验证），
即我们的 zlib 重建对原内容是透明的、不可能产生"重建器 artifact"。
当前所有补丁/变体涉及的 ark **100% 是 zlib 类**（segs 类 ark 只有 hud.ark /
talk_window01.ark / hud_menu00.ark，均在 cockpit 排除域内；.dds 的 segs 从不改动）。

判别变体 `pack/data.dat.rebuildtest`（`uw_pack_rebuild.py` 生成）：
dialog.ark 内容零改动、仅以 **level 6** 重压写回（level 9 重压=原字节、无判别力，
故改用 level 6 使 stream 不同而 dec 逐字节一致——`78 9c` 合法 zlib 头）。
- stored 0xd8e → 0xe87（**+249 字节**），落在原 0x800 槽（0x1000）内
- 记录表仅 1 条 stored 字段更新；dec 回读与原逐字节一致（VERIFY OK）
- md5 `32e45ccf259f1201471cfe0fab786b7c`

实机判读：rebuildtest 弹 corrupt → 游戏对 stored stream 字节/编码级敏感（重写即失败）；
干净 → 坐实 corrupt 是 dialog.ark 加宽的宽度语义触发。现役 data.dat = 原件（未动）。

## 11. data2.dat 全补丁变体（cockpitin）

实机新事实：原始 data.dat 下 face_dummy 探测本来就有（108 次常态，corrupt=0）→
corrupt 由 dialog.ark 单独解释，hud.ark 未独立测过。生成 `pack/data2.dat.cockpitin`
（data2.dat 原件副本，**全补丁不排除任何路径**，含 cockpit/hud 全族）：
- 写入 ark **17 个**；LAYO 头 **186** + 元素 **9**（+半宽 9）；记录 12 条 stored-only；
  非法改动 0；`ROUNDTRIP ALL OK`
- 含全部 segs 类 ark：hud.ark（107头+4元素）、talk_window01.ark（23）、hud_menu00.ark（14）等
- 用途：实机测 cockpit/hud 2560 化是否独立触发 _L/_R 分屏 ENOENT→SPU 崩溃
- 现役 data.dat = 排除 cockpit+dialog 版（干净基线）、data2.dat = 原件，均未动

## 12. 元素位置结构与 HUD 居中变体（data2.dat.center640）

**元素 x 字段定位（EBOOT 解析器格式串 + L/C/R 差分双重证据）**：
- LAYO 头 = "32c2s8i3i"（name[0x20]@+0x10；2s@+0x30；8i@+0x34={0x78,flags,dur,nelt,w,h,
  elem_off=0x50,track_off}；3i@+0x54）。EBOOT 块分发器在 0x68b1a0（TXOS/TEXS/TEX2/LAYO/
  LAY2/ARKF/GENE 分派），LAYO 处理器 0x68b57c。
- 元素记录 = "i4c2i32c8i"（0x50：size,tag,2i,name[32],8i={w,h,hw,hh,color/flag,…}），
  **无位置字段**。
- 位置在轨迹段（@chunk+0x10+track_off）的关键帧块：每块以 u32 `0x00140034` 打头，
  +0x04 flags(=0x1f)，+0x08 帧号，**+0x14 = x，+0x18 = y（i32 LE，设计画布坐标）**，
  +0x1c RGBA 颜色，+0x28 次要 x 增量（lader L/C/R = -30/+30/+90，保留不动），
  +0x34/+0x38 = scale(100,100)。多关键帧 = 多 marker 块串联。
  证据：time_window 9 数字 x=1044..1166 递增（字距）；lader L/C/R 仅 +0x28 差分。
  **未见锚点标志位**——坐标就是设计画布坐标，无左/中/右锚枚举。

**center640 变体**：`pack/data2.dat.center640`（cockpitin 副本，`uw_pack_center640.py`，
dx 参数化默认 +640）——仅对 /data/cockpit/ 下 ark 中 **w=2560×720 的 LAYO** 的关键帧 x
一律 +640；小画布 LAYO（元素为局部坐标）不动。
- 13 个 ark 写入；**平移关键帧 4845 处，跳过 0**；roundtrip 全量 u32 diff：4845 处全部
  恰好 +640、零其它改动；stored 均在原 0x800 槽内
- 抽查：time_window 数字 1044..1166 → 1684..1806；lader 957 → 1597
- md5 `1d613044ac66dba039a70e4f53713dba`

**注意（实测含义）**：雷达偏右 ~62% ≈ 设计 x(957)+640 → 运行时很可能已自带
+(canvas−1280)/2 居中偏移；若实机证实如此，再 +640 会推到 ~87%，应改用
`uw_pack_center640.py <src> <dst> -640` 反向变体。

**现役实况核对（md5）**：`data.dat` == .bak（**原件**，并非此前所述"排除 cockpit+dialog"版）；
`data2.dat` == cockpitin（**全补丁版**，并非"原件"）。两个变体在 pack/ 内备用。

**状态修订（同日再后续）**：现役 data.dat 重建为**排除 cockpit + dialog.ark** 版
（先 cp .bak 还原再 apply；曾出现一次 dialog.ark 残留旧补丁被 roundtrip 拦下——
验证闸有效）。终态：**313 ark、头 618 + 元素 255、记录 206 条 stored-only、
非法改动 0、ROUNDTRIP ALL OK**，md5 `ad6884a83546390e46716ea27efeadb7`。
data2.dat 保持 cockpitin（md5 `21b780287a7a8232073692953fda3597`）未动。

## 13. x+640 推广（全量居中变体）

实机：cockpit 元素 x+640 后通用界面正确居中；loading 屏（VF-25）偏左 → 推广到所有被加宽
LAYO 的元素轨迹关键帧（小画布 LAYO 不动；只动 x，不动 y/w/h/半宽/color/scale/delta）。
`uw_pack_center640.py` 加第 4 参路径过滤（ALL=全部 ark）。

- `pack/data.dat.center640` = 现役 selective（排除 cockpit+dialog）+ 全部 ark 加宽 LAYO
  关键帧 x+640：**314 ark、20159 处、跳过 0**；roundtrip 全量 diff 恰为 +640、零其它，ALL OK。
  md5 `3a79c42968977654924b043a9a1ed80e`
- `pack/data2.dat.center640full` = cockpitin + 全部 ark（含 menu 系 control_guide/credit/
  csound）：**16 ark、5083 处、跳过 0**；ALL OK。md5 `8e93944768e2a5f0e24b57538f7d9f4f`

过程修正：① `event_sar.ark` 重压后超 0x800 槽 3 字节（lvl9=0x803）→ 引入 **zopfli 回退**
（0x7ae，合法 zlib 流）解决，已固化进 `uw_pack_center640.py`；② flags 高位 0x8000001f
（placename 系列 187 处）为合法关键帧，过滤放宽为 `flags&0x7FFFFFFF==0x1F` 后全部纳入；
credit.ark 2 处 y 越界（滚动文本容器）同样纳入（y 不做范围限制）。

**现役实况（md5）**：data.dat = selective 版（`ad6884a8…`）；data2.dat = **center640**
（`1d613044…`，即 cockpitin+cockpit 平移，已换入实测居中 ✓）。

## 14. center640 corrupt 溯源与重建（排除版）

实机：data.dat.center640 弹 corrupt ×2。**用户初始假设（dialog.ark 被平移触发）经字节级
证伪**：dialog.ark 在 selective 基底里宽度未补丁（LAYO 仍 1280），center 的 0xA00 过滤
本就自动跳过它——旧 center640 里 dialog.ark 与 .bak 逐字节一致（记录/原始/dec 三相皆同）。
真正差异 ark 集合对比：selective（干净）改 313 ark，center640（弹）改 314 ark，多出的
第 314 个 = **`mechroom_develop.ark`（含原生 2560×720 的 chart_devellop LAYO）**——
宽度补丁从不碰它，而 x 平移的 `w==0xA00` 过滤误伤了它的原生 2560 内容（元素被推到
画布外）。它是"selective 干净而 center640 弹"的唯一内容差异 → 头号嫌疑（逐资源校验
很可能覆盖它，如同 dialog.ark）。

重建 `pack/data.dat.center640`（selective 基底 + 全 ark 平移，**排除
/data/menu/dialog/dialog.ark 与 mechroom_develop.ark**；center 工具已加 --exclude）：
- **313 ark、平移 19804 处、跳过 0**；与 bak 全量 diff 分类：w 873 + 半宽 255 + x+640
  19804（含 679 处负 x、186 处原 x=640 落入 0x500 桶），**零其它改动**
- dialog.ark / mechroom_develop.ark 与 .bak **逐字节一致**（验证通过）
- md5 `18ff20ecfab08b99e05cb62134f8b364`（与旧 corrupt 版 3a79c429 不同）
- 若此版仍弹 corrupt → 触发源在 313 个共享 ark 的 x 平移内容本身，再行二分

CRC 调查进展（挂起）：EBOOT 0x653aa0 = slice-by-4 CRC32（init=~bswap(seed)、
结果 bswap(~acc)），12 个调用点集中于 0x650d7c-0x652454（结构化流读取器的滚动校验，
非逐资源比对）；dialog.ark/mechroom_develop.ark 的期望值存放点未找到（packs 原始/
解压、EBOOT 均无 crc32 针值命中）——覆盖清单与判定链路待继续。

## 15. quest_reward.ark 嫌疑（进任务后 corrupt）

实机：排除 dialog+mechroom 版 center640 boot 干净，但读存档进任务后 corrupt，
崩溃前最后动作 = 一次 data.dat 读取结束于 **0x4deaf094** —— 恰为
`/data/menu/quest_clear/quest_reward.ark` stored 区间 [0x4deae000, +0x1094) 的**末尾**。
即：游戏读完 quest_reward.ark 后判 corrupt → 该 ark 为头号嫌疑。

- quest_reward.ark：7 个 1280×720 LAYO（reward_window00/01/02/03、reward_icon、
  reward_icon_02/03），selective 宽度补丁 7 处 + center640 平移 **151 处**；未排除
- 紧邻的 quest_reward_sub.ark（quest_clear 子画面）：1 宽度 + 65 平移，同样未排除
- 覆盖校验嫌疑集现状：{dialog.ark(实证), quest_reward.ark(强嫌疑), mechroom_develop.ark(嫌疑)}
  —— 共同特征：**剧情/结算流程关键 UI**；系统/菜单 UI 不覆盖
- 注意：selective 的"干净"只到 boot 层；quest_clear 资源在任务结算时才加载，
  无法区分触发的是宽度改动还是平移改动 → 该 ark 应保持完全原件（宽度也不改）
- 下一步建议：变体排除整个 `/data/menu/quest_clear/`（宽度+平移双排除），
  若仍弹 → 继续按"任务流程加载的 ark"二分（cutin_*/event_*/skill_* 系列在任务播片路径上）

## 16. 排除 quest_clear 版 + CRC 调查进展

**A. 现役变体重建**（selective + 全 ark 平移，排除 dialog.ark / mechroom_develop.ark /
**/data/menu/quest_clear/ 整目录**）：
- 宽度 311 ark（610 头+255 元素）、平移 311 ark **19588 处**、跳过 0
- 排除项 dialog.ark / mechroom_develop.ark / quest_clear 目录 9 资源全部与 .bak 逐字节一致 ✓
- 全量 diff 分类：w 865 + 半宽 255 + x+640 19588，零其它（`other=0`）
- md5 `67fbc4bff37d4a9641d9a1136c53de8d`

**B. 完整性校验调查进展**：
- CRC 例程入口 **0x653aa0**（slice-by-4，init=~bswap(seed)、结果 bswap(~acc)），
  12 个直接调用点全在 **0x650040-0x652454 一个大读取器模块**内（vtable @0xab1820，
  字段名串 "R_SystemTextTypeAB_A/B"、"strText" 等）——它是**带滚动 CRC 的自校验
  结构化记录读取器**（如 0x651f60 cmpw 滚动值 vs 流内联值，不符 → 错误码 0x1b → 错误路径）。
  即：它校验的是"记录内嵌 CRC 的容器"，不是独立的逐文件 CRC 清单。
- 期望值存放处搜索：**dialog.ark 的 crc32/adler32（stored/dec × LE/BE × 取反/字节序变体）
  在 packs 原始字节、全部解压内容、EBOOT 三处均无命中** → 不是标准 CRC32 的静态表。
- 证据张力记录：rebuildtest（dialog.ark 仅 stored 流字节变、dec 不变）弹 corrupt →
  校验读 stored 流或记录；但若校验在解压后内容上（滚动 CRC 读取器这类），dec 不变应通过。
  两点矛盾未解，说明真正的判定点尚未找到。
- 下一步候选：① 从 vtable 0xab1820 反查该读取器作用的对象文件；② 按 NID 找
  cellGameContentErrorDialog 调用点回溯错误码链；③ 对"stored 字节+种子未知"的
  例程精确实装后重算针值再搜。

## 17. shaders.dat HUD 居中 cgb 补丁变体（cgbfix）

落地 agent-1 的 VP 分析：`pack/shaders.dat.cgbfix`（`uw_cgb_fix.py` 生成，
src=shaders.dat.bak，已先备份 ~88MB）：
- 目标 4 个 cgb（全部 zlib 存储，无 segs）：`vs_ScreenToClipspace.cgb`(rec 26288)、
  `vs_ScreenToClipspaceColor.cgb`(26289)、`vs_ScreenToClipspaceTex.cgb`(26290)、
  `vs_ScreenToClipspaceTexColor.cgb`(26291)
- 每解压内容 2 点：dec+0xAB `E0→F8`（MAD 加数 swizzle .xxxx→.wxxx）+
  dec+0xCC `00000000→3F000000`（c466.w 0.0→0.5）；前件字节已逐一核验后写入
- stored 变化：ab→ad / b1→b3 / b3→b5 / b4→b6（各 +2，均远在 0x800 槽内）；
  记录表仅这 4 条 stored 字段更新；pool/偏移/pack.idx 零变化
- roundtrip：4 个 cgb 重解压 diff == 恰好这 2 点，其余全同 → **ALL OK**
- md5 `9325111a807c7f55a5b3788f2fb48bff`；现役 shaders.dat 未动（== .bak）

## 18. 无平移现役组合（着色器偏移路线配套）

HUD 居中改走 cgb 着色器偏移后，元素 x 平移会叠加重复，故产无平移组合：
- `pack/data.dat.selective` = 仅宽度补丁（排除 cockpit + dialog.ark，无 x 平移）：
  313 ark、头 618 + 元素 255、ROUNDTRIP ALL OK；md5 `ad6884a83546390e46716ea27efeadb7`
  （与此前 selective 版逐字节一致，重压确定性复现）
- `pack/data2.dat.cockpitin` 无平移全补丁版在位：md5 `21b780287a7a8232073692953fda3597`
- 实况（md5）：data.dat = center640 排除 quest_clear 版（`67fbc4bf…`，用户换入测试）、
  data2.dat = center640full（`8e939447…`）、shaders.dat = 原件（== .bak）
