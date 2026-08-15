# Macross 30 (BLJS10184) — RPCS3 32:9 Ultrawide Patch & Toolkit

A 32:9 (7680×2160) ultrawide patch for **Macross 30: Ginga o Tsunagu Utagoe (BLJS10184)** on **RPCS3 v0.0.32-16803**, plus the full reverse-engineering toolkit used to build it.

**Current state (all verified on hardware)**:

- 3D projection renders native 32:9 (main camera matrix m00 halved, 0.974→0.487)
- HUD, menus and text are natively centered to the middle 16:9 region (CPU baker patches, not stretching)
- Movies stay stretched 16:9 (pre-rendered 16:9 sources — nothing can be done)
- Known leftover: a vertical seam line on the boost motion blur — see "The Next Path" below

---

## Installation

1. You must use RPCS3 **v0.0.32-16803** (newer builds can't play this game's videos — see RPCS3 issue #17485)
2. Copy `patches/patch.yml` into your rpcs3 `patches/` folder, and `patches/config_BLJS10184.yml` into `config/custom_configs/` (edit the VFS path inside to point at your game folder)
3. Enable the patch in the patch manager, check **Stretch To Display Area**, and play in **fullscreen** (horizontal squish in windowed mode is expected)
4. PPU patches work under the LLVM recompiler. Do not use the interpreter (0.08 fps, debug only)

## Troubleshooting

- **"Dead FIFO commands queue state has been detected!" mid-game**: an RSX↔PPU command-stream race (a known RPCS3 issue class — the FIFO walker consumed a `call` whose target the PPU had not finished writing). Not caused by this patch. Mitigation ladder in Advanced settings: **Driver Wake-Up Delay 20 → 200µs**, then **RSX FIFO Accuracy: Atomic** (costs some performance). Observed twice, both ~25 min into combat-heavy play.
- **Fatal Error dialog on exit (in `ZCULL_control`)**: a harmless teardown race in this RPCS3 build — all CPU threads and saves are already done when it happens. Our build2 source tree carries an SEH guard for it (`rpcs3/Emu/RSX/RSXZCULL.cpp`, verified in production: two corrupted blocks skipped with a log line instead of a crash dialog); on a stock 0.0.32-16803 the dialog may still appear on exit — safe to dismiss.
- **"Game data is corrupted" at boot / `exception: vector<T> too long` self-abort (esp. entering the hangar)**: **not an emulator or patch issue** — stale experimental pack files (`data.dat`/`data2.dat`/`shaders.dat` variants produced by this repo's pack tools) sitting in the `dev_hdd0/game/BLJS10184_INSTALL/USRDIR/data/pack/` override directory. The game loads that directory with priority over the disc, and one experimental table made the hangar menu constructor overflow a `std::vector`; removing the override makes the integrity check fail instead. Fix: quarantine the whole `BLJS10184_INSTALL` directory (the game reinstalls pristine data from the disc). **If you never used the pack tools, this cannot happen to you.**

## Known issues

- **Comm-scene portraits horizontally squashed (×0.5)**: the monitor/dialog portraits are drawn by writer `0x5e5ea4` in **framebuffer pixel space** (already 32:9-correct from the 3D projection), but the same writer also draws LAYO-space nine-patch dialog quads that need the centering formula — a mixed painter. Centering it squashes the portraits; exempting it stretches the dialog frames. Proper fix = per-caller routing (route the portrait caller to an unpatched sibling writer) or emulator-side gating — see "The Next Path". Cosmetic only.
- **Boost motion-blur seam** — see "The Next Path" below.

---

## How the patch works (the hard-won parts)

Written for whoever comes next. Each section is a wall we spent days on; reading them in order will save you from our dead ends. Full chronicle in `docs/HANDOFF.md` (Chinese), complete writer-function analysis in `docs/BAKER_FINDING.md` (appendices A–D), cold-start handoff in `docs/COLDSTART.md`.

### 1. 3D widening: don't touch the projection matrix — touch its ingredients

> Credit: this approach comes from **[@wagrenier](https://github.com/wagrenier)**'s Star Ocean patch work. The 3D part of this project went smoothly because we had seen the same trap in his solutions.

Symptom: at 32:9 the 3D scene is squashed. The obvious target is the projection matrix (m00 / tan(fov)), but in this game the projection is **recomputed every frame**:

- `aspect = (float)w / (float)h`, where w/h come from integer→float `fcfid` conversions followed by `frsp`
- Change the width conversions `frsp fX, f13` to `fadds fX, f13, f13` (width ×2) and aspect becomes 32:9 — every downstream projection builder becomes correct automatically
- One scalar builder path uses a **static aspect constant table** `@0xad5328`; patch 16/9 (`0x3FE38E39`) to 32/9 (`0x40638E39`)

Lesson: **patching inputs is safer than patching formulas**. The matrix is rebuilt in memory every frame; chasing the matrix itself never ends. Chasing its operands works once and for all.

> Note for readers of the chronicle: the "rainbow stripes" in HANDOFF.md were an artifact of the **retired** `li 1280→2560` route (widened surface VPs outgrew tile pitch). The shipped ingredient route never touches surface widths — there is no rainbow. The tile1/2 tier-preset-table hunt only matters if someone revives that retired route.

### 2. HUD centering: find the writer functions, not constants

Symptom: at 32:9 the entire HUD is squeezed into the left third of the screen.

HUD vertices are **CPU-baked per corner** as f32 quads, written by a **function family** (a generic 2D class vtable: 36 writer functions + 2 text renderers). Every function follows the same pattern:

```
reads runtime W/H from 0x5bba04 on every draw
  (so there is NO static constant to search for!)
A = W * K,  K = 0.5 (constant @0xad7058, TOC1+0x599c)
ndc_x = (px - A) / A      // px ∈ [0,1280] design coordinates
ndc_y = -(py - B) / B
```

At 32:9 the runtime W is 3840, so A=1920 and px∈[0,1280] maps to [-1, -1/3] — that's the left-third squeeze. **Searching for constants like 51.2 / 32767 / 1280 is a dead end**: the width is read at runtime, so you must find the writer functions themselves.

The centering fix (2 instructions per x-corner; y untouched):

```ppc
# original:  fsubs f13, f13, fA    ; px - A
#            fdivs f13, f13, fA    ; / A
# patched:   fdivs f13, f13, fA    ; px / A
#            fmsubs f13, f13, fS, fS  ; (px/A)*0.5 - 0.5 = px/(2A) - 0.5
```

Result `px/(2A) - 0.5`: design coordinates [0,1280] map exactly onto NDC [-0.5, 0.5], the middle 16:9 region, **without aspect distortion** (x scale factor matches y). The fS=0.5 seed goes into an existing `nop` slot as `lfs fS, 0x599c(r2)`.

PPC A-form encoding gotchas (learned the hard way): **frC is at bits 10-6, frB at bits 15-11**; fdivs XO=18, fmsubs XO=28, fmuls XO=25 (all opcode 59); `fmsubs(a,b,c) = a*b - c`. frsp & co. are opcode **63**, not 59.

### 3. Fullscreen effects must be exempted: UI and effects share the same vtable

A handful of the 36 writers **draw not only UI but also fullscreen effect quads** (the source of the black drag band during boost). Those quads' design coordinates already span the full screen; the centering patch squeezes them into the middle band = a black shadow trail.

Handling: **leave the 7 quad+UV variants (0x5e48ac / 0x5e4bc8 / 0x5e4ee0 / 0x5e51f8 / 0x5e5510 / 0x5e5828 / 0x5e5b7c) completely unpatched**, keeping the original `(px-A)/A` — which for fullscreen quads is already correct at any aspect ratio.

Lesson: **the minimum granularity of a static patch is a whole function**. When one function draws both UI and effects, inline width-gating is impossible (only 2 instruction slots per corner, `fsel` needs 3, and there is no code cave under the JIT), so you can only accept/reject whole functions — or move to emulator-side runtime gating (see below).

### 4. Text renderer: register lifetimes are harder than formulas

Text doesn't go through the 36 writers; it uses `0x1a1244` (single sprite) and `0x1a1a54` (batched sprite `bdnz` loop) with a different K constant (@0xac18a4, TOC2-0x2fc). Same formula fix, but the batch loop hides a trap:

- After `f12` is loaded with K=0.5, an in-loop `frsp f12, f7` (int→float conversion of texH, the UV v-divisor) **clobbers it** — texW/texH are loop-invariant, yet the compiler recomputes them every iteration
- Fix: relocate texH — change `frsp f12,f7` to `frsp f13,f7`, and retarget the two UV v-divisions `fdivs f10,f10,f12` / `fdivs f8,f8,f12` to f13. f13 is a per-corner `lfs`-reloaded scratch anyway, so there is no timing conflict; f12 then holds K for the whole loop
- **Daring to use f12 across the `bl` requires proof**: we disassembled the entire call tree (0x8daf08 trampoline → 0x574190 → memcpy-style utilities) and confirmed **zero FP writes** end to end. Assuming a volatile register survives a call is how you get garbage

Lesson: the batch loop's record advance pointer is `r31` (`addi r31,r31,0x20`). An earlier patch version stole `clrldi` slots for seeds and compensated the wrong register — text collapsed into a vertical line. **Before patching loop code, map every register's lifetime first.**

### 5. Build environment (custom RPCS3 "build2")

- The patch vehicle is a standard `patch.yml` (be32 words); it works under LLVM, no emulator changes needed
- PPU patch addresses = decrypted EBOOT vaddrs (dump/disassembly tooling in `tools/`; remember capstone `skipdata` mode or disassembly stops at data)
- **A set of `li 1280→2560` immediate patches causes a random "kaleidoscope"** (layout takes multiple paths) — abandoned; same for the v11 li group, keep them off
- Live guest memory base measured at `0x400000000` (pymem reads at base+vaddr verify whether patches are live)

---

## The Next Path (boost-blur seam) — starting point, written down

**Symptom**: during boost, the 3D motion-blur trail shows a vertical seam line. Everything else is fine; the game is fully playable.

**Already established (appendix D — no need to re-derive)**:

- Motion blur = 3 passes × 7 taps sampling the main display texture `0x027b0000`; shader VP local addresses (low 24 bits) `0xf3d181 / 0x7b01 / 0xabf81` are **runtime-allocated** — they don't exist as literals in the EBOOT, static search is futile
- All three passes use the **0x822 dummy-quad composite path**: slot0 all-zero, slot12 = shared float table **`@0x81eb1e04`**; emitter at `0x9b1d8` (with ori 0x822 format commands at `0x9b420` / `0x9b7f8`)
- This path **does not go through** the 36 patched writers (those emit 0x1032/0x1432 real vertices, slot0 non-zero). The blur chain itself is not compressed — **there are no more functions to strip**; stripping more only eats UI
- The seam is the boundary between the fullscreen blur region and everything else — **not** a compressed blur writer still hiding somewhere

**Two viable routes**:

1. **(The right way) Emulator-side runtime gating in build2**: hook the existing `RPCS3_UW_HUD` chain and gate per-draw by quad width — near-fullscreen quads skip centering, UI-width quads get centered. The only way to have both "effects fullscreen" and "UI centered". Cost: emulator code change + rebuild.
2. **(Recon) Locate the 0x822 baker**: use the build2 logging method at the end of appendix C — on 0x822 draws with tex==`0x027b0000`, record the CPU PC that writes the slot12 table. One measured run settles it. Then either exempt that writer specifically, or confirm it should stay fullscreen and close the case.

**Do NOT**: re-patch the 7 quad+UV variants (trades the seam for the black band); strip more `0x5exxxx` functions (each one takes a chunk of UI with it).

## The Next Path II (comm-portrait squash) — FIXED, pending final sign-off

**Symptom (resolved)**: in story/comm scenes, the on-monitor character portraits rendered at half horizontal width.

**Root cause (5-round bisect, verified on hardware)**: the portraits are drawn by writer **`0x5e5ea4`** in **framebuffer pixel space** (quad coords come from the 3D projection of the in-world monitors), while the same writer draws LAYO-space nine-patch dialog quads that need centering. A genuine mixed painter — centering it squashed portraits, exempting it stretched dialog frames.

**Fix (implemented)**: make the writer's seed factor **fS switch per call** — the patched corner math `(px/A)·fS − fS` equals the centered formula at fS=0.5 and the original formula at fS=1.0, so one writer serves both quad families. The discriminator is the **caller's return address** (coords alone can't separate the two families — dialog frames are framebuffer-space too): LR low16 == `0x9678` selects the portrait path (`0x79674` assembly). 10 extra patch words:

- the `0x7009c4` trampoline's final branch now lands on an 8-word gate routine at `0x8defd4` (a zero-fill gap verified unreferenced): `mflr` → compare → `cntlzw` → shift/mask, yielding `0x3F80`/`0x3F00` (1.0/0.5) in r12
- the writer's free nop at `0x5e5f08` stores r12 to `writer_frame+0x88`; the seed slot at `0x5e5fcc` loads it (`lfs f11, 0x88(r1)`). r12 is clobber-safe: the only call in between (`0x5bba04`) touches r3 only

Edge rule: LR compare is exact — dialog sites (`0x4c214`/`0x4c9f0`/`0x4ca64`) all take fS=0.5. Verified on hardware: Load Save frames, unit labels, item menus all correct; **final visual sign-off on a comm scene (faces + frames simultaneously) is the only open item.**

**Hard-won gotcha**: an earlier revision of the gate forgot the `srwi` after `cntlzw` — `cntlzw` yields 32 on equality but 17–20 on inequality, so dialogs got fS≈0.77–0.81 instead of 0.5 and every menu frame silently moved off-screen. `cntlzw` alone is never a boolean.

---

## Toolkit

- `uw_measure.py` — live tile-pitch / projection-matrix m00 probe (pymem, auto ASLR base)
- `uw_gdb_trace.py` — RPCS3 GDB stub breakpoint tracer (Z0 breakpoints + arbitrary registers + memory deref)
- `uw_vp_disasm.py` / `uw_vp_*.py` — RSX vertex-program microcode disassembler / capture draw miners
- `uw_pack_re.py` / `uw_pack_patch.py` / `uw_pack_center640.py` — pack container (PIDX/AXL) parser/patcher/LAYO widener (operates only on your own game files; integrity-checked resources trigger "Game data is corrupted" and are excluded by default)
- `uw_cgb_fix.py` — .cgb microcode patcher inside shaders.dat
- `uw_harness*.sh` / `postkey.ps1` — automated boot→navigate→3D test loops, key injection
- `uw_guest.py` / `uw_findbase.py` / `uw_poke_desc.py` — guest memory dump / base finder / live pokes

## Docs (Chinese unless noted)

- `docs/FINAL_HANDOFF.md` — the two-weekend wrap-up: final state, open items with entry points, and everything you must remember before resuming (read this first)
- `docs/COLDSTART.md` — cold-start handoff
- `docs/HANDOFF.md` — chronological debug log (everything, including failed routes)
- `docs/BAKER_FINDING.md` — HUD baker analysis (appendix A: the 35-function family; B: text renderer; C: RSX capture method; D: blur-chain final verdict)
- `docs/UW_PACK_RE.md` — pack/PIDX/AXL format documentation
- `docs/UW_VP_OFFSET.md` — HUD offset VP microcode analysis
- `docs/publishing/` — ready-to-post release drafts: Reddit (EN), PSXPlace (EN), Bilibili (中文)

## Open items (besides the seam)

- Per-resource integrity check (CRC32 @0x653aa0) reverse engineering for dialog.ark / mechroom_develop.ark / quest_clear

## Credits

- **[ElysionLhant](https://github.com/ElysionLhant)** — project owner: direction, all on-hardware testing, RSX captures, and the stubbornness to see a 1280-pixel wall through to the end
- **Kimi (Moonshot AI)** — reverse engineering & patch development: baker family analysis, PPC encodings, text-renderer register surgery, toolkit
- **[@wagrenier](https://github.com/wagrenier)** — author of the Star Ocean patch series. The 3D widening approach ("patch the width source, not the projection formula") was learned from his work. Thank you!

## Disclaimer

Game modification tools and patches for educational/research purposes only. No game data files are included; all pack tools operate solely on the user's own legally obtained copy. All rights to the game belong to Bandai Namco / Artdink.
