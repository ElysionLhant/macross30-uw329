# -*- coding: utf-8 -*-
# 在 shaders.dat 的 .cgb 中定位: HUD VP 微码字节 + {1/1280,1/720} 浮点向量
import sys, struct, os
sys.argv = ['x', 'uw_capture.pkl']
import uw_vp_disasm as m
sys.path.insert(0, '.')
from uw_pack_re import Pack, PACK_DIR

def session_blob(si, be=True):
    s = m.sessions[si]
    words = s['words']
    maxa = max(words)
    out = b''
    for a in range(maxa + 1):
        w4 = words.get(a)
        if w4 is None:
            return None
        for w in w4:
            out += struct.pack('>I' if be else '<I', w)
    return out

progs = {
    'pass3_mov_zw_c467.xxxx (sess1)': 1,
    'pass3_mov_zw_c467.xxxy (sess6)': 6,
    'pass2_mov_z_c467 (sess7)': 7,
    'pass4_color467 (sess53)': 53,
    'mat19_color467 (sess17)': 17,
}
blobs = {}
for name, si in progs.items():
    b = session_blob(si, True)
    if b:
        blobs[name + ' BE'] = b
    b2 = session_blob(si, False)
    if b2:
        blobs[name + ' LE'] = b2

# 也拿 79-instr 3D 程序前 3 条指令做指纹
b = session_blob(4, True)
if b:
    blobs['3D79 first48B BE'] = b[:48]

FLOATS = {
    '{1/1280,1/720,0,0}': struct.pack('<4f', 1/1280, 1/720, 0, 0),
    '{2/1280,2/720,0,0}': struct.pack('<4f', 2/1280, 2/720, 0, 0),
    '{1/1280,1/720} BE': struct.pack('>2f', 1/1280, 1/720),
    '{1/1280} LE': struct.pack('<f', 1/1280),
}

print('PACK_DIR=%s' % PACK_DIR)
p = Pack(PACK_DIR + 'shaders.dat')
nfiles = 0
hits = []
for i, path, off, dec, stored in p.files():
    if not path.lower().endswith('.cgb'):
        continue
    nfiles += 1
    blob, kind = p.read_file(off, dec, stored)
    for name, pat in blobs.items():
        j = blob.find(pat)
        if j >= 0:
            hits.append((path, name, j, len(blob), kind))
    for name, pat in FLOATS.items():
        start = 0
        while True:
            j = blob.find(pat, start)
            if j < 0:
                break
            hits.append((path, name, j, len(blob), kind))
            start = j + 1
print('cgb files scanned: %d' % nfiles)
print('hits: %d' % len(hits))
for h in hits[:80]:
    print('  %-60s %-36s @0x%x (size 0x%x, %s)' % h)
