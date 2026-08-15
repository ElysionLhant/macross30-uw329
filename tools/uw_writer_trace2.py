# -*- coding: utf-8 -*-
# 混画门控现场取证 v2: 解析停止回复, 附加到命中线程再读寄存器
# 用法: uw_venv/Scripts/python.exe uw_writer_trace2.py [max_hits=200] [timeout_s=600]
import socket, sys, struct, time, re

MAX_HITS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
TIMEOUT = int(sys.argv[2]) if len(sys.argv) > 2 else 600
OUT = r'C:\Users\Elysion\Desktop\UW32_Macross30\data\uw_writer_trace2.log'

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
    r = cmd('m%x,%x' % (addr, ln))
    try: return bytes.fromhex(r)
    except Exception: return b''

def f32(b, o):
    return struct.unpack('>f', b[o:o+4])[0]

print('qSupported:', cmd('qSupported'))
ti = cmd('qfThreadInfo')
print('threads:', ti[:100])
print('Z0 set:', cmd('Z0,7009c4,4'))
t0 = time.time()
hits = 0
log.write('# stop_thread lr r4 x0..y3 r6 r7\n')
while hits < MAX_HITS and (time.time() - t0) < TIMEOUT:
    stop = cmd('c', timeout=TIMEOUT)
    m = re.search(r'thread:([0-9a-fA-F]+)', stop)
    if not m:
        print('stop(no thread):', stop[:80]); continue
    tid = m.group(1)
    cmd('Hg%s' % tid)
    lr = reg(67) & 0xFFFFFFFF
    r4 = reg(4) & 0xFFFFFFFF
    r6 = reg(6) & 0xFFFFFFFF
    r7 = reg(7) & 0xFFFFFFFF
    raw = mem(r4, 32) if 0x10000 <= r4 < 0x40000000 else b''
    if len(raw) == 32:
        xs = [f32(raw, i*4) for i in range(8)]
        line = ('hit %4d tid=%s lr=0x%08x | x0=%9.2f y0=%9.2f x1=%9.2f y1=%9.2f x2=%9.2f y2=%9.2f x3=%9.2f y3=%9.2f | r6=0x%08x r7=0x%08x'
                % (hits, tid, lr, *xs, r6, r7))
    else:
        line = 'hit %4d tid=%s lr=0x%08x r4=0x%08x <no mem> | r6=0x%08x r7=0x%08x' % (hits, tid, lr, r4, r6, r7)
    print(line)
    log.write(line + '\n')
    hits += 1
log.close()
print('done, %d hits -> %s' % (hits, OUT))
