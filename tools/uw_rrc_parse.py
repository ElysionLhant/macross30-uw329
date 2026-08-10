# -*- coding: utf-8 -*-
# RRC v5 解析: 提取 FIFO 命令流 + 内存块索引
import struct, sys

raw = open('uw_capture4.bin','rb').read()
pos = 12  # skip magic/version/LE

def vle():
    global pos
    v = 0; shift = 0
    while True:
        b = raw[pos]; pos += 1
        v |= (b & 0x7f) << shift
        if not (b & 0x80): break
        shift += 7
    return v

# tile_map
n = vle()
tiles = {}
for _ in range(n):
    k = struct.unpack('<Q', raw[pos:pos+8])[0]
    tiles[k] = raw[pos+8:pos+8+432]
    pos += 8 + 432
print('tile_map: %d entries' % n)

# memory_map
n = vle()
mem_map = {}
for _ in range(n):
    k = struct.unpack('<Q', raw[pos:pos+8])[0]
    off, loc, ds = struct.unpack('<IIQ', raw[pos+8:pos+8+16])
    mem_map[k] = (off, loc, ds)
    pos += 8 + 16
print('memory_map: %d entries' % n)

# memory_data_map
n = vle()
mem_data = {}
for _ in range(n):
    k = struct.unpack('<Q', raw[pos:pos+8])[0]
    pos += 8
    sz = vle()
    mem_data[k] = raw[pos:pos+sz]
    pos += sz
print('memory_data_map: %d entries' % n)

# display_buffers_map
n = vle()
pos += n * (8 + 132)
print('display_buffers_map: %d entries' % n)

# replay_commands
n = vle()
cmds = []
for _ in range(n):
    first, second = struct.unpack('<II', raw[pos:pos+8])
    pos += 8
    ms = vle()
    pos += ms * 8
    tile, disp = struct.unpack('<QQ', raw[pos:pos+16])
    pos += 16
    cmds.append((first, second))
print('replay_commands: %d' % n)

# ---- decode FIFO ----
def reg_of(first):
    return ((first >> 2) & 0x1fff) << 2

fifo = []  # (reg, [values])
i = 0
count = 0
cur_reg = 0
cur_vals = []
while i < len(cmds):
    first, second = cmds[i]
    if count == 0:
        c = (first >> 18) & 0x7ff
        if c == 0:
            # special: jump/call/nop etc
            fifo.append(('SPECIAL', first, second))
            i += 1
            continue
        cur_reg = reg_of(first)
        cur_vals = [second]
        count = c - 1
        if count == 0:
            fifo.append((cur_reg, cur_vals))
        i += 1
    else:
        cur_vals.append(second)
        count -= 1
        if count == 0:
            fifo.append((cur_reg, cur_vals))
        i += 1
print('fifo entries: %d' % len(fifo))

import pickle
pickle.dump({'fifo': fifo, 'mem_map': mem_map, 'mem_data': mem_data}, open('uw_capture4.pkl','wb'))
print('saved uw_capture4.pkl')
