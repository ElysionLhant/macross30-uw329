# -*- coding: utf-8 -*-
# 混画门控现场取证 v3: 在 v2 基础上加 r3/r5、UV 块 dump、宽高统计、按 LR 分组汇总
# 用法: uw_venv/Scripts/python.exe uw_writer_trace3.py [max_hits=300] [timeout_s=600]
# 注意: 游戏完全进场景后再启动; 每次连接前必须重启模拟器 (GDB 线程一次性)
import socket, sys, struct, time, re
from collections import defaultdict

MAX_HITS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
TIMEOUT = int(sys.argv[2]) if len(sys.argv) > 2 else 600
OUT = r'C:\Users\Elysion\Desktop\UW32_Macross30\data\uw_writer_trace3.log'

s = socket.create_connection(('127.0.0.1', 2345), timeout=5)
log = open(OUT, 'w', buffering=1)

def ck(d): return '%02x' % (sum(d.encode('latin1')) % 256)

def read_pkt(timeout=10):
    s.settimeout(timeout)
    while True:
        c = s.recv(1)
        if not c: raise ConnectionError('eof')
        if c == b'$': break
    p = b''
    while True:
        c = s.recv(1)
        if c == b'#':
            s.recv(2); break
        p += c
    s.sendall(b'+')
    return p.decode('latin1', errors='replace')

def cmd(d, timeout=10):
    s.sendall(('+$%s#%s' % (d, ck(d))).encode('latin1'))
    return read_pkt(timeout)

def reg(rid):
    r = cmd('p%x' % rid)
    try: return int(r, 16)
    except Exception: return -1

def mem(addr, ln):
    if not (0x10000 <= addr < 0x40000000): return b''
    r = cmd('m%x,%x' % (addr, ln))
    try: return bytes.fromhex(r)
    except Exception: return b''

def f32(b, o):
    return struct.unpack('>f', b[o:o+4])[0]

def sane(v):
    return -1e6 < v < 1e6

print('qSupported:', cmd('qSupported'))
print('threads:', cmd('qfThreadInfo')[:100])
print('Z0 set:', cmd('Z0,7009c4,4'))
t0 = time.time()
hits = 0
stats = defaultdict(list)  # lr -> list of (w, h, uvspan, r3, r7)
log.write('# stop_thread lr r3 r5 r4 x0..y3 r6 r7 uv0..7\n')
while hits < MAX_HITS and (time.time() - t0) < TIMEOUT:
    stop = cmd('c', timeout=TIMEOUT)
    m = re.search(r'thread:([0-9a-fA-F]+)', stop)
    if not m:
        print('stop(no thread):', stop[:80]); continue
    tid = m.group(1)
    cmd('Hg%s' % tid)
    lr = reg(67) & 0xFFFFFFFF
    r3 = reg(3) & 0xFFFFFFFF
    r4 = reg(4) & 0xFFFFFFFF
    r5 = reg(5) & 0xFFFFFFFF
    r6 = reg(6) & 0xFFFFFFFF
    r7 = reg(7) & 0xFFFFFFFF
    raw = mem(r4, 32)
    uvraw = mem(r7, 32)
    if len(raw) == 32:
        xs = [f32(raw, i*4) for i in (0, 2, 4, 6)]
        ys = [f32(raw, i*4) for i in (1, 3, 5, 7)]
        w = max(xs) - min(xs); h = max(ys) - min(ys)
        uvs = [f32(uvraw, i*4) for i in range(8)] if len(uvraw) == 32 else []
        us = uvs[0::2]; vs = uvs[1::2]
        uspan = (max(us) - min(us)) if us and all(sane(u) for u in us) else -1
        vspan = (max(vs) - min(vs)) if vs and all(sane(v) for v in vs) else -1
        line = ('hit %4d tid=%s lr=0x%08x r3=0x%08x r5=0x%08x | x0=%8.2f y0=%8.2f x1=%8.2f y1=%8.2f x2=%8.2f y2=%8.2f x3=%8.2f y3=%8.2f | w=%7.2f h=%7.2f | r6=0x%08x r7=0x%08x | uvspan=%.3f/%.3f'
                % (hits, tid, lr, r3, r5, xs[0], ys[0], xs[1], ys[1], xs[2], ys[2], xs[3], ys[3], w, h, r6, r7, uspan, vspan))
        if uvs:
            line += ' | uv=' + ' '.join('%7.4f' % u for u in uvs)
        stats[lr].append((w, h, uspan, vspan, r3, r7))
    else:
        line = 'hit %4d tid=%s lr=0x%08x r4=0x%08x <no mem> r3=0x%08x | r6=0x%08x r7=0x%08x' % (hits, tid, lr, r4, r3, r6, r7)
    print(line)
    log.write(line + '\n')
    hits += 1

print()
print('=== summary by LR ===')
log.write('=== summary by LR ===\n')
for lr, rows in sorted(stats.items(), key=lambda kv: -len(kv[1])):
    ws = sorted(r[0] for r in rows); hs = sorted(r[1] for r in rows)
    usp = sorted(r[2] for r in rows); vsp = sorted(r[3] for r in rows)
    r3s = sorted(set(r[4] for r in rows)); r7s = sorted(set(r[5] for r in rows))
    s_line = ('lr=0x%08x n=%d | w[%.0f..%.0f] med=%.0f | h[%.0f..%.0f] | uspan[%.3f..%.3f] vspan[%.3f..%.3f] | r3: %s | r7: %s'
              % (lr, len(rows), ws[0], ws[-1], ws[len(ws)//2], hs[0], hs[-1], usp[0], usp[-1], vsp[0], vsp[-1],
                 ','.join('0x%08x' % v for v in r3s[:6]) + ('...' if len(r3s) > 6 else ''),
                 ','.join('0x%08x' % v for v in r7s[:4]) + ('...' if len(r7s) > 4 else '')))
    print(s_line)
    log.write(s_line + '\n')
log.close()
print('done, %d hits -> %s' % (hits, OUT))
