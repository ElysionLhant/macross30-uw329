#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uw_pack_re.py - Macross 30 (BLJS10184) PIDX pack 逆向/提取/扫描工具

格式要点(详见 UW_PACK_RE.md):
  PIDX0 头:  u32 magic"PIDX0\\0\\0\\0" 之后 8 个 LE u32:
             [ver, hdr_size, n_records, f3, recs_end, gap_size, data_start, pool_size]
             hdr_size: .dat=0x50, pack.idx=0x150 (含 9*0x20 pack 条目)
             恒有 recs_end == hdr_size + n_records*0x18; data_start == recs_end + gap_size
  记录(0x18): 目录 {flag=1, name_off, n_children, first_child_idx, 0, 0}
             文件 {flag=0, name_off, 0, abs_offset, dec_size, stored_size}
             (stored_size==0 或 ==dec_size -> 原始存储; 否则看魔数: 78xx=zlib, "segs"=分段raw-deflate)
  名字池:    data_start 起 pool_size 字节, 以 data/pack/<自身文件名> 开头, NUL 结尾相对偏移
  gap 表:    [u32 count][u32 off[count]] + count*0x14 字节记录 (流式 chunk 表)
  "segs":    "segs" + u16be ver(=5) + u16be nseg + u32be 解压总长 + u32be 压缩总长
             + nseg*8: {u16be comp_len, u16be dec_len(0=0x10000), u16be 0, u16be src_off+1}
             载荷从 0x10+nseg*8 按 0x10 对齐处开始, 每段为 raw deflate(wbits=-15), 段间有零填充
  .ark:      整文件 zlib(78da), 解压后为 "ARK ARKF" 容器, 内含 "ARK TEXS/TXOS/LAYO..." 块

用法:
  python uw_pack_re.py info                          # 各 pack 头/表统计
  python uw_pack_re.py list <pack.dat> [过滤子串]     # 列文件树
  python uw_pack_re.py extract <pack.dat> <路径子串> <输出目录>
  python uw_pack_re.py scan                          # 全 pack 扫描述体名 + dims 模式
  python uw_pack_re.py layos                         # 生成 1280x720 LAYO 补丁点清单
  python uw_pack_re.py hashcheck                     # pack.idx 16字节值 vs 常见哈希
