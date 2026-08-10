# -*- coding: utf-8 -*-
# 读 UW trace buffer (guest 0x3B800000): count + {caller_r0, r3, r4, r5, r6}*N
import pymem, struct, sys

pm = pymem.Pymem('rpcs3.exe')
base = None
for cand in [0x300000000, 0x400000000, 0x700000000, 0x200000000, 0x1000000000, 0x500000000, 0x600000000]:
    try:
        if pm.read_bytes(cand + 0x10000, 4) == b'\x7fELF':
            base = cand
            break
    except Exception:
        pass
if not base:
    print('0'); sys.exit(1)

cnt = struct.unpack('>I', pm.read_bytes(base + 0x3B800000, 4))[0]
print(cnt)
n = min(cnt, 300)
d = pm.read_bytes(base + 0x3B800004, n * 12)
seen = {}
order = []
for i in range(n):
    r0, r3, r4 = struct.unpack('>III', d[i*12:i*12+12])
    key = (r0, r3, r4)
    if key not in seen:
        seen[key] = 0
        order.append(key)
    seen[key] += 1
for k in order:
    print('caller=0x%08x r3=0x%08x r4=0x%08x  x%d' % (*k, seen[k]), file=sys.stderr)
