# -*- coding: utf-8 -*-
# 在 rpcs3 进程内存中定位 PS3 客体内存映射: 搜游戏标题 ID 字符串锚点
# 用法: python uw_findbase.py   (需要游戏在运行)
import pymem, pymem.memory, re

pm = pymem.Pymem('rpcs3.exe')
NEEDLE = b'BLJS10184'
# 优先扫已知活跃区: 0x400000000 - 0x800000000 (之前投影矩阵命中区在 0x56xxxxx)
RANGES = [(0x400000000, 0x800000000), (0x100000000, 0x400000000), (0x700000000, 0x708000000)]
CHUNK = 16 * 1048576
found = []
for lo, hi in RANGES:
    addr = lo
    while addr < hi and len(found) < 8:
        try:
            mbi = pymem.memory.virtual_query(pm.process_handle, addr)
        except Exception:
            break
        if mbi.BaseAddress < lo or mbi.BaseAddress >= hi:
            addr = mbi.BaseAddress + mbi.RegionSize
            continue
        base = mbi.BaseAddress
        size = min(mbi.RegionSize, hi - base)
        addr = base + mbi.RegionSize
        if mbi.State != 0x1000 or mbi.Protect not in (0x04, 0x08, 0x40, 0x80):
            continue
        off = 0
        while off < size:
            n = min(CHUNK, size - off)
            try:
                data = pm.read_bytes(base + off, n)
            except Exception:
                off += n
                continue
            p = 0
            while True:
                i = data.find(NEEDLE, p)
                if i < 0:
                    break
                found.append(base + off + i)
                p = i + 1
                if len(found) >= 8:
                    break
            off += n
print(f'{len(found)} hits')
for h in found:
    print(f'{h:X}')
