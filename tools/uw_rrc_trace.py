# -*- coding: utf-8 -*-
# FIFO 帧结构分析 v2: 正确的 GCM 语义
import pickle, struct

d = pickle.load(open('uw_capture2.pkl','rb'))
fifo = d['fifo']

def f32(w):
    return struct.unpack('<f', struct.pack('<I', w))[0]

out = []
vp = None
surf = None
consts = []
in_begin = False
seg_id = 0
pending = []  # recent events for context

for idx, item in enumerate(fifo):
    if item[0] == 'SPECIAL':
        continue
    reg, vals = item
    line = None
    if reg == 0x200:
        line = 'SURF_CLIP_H x=%d w=%d' % (vals[0] >> 16, vals[0] & 0xFFFF)
    elif reg == 0x204:
        line = 'SURF_CLIP_V y=%d h=%d' % (vals[0] >> 16, vals[0] & 0xFFFF)
    elif reg == 0x208:
        line = 'SURF_FORMAT 0x%08x' % vals[0]
        surf = vals[0]
    elif reg == 0xA00:
        line = 'VIEWPORT_H x=%d w=%d' % (vals[0] >> 16, vals[0] & 0xFFFF)
        vp = vals[0]
    elif reg == 0xA04:
        line = 'VIEWPORT_V y=%d h=%d' % (vals[0] >> 16, vals[0] & 0xFFFF)
    elif reg == 0x8C0:
        line = 'SCISSOR_H x=%d w=%d' % (vals[0] >> 16, vals[0] & 0xFFFF)
    elif reg == 0x8C4:
        line = 'SCISSOR_V y=%d h=%d' % (vals[0] >> 16, vals[0] & 0xFFFF)
    elif reg == 0xA20:
        line = 'VIEWPORT_OFFSET ' + ' '.join('%.3f' % f32(v) for v in vals)
    elif reg == 0xA30:
        line = 'VIEWPORT_SCALE ' + ' '.join('%.3f' % f32(v) for v in vals)
    elif reg == 0x1F00:
        line = 'TRANSFORM_CONST x%d' % len(vals)
        consts.append((idx, vals))
    elif reg == 0xB80:
        line = 'TRANSFORM_PROGRAM x%d' % len(vals)
    elif reg == 0x1808:
        if vals[0] != 0:
            line = 'BEGIN mode=%d' % vals[0]
            in_begin = True
        else:
            line = 'END'
            in_begin = False
    elif reg == 0x1814:
        line = 'DRAW_ARRAYS first=%d count=%d' % (vals[0] & 0xFFFFFF, vals[0] >> 24)
    elif reg == 0x1824:
        line = 'DRAW_INDEX first=%d count=%d' % (vals[0] & 0xFFFFFF, vals[0] >> 24)
    elif reg == 0x1818:
        line = 'INLINE_ARRAY x%d' % len(vals)
    elif reg == 0x1680:
        line = 'VTX_OFFSET 0x%08x' % vals[0]
    elif reg == 0x1740:
        line = 'VTX_FORMAT 0x%08x' % vals[0]
    elif reg == 0x181C:
        line = 'INDEX_ADDR 0x%08x' % vals[0]
    if line:
        out.append('@%5d %s' % (idx, line))

open('uw_fifo_trace2.txt','w').write('\n'.join(out))
print('%d trace lines -> uw_fifo_trace2.txt' % len(out))
# 概要: BEGIN..END 段统计
print('transform const uploads: %d' % len(consts))
