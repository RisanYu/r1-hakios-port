#!/usr/bin/env python3
"""Run trident_cycle.py for a list of arm_init checkpoints, stop early on a hit.

For each checkpoint N:
  HAKIOS_CHECKPOINT=N python tools/trident_cycle.py ck-N "<cmdline>"
and read the produced logdump analysis (backup/cycles/ck-N-logdump.txt) for
"STOPPED AT CHECKPOINT" / "EARLY KERNEL EXCEPTION".

Usage:
  python tools/ck_sweep.py "rd=md0 hv_wdt_pet=1 cpus=1 bootcpu=2 cpufreq=1 ufs=2 -v debug=0x144 keepsyms=1 loader_return_after=30" 21 10 11 15 16
  python tools/ck_sweep.py --until-miss "<cmdline>" 99 100 101 102
    (walk the list forward while every checkpoint is hit; stop at the first
     checkpoint that is NOT reached and report it as the hang boundary)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CYCLE = ROOT / 'tools' / 'trident_cycle.py'
CYCLE_LOG = ROOT / 'backup' / 'cycles'

sys.path.insert(0, str(ROOT / 'tools'))
# The bundled python executable is the one able to import pyusb/fatfs; when this
# script runs under it, sys.executable is that interpreter.
PY = sys.executable


def log(msg: str) -> None:
    print(msg, flush=True)


def run_one(cp: int, cmdline: str) -> dict:
    name = f'ck-{cp}'
    env = dict(os.environ)
    env['HAKIOS_CHECKPOINT'] = str(cp)
    log(f'=== {name}: checkpoint {cp} ===')
    proc = subprocess.run(
        [PY, str(CYCLE), name, cmdline],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        errors='replace',
    )
    out = (proc.stdout or '') + (proc.stderr or '')
    for line in out.splitlines():
        log('  ' + line)
    txt = CYCLE_LOG / f'{name}-logdump.txt'
    dump = txt.read_text(errors='replace') if txt.exists() else ''
    stop = re.search(r'STOPPED AT CHECKPOINT (\d+)', dump)
    early = re.search(r'EARLY KERNEL EXCEPTION: esr=([0-9a-fA-F]+) elr=([0-9a-fA-F]+) far=([0-9a-fA-F]+)', dump)
    returned = re.search(r'kernel returned: log at ([0-9a-fA-F]+), (\d+) bytes', dump)
    res = {
        'checkpoint': cp,
        'stop': int(stop.group(1)) if stop else None,
        'early': early.group(0) if early else None,
        'returned': (returned.group(1), int(returned.group(2))) if returned else None,
        'rc': proc.returncode,
    }
    log(f'--- {name}: rc={res["rc"]} stop={res["stop"]} early={res["early"]} returned={res["returned"]}')
    return res


def main() -> int:
    args = sys.argv[1:]
    until_miss = False
    if args and args[0] == '--until-miss':
        until_miss = True
        args = args[1:]
    if len(args) < 2:
        print(__doc__)
        return 2
    cmdline = args[0]
    checkpoints = [int(x) for x in args[1:]]
    results = []
    for cp in checkpoints:
        res = run_one(cp, cmdline)
        results.append(res)
        if until_miss:
            if res['stop'] is None:
                log(f'*** checkpoint {cp} NOT reached: the hang is before it ***')
                break
            log(f'*** checkpoint {res["stop"]} reached, walking on ***')
            continue
        if res['stop'] is not None:
            log(f'*** kernel reached checkpoint {res["stop"]}: arm_init completed up to there ***')
            break
        if res['early']:
            log('*** early kernel exception, stop sweep ***')
            break
    log('=== summary ===')
    for r in results:
        log(str(r))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
