# Reddit 发布稿 — r/ultrawidemasterrace（可剪后转 r/rpcs3）

**Title**:

> Macross 30 (PS3, RPCS3) — native 32:9 ultrawide patch: 3D widened, HUD/text natively centered, full RE write-up inside

**Body**:

After two long weekends of reverse engineering, here's a native 32:9 (7680×2160) patch for **Macross 30: Ginga o Tsunagu Utagoe (BLJS10184)** on RPCS3 — not a stretched hack: the 3D projection renders natively at 32:9, and the entire HUD, menus and text are **natively centered** into the middle 16:9 region by patching the game's CPU-side quad bakers.

**[SCREENSHOTS HERE — cockpit HUD + menu, before/after if you have them]**

## What works

- Native 32:9 3D (main camera matrix m00 halved: 0.974 → 0.487)
- HUD / menus / text centered without distortion (2 instructions patched per vertex corner, 36 writer functions + 2 text renderers)
- Fully playable start to finish
- Movies stay 16:9 (pre-rendered, nothing to do about it)
- Known cosmetic leftover: a faint seam on the boost motion blur — documented as the next path in the repo

## Why this was hard (the fun part)

- The game's UI vertices are **CPU-baked per corner** reading the runtime resolution every draw — there were literally no constants to search for. We had to find the whole *family* of 36 quad-writer functions and patch each corner with `fdivs` + `fmsubs` to remap design coordinates into the center band.
- Fullscreen effects share the same vtable as UI, so 7 functions had to be *exempted* or boost effects turned into a black band.
- The text renderer's batch loop clobbered the one register we needed (f12) with a UV divisor — fixed by relocating the divisor to a different register mid-loop. Register lifetime archaeology.
- Full write-up (with PPC encoding details, formulas, and the "do NOT do these three things" list) is in the repo README.

## Requirements (important!)

- RPCS3 **v0.0.32-16803 exactly** — newer builds can't play this game's videos (RPCS3 issue #17485)
- Enable patch + **Stretch To Display Area** + play **fullscreen**

## Links

- GitHub (patch + toolkit + full reverse-engineering docs): https://github.com/ElysionLhant/macross30-uw329

Credits: 3D widening approach learned from [@wagrenier](https://github.com/wagrenier)'s Star Ocean patches. Co-developed with Kimi (Moonshot AI) as an AI pair-reverse-engineer — yes, really, and it held up on hardware.

---

**r/rpcs3 剪辑版**：去掉 ultrawide 受众梗，开头加 "first native 32:9 ultrawide patch for this title; HUD centering done on the CPU baker side, might be useful reference for other Artdink titles"，其余相同。
