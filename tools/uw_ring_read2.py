# -*- coding: utf-8 -*-
# 混画取证环形缓冲读取器 v2: 每条记录带 r5 描述体纹理路径
# 用法: uw_venv/Scripts/python.exe uw_ring_read2.py [n=32]
import struct, sys, pymem
from collections import defaultdict

DATA = 0xa6c000
CNTR = 0xa6e000
NREC, REC = 64, 128
TRAMP = 0x7009d0

pm = pymem.Pymem('rpcs3.exe')

CAND = [0x400000000, 0x300000000, 0x700000000, 0x200000000, 0x100000000, 0x500000000, 0x600000000]
base = None
for c in CAND:
    try:
        w = struct.unpack('>I', pm.read_bytes(c + TRAMP, 4))[0]
        if w in (0x4bee54d4, 0x482e25bc):
            base = c
            break
    except Exception:
        continue
if base is None:
    print('no base found; game not running?')
    sys.exit(1)

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
        p = struct.unpack('>I', pm.read_bytes(base + r5 + 0x1c, 4))[0]
        return cstr_at(p)
    except Exception:
        return ''

counter = struct.unpack('>I', pm.read_bytes(base + CNTR, 4))[0]
raw = pm.read_bytes(base + DATA, NREC * REC)

def rf32(b, o): return struct.unpack('>f', b[o:o+4])[0]
def ru32(b, o): return struct.unpack('>I', b[o:o+4])[0]

recs = []
for i in range(NREC):
    r = raw[i*REC:(i+1)*REC]
    if ru32(r, 116) != 0xBEEF5EA5:
        continue
    lr, r3, r5, r6, r7 = struct.unpack('>IIIII', r[0:20])
    coords = [rf32(r, 20+k*4) for k in range(8)]
    uvs = [rf32(r, 52+k*4) for k in range(8)]
    recs.append({'idx': i, 'lr': lr, 'r5': r5, 'coords': coords, 'uvs': uvs})

names = {}
for r in recs:
    if r['r5'] not in names:
        names[r['r5']] = texname(r['r5'])

print('counter=%d valid=%d  (tramp %s)' % (counter, len(recs), 'LOGGER ON' if struct.unpack('>I', pm.read_bytes(base+TRAMP, 4))[0] == 0x482e25bc else 'off'))

n = int(sys.argv[1]) if len(sys.argv) > 1 else 32
by5 = defaultdict(list)
for r in recs:
    by5[r['r5']].append(r)

print()
print('=== by texture (r5 descriptor) ===')
for r5, rows in sorted(by5.items(), key=lambda kv: -len(kv[1])):
    name = names[r5] or '<no name>'
    print('r5=0x%08x n=%2d  %s' % (r5, len(rows), name))
    for r in rows[:4]:
        xs = r['coords'][0::2]; ys = r['coords'][1::2]
        us = r['uvs'][0::2]; vs = r['uvs'][1::2]
        print('   #%02d x[%7.1f..%7.1f] w=%6.1f y[%6.1f..%6.1f] h=%6.1f uvspan=%.3f/%.3f lr=0x%08x'
              % (r['idx'], min(xs), max(xs), max(xs)-min(xs), min(ys), max(ys), max(ys)-min(ys),
                 max(us)-min(us), max(vs)-min(vs), r['lr']))