"""
import os, re, sys, zlib, struct, mmap, hashlib

PACK_DIR = 'C:/Users/Elysion/Desktop/rpcs3-src/build/bin/dev_hdd0/game/BLJS10184_INSTALL/USRDIR/data/pack/'
PACKS = ['data.dat', 'data2.dat', 'fileset0.dat', 'fileset1.dat', 'fileset2.dat',
         'init.dat', 'lua.dat', 'shaders.dat', 'sound.dat']

DESC_NAMES = [b'pose_ob_dialogue', b'pose_dialogue_cursor_off', b'enemy_guage_ace',
              b'own_barrier_gauge', b'cap_obj', b'caption1', b'black_back',
              b'sankaku_b', b'stay_dialogue_flame_s2', b'LAYOUT0', b'rsrt_ob_dialogue2']

DIM_PATTERNS = [
    ('LE32pair', b'\x00\x05\x00\x00\xd0\x02\x00\x00'),   # {1280,720} LE u32 相邻
    ('BE32pair', b'\x00\x00\x05\x00\x00\x00\x02\xd0'),   # {1280,720} BE u32 相邻
    ('LE16pair', b'\x00\x05\xd0\x02'),                   # u16 LE 相邻
    ('BE16pair', b'\x05\x00\x02\xd0'),                   # u16 BE 相邻
    ('F32LEpair', b'\x00\x00\xa0\x44\x00\x00\x34\x44'),  # float32 LE 1280.0,720.0
    ('F32BEpair', b'\x44\xa0\x00\x00\x44\x34\x00\x00'),  # float32 BE
    ('LE32pair_rev', b'\xd0\x02\x00\x00\x00\x05\x00\x00'),
]
PITCH_LE = b'\x00\x14\x00\x00'
PITCH_BE = b'\x00\x00\x14\x00'


class Pack:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.fd = open(path, 'rb')
        self.mm = mmap.mmap(self.fd.fileno(), 0, access=mmap.ACCESS_READ)
        hdr = self.mm[:0x50]
        assert hdr[:5] == b'PIDX0', 'bad magic'
        (self.ver, self.hsz, self.nrec, self.f3,
         self.recs_end, self.gap_size, self.data_start, self.pool_size) = \
            struct.unpack('<8I', hdr[8:40])
        # 记录表从 hsz 开始 (.dat 为 0x50, pack.idx 为 0x150)
        assert self.recs_end == self.hsz + self.nrec * 0x18, \
            'recs_end mismatch: %x vs %x' % (self.recs_end, self.hsz + self.nrec * 0x18)
        self.pool = self.mm[self.data_start:self.data_start + self.pool_size]
        self.recs = []
        for i in range(self.nrec):
            self.recs.append(struct.unpack('<6I', self.mm[self.hsz + i * 0x18: self.hsz + (i + 1) * 0x18]))
        # 可能有多个根 (pack.idx: "data" + "bin"); 根 = 未被任何目录引用的目录
        self.paths = {}
        if self.nrec:
            child = set()
            for r in self.recs:
                if r[0] == 1:
                    child.update(range(r[3], r[3] + r[2]))
            for i, r in enumerate(self.recs):
                if r[0] == 1 and i not in child:
                    self._walk(i, '')

    def cstr(self, off):
        e = self.pool.index(b'\x00', off)
        return self.pool[off:e].decode('ascii', 'replace')

    def _walk(self, idx, prefix):
        fl, noff, f2, f3, f4, f5 = self.recs[idx]
        p = prefix + '/' + self.cstr(noff)
        self.paths[idx] = p
        if fl == 1:
            for c in range(f3, f3 + f2):
                self._walk(c, p)

    def files(self):
        """yield (idx, path, abs_off, dec_size, stored_size)"""
        for i, r in enumerate(self.recs):
            if r[0] == 0:
                off, dec, stored = r[3], r[4], r[5]
                if off == 0 and dec == 0:
                    continue
                yield i, self.paths.get(i, '<orphan>/' + self.cstr(r[1])), off, dec, stored

    def read_stored(self, off, stored, dec):
        n = stored if (stored and stored < dec) else dec
        return bytes(self.mm[off:off + n])

    @staticmethod
    def inflate_segs(blob):
        """解 segs 分段 raw-deflate 容器 -> bytes; 非 segs 抛异常"""
        if blob[:4] != b'segs':
            raise ValueError('not segs')
        nseg = struct.unpack('>H', blob[6:8])[0]
        off = 0x10 + nseg * 8
        # 对齐到 0x10
        off = (off + 0xF) & ~0xF
        out = b''
        for _ in range(nseg):
            got = False
            for probe in range(off, min(off + 0x20, len(blob))):
                try:
                    d = zlib.decompressobj(wbits=-15)
                    r = d.decompress(blob[probe:])
                    if len(r) < 0x20:
                        continue
                    consumed = len(blob[probe:]) - len(d.unused_data)
                    out += r
                    off = probe + consumed
                    got = True
                    break
                except zlib.error:
                    continue
            if not got:
                break
        return out

    def read_file(self, off, dec, stored, want_decompress=True):
        """返回 (blob, kind): kind in raw/zlib/segs/raw-too-big"""
        blob = self.read_stored(off, stored, dec)
        if not want_decompress or len(blob) > 64 * 1024 * 1024:
            return blob, 'raw'
        if blob[:4] == b'segs' and stored and stored < dec:
            try:
                d = self.inflate_segs(blob)
                if len(d) == dec:
                    return d, 'segs'
            except Exception:
                pass
            return blob, 'raw'
        if len(blob) >= 2 and blob[0] == 0x78 and stored and stored < dec:
            try:
                d = zlib.decompress(blob)
                if len(d) == dec:
                    return d, 'zlib'
            except zlib.error:
                pass
        return blob, 'raw'


def scan_blob(blob):
    """返回 {tag: [offsets]}"""
    hits = {}
    for nm in DESC_NAMES:
        pos = []
        start = 0
        while True:
            i = blob.find(nm, start)
            if i < 0:
                break
            pos.append(i)
            start = i + 1
            if len(pos) > 100:
                break
        if pos:
            hits['NAME:' + nm.decode()] = pos
    for tag, pat in DIM_PATTERNS:
        pos = []
        start = 0
        while True:
            i = blob.find(pat, start)
            if i < 0:
                break
            pos.append(i)
            start = i + 1
            if len(pos) > 10000:
                break
        if pos:
            hits[tag] = pos
    return hits


def cmd_info():
    for fn in PACKS + ['pack.idx']:
        p = Pack(PACK_DIR + fn)
        nf = sum(1 for _ in p.files())
        print('%-13s ver=%d nrec=%d files=%d recs_end=0x%x gap=0x%x data_start=0x%x pool=0x%x' %
              (fn, p.ver, p.nrec, nf, p.recs_end, p.gap_size, p.data_start, p.pool_size))


def cmd_list(pack, filt=''):
    p = Pack(PACK_DIR + pack)
    for i, path, off, dec, stored in p.files():
        if filt and filt.lower() not in path.lower():
            continue
        print('%-60s off=%-12x dec=%-10x stored=%x' % (path, off, dec, stored))


def cmd_extract(pack, filt, outdir):
    os.makedirs(outdir, exist_ok=True)
    p = Pack(PACK_DIR + pack)
    n = 0
    for i, path, off, dec, stored in p.files():
        if filt.lower() not in path.lower():
            continue
        blob, kind = p.read_file(off, dec, stored)
        fn = os.path.join(outdir, os.path.basename(path))
        with open(fn, 'wb') as f:
            f.write(blob)
        print('%-55s -> %-40s [%s] %x -> %x' % (path, fn, kind, stored or dec, len(blob)))
        n += 1
    print('extracted %d files' % n)


def cmd_scan():
    grand = {}
    out_lines = []

    def report(line):
        print(line)
        out_lines.append(line)

    for fn in PACKS:
        p = Pack(PACK_DIR + fn)
        nfiles = 0
        for i, path, off, dec, stored in p.files():
            blob, kind = p.read_file(off, dec, stored)
            if kind == 'raw' and len(blob) > 64 * 1024 * 1024:
                continue  # 电影等大文件跳过
            nfiles += 1
            hits = scan_blob(blob)
            if not hits:
                continue
            line = '%s %s [%s]' % (fn, path, kind)
            for tag, pos in hits.items():
                line += '  %s x%d @%s' % (tag, len(pos),
                                          ','.join('%x' % x for x in pos[:6]))
                grand[tag] = grand.get(tag, 0) + len(pos)
            report(line)
        if nfiles == 0 or fn in ('fileset0.dat', 'fileset1.dat', 'fileset2.dat', 'sound.dat'):
            # 无树记录的包(fileset) / 音频包: 整包原始扫描
            report('-- %s: 整包 raw 扫描 --' % fn)
            blob = p.mm
            hits = scan_blob(blob)
            for tag, pos in hits.items():
                report('   %s x%d @%s' % (tag, len(pos), ','.join('%x' % x for x in pos[:6])))
                grand[tag + '(raw)'] = grand.get(tag + '(raw)', 0) + len(pos)
    print('\n=== 汇总(命中次数) ===')
    out_lines.append('\n=== 汇总 ===')
    for tag, c in sorted(grand.items(), key=lambda kv: -kv[1]):
        print('%-32s %d' % (tag, c))
        out_lines.append('%-32s %d' % (tag, c))
    with open('C:/Users/Elysion/Desktop/UW32_Macross30/data/uw_pack_scan.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))


def cmd_layos(out_path='C:/Users/Elysion/Desktop/UW32_Macross30/data/uw_layo_sites.txt'):
    """枚举全部 .ark 的 ARK LAYO 块, 生成 1280x720 补丁点清单"""
    import re as _re
    lines, nsite, nfile, elem_n, txos_n = [], 0, 0, 0, 0
    by_pack = {}
    for fn in ['data.dat', 'data2.dat', 'init.dat', 'lua.dat']:
        p = Pack(PACK_DIR + fn)
        for i, path, off, dec, stored in p.files():
            if not path.lower().endswith('.ark'):
                continue
            blob, kind = p.read_file(off, dec, stored)
            if blob[:8] != b'ARK ARKF':
                continue
            layoffs = {m.start(): m for m in _re.finditer(b'ARK LAYO', blob)}
            hdr_sites = []
            for b, m in layoffs.items():
                name = blob[b + 0x10:b + 0x30].split(b'\x00')[0].decode('ascii', 'replace')
                w, h = struct.unpack('<2I', blob[b + 0x44:b + 0x4c])
                if (w, h) == (1280, 720):
                    hdr_sites.append((b, name))
            e_hits = t_hits = 0
            heads = sorted(m.start() for m in _re.finditer(b'ARK ', blob))
            for m in _re.finditer(b'\x00\x05\x00\x00\xd0\x02\x00\x00', blob):
                x = m.start()
                if x in set(b + 0x44 for b in layoffs):
                    continue
                hb = max(h for h in heads if h < x)
                tag = blob[hb:hb + 8]
                if tag == b'ARK LAYO':
                    e_hits += 1
                elif tag == b'ARK TXOS':
                    t_hits += 1
            if hdr_sites or e_hits:
                lines.append('%s %s [%s dec=%x stored=%x]' % (fn, path, kind, dec, stored))
                for b, name in hdr_sites:
                    lines.append('    LAYO_HDR +%06x  %s' % (b, name))
                if e_hits:
                    lines.append('    ELEMENT_CANVAS x%d' % e_hits)
                if t_hits:
                    lines.append('    TXOS_TEX x%d' % t_hits)
                nsite += len(hdr_sites)
                elem_n += e_hits
                txos_n += t_hits
                nfile += 1
                by_pack[fn] = by_pack.get(fn, 0) + len(hdr_sites)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('LAYO_HDR 1280x720 sites: %d (across %d arks) by_pack=%s' % (nsite, nfile, by_pack))
    print('ELEMENT_CANVAS x%d  TXOS_TEX x%d  -> %s' % (elem_n, txos_n, out_path))


def cmd_hashcheck():
    p = Pack(PACK_DIR + 'pack.idx')
    order = PACKS
    print('idx header: nrec=%d data_start=0x%x pool=0x%x' % (p.nrec, p.data_start, p.pool_size))
    for i in range(9):
        e = p.mm[0x40 + i * 0x20: 0x40 + (i + 1) * 0x20]
        want = e[:16].hex()
        fn = order[i]
        data = open(PACK_DIR + fn, 'rb').read()
        ver, hsz, nrec, f3, recend, gapz, ds, ps = struct.unpack('<8I', data[8:40])
        cands = {
            'file': data, 'hdr': data[:0x50], 'recs': data[0x50:recend],
            'recsgap': data[0x50:ds], 'pool': data[ds:ds + ps],
            'tables': data[:ds + ps], 'file[0x50:]': data[0x50:],
        }
        m = [k for k, v in cands.items() if hashlib.md5(v).hexdigest() == want]
        m += ['sha1:' + k for k, v in cands.items() if hashlib.sha1(v).hexdigest()[:32] == want]
        print('%-13s %s pooloff=%-4x -> %s' % (fn, want, struct.unpack('<I', e[16:20])[0],
                                               'MATCH ' + ','.join(m) if m else 'no match (build GUID?)'))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'info':
        cmd_info()
    elif cmd == 'list':
        cmd_list(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '')
    elif cmd == 'extract':
        cmd_extract(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'scan':
        cmd_scan()
    elif cmd == 'layos':
        cmd_layos()
    elif cmd == 'hashcheck':
        cmd_hashcheck()
    else:
        print('unknown cmd', cmd)
