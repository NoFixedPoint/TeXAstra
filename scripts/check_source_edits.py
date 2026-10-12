"""Build and run source index / UTF-16 delta boundary checks on Linux or WSL."""
import json
import os
import subprocess
from cpp_client import ROOT, linux

prefix = ['wsl', '-d', 'Ubuntu-22.04', '--exec'] if os.name == 'nt' else []
binary = ROOT/'.work/check-source-edits'
subprocess.run(prefix+['g++', '-std=c++17', '-O2', '-Wall', '-Wextra',
                      '-I'+linux(ROOT/'native'), '-I'+linux(ROOT/'.work/cpp-build'),
                      linux(ROOT/'scripts/check_source_edits.cpp'), '-o', linux(binary)], check=True)
subprocess.run(prefix+[linux(binary), linux(ROOT/'.work/source-edit-ranges.txt')], check=True)
(ROOT/'results/source-edits.json').write_text(json.dumps({'ok': True, 'checks': [
    'Unicode line and UTF-16 column positions', 'Empty and shortened buffers',
    'Retained command ranges and intersecting edits', 'UTF-16 multi-cursor changes with CRLF',
    'Atomic rejection of invalid version, length, surrogate and bounds',
    'Legacy-encoded sources preserve bytes without stale mappings or slot collisions']}, indent=2)+'\n')
