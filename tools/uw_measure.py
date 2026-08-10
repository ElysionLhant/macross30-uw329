# -*- coding: utf-8 -*-
# 夜间迭代测量: ASLR 基址 + tile pitch + 主相机 m00 + 崩溃检查
import struct, sys, pymem

pm = pymem.Pymem('rpcs3.exe')
base = None
for gb in range(1, 64):
    b = gb * 0x100000000
    try:
        if pm.read_bytes(b + 0x10000, 4) == b'\x7fELF':
            base = b
            break
    except Exception:
        pass
if base is None:
    print('BASE_NOT_FOUND')
    sys.exit(1)
print('base=0x%x' % base)

def u32(a):
    return struct.unpack('>I', pm.read_bytes(base + a, 4))[0]

def f32(a):
    return struct.unpack('>f', pm.read_bytes(base + a, 4))[0]

# tile array @0x1020ae0: tile_i at +0x10*i: region, limit, pitch, format
for t in (1, 2, 9, 10):
    off = 0x1020ae0 + 0x10 * t
    region, limit, pitch = u32(off), u32(off + 4), u32(off + 8)
    print('tile%d pitch=0x%x (%d px RGBA32) region=0x%08x' % (t, pitch, pitch // 4, region))
try:
    print('main m00=%.6f  aspect_tbl=%.6f' % (f32(0xb94260), f32(0xad5328)))
except Exception as e:
    print('matrix read fail: %s' % e)
