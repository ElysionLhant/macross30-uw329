# PSXPlace 发布稿 — Game Patches 帖

**Title**:

> [RPCS3] Macross 30 (BLJS10184) — native 32:9 ultrawide patch (3D + centered HUD/text) + RE toolkit

**Body**:

```text
Game: Macross 30: Ginga o Tsunagu Utagoe (BLJS10184, JP)
Platform: RPCS3 v0.0.32-16803 (version pinned — newer builds break video playback, issue #17485)
Patch format: RPCS3 patch.yml (PPU be32 words, works under LLVM recompiler)
Repo: https://github.com/ElysionLhant/macross30-uw329
```

## Summary

Native 32:9 (7680×2160) for Macross 30. Three layers, all verified on hardware:

1. **3D projection** — aspect is computed per-frame from integer width via `fcfid`/`frsp`. Patch the width conversions `frsp fX,f13 → fadds fX,f13,f13` (width ×2) plus the static aspect table `@0xad5328` (16/9 → 32/9). Main camera m00 verified halved (0.974 → 0.487). Approach credit: [@wagrenier](https://github.com/wagrenier)'s Star Ocean work.

2. **HUD centering** — the hard part. UI vertices are CPU-baked per corner by a **family of 36 f32 quad-writer functions** (generic 2D class vtable), all following:
   ```
   W,H read from 0x5bba04 every draw; A = W*0.5
   ndc_x = (px - A)/A, px ∈ [0,1280] design space
   ```
   At 3840 wide that maps everything to [-1, -1/3] (the "left third" squeeze). No static constants exist — you must find the writers. Fix is 2 instructions per x-corner:
   ```
   fsubs f13,f13,fA → fdivs f13,f13,fA
   fdivs f13,f13,fA → fmsubs f13,f13,fS,fS   ; fS=0.5 seeded into a nop slot
   ⇒ ndc_x = px/(2A) - 0.5  → center band, undistorted
   ```

3. **Text renderer** — `0x1a1244`/`0x1a1a54` (batch `bdnz` loop), same formula, different K constant. The loop clobbers f12 (=K) with a UV divisor `frsp`; fixed by relocating texH to f13 and retargeting the two v-divisions. Whole call tree verified FP-write-free before trusting f12 across `bl`.

## Exemptions (important for anyone extending this)

- 7 quad+UV variants (`0x5e48ac/0x5e4bc8/0x5e4ee0/0x5e51f8/0x5e5510/0x5e5828/0x5e5b7c`) also draw **fullscreen effect quads** and are left unpatched on purpose — patching them squashes boost effects into a black band. Original `(px-A)/A` is already correct for fullscreen quads at any aspect.
- Static PPU patches can only gate at whole-function granularity (2 instruction slots per corner, no code cave under JIT). Mixed UI+effects functions need emulator-side width gating — see below.

## Known leftover / next path

Boost motion blur shows a vertical seam. Established facts (repo, appendix D):

- Blur = 3 passes × 7 taps on main tex `0x027b0000`, via the **0x822 dummy-quad composite path** (slot0 zero, slot12 shared table `@0x81eb1e04`, emitter `0x9b1d8`) — NOT the 36 patched writers. Nothing left to strip.
- Routes: emulator-side runtime gating by quad width (build2 `RPCS3_UW_HUD` hook chain), or locate the slot12-table writer via build2 logging on 0x822 draws with tex==`0x027b0000`.

## Toolkit (in repo)

RSX VP microcode disassembler & capture miners, GDB-stub breakpoint tracer, pymem live probes (guest base `0x400000000`), pack (PIDX/AXL) parser/patcher, automated boot→nav→3D harness. Docs: chronological HANDOFF, BAKER_FINDING (appendices A–D), COLDSTART, pack format RE.

## Requirements

RPCS3 v0.0.32-16803, patch enabled, **Stretch To Display Area**, **fullscreen**. Interpreter is debug-only (0.08 fps).

Credits: ElysionLhant (direction/testing), Kimi (Moonshot AI — RE & patch dev), [@wagrenier](https://github.com/wagrenier) (3D approach, from his Star Ocean patches). No game data included; patch tools operate only on your own copy.
