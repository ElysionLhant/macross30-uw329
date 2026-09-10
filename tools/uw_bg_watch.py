# -*- coding: utf-8 -*-
# 全程后台监听: 0x4cxxx 每次触发都记; 0x79674 只记首次出现的组合
# 输出: UW32_Macross30/data/uw_bg_watch.log
import struct, pymem, time, sys

OUT = r'C:\Users\Elysion\Desktop\UW32_Macross30\data\uw_bg_watch.log'
DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 3600
DATA, CNTR, NREC, REC = 0xa6c000, 0xa6e000, 64, 128

def attach():
    while True:
        try:
            pm = pymem.Pymem('rpcs3.exe')
        except Exception:
            time.sleep(5)
            continue
        for c in (0x400000000, 0x300000000, 0x700000000, 0x200000000, 0x100000000, 0x500000000, 0x600000000):
            try:
                w = struct.unpack('>I', pm.read_bytes(c + 0x7009d0, 4))[0]
                if w in (0x4bee54d4, 0x482e25bc):
                    return pm, c
            except Exception:
                pass
        time.sleep(5)

pm, base = attach()
print('base = 0x%x' % base)
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

log = open(OUT, 'a', buffering=1)
log.write('\n=== watch start %.0f ===\n' % time.time())
seen = {}
t0 = time.time()
n4 = 0
while time.time() - t0 < DUR:
    try:
        cnt = struct.unpack('>I', pm.read_bytes(base + CNTR, 4))[0]
        raw = pm.read_bytes(base + DATA, NREC * REC)
    except Exception as e:
        log.write('t=%.1f READ ERR %r (game closed? waiting for relaunch)\n' % (time.time() - t0, e))
        time.sleep(5)
        try:
            pm, base = attach()
            log.write('t=%.1f reattached, base=0x%x\n' % (time.time() - t0, base))
        except Exception:
            pass
        continue
    t = time.time() - t0
    for i in range(NREC):
        r = raw[i*REC:(i+1)*REC]
        if ru32(r, 116) != 0xBEEF5EA5: continue
        lr = ru32(r, 0); r5 = ru32(r, 8)
        coords = tuple(round(rf32(r, 20+k*4), 2) for k in range(8))
        uvs = tuple(round(rf32(r, 52+k*4), 4) for k in range(8))
        key = (lr, r5, coords, uvs)
        is4 = lr in (0x4c214, 0x4c9f0, 0x4ca64)
        if is4 or key not in seen:
            name = texname(r5)
            xs = coords[0::2]; ys = coords[1::2]; us = uvs[0::2]; vs = uvs[1::2]
            log.write('t=%7.2f %s lr=0x%08x r5=0x%08x x[%7.1f..%7.1f] y[%6.1f..%6.1f] uv=%.4f/%.4f %s\n' % (
                t, '4XXX' if is4 else 'new ', lr, r5, min(xs), max(xs), min(ys), max(ys),
                max(us)-min(us), max(vs)-min(vs), name))
            if is4:
                n4 += 1
        seen[key] = t
    time.sleep(0.05)
log.write('=== watch end %.0f; distinct=%d; 4cxxx events=%d ===\n' % (time.time(), len(seen), n4))
log.close()
print('done -> %s' % OUT)
