from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

from compiler_provenance.parsing.superc import SuperC
from compiler_provenance.parsing.presence_condition import PresenceCondition


['java', 'superc.SuperC', '-restrictFreeToHeader', '/workspaces/RevEng/header/libraries/libpcap.h', '-include', '/workspaces/RevEng/header/other_defines/other_defines_libpcap.h', '-I', '/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5', '-I', '/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5', '-I', '/workspaces/RevEng/buildroot-2025.02.4/output/host/lib/gcc/arm-buildroot-linux-gnueabihf/13.3.0/include', '-sourcelinePC', '/workspaces/RevEng/all_strings/all_strings_libpcap_pcap.txt', '/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5/pcap.c']
print("Running SuperC for error line")
superc = SuperC()
print("SuperC instance created")
src_file = Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5/pcap.c')
library_dir = '/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5'
line_no = None
config_h = Path('/workspaces/RevEng/header/libraries/libpcap.h')
presence_conditions = superc.get_pc_and_macro_values(src_file, library_dir=library_dir, line_number=line_no, macro=None, config_h= config_h, name='libpcap-test-1', include_dir=library_dir, extra_include="")