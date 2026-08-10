# -*- coding: utf-8 -*-
# 精确解码 vs_ScreenToClipspace 微码的每条指令字段
import struct

VEC_OPS = ["NOP","MOV","MUL","ADD","MAD","DP3","DPH","DP4","DST","MIN","MAX","SLT","SGE","ARL","FRC","FLR",
           "SEQ","SFL","SGT","SLE","SNE","STR","SSG","?","?","TXL"]
SCA_OPS = ["NOP","MOV","RCP","RCC","RSQ","EXP","LOG","LIT","BRA","BRI","CAL","CLI","RET","LG2","EX2","SIN",
           "COS","BRB","CLB","PSH","POP"]

def src_str(v17, const_src, input_src, index_const):
    rt = v17 & 3
    tmp = (v17 >> 2) & 0x3F
    sw = ((v17 >> 14) & 3, (v17 >> 12) & 3, (v17 >> 10) & 3, (v17 >> 8) & 3)
    neg = (v17 >> 16) & 1
    if rt == 0:
        return 'unused(0)'
    if rt == 1:
        r = 'R%d' % tmp
    elif rt == 2:
        r = 'v[%d]' % input_src
    else:
        r = 'c[%d]' % const_src + ('+A0' if index_const else '')
    r += '.' + ''.join('xyzw'[i] for i in sw)
    if neg:
        r = '-' + r
    return r

def decode(words, idx):
    d0, d1, d2, d3 = words
    f = {}
    f['cond'] = (d0 >> 10) & 7
    f['cond_test'] = (d0 >> 13) & 1
    f['dst_tmp'] = (d0 >> 15) & 0x3F
    f['sat'] = (d0 >> 26) & 1
    f['vec_result'] = (d0 >> 30) & 1
    f['input_src'] = (d1 >> 8) & 0xF
    f['const_src'] = (d1 >> 12) & 0x3FF
    f['vec_op'] = (d1 >> 22) & 0x1F
    f['sca_op'] = (d1 >> 27) & 0x1F
    src0h = d1 & 0xFF
    src0l = (d2 >> 23) & 0x1FF
    f['src0'] = src0l | (src0h << 9)
    f['src1'] = (d2 >> 6) & 0x1FFFF
    src2h = d2 & 0x3F
    src2l = (d3 >> 21) & 0x7FF
    f['src2'] = src2l | (src2h << 11)
    f['end'] = d3 & 1
    f['index_const'] = (d3 >> 1) & 1
    f['dst'] = (d3 >> 2) & 0x1F
    f['sca_dst_tmp'] = (d3 >> 7) & 0x3F
    f['vmask'] = ''.join(c for c, b in zip('xyzw', [(d3>>16)&1, (d3>>15)&1, (d3>>14)&1, (d3>>13)&1]) if b)
    f['smask'] = ''.join(c for c, b in zip('xyzw', [(d3>>20)&1, (d3>>19)&1, (d3>>18)&1, (d3>>17)&1]) if b)
    return f

def show(idx, words):
    f = decode(words, idx)
    cs, isrc, ic = f['const_src'], f['input_src'], f['index_const']
    print('[%d] vec=%s sca=%s | dst o[%d] vmask=%s | tmpR%d | sca_tmpR%d smask=%s | sat=%d vecres=%d end=%d' % (
        idx, VEC_OPS[f['vec_op']], SCA_OPS[f['sca_op']], f['dst'], f['vmask'] or '-',
        f['dst_tmp'], f['sca_dst_tmp'], f['smask'] or '-', f['sat'], f['vec_result'], f['end']))
    print('     src0=%s' % src_str(f['src0'], cs, isrc, ic))
    print('     src1=%s' % src_str(f['src1'], cs, isrc, ic))
    print('     src2=%s' % src_str(f['src2'], cs, isrc, ic))

import sys
hexstr = open(sys.argv[1]).read().strip() if len(sys.argv) > 1 else None
blob = bytes.fromhex(hexstr)
ucode_off = 0x20
for a in range(9):
    w4 = struct.unpack('>4I', blob[ucode_off + a*16: ucode_off + a*16 + 16])
    show(a, w4)
