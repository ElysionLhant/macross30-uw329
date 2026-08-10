#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uw_pack_center640.py - cockpit HUD 元素 x 平移变体生成器

在 data2.dat.cockpitin(已全补丁 2560) 基础上, 对 /data/cockpit/ 下 ark 中
所有 **2560x720 LAYO** 的关键帧轨迹段做 x += dx (默认 +640), 其它一律不动。

结构依据(EBOOT 解析器 + 差分验证):
  LAYO 头 "32c2s8i3i": name[0x20] @+0x10, 2s @+0x30,
      8i @+0x34..+0x53 = {0x78, flags, dur, nelt, w, h, elem_off(=0x50), track_off}
      3i @+0x54
  元素记录(0x50, "i4c2i32c8i") @chunk+0x60: 无位置字段, 只有 {size,tag,2i,name[32],8i={w,h,hw,hh,color,...}}
  轨迹段 @chunk+0x10+track_off: 关键帧块, 每块以 u32 0x00140034(LE 字节 34 00 14 00)开头,
      块内 +0x04 flags(=0x1f), +0x08 帧号, +0x14 = x, +0x18 = y (i32 LE, 设计画布坐标),
      +0x1c = RGBA color, +0x28 = 次要 x 增量(lader L/C/R 差分 -30/+30/+90, 不动),
      +0x34/+0x38 = scale (100,100)
  多关键帧 = 多个 marker 块串联; 只改 x, y/color/scale/delta 全保持

用法: python uw_pack_center640.py [src=data2.dat.cockpitin] [dst=data2.dat.center640] [dx=640] [path_filter=/data/cockpit/]
  path_filter 传 ALL 时处理全部 ark
