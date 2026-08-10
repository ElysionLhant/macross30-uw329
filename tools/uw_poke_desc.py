# -*- coding: utf-8 -*-
# 扫/戳表面描述体: {w=0x500@N, h=0x2D0@N+4} 且 pitch=0x1400 在 ±0x40 内
# 用法: uw_poke_desc.py scan | poke
import pymem, struct, sys

MODE = sys.argv[1] if len(sys.argv) > 1 else 'scan'
pm = pymem.Pymem('rpcs3.exe')
base = None
for cand in [0x300000000, 0x400000000, 0x700000000, 0x200000000, 0x1000000000, 0x500000000]:
    try:
        if pm.read_bytes(cand + 0x10000, 4) == b'\x7fELF':
            base = cand
            break
    except Exception:
        pass
if not base:
    print('base not found'); sys.exit(1)
print('base=0x%x' % base)

# 枚举已提交区域（客体 32GB 空间）
regions = []
addr = base
end = base + 0x800000000
import pymem.memory
while addr < end:
    try:
        mbi = pymem.memory.virtual_query(pm.process_handle, addr)
    except Exception:
        break
    if mbi.BaseAddress < base:
        addr = base
        continue
    if mbi.BaseAddress >= end:
        break
    size = min(mbi.RegionSize, end - mbi.BaseAddress)
    if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x08, 0x40, 0x80):
        regions.append((mbi.BaseAddress, size))
    addr = mbi.BaseAddress + mbi.RegionSize

pat = struct.pack('>II', 0x500, 0x2D0)
hits = []
for rbase, size in regions:
    gbase = rbase - base
    # 只扫堆/数据区（跳过 EBOOT 0x10000-0xd96080 的代码段没有意义，但也无害）
    try:
        data = pm.read_bytes(rbase, size)
    except Exception:
        continue
    off = 0
    while True:
        i = data.find(pat, off)
        if i < 0:
            break
        off = i + 1
        g = gbase + i
        # pitch 0x1400 在 ±0x40 内？
        lo = max(0, i - 0x40)
        hi = min(size, i + 0x48)
        win = data[lo:hi]
        has_pitch = struct.pack('>I', 0x1400) in win
        hits.append((g, has_pitch))

print('pattern hits: %d (with pitch nearby: %d)' % (len(hits), sum(1 for _, p in hits if p)))
for g, p in hits[:60]:
    print('  desc@0x%08x pitch1400=%s' % (g, p))

if MODE == 'poke':
    n = 0
    for g, p in hits:
        if not p:
            continue
        pm.write_bytes(base + g, struct.pack('>I', 0xA00), 4)
        n += 1
    print('poked %d descriptors w->0xA00' % n)
