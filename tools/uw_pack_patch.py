#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uw_pack_patch.py - Macross 30 pack 内 LAYO 1280x720 -> 2560x720 原位补丁器

补丁内容(严格过滤):
  1) LAYO 头 {w=0x500,h=0x2D0}@+0x44/+0x48 -> {0xA00,0x2D0}   (只动恰好 1280x720 的 LAYO)
  2) LAYO 内元素级 canvas 记录 {0x500,0x2D0,0x280,0x168} -> {0xA00,0x2D0,0x500,0x168}
     (16 字节全匹配才改; 不匹配半宽/半高的 LE32pair 视为 anomaly 跳过)
  3) TXOS 内 8 处纹理尺寸不碰; 小部件 LAYO(非 1280x720)一律不碰

存储回写:
  zlib ark -> zlib.compress(dec,9) (已验证与游戏压缩器字节级一致)
  segs ark -> 0x10000 分段 raw-deflate(level 9) 重建 (已验证 <= 原 stored)
  新 stored <= 原 0x800 对齐槽才写; 仅更新记录 stored 字段(定长); 不动偏移/pack.idx

用法:
  python uw_pack_patch.py --dry-run [--include 子串 ...] [--exclude 子串 ...] [--file 目标 ...]
  python uw_pack_patch.py --apply   [--include 子串 ...] [--exclude 子串 ...] [--file 目标 ...]
  python uw_pack_patch.py --restore-from-bak               # 从 .bak 恢复(仅标准包)
  --include 可多次: 只补丁路径含任一子串的 ark (与 --exclude 可叠加)
  --exclude 可多次: ark 路径含任一子串时跳过其全部补丁点
  --file    可多次: 覆盖目标包(默认 data.dat+data2.dat); 可指变体副本
            (如 data.dat.dialogonly, 参照原版自动映射 data.dat.bak, 不做备份)
