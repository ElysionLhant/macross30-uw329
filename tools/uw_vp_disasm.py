# -*- coding: utf-8 -*-
# VP 微码反汇编 (NV40/RSX 128-bit BE) + 会话分组 + vc[467] 引用定位
import pickle, struct, sys

PKL = sys.argv[1] if len(sys.argv) > 1 else 'uw_capture.pkl'
d = pickle.load(open(PKL, 'rb'))
fifo = d['fifo']

PROG_DATA, PROG_LOAD, PROG_START = 0x0B80, 0x1E9C, 0x1EA0
CONST_DATA, CONST_LOAD = 0x1F00, 0x1EFC

# ---------- 会话分组: load=0 开始新会话，后续连续地址续写 ----------
prog_load = 0
prog_start = 0
sessions = []  # {'start_idx':, 'end_idx':, 'words': {addr: [4 words]}}
cur = None
const_load = 0
slot467_marks = []  # fifo idx where slot467 = {1/1280,...} or {2/1280,...}

def f32(w):
    return struct.unpack('<f', struct.pack('<I', w & 0xFFFFFFFF))[0]

for idx, item in enumerate(fifo):
    if item[0] == 'SPECIAL':
        continue
    reg, vals = item
    if reg == PROG_LOAD:
        prog_load = vals[0]
        if prog_load == 0:
            cur = {'start_idx': idx, 'end_idx': idx, 'words': {}, 'start_val': prog_start}
            sessions.append(cur)
    elif reg == PROG_START:
        prog_start = vals[0]
        if cur is not None:
            cur['start_val'] = prog_start
    elif reg == CONST_LOAD:
        const_load = vals[0]
    elif reg == CONST_DATA:
        for i in range(0, len(vals) - 3, 4):
            slot = const_load + i // 4
            if slot == 467:
                w = vals[i:i+4]
                if w[0] in (0x3A4CCCCD, 0x3ACCCCCD, 0x3A088889):
                    slot467_marks.append((idx, w))
        const_load += len(vals) // 4
    elif reg == PROG_DATA:
        if cur is not None:
            for i in range(0, len(vals) - 3, 4):
                addr = prog_load + i // 4
                cur['words'][addr] = vals[i:i+4]
            cur['end_idx'] = idx
        prog_load += len(vals) // 4

if __name__ == '__main__':
    print('sessions: %d' % len(sessions))
    print('slot467 marks: %d (first %s)' % (len(slot467_marks), slot467_marks[:3]))

# ---------- 反汇编 ----------
VEC_OPS = ["NOP","MOV","MUL","ADD","MAD","DP3","DPH","DP4","DST","MIN","MAX","SLT","SGE","ARL","FRC","FLR",
           "SEQ","SFL","SGT","SLE","SNE","STR","SSG","?","?","TXL","?","?","?","?","?","?","?"]
SCA_OPS = ["NOP","MOV","RCP","RCC","RSQ","EXP","LOG","LIT","BRA","BRI","CAL","CLI","RET","LG2","EX2","SIN",
           "COS","BRB","CLB","PSH","POP","?","?","?","?","?","?","?","?","?","?","?"]

def parse_src(v17):
    reg_type = v17 & 3
    tmp_src = (v17 >> 2) & 0x3F
    swz_w = (v17 >> 8) & 3
    swz_z = (v17 >> 10) & 3
    swz_y = (v17 >> 12) & 3
    swz_x = (v17 >> 14) & 3
    neg = (v17 >> 16) & 1
    return reg_type, tmp_src, (swz_x, swz_y, swz_z, swz_w), neg