"""
import os, re, sys, zlib, struct, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uw_pack_re import Pack, PACK_DIR
from uw_pack_patch import rebuild_segs

MARKER = b'\x34\x00\x14\x00'   # u32 0x00140034 LE


def center_blob(blob, dx, path, log):
    """对解压后 ark blob 做 x 平移. 返回 (new_bytes, n_patched, n_skipped, n_layo)"""
    if blob[:8] != b'ARK ARKF':
        return blob, 0, 0, 0
    d = bytearray(blob)
    n_patched = n_skipped = n_layo = 0
    for m in re.finditer(b'ARK LAYO', bytes(d)):
        b = m.start()
        size = struct.unpack('<I', d[b + 8:b + 12])[0]
        w, h = struct.unpack('<2I', d[b + 0x44:b + 0x4c])
        if (w, h) != (0xA00, 720):
            continue  # 只处理被加宽的 1280->2560 画布 LAYO; 小画布 LAYO 元素是局部坐标, 不动
        n_layo += 1
        track_off = struct.unpack('<I', d[b + 0x50:b + 0x54])[0]
        if track_off == 0:
            continue
        t0 = b + 0x10 + track_off
        t1 = b + 0x10 + size
        if t1 <= t0 or t1 > len(d):
            continue
        layo_nm = d[b + 0x10:b + 0x30].split(b'\x00')[0].decode('ascii', 'replace')
        # 段内扫描关键帧 marker
        seg = bytes(d[t0:t1])
        start = 0
        while True:
            j = seg.find(MARKER, start)
            if j < 0:
                break
            start = j + 1
            pos = t0 + j
            flags = struct.unpack('<I', d[pos + 4:pos + 8])[0]
            x, y = struct.unpack('<2i', d[pos + 0x14:pos + 0x1c])
            if (flags & 0x7FFFFFFF) != 0x1F or not (-4096 <= x <= 4096):
                n_skipped += 1
                log('  [SKIP] %s %s @%x flags=%x x=%d y=%d' % (path, layo_nm, pos, flags, x, y))
                continue
            struct.pack_into('<i', d, pos + 0x14, x + dx)
            n_patched += 1
    return bytes(d), n_patched, n_skipped, n_layo


def main():
    args = sys.argv[1:]
    excludes = []
    pos = []
    i = 0
    while i < len(args):
        if args[i] == '--exclude':
            excludes.append(args[i + 1])
            i += 2
        else:
            pos.append(args[i])
            i += 1
    src_name = pos[0] if len(pos) > 0 else 'data2.dat.cockpitin'
    dst_name = pos[1] if len(pos) > 1 else 'data2.dat.center640'
    dx = int(pos[2]) if len(pos) > 2 else 640
    path_filter = pos[3] if len(pos) > 3 else '/data/cockpit/'
    if path_filter == 'ALL':
        path_filter = ''
    src = src_name if (os.sep in src_name or '/' in src_name) else PACK_DIR + src_name
    dst = dst_name if (os.sep in dst_name or '/' in dst_name) else PACK_DIR + dst_name
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    p = Pack(dst)
    f = open(dst, 'r+b')
    tot_p = tot_s = 0
    nfile = 0
    loglines = []
    def log(s):
        print(s)
        loglines.append(s)
    for i, path, off, dec, stored in p.files():
        if path_filter and path_filter not in path:
            continue
        if excludes and any(x in path for x in excludes):
            continue
        if not path.lower().endswith('.ark'):
            continue
        blob, kind = p.read_file(off, dec, stored)
        new_dec, n_p, n_s, n_l = center_blob(blob, dx, path, log)
        if n_p == 0 and n_s == 0:
            continue
        orig_stored_len = stored if (stored and stored < dec) else dec
        raw_stored = bytes(p.mm[off:off + orig_stored_len])
        if n_p == 0:
            log('  [无有效关键帧] %s (layo2560=%d skipped=%d)' % (path, n_l, n_s))
            continue
        slot = ((orig_stored_len + 0x7FF) // 0x800) * 0x800
        if kind == 'zlib':
            new_stored = zlib.compress(new_dec, 9)
            if len(new_stored) > slot:
                import zopfli.zlib
                new_stored = zopfli.zlib.compress(new_dec)  # 更优 deflate, 仍合法 zlib 流
                log('  [zopfli] %s lvl9 超槽, zopfli 后 %x (slot %x)' % (path, len(new_stored), slot))
        elif kind == 'segs':
            new_stored = rebuild_segs(raw_stored, new_dec)
        else:
            new_stored = new_dec
        assert len(new_stored) <= slot, '槽位不足 %s' % path
        f.seek(off)
        f.write(new_stored)
        if len(new_stored) < slot:
            f.write(b'\x00' * (slot - len(new_stored)))
        if len(new_stored) != orig_stored_len:
            f.seek(p.hsz + i * 0x18 + 0x14)
            f.write(struct.pack('<I', len(new_stored)))
        log('PATCH %s [%s] layo2560=%d x关键帧 %+d x%d (skipped=%d) stored %x->%x' %
            (path, kind, n_l, dx, n_p, n_s, orig_stored_len, len(new_stored)))
        tot_p += n_p
        tot_s += n_s
        nfile += 1
    f.close()
    log('=== 合计: %d 个 ark, 平移关键帧 %d 处, 跳过 %d 处 ===' % (nfile, tot_p, tot_s))
    # ---- roundtrip: 与 src 逐 u32 diff, 只允许 x 字段 +dx ----
    q_src = Pack(src)
    q_new = Pack(dst)
    bad = 0
    checked = 0
    ndiff = 0
    for i, path, off, dec, stored in q_new.files():
        if not path.lower().endswith('.ark'):
            continue
        bn, _ = q_new.read_file(off, dec, q_new.recs[i][5])
        bo, _ = q_src.read_file(off, dec, q_src.recs[i][5])
        if bn == bo:
            continue
        checked += 1
        assert len(bn) == len(bo) and bn[:8] == b'ARK ARKF'
        for u in range(0, len(bo) - 4, 4):
            ov = struct.unpack('<i', bo[u:u + 4])[0]
            nv = struct.unpack('<i', bn[u:u + 4])[0]
            if ov == nv:
                continue
            ndiff += 1
            if nv - ov == dx:
                pass
            else:
                bad += 1
                print('!! 非法改动 %s @%x: %d -> %d' % (path, u, ov, nv))
    print('roundtrip: %d 个 ark 有差异, 差异 u32 共 %d (应等于平移数 %d), 非法 %d -> %s' %
          (checked, ndiff, tot_p, bad, 'ALL OK' if (bad == 0 and ndiff == tot_p) else 'FAILED'))
    with open('C:/Users/Elysion/Desktop/UW32_Macross30/data/uw_center_%s.log' % os.path.basename(dst).replace('.', '_'), 'w', encoding='utf-8') as lf:
        lf.write('\n'.join(loglines))


if __name__ == '__main__':
    main()
