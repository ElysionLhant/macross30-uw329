# -*- coding: utf-8 -*-
# 提取 VP 微码上传 + 常量上传，定位 HUD pass (scale {1/1280,1/720} @ slot 467)
import pickle, struct, sys

PKL = sys.argv[1] if len(sys.argv) > 1 else 'uw_capture.pkl'
d = pickle.load(open(PKL, 'rb'))
fifo = d['fifo']

def f32(w):
    return struct.unpack('<f', struct.pack('<I', w & 0xFFFFFFFF))[0]

PROG_DATA = 0x0B80   # NV4097_SET_TRANSFORM_PROGRAM
PROG_LOAD = 0x1E9C   # NV4097_SET_TRANSFORM_PROGRAM_LOAD
PROG_START = 0x1EA0  # NV4097_SET_TRANSFORM_PROGRAM_START
CONST_DATA = 0x1F00  # NV4097_SET_TRANSFORM_CONSTANT
CONST_LOAD = 0x1EFC  # NV4097_SET_TRANSFORM_CONSTANT_LOAD

prog_load = 0
prog_start = 0
const_load = 0

prog_writes = []   # (fifo_idx, load_addr, [words])
const_writes = []  # (fifo_idx, load_addr, [words])

for idx, item in enumerate(fifo):
    if item[0] == 'SPECIAL':
        continue
    reg, vals = item
    if reg == PROG_LOAD:
        prog_load = vals[0]
    elif reg == PROG_START:
        prog_start = vals[0]
    elif reg == CONST_LOAD:
        const_load = vals[0]
    elif reg == PROG_DATA:
        prog_writes.append((idx, prog_load, vals))
        prog_load += len(vals) // 4
    elif reg == CONST_DATA:
        const_writes.append((idx, const_load, vals))
        const_load += len(vals) // 4

print('=== %s ===' % PKL)
print('program writes: %d' % len(prog_writes))
for idx, addr, vals in prog_writes:
    print('  @fifo %-6d load=%-4d words=%-3d (instr %d..%d)' % (idx, addr, len(vals), addr, addr + len(vals)//4 - 1))
print('program_start=%d (last seen)' % prog_start)
print()
print('const writes: %d' % len(const_writes))

# 收集全部常量槽 -> (fifo_idx, floats)
const_db = {}
for idx, addr, vals in const_writes:
    for i in range(0, len(vals) - 3, 4):
        slot = addr + i // 4
        const_db.setdefault(slot, []).append((idx, vals[i:i+4]))

# 找 1/1280 / 1/720 / 2/1280 / 2/720 / 640 / -1 / 0.5
TARGETS = {0x3A4CCCCD: '1/1280', 0x3AB60B61: '1/720', 0x3ACCCCCD: '2/1280',
           0x3B360B61: '2/720', 0x44200000: '640.0', 0xBF800000: '-1.0',
           0x3F000000: '0.5', 0x3A088889: '1/2560?'}
print()
print('=== slots containing target floats ===')
for slot in sorted(const_db):
    for idx, words in const_db[slot]:
        tags = [TARGETS.get(w) for w in words]
        if any(tags):
            fs = ' '.join('%s=%g' % (t if t else ('0x%08x' % w), f32(w)) for w, t in zip(words, tags))
            print('  slot %-4d @fifo %-6d: %s' % (slot, idx, fs))

# slot 460-475 概览
print()
print('=== slots 460..475 ===')
for slot in range(460, 476):
    if slot in const_db:
        idx, words = const_db[slot][-1]
        print('  slot %-4d @fifo %-6d: %s' % (slot, idx, ' '.join('%g' % f32(w) for w in words)))
