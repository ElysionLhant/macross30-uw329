#!/usr/bin/env python3
# 生成单点 trampoline patch.yml: uw_single_site.py <站点名>
import sys

HDR = '''Version: 1.2

PPU-15a011c611e0a0a1fedff55159bc26336db4dfd7:
  "32:9 Ultrawide (7680x2160)":
    Games:
      "Macross 30":
        "BLJS10184": [ All ]
    Author: Kimi
    Notes: "single site probe"
    Patch Version: 1.0
    Patch:
'''
CAVE = [(0x008dc8ac, 0x4bce32b0), (0x008dc8b0, 0x60000000), (0x008dc8b4, 0x60000000), (0x008dc8b8, 0x60000000)]
SITES = {
    's0': (0x00584178, 0x48358735), 's1': (0x00586a98, 0x48355e15),
    's2': (0x005876d8, 0x483551d5), 's3': (0x005a88dc, 0x48333fd1),
    's4': (0x005ac1ac, 0x48330701), 's5': (0x005ac658, 0x48330255),
    's6': (0x005acbbc, 0x4832fcf1), 's7': (0x005ad0b0, 0x4832f7fd),
    's8': (0x005ad570, 0x4832f33d), 's9': (0x005af708, 0x4832d1a5),
    's10': (0x005b02e0, 0x4832c5cd), 's11': (0x005bfc9c, 0x4831cc11),
    's12': (0x005bfdc4, 0x4831cae9), 's13': (0x005d40a8, 0x48308805),
}

name = sys.argv[1]
out = HDR
for a, v in CAVE + [SITES[name]]:
    out += '      - [ be32, 0x%08x, 0x%08x ]\n' % (a, v)
open('patch.yml', 'w').write(out)
print('patch.yml = cave +', name, '0x%08x' % SITES[name][0])
