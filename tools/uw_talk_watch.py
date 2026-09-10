# -*- coding: utf-8 -*-
# 说话监听: 高频读环, 记录 0x4cxxx 命中的时间戳与内容变化 (嘴型重烘焙侦测)
# 用法: uw_venv/Scripts/python.exe uw_talk_watch.py [秒数=60]
import struct, pymem, time, sys
pm = pymem.Pymem('rpcs3.exe')
base = 0x400000000
DATA, CNTR, NREC, REC = 0xa6c000, 0xa6e000, 64, 128
DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 60
def rf32(b, o): return struct.unpack('>f', b[o:o+4])[0]
def ru32(b, o): return struct.unpack('>I', b[o:o+4])[0]
def cstr_at(addr, ln=64):
    if not (0x10000 <= addr < 0x40000000): return ''
    try:
        d = pm.read_bytes(base + addr, ln)
        end = d.find(b'\x00')
        return d[:end if end >= 0 else ln].decode('ascii', 'replace')
    except Exception:
        return ''
def texname(r5):
    try:
        cap = struct.unpack('>I', pm.read_bytes(base + r5 + 0x30, 4))[0]
        if cap == 0xF:
            return cstr_at(r5 + 0x1c)
        p = struct.unpack('>I', pm.read_bytes(base + r5 + 0x1c, 4))[0]
        return cstr_at(p)
    except Exception:
        return ''

last_cnt = None
hits4 = []     # (t, lr, r5, coords, uvs)
t0 = time.time()
while time.time() - t0 < DUR:
    cnt = struct.unpack('>I', pm.read_bytes(base + CNTR, 4))[0]
    raw = pm.read_bytes(base + DATA, NREC * REC)
    t = time.time() - t0
    for i in range(NREC):
        r = raw[i*REC:(i+1)*REC]
        if ru32(r, 116) != 0xBEEF5EA5: continue
        lr = ru32(r, 0)
        if lr not in (0x4c214, 0x4c9f0, 0x4ca64): continue
        r5 = ru32(r, 8)
        coords = tuple(round(rf32(r, 20+k*4), 1) for k in range(8))
        uvs = tuple(round(rf32(r, 52+k*4), 4) for k in range(8))
        key = (lr, r5, coords, uvs)
        if not hits4 or hits4[-1][1] != key:
            hits4.append((t, key))
    time.sleep(0.05)
print('--- 0x4cxxx activity over %ds: %d distinct transitions ---' % (DUR, len(hits4)))
for t, (lr, r5, coords, uvs) in hits4:
    xs = coords[0::2]; ys = coords[1::2]; us = uvs[0::2]; vs = uvs[1::2]
    print('t=%6.2f lr=0x%08x x[%7.1f..%7.1f] y[%6.1f..%6.1f] uv=%.4f/%.4f %s' % (
        t, lr, min(xs), max(xs), min(ys), max(ys), max(us)-min(us), max(vs)-min(vs), texname(r5)))
