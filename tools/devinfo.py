#!/usr/bin/env python3
"""Parse / patch a Qualcomm `devinfo` partition image (bootloader lock flags).

Layout (confirmed by 0xmehr4b's POCO X3 Pro EDL unlocker guide and its
`firmware/devinfo_unlocked.img` sample):

    offset 0x00..0x0C  "ANDROID-BOOT!"          magic, 13 bytes
    offset 0x0D        is_unlocked              1 byte, 1 = unlocked
    offset 0x0E        is_unlock_critical       1 byte, 1 = critical partitions unlocked
    offset 0x0F..       other data (board/display/charger), byte-for-byte untouched

ABL (Android Bootloader) reads exactly these two bytes when
IsSecureBootEnabled() == 0; it skips the oem_misc1 token checks then and
trusts the devinfo flags.

usage:
    devinfo.py info    <devinfo.img>
    devinfo.py unlock  <devinfo_in> <devinfo_out>
    devinfo.py verify  <before> <after>

Everything outside offsets 0x0D and 0x0E is copied unchanged; the patched
image is 4096 bytes (one UFS sector) as the partition is.
"""
import sys

MAGIC = b"ANDROID-BOOT!"
OFF_UNLOCKED = 0x0D
OFF_CRITICAL = 0x0E


def load(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def describe(data):
    nz = [i for i, b in enumerate(data[:64]) if b]
    print("file size            : %d bytes" % len(data))
    print("magic (offset 0x00)  : %r" % bytes(data[:13]))
    print("magic ok             : %s" % (bytes(data[:13]) == MAGIC))
    print("is_unlocked (0x0D)   : %d" % data[OFF_UNLOCKED])
    print("is_unlock_critical(0x0E): %d" % data[OFF_CRITICAL])
    print("non-zero bytes < 64  : %s" % nz)
    print("first 32 bytes       : %s" % " ".join("%02x" % b for b in data[:32]))


def cmd_info(path):
    data = load(path)
    describe(data)
    if bytes(data[:13]) != MAGIC:
        print("WARNING: no ANDROID-BOOT! magic; this does not look like a devinfo image")


def cmd_unlock(src, dst):
    data = load(src)
    if bytes(data[:13]) != MAGIC:
        raise SystemExit("no ANDROID-BOOT! magic at 0x00; refusing to patch")
    before = bytes(data)
    data[OFF_UNLOCKED] = 1
    data[OFF_CRITICAL] = 1
    with open(dst, "wb") as f:
        f.write(data)
    after = bytes(data)
    diff = [i for i in range(len(before)) if before[i] != after[i]]
    describe(data)
    print("patched -> %s" % dst)
    print("changed offsets      : %s" % diff)
    bad = [i for i in diff if i not in (OFF_UNLOCKED, OFF_CRITICAL)]
    if bad:
        raise SystemExit("BUG: unexpected offsets changed: %s" % bad)
    if not diff:
        print("note: nothing changed (already unlock flags set)")


def cmd_verify(before_path, after_path):
    a = load(before_path)
    b = load(after_path)
    if len(a) != len(b):
        raise SystemExit("size differs: %d vs %d" % (len(a), len(b)))
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    print("sizes equal (%d bytes)" % len(a))
    print("differing offsets: %s" % diff)
    print("before: is_unlocked=%d is_unlock_critical=%d" % (a[OFF_UNLOCKED], a[OFF_CRITICAL]))
    print("after : is_unlocked=%d is_unlock_critical=%d" % (b[OFF_UNLOCKED], b[OFF_CRITICAL]))
    bad = [i for i in diff if i not in (OFF_UNLOCKED, OFF_CRITICAL)]
    print("OK: only the two flag bytes changed" if not bad else "PROBLEM: other bytes changed: %s" % bad)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "info" and len(sys.argv) == 3:
        cmd_info(sys.argv[2])
    elif cmd == "unlock" and len(sys.argv) == 4:
        cmd_unlock(sys.argv[2], sys.argv[3])
    elif cmd == "verify" and len(sys.argv) == 4:
        cmd_verify(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