"""
import os, re, sys, zlib, struct, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uw_pack_re import Pack, PACK_DIR

TARGETS = ['data.dat', 'data2.dat']
ELEM_PAT = b'\x00\x05\x00\x00\xd0\x02\x00\x00\x80\x02\x00\x00\x68\x01\x00\x00'  # {1280,720,640,360}
ELEM_REP = b'\x00\x0a\x00\x00\xd0\x02\x00\x00\x00\x05\x00\x00\x68\x01\x00\x00'  # {2560,720,1280,360}
LE32PAIR = b'\x00\x05\x00\x00\xd0\x02\x00\x00'
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uw_pack_patch.log')


def patch_dec(dec):
    """在解压后的 ark blob 上打补丁. 返回 (new_bytes, n_hdr, n_elem, n_layo_skip, n_anomaly)"""
    if dec[:8] != b'ARK ARKF':
        return dec, 0, 0, 0, -1
    d = bytearray(dec)
    n_hdr = n_skip = 0
    layos = []
    for m in re.finditer(b'ARK LAYO', bytes(d)):
        b = m.start()
        w, h = struct.unpack('<2I', d[b + 0x44:b + 0x4c])
        if (w, h) == (1280, 720):
            struct.pack_into('<I', d, b + 0x44, 0xA00)
            n_hdr += 1
        else:
            n_skip += 1
        size = struct.unpack('<I', d[b + 8:b + 12])[0]
        layos.append((b, b + 0x10 + size))
    if not layos:
        return dec, 0, 0, 0, 0
    hdr_pos = set(b + 0x44 for b, _ in layos)
    n_elem = 0
    for b0, b1 in layos:
        seg = bytes(d[b0:b1])
        start = 0
        while True:
            i = seg.find(ELEM_PAT, start)
            if i < 0:
                break
            pos = b0 + i
            start = i + 1
            if pos in hdr_pos:
                continue
            d[pos:pos + 16] = ELEM_REP
            n_elem += 1
    # anomaly: 补丁后 LAYO 内仍残留 {0x500,0x2D0}(半宽/半高不匹配的记录)
    n_anom = 0
    for b0, b1 in layos:
        seg = bytes(d[b0:b1])
        start = 0
        while True:
            i = seg.find(LE32PAIR, start)
            if i < 0:
                break
            n_anom += 1
            start = i + 1
    return bytes(d), n_hdr, n_elem, n_skip, n_anom


def rebuild_segs(orig_blob, new_dec):
    """按 0x10000 分段 raw-deflate 重建 segs 容器"""
    segs = []
    pos = 0
    while pos < len(new_dec):
        chunk = new_dec[pos:pos + 0x10000]
        c = zlib.compressobj(9, zlib.DEFLATED, -15)
        cc = c.compress(chunk) + c.flush()
        if len(cc) > 0xFFFF:
            raise ValueError('segment too big for u16: %x' % len(cc))
        segs.append((cc, len(chunk)))
        pos += len(chunk)
    nseg = len(segs)
    tabend = (0x10 + nseg * 8 + 0xF) & ~0xF
    tab = b''
    payload = b''
    for cc, dl in segs:
        tab += struct.pack('>H', len(cc)) + struct.pack('>H', 0 if dl == 0x10000 else dl) \
               + b'\x00\x00' + struct.pack('>H', (tabend + len(payload) + 1) & 0xFFFF)
        payload += cc
    total = tabend + len(payload)
    if total > 0xFFFF:
        raise ValueError('segs total too big for u16 offsets: %x' % total)
    new = b'segs' + struct.pack('>HH', 5, nseg) + struct.pack('>I', len(new_dec)) \
          + struct.pack('>I', total) + tab
    new += b'\x00' * (tabend - len(new)) + payload
    return new


def analyze(targets=TARGETS, includes=(), excludes=()):
    """只读分析: 返回每包改动计划 [(rec_idx, path, off, dec, stored, kind, new_stored_len, n_hdr, n_elem)]
    includes: 非空时只补丁路径含任一子串的 ark
    excludes: 路径含任一子串的 ark 整个跳过(仍统计其补丁点数供汇报)"""
    plans = {}
    stats = dict(hdr=0, elem=0, skip=0, anom=0, noarkf=0, overflow=0, files=0,
                 excl_files=0, excl_hdr=0, excl_elem=0, excl_paths=[],
                 incl_skip=0)
    for fn in targets:
        p = Pack(fn) if os.sep in fn or '/' in fn else Pack(PACK_DIR + fn)
        plan = []
        for i, path, off, dec, stored in p.files():
            if not path.lower().endswith('.ark'):
                continue
            if excludes and any(x in path for x in excludes):
                blob, kind = p.read_file(off, dec, stored)
                _, nh, ne, _, _ = patch_dec(blob)
                if nh or ne:
                    stats['excl_files'] += 1
                    stats['excl_hdr'] += nh
                    stats['excl_elem'] += ne
                    stats['excl_paths'].append('%s %s (hdr=%d elem=%d)' % (os.path.basename(fn), path, nh, ne))
                continue
            if includes and not any(x in path for x in includes):
                stats['incl_skip'] += 1
                continue
            blob, kind = p.read_file(off, dec, stored)
            new_dec, n_hdr, n_elem, n_skip, n_anom = patch_dec(blob)
            if n_anom == -1:
                stats['noarkf'] += 1
                continue
            stats['skip'] += n_skip
            stats['anom'] += n_anom
            if n_hdr == 0 and n_elem == 0:
                continue
            # 计算新 stored
            orig_stored_len = stored if (stored and stored < dec) else dec
            raw_stored = bytes(p.mm[off:off + orig_stored_len])
            try:
                if kind == 'zlib':
                    new_stored = zlib.compress(new_dec, 9)
                elif kind == 'segs':
                    new_stored = rebuild_segs(raw_stored, new_dec)
                else:  # raw ARKF: 直接等长写
                    new_stored = new_dec
            except ValueError as e:
                stats['overflow'] += 1
                plan.append((i, path, off, dec, stored, kind, -1, n_hdr, n_elem, str(e)))
                continue
            slot = ((orig_stored_len + 0x7FF) // 0x800) * 0x800
            if len(new_stored) > slot:
                stats['overflow'] += 1
                plan.append((i, path, off, dec, stored, kind, -2, n_hdr, n_elem,
                             'slot %x < new %x' % (slot, len(new_stored))))
                continue
            plan.append((i, path, off, dec, stored, kind, len(new_stored), n_hdr, n_elem, ''))
            stats['hdr'] += n_hdr
            stats['elem'] += n_elem
            stats['files'] += 1
        plans[fn] = (p, plan)
    return plans, stats


def do_backup(targets=TARGETS):
    for fn in targets:
        base = os.path.basename(fn)
        if base not in TARGETS:
            print('变体文件无需备份: %s' % fn)
            continue
        src = fn if (os.sep in fn or '/' in fn) else PACK_DIR + fn
        dst = src + '.bak'
        if os.path.exists(dst):
            print('备份已存在, 跳过: %s' % dst)
            continue
        print('备份 %s -> %s ...' % (src, dst))
        shutil.copyfile(src, dst)
        print('  done (%d bytes)' % os.path.getsize(dst))


def do_restore():
    for fn in TARGETS:
        bak = PACK_DIR + fn + '.bak'
        if not os.path.exists(bak):
            print('无备份, 跳过: %s' % bak)
            continue
        shutil.copyfile(bak, PACK_DIR + fn)
        print('已恢复 %s' % fn)


def do_apply(plans, targets=TARGETS):
    do_backup(targets)
    log = open(LOG_PATH, 'w', encoding='utf-8')
    for fn in targets:
        p, plan = plans[fn]
        if not plan:
            p.mm.close()
            p.fd.close()
            continue
        path_fn = fn if (os.sep in fn or '/' in fn) else PACK_DIR + fn
        f = open(path_fn, 'r+b')
        nwrite = 0
        for rec in plan:
            i, path, off, dec, stored, kind, new_len, n_hdr, n_elem, note = rec
            if new_len < 0:
                log.write('SKIP_OVERFLOW %s %s %s\n' % (fn, path, note))
                continue
            orig_stored_len = stored if (stored and stored < dec) else dec
            raw_stored = bytes(p.mm[off:off + orig_stored_len])
            blob, kind2 = p.read_file(off, dec, stored)
            assert kind2 == kind and blob[:8] == b'ARK ARKF', 'kind/magic changed: %s' % path
            new_dec, nh, ne, _, _ = patch_dec(blob)
            assert nh == n_hdr and ne == n_elem, 'patch count changed: %s' % path
            if kind == 'zlib':
                new_stored = zlib.compress(new_dec, 9)
            elif kind == 'segs':
                new_stored = rebuild_segs(raw_stored, new_dec)
            else:
                new_stored = new_dec
            assert len(new_stored) == new_len, 'recompute mismatch %s' % path
            slot = ((orig_stored_len + 0x7FF) // 0x800) * 0x800
            f.seek(off)
            f.write(new_stored)
            if new_len < slot:
                f.write(b'\x00' * (slot - new_len))
            if new_len != orig_stored_len:
                # 更新记录 stored 字段 (hsz + i*0x18 + 0x14), 定长原地位
                f.seek(p.hsz + i * 0x18 + 0x14)
                f.write(struct.pack('<I', new_len))
            log.write('PATCH %s %-50s kind=%-4s stored %x -> %x (slot %x) hdr=%d elem=%d\n' %
                      (fn, path, kind, orig_stored_len, new_len, slot, n_hdr, n_elem))
            nwrite += 1
        f.close()
        p.mm.close()
        p.fd.close()
        print('%s: 写入 %d 个 ark' % (fn, nwrite))
    log.close()
    print('明细日志: %s' % LOG_PATH)


def do_verify(plans, targets=TARGETS, includes=(), excludes=(), refmap=None):
    """roundtrip 严格验证:
    1) 记录表与参照原版(.bak)比对 — 仅 stored 字段允许不同
    2) 名字池/文件尺寸不变
    3) 每个被改 ark 解压后与原版做 u32 粒度 diff:
       只允许 LAYO 内 0x500->0xA00(头+元素w) 与 0x280->0x500(元素半宽)
    4) 未命中 include / 命中 exclude 的 ark: 与原版逐字节一致且记录未动
    refmap: {目标文件路径: 参照 .bak 路径}, 缺省 <目标>.bak
    """
    ok = True
    tot = {'hdr': 0, 'elem_w': 0, 'elem_hw': 0, 'bad': 0}
    for fn in targets:
        path_fn = fn if (os.sep in fn or '/' in fn) else PACK_DIR + fn
        bak = (refmap or {}).get(fn, path_fn + '.bak')
        if not os.path.exists(bak):
            print('!! 无参照 .bak, 跳过比对 %s' % fn)
            ok = False
            continue
        p_new = Pack(path_fn)
        p_old = Pack(bak)
        changed_recs = 0
        for i in range(p_new.nrec):
            r_new, r_old = p_new.recs[i], p_old.recs[i]
            if r_new != r_old:
                if r_new[:5] == r_old[:5] and r_new[5] != r_old[5]:
                    changed_recs += 1
                else:
                    print('!! %s 记录 %d 非法差异: %s -> %s' % (fn, i, r_old, r_new))
                    ok = False
        if p_new.pool != p_old.pool:
            print('!! %s 名字池被改!' % fn)
            ok = False
        if os.path.getsize(path_fn) != os.path.getsize(bak):
            print('!! %s 文件尺寸变化!' % fn)
            ok = False
        res = {'hdr': 0, 'elem_w': 0, 'elem_hw': 0, 'bad': 0}
        nfile = nexcl = 0
        for i, path, off, dec, stored in p_new.files():
            if not path.lower().endswith('.ark'):
                continue
            rn, ro = p_new.recs[i], p_old.recs[i]
            targeted = (not includes or any(x in path for x in includes)) and \
                       (not excludes or not any(x in path for x in excludes))
            bn, _ = p_new.read_file(off, dec, rn[5])
            bo, _ = p_old.read_file(off, dec, ro[5])
            if not targeted:
                if bn != bo or rn != ro:
                    print('!! 未纳入项被改动: %s %s (blob_eq=%s rec_eq=%s)' %
                          (fn, path, bn == bo, rn == ro))
                    ok = False
                else:
                    nexcl += 1
                continue
            if bn == bo:
                continue
            nfile += 1
            if len(bn) != len(bo) or bn[:8] != b'ARK ARKF':
                print('!! %s %s 解压异常' % (fn, path))
                ok = False
                continue
            layos = []
            for m in re.finditer(b'ARK LAYO', bo):
                b = m.start()
                size = struct.unpack('<I', bo[b + 8:b + 12])[0]
                layos.append((b, b + 0x10 + size))
            hdrpos = set(b + 0x44 for b, _ in layos)
            for u in range(0, len(bo) - 4, 4):
                ov = struct.unpack('<I', bo[u:u + 4])[0]
                nv = struct.unpack('<I', bn[u:u + 4])[0]
                if ov == nv:
                    continue
                inlayo = any(b0 <= u < b1 for b0, b1 in layos)
                if ov == 0x500 and nv == 0xA00 and u in hdrpos and inlayo:
                    res['hdr'] += 1
                elif ov == 0x500 and nv == 0xA00 and inlayo:
                    res['elem_w'] += 1
                elif ov == 0x280 and nv == 0x500 and inlayo:
                    res['elem_hw'] += 1
                else:
                    res['bad'] += 1
                    print('!! 非法改动 %s %s @%x: %x -> %x (in LAYO: %s)' %
                          (fn, path, u, ov, nv, inlayo))
                    ok = False
        print('%s: 记录差异 %d 条(仅 stored), 改动 ark %d 个, 排除未动 ark %d 个, 头w=%d 元素w=%d 半宽=%d 非法=%d' %
              (fn, changed_recs, nfile, nexcl, res['hdr'], res['elem_w'], res['elem_hw'], res['bad']))
        for k in tot:
            tot[k] += res[k]
    print('TOTAL: 头w=%d 元素w=%d 半宽=%d 非法=%d' % (tot['hdr'], tot['elem_w'], tot['elem_hw'], tot['bad']))
    return ok


def main():
    args = sys.argv[1:]
    excludes, includes, files = [], [], []
    mode = None
    i = 0
    while i < len(args):
        if args[i] == '--exclude':
            excludes.append(args[i + 1])
            i += 2
        elif args[i] == '--include':
            includes.append(args[i + 1])
            i += 2
        elif args[i] == '--file':
            files.append(args[i + 1])
            i += 2
        elif args[i] in ('--dry-run', '--apply', '--restore-from-bak'):
            mode = args[i]
            i += 1
        else:
            i += 1
    if mode is None:
        print(__doc__)
        sys.exit(1)
    if mode == '--restore-from-bak':
        do_restore()
        return
    targets = files if files else TARGETS
    # 变体文件的参照原版: 同名标准包的 .bak (如 data.dat.dialogonly -> data.dat.bak)
    refmap = {}
    for f in targets:
        base = os.path.basename(f)
        for std in TARGETS:
            if base.startswith(std) and base != std:
                refmap[f] = PACK_DIR + std + '.bak'
    if includes:
        print('只补丁含子串: %s' % (', '.join(includes)))
    if excludes:
        print('排除子串: %s' % (', '.join(excludes)))
    if files:
        print('目标文件: %s' % (', '.join(targets)))
    plans, stats = analyze(targets, includes, excludes)
    print('=== dry-run 统计 ===')
    print('LAYO 头补丁点(1280x720->2560x720): %d' % stats['hdr'])
    print('元素级 canvas 补丁点:              %d' % stats['elem'])
    print('跳过的小部件 LAYO(非 1280x720):    %d' % stats['skip'])
    print('anomaly(LE32pair 无半尺寸匹配):    %d' % stats['anom'])
    print('非 ARKF 的 .ark(跳过):             %d' % stats['noarkf'])
    print('槽位不足被跳过的文件:              %d' % stats['overflow'])
    print('涉及 ark 文件数:                   %d' % stats['files'])
    if excludes:
        print('--- 排除统计 ---')
        print('被排除 ark: %d 个 (内含头 %d + 元素 %d 补丁点, 未改)' %
              (stats['excl_files'], stats['excl_hdr'], stats['excl_elem']))
        for s in stats['excl_paths']:
            print('   [EXCL]', s)
    if includes:
        print('未命中 include 的 ark(跳过): %d 个' % stats['incl_skip'])
    # 字节差汇总
    for fn in targets:
        _, plan = plans[fn]
        grow = sum(1 for r in plan if r[6] > (r[4] if r[4] else r[3]))
        shrink = sum(1 for r in plan if 0 <= r[6] < (r[4] if r[4] else r[3]))
        same = sum(1 for r in plan if r[6] == (r[4] if r[4] else r[3]))
        print('%s: stored 变大 %d / 变小 %d / 等长 %d (需更新 stored 字段的 %d 个)' %
              (fn, grow, shrink, same, grow + shrink))
    if mode == '--dry-run':
        print('dry-run 结束, 未写盘。')
        return
    print('\n=== apply ===')
    do_apply(plans, targets)
    print('\n=== roundtrip 验证 ===')
    if do_verify(plans, targets, includes, excludes, refmap):
        print('ROUNDTRIP ALL OK')
    else:
        print('!! ROUNDTRIP FAILED; 可用 --restore-from-bak 回滚')
        sys.exit(2)


if __name__ == '__main__':
    main()
