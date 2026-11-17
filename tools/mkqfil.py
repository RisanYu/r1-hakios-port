#!/usr/bin/env python3
"""Generate a firehose rawprogram XML (+ empty patch XML) for writing raw sectors
through EDL, which is how the GPT head/tail are written back after gpt-edit.py.

usage:
    mkqfil.py <outdir> <sector_size> <filename>:<start_sector>:<num_sectors> [...]

example (UFS, 4096-byte sectors, R1 GPT head = 6 LBAs, tail = 5 LBAs):
    mkqfil.py out 4096 gpt-head-new.img:0:6 gpt-tail-new.img:<total-5>:5

Then:
    tools\\run-edl.cmd qfil out\\rawprogram0.xml out\\patch0.xml out --loader <firehose>
"""
import os
import sys


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    outdir = sys.argv[1]
    ss = sys.argv[2]
    entries = sys.argv[3:]
    os.makedirs(outdir, exist_ok=True)
    lines = ['<?xml version="1.0" ?>', "<data>"]
    for e in entries:
        filename, start, count = e.split(":")
        lines.append(
            '  <program SECTOR_SIZE_IN_BYTES="%s" file_sector_offset="0" filename="%s" '
            'label="" num_partition_sectors="%s" partofsingleimage="false" '
            'physical_partition_number="0" start_sector="%s" />'
            % (ss, filename, count, start))
    lines.append("</data>")
    raw = os.path.join(outdir, "rawprogram0.xml")
    patch = os.path.join(outdir, "patch0.xml")
    with open(raw, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(patch, "w", newline="\n") as f:
        f.write('<?xml version="1.0" ?>\n<data>\n</data>\n')
    print("wrote %s and %s (%d program entries)" % (raw, patch, len(entries)))


if __name__ == "__main__":
    main()
