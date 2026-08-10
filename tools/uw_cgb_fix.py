#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uw_cgb_fix.py - vs_ScreenToClipspace 系 HUD 顶点着色器居中补丁变体生成器
(agent-1 VP 分析结论落地)

对 4 个 cgb (rec_idx 26288-26291) 解压内容各打 2 点:
  dec+0xAB: E0 -> F8   (末条 MAD 加数 swizzle .xxxx -> .wxxx, X 偏移改指 c466.w)
  dec+0xCC: 00000000 -> 3F000000  (c466.w: 0.0 -> 0.5)
效果: o.x = px*(2/2560) - 0.5 -> HUD 内容居中 (UV [0.25,0.75])

用法: python uw_cgb_fix.py [src=shaders.dat.bak] [dst=shaders.dat.cgbfix]
"""
import os, sys, zlib, struct, shutil, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uw_pack_re import Pack, PACK_DIR

RECS = [26288, 26289, 26290, 26291]
PATCH = ((0xAB, b'\xe0', b'\xf8'), (0xCC, b'\x00\x00\x00\x00', b'\x3f\x00\x00\x00'))


def main():
    src_name = sys.argv[1] if len(sys.argv) > 1 else 'shaders.dat.bak'
    dst_name = sys.argv[2] if len(sys.argv) > 2 else 'shaders.dat.cgbfix'
    src = src_name if (os.sep in src_name or '/' in src_name) else PACK_DIR + src_name
    dst = dst_name if (os.sep in dst_name or '/' in dst_name) else PACK_DIR + dst_name
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    p = Pack(dst)
    f = open(dst, 'r+b')
    for idx in RECS:
        fl, noff, f2, off, dec, stored = p.recs[idx]
        path = p.paths.get(idx, '<orphan>/' + p.cstr(noff))
        blob, kind = p.read_file(off, dec, stored)
        assert kind == 'zlib', '%s 非 zlib(%s), 跳过' % (path, kind)
        d = bytearray(blob)
        for poff, old, new in PATCH:
            assert bytes(d[poff:poff + len(old)]) == old, '%s @%x 前件不符' % (path, poff)
            d[poff:poff + len(old)] = new
        new_stored = zlib.compress(bytes(d), 9)
        assert zlib.decompress(new_stored) == bytes(d)
        slot = ((stored + 0x7FF) // 0x800) * 0x800
        assert len(new_stored) <= slot, '%s 超槽' % path
        f.seek(off)
        f.write(new_stored)
        if len(new_stored) < slot:
            f.write(b'\x00' * (slot - len(new_stored)))
        if len(new_stored) != stored:
            f.seek(p.hsz + idx * 0x18 + 0x14)
            f.write(struct.pack('<I', len(new_stored)))
        print('PATCH %-40s stored %x -> %x (slot %x)' % (path, stored, len(new_stored), slot))
    f.close()
    # roundtrip: 与 src 比
    q_src = Pack(src)
    q_new = Pack(dst)
    bad = 0
    nfiles = 0
    # 记录表比对
    rec_diff = [i for i in range(q_new.nrec) if q_new.recs[i] != q_src.recs[i]]
    for i in rec_diff:
        a, b = q_src.recs[i], q_new.recs[i]
        if not (a[:5] == b[:5] and a[5] != b[5]):
            print('!! 记录 %d 非法差异: %s -> %s' % (i, a, b))
            bad += 1
    print('记录表差异: %d 条 %s' % (len(rec_diff), rec_diff))
    # 内容比对
    for idx in RECS:
        fl, noff, f2, off, dec, stored = q_new.recs[idx]
        path = q_new.paths.get(idx)
        bn, _ = q_new.read_file(off, dec, q_new.recs[idx][5])
        bo, _ = q_src.read_file(off, dec, q_src.recs[idx][5])
        diffs = [(u, bo[u], bn[u]) for u in range(len(bo)) if bo[u] != bn[u]]
        expect = [(0xAB, 0xE0, 0xF8), (0xCC, 0, 0x3F)]
        ok = diffs == expect
        nfiles += 1
        if not ok:
            bad += 1
            print('!! %s 差异不符: %s' % (path, diffs[:8]))
        else:
            print('VERIFY OK %-40s 仅 2 点差异 (0xAB, 0xCC-0xCF)' % path)
    print('roundtrip: %s' % ('ALL OK' if bad == 0 and len(rec_diff) <= 4 else 'FAILED'))
    h = hashlib.md5()
    with open(dst, 'rb') as fh:
        for c in iter(lambda: fh.read(1 << 24), b''):
            h.update(c)
    print('md5:', h.hexdigest())


if __name__ == '__main__':
    main()