def disasm(words):
    d0, d1, d2, d3 = words
    # d0 fields
    d0_dst_tmp = (d0 >> 15) & 0x3F
    src0_abs = (d0 >> 21) & 1
    src1_abs = (d0 >> 22) & 1
    src2_abs = (d0 >> 23) & 1
    saturate = (d0 >> 26) & 1
    cond_upd0 = (d0 >> 14) & 1
    cond_upd1 = (d0 >> 29) & 1
    vec_result = (d0 >> 30) & 1
    cond = (d0 >> 10) & 7
    cond_test = (d0 >> 13) & 1
    # d1
    src0h = d1 & 0xFF
    input_src = (d1 >> 8) & 0xF
    const_src = (d1 >> 12) & 0x3FF
    vec_op = (d1 >> 22) & 0x1F
    sca_op = (d1 >> 27) & 0x1F
    # d2
    src2h = d2 & 0x3F
    src1 = (d2 >> 6) & 0x1FFFF
    src0l = (d2 >> 23) & 0x1FF
    # d3
    end = d3 & 1
    index_const = (d3 >> 1) & 1
    dst = (d3 >> 2) & 0x1F
    sca_dst_tmp = (d3 >> 7) & 0x3F
    vw = (d3 >> 13) & 1; vz = (d3 >> 14) & 1; vy = (d3 >> 15) & 1; vx = (d3 >> 16) & 1
    sw = (d3 >> 17) & 1; sz = (d3 >> 18) & 1; sy = (d3 >> 19) & 1; sx = (d3 >> 20) & 1
    src2l = (d3 >> 21) & 0x7FF

    src0 = src0l | (src0h << 9)
    src2 = src2l | (src2h << 11)

    def fmt_src(v17, absf):
        rt, tmp, swz, neg = parse_src(v17)
        if rt == 0:
            return '-'
        if rt == 1:
            r = 'R%d' % tmp
        elif rt == 2:
            r = 'v[%d]' % input_src
        else:
            r = 'c[%d]' % const_src + ('+A0' if index_const else '')
        f = 'xyzw'
        s = ''.join(f[i] for i in swz)
        if s != 'xyzw':
            r += '.' + s
        if absf:
            r = '|' + r + '|'
        if neg:
            r = '-' + r
        return r

    NSRC = {'MOV':1,'ARL':1,'FRC':1,'FLR':1,'SSG':1,'MUL':2,'ADD':2,'DP3':2,'DPH':2,'DP4':2,
            'DST':2,'MIN':2,'MAX':2,'SLT':2,'SGE':2,'SEQ':2,'SFL':2,'SGT':2,'SLE':2,'SNE':2,
            'STR':2,'MAD':3,'TXL':1}

    vmask = ''.join(c for c, m in zip('wzyx', (vw, vz, vy, vx)) if m)[::-1]
    smask = ''.join(c for c, m in zip('wzyx', (sw, sz, sy, sx)) if m)[::-1]

    parts = []
    if vec_op:
        dsts = []
        if vec_result and dst != 0x1F:
            dsts.append('o[%d]' % dst)
        if d0_dst_tmp != 0x3F:
            dsts.append('R%d' % d0_dst_tmp)
        dtxt = ','.join(dsts) if dsts else ('CC' if (cond_upd0 or cond_upd1) else '??')
        ns = NSRC.get(VEC_OPS[vec_op], 3)
        srcs = [fmt_src(s, a) for s, a in ((src0, src0_abs), (src1, src1_abs), (src2, src2_abs))][:ns]
        parts.append('%s%s %s.%s, %s' % (
            VEC_OPS[vec_op], 's' if saturate else '', dtxt, vmask or '-',
            ', '.join(srcs)))
    if sca_op:
        dsts = []
        if not vec_result and dst != 0x1F:
            dsts.append('o[%d]' % dst)
        if sca_dst_tmp != 0x3F:
            dsts.append('R%d' % sca_dst_tmp)
        dtxt = ','.join(dsts) if dsts else ('CC' if (cond_upd0 or cond_upd1) else '??')
        parts.append('%s%s %s.%s, %s' % (
            SCA_OPS[sca_op], 's' if saturate else '', dtxt, smask or '-',
            fmt_src(src2, src2_abs)))
    if not parts:
        parts.append('NOP')
    out = ' ; '.join(parts)
    if end:
        out += '  END'
    return out, (vec_op, sca_op, const_src, [parse_src(s)[0] for s in (src0, src1, src2)], dst, vec_result)

# ---------- 分析每个会话 ----------
if __name__ == '__main__':
    print()
    for si, s in enumerate(sessions):
        words = s['words']
        if not words:
            continue
        maxa = max(words)
        refs467 = []
        lines = []
        for a in range(maxa + 1):
            if a not in words:
                lines.append((a, '<missing>', None))
                continue
            txt, meta = disasm(words[a])
            vec_op, sca_op, const_src, rts, dst, vec_result = meta
            if 3 in rts and const_src == 467:
                refs467.append(a)
            lines.append((a, txt, meta))
        mark = ' <== uses c[467] at %s' % refs467 if refs467 else ''
        print('--- session %d @fifo %d..%d, %d instrs, entry=%d%s' % (
            si, s['start_idx'], s['end_idx'], maxa + 1, s['start_val'], mark))
        if refs467 or si < 2:
            for a, txt, meta in lines:
                print('    [%2d] %s' % (a, txt))
