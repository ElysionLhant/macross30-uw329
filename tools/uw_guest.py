# -*- coding: utf-8 -*-
# RPCS3 PS3 客体内存工具: 转储/搜索
# 用法:
#   python uw_guest.py dump  [out.bin] [maxMB]   转储客体内存到文件(稀疏)
#   python uw_guest.py base                      只打印客体基址信息
import struct, sys, pymem, pymem.memory

GUEST_BASE = 0x700000000  # rpcs3 vm 基址(2024 年代码默认值)
GUEST_SIZE = 0x800000000  # 32GB

def open_pm():
    return pymem.Pymem('rpcs3.exe')

def committed_regions(pm):
    regs = []
    addr = GUEST_BASE
    end = GUEST_BASE + GUEST_SIZE
    while addr < end:
        try:
            mbi = pymem.memory.virtual_query(pm.process_handle, addr)
        except Exception:
            break
        if mbi.BaseAddress < GUEST_BASE:
            addr = GUEST_BASE
            continue
        if mbi.BaseAddress >= end:
            break
        size = min(mbi.RegionSize, end - mbi.BaseAddress)
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x08, 0x40, 0x80):
            regs.append((mbi.BaseAddress, size))
        addr = mbi.BaseAddress + mbi.RegionSize
    return regs

def cmd_dump(out, max_mb):
    pm = open_pm()
    regs = committed_regions(pm)
    total = 0
    CHUNK = 16 * 1048576
    with open(out, 'wb') as f:
        for base, size in regs:
            off = 0
            while off < size and total < max_mb * 1048576:
                n = min(CHUNK, size - off, max_mb * 1048576 - total)
                g_off = base + off - GUEST_BASE
                try:
                    data = pm.read_bytes(base + off, n)
                except Exception as e:
                    print(f'skip {base+off:X}: {e}')
                    off += n
                    continue
                f.seek(g_off)
                f.write(data)
                total += n
                off += n
            if total >= max_mb * 1048576:
                break
            print(f'dumped up to guest 0x{base + size - GUEST_BASE:08X}')
    print(f'total {total/1048576:.1f}MB -> {out}')

if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == 'dump':
        out = sys.argv[2] if len(sys.argv) > 2 else r'C:\Users\Elysion\Desktop\guest.bin'
        mb = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
        cmd_dump(out, mb)
    else:
        pm = open_pm()
        for base, size in committed_regions(pm):
            print(f'guest 0x{base-GUEST_BASE:08X}  host 0x{base:X}  {size/1048576:.1f}MB')
