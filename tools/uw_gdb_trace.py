# -*- coding: utf-8 -*-
# rpcs3 GDB stub RSP 客户端 v2: 断点 + 寄存器采集
# 用法: uw_gdb_trace.py [addr=5bfb5c] [max_hits=40] [timeout_s=420]
# 注意: 必须连全新启动的 rpcs3（每次断连 gdb 线程会死）
import socket, sys, time

ADDR = sys.argv[1] if len(sys.argv) > 1 else '5bfb5c'
MAX_HITS = int(sys.argv[2]) if len(sys.argv) > 2 else 40
TIMEOUT = int(sys.argv[3]) if len(sys.argv) > 3 else 420
REGS = sys.argv[4].split(',') if len(sys.argv) > 4 else ['3', '4', '5', '6', '43', '40']
OUT = r'C:\Users\Elysion\Desktop\UW32_Macross30\data\uw_gdb_trace.log'

s = socket.create_connection(('127.0.0.1', 2345), timeout=5)
s.settimeout(10)
log = open(OUT, 'w', buffering=1)

def ck(d): return '%02x' % (sum(d.encode('latin1')) % 256)

def read_pkt(timeout=10):
    s.settimeout(timeout)
    while True:
        c = s.recv(1)
        if not c:
            raise ConnectionError('eof')
        if c == b'$':
            break
    p = b''
    while True:
        c = s.recv(1)
        if c == b'#':
            s.recv(2)
            break
        p += c
    s.sendall(b'+')
    return p.decode('latin1', errors='replace')

def cmd(d, timeout=10):
    s.sendall(('+$%s#%s' % (d, ck(d))).encode('latin1'))
    return read_pkt(timeout)

def reg(rid):
    r = cmd('p%x' % rid)
    return int(r, 16) if r and 'x' not in r and r != '' else -1

def mem(addr, ln=8):
    r = cmd('m%x,%x' % (addr, ln))
    try:
        return bytes.fromhex(r)
    except Exception:
        return b''

try:
    print('qSupported:', cmd('qSupported'))
    ti = cmd('qfThreadInfo')
    print('threads:', ti)
    tid = None
    if ti.startswith('m'):
        for t in ti[1:].rstrip('l').split(','):
            if int(t, 16) == 0x1000000:
                tid = t
    print('Hg:', cmd('Hg' + (tid or '-1')))
    print('vCont?:', cmd('vCont?'))
    print('Z0:', cmd('Z0,%s,4' % ADDR))

    hits = 0
    seen = set()
    SKIP = {0x5b02e4}  # 1x1 dummy 刷屏点，不计入
    t0 = time.time()
    cmd('vCont;c', timeout=1) if False else s.sendall(('+$%s#%s' % ('vCont;c', ck('vCont;c'))).encode('latin1'))
    while hits < MAX_HITS and time.time() - t0 < TIMEOUT:
        try:
            stop = read_pkt(timeout=60)
        except socket.timeout:
            print('.. no stop in 60s, hits=%d' % hits)
            continue
        vals = {int(r, 16): reg(int(r, 16)) for r in REGS}
        lr = vals.get(0x43, -1)
        memnote = ''
        if 4 in vals and vals[4] > 0x10000:
            m = mem(vals[4], 8)
            if len(m) == 8:
                memnote = ' [r4]=0x%08x [r4+4]=0x%08x' % (int.from_bytes(m[:4],'big'), int.from_bytes(m[4:],'big'))
        key = tuple(vals[r] for r in sorted(vals))
        if lr in SKIP or key in seen:
            s.sendall(('+$%s#%s' % ('vCont;c', ck('vCont;c'))).encode('latin1'))
            continue
        seen.add(key)
        parts = ' '.join('r%s=0x%08x' % (r, vals[r]) for r in [int(x, 16) for x in REGS])
        # 栈回溯：*sp=前帧SP, 保存的LR在 前帧+0x10
        chain = []
        sp = vals.get(1, 0)
        for _ in range(8):
            try:
                raw = mem(sp, 0x14)
                if len(raw) < 0x14:
                    break
                prev = int.from_bytes(raw[0:4], 'big')
                lrv = int.from_bytes(raw[0x10:0x14], 'big')
                if prev == 0 or lrv < 0x10000 or lrv > 0x10000000:
                    break
                chain.append(lrv)
                sp = prev
            except Exception:
                break
        memnote += ' chain=' + ','.join('0x%x' % c for c in chain)
        line = 'hit#%d %s%s' % (hits, parts, memnote)
        print(line)
        log.write(line + '\n')
        hits += 1
        s.sendall(('+$%s#%s' % ('vCont;c', ck('vCont;c'))).encode('latin1'))
    print('done: %d hits in %.0fs -> %s' % (hits, time.time() - t0, OUT))
    try:
        print('z0:', cmd('z0,%s,4' % ADDR))
    except Exception:
        pass
    time.sleep(20)  # 让 stub 从容收尾，避免致命
except Exception as e:
    print('ERR:', e)
finally:
    s.close()
