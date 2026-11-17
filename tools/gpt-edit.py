#!/usr/bin/env python3
"""Read and patch a GPT's partition type GUIDs from raw dumps taken through EDL.

Used for the R1 M4 step: make `system_b` an EFI System Partition (type GUID
C12A7328-F81F-11D2-BA4B-00A0C93EC93B) so the Renegade UEFI finds and boots the
HakiOS ESP inside it.

The two dumps are what `edl.py rs` reads:
    head = LBA 0 .. (1 + 1 + entries_sectors - 1)      (MBR + header + entries)
    tail = last (entries_sectors + 1) LBAs             (backup entries + header)

usage:
    gpt-edit.py list  --head head.img --sector-size 4096
    gpt-edit.py set-esp --head head.img --tail tail.img --name system_b \
                        --out-head new-head.img --out-tail new-tail.img --sector-size 4096

Everything except the entry type GUID, the entries CRC and the header CRC is
kept byte-for-byte identical; the tool checks both dumps agree before patching.
"""
import binascii
import struct
import sys
import uuid

ESP_GUID = uuid.UUID("C12A7328-F81F-11D2-BA4B-00A0C93EC93B")


def crc32(data):
    return binascii.crc32(data) & 0xFFFFFFFF


class Header:
    def __init__(self, sector_size, offset=0):
        self.sector_size = sector_size
        self.offset = offset
        self.raw = None
        self.fields = None

    def parse(self, data):
        if data[:8] != b"EFI PART":
            raise SystemExit("not a GPT header at this offset (first bytes: %r)" % data[:8])
        rev, hdrsize, crc, _res, current, backup, first_u, last_u, disk = struct.unpack_from("<IIIIQQQQ16s", data, 8)
        entries_lba, num, esize, ecrc = struct.unpack_from("<QIII", data, 72)
        self.hdrsize = hdrsize
        self.current = current
        self.backup = backup
        self.first_usable = first_u
        self.last_usable = last_u
        self.disk_guid = uuid.UUID(bytes_le=disk)
        self.entries_lba = entries_lba
        self.num = num
        self.esize = esize
        self.ecrc = ecrc
        self.raw = bytearray(data[:hdrsize])
        self.fields = (rev, hdrsize, crc, _res, current, backup, first_u, last_u, disk, entries_lba, num, esize, ecrc)
        return self

    @property
    def entries_sectors(self):
        return (self.num * self.esize + self.sector_size - 1) // self.sector_size

    def header_crc_ok(self):
        tmp = bytearray(self.raw)
        struct.pack_into("<I", tmp, 16, 0)
        return crc32(bytes(tmp)) == self.fields[2]

    def entries_crc_ok(self, entries):
        return crc32(entries) == self.ecrc

    def rebuild(self, entries):
        """new header bytes with entries CRC and header CRC updated"""
        raw = bytearray(self.raw)
        struct.pack_into("<I", raw, 88, crc32(entries))
        struct.pack_into("<I", raw, 16, 0)
        struct.pack_into("<I", raw, 16, crc32(bytes(raw)))
        return bytes(raw) + b"\0" * (self.sector_size - len(raw))


def read_entries(data, hdr, start):
    size = hdr.num * hdr.esize
    return bytearray(data[start:start + size])


def parse_entry(entry):
    t = uuid.UUID(bytes_le=bytes(entry[0:16]))
    u = uuid.UUID(bytes_le=bytes(entry[16:32]))
    first, last, attrs = struct.unpack_from("<QQQ", entry, 32)
    name = bytes(entry[56:128]).decode("utf-16-le", "replace").rstrip("\0")
    return t, u, first, last, attrs, name


def list_gpt(head, sector_size):
    hdr = Header(sector_size).parse(head[sector_size:])
    entries = read_entries(head, hdr, hdr.entries_lba * sector_size)
    print("header CRC: %s   entries CRC: %s" % (hdr.header_crc_ok(), hdr.entries_crc_ok(bytes(entries))))
    print("disk GUID : %s" % hdr.disk_guid)
    print("first/last usable LBA: %d/%d" % (hdr.first_usable, hdr.last_usable))
    for i in range(hdr.num):
        e = entries[i * hdr.esize:(i + 1) * hdr.esize]
        if not any(e):
            continue
        t, u, first, last, attrs, name = parse_entry(e)
        print("  %2d: %-24s type=%s  LBA %d..%d  (%.1f MB)  attrs=0x%x  uuid=%s"
              % (i, name, t, first, last, (last - first + 1) * sector_size / 1e6, attrs, u))
    return hdr, entries


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    mode = args[0]
    opts = {}
    i = 1
    while i < len(args):
        if args[i].startswith("--"):
            opts[args[i][2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    ss = int(opts.get("sector-size", "4096"))
    head_path = opts.get("head")
    if not head_path:
        sys.exit("--head is required")
    head = open(head_path, "rb").read()

    if mode == "list":
        list_gpt(head, ss)
        return
    if mode != "set-esp":
        sys.exit(__doc__)

    hdr, entries = list_gpt(head, ss)
    name_wanted = opts.get("name")
    if not name_wanted:
        sys.exit("--name is required")
    idx = None
    for i in range(hdr.num):
        e = entries[i * hdr.esize:(i + 1) * hdr.esize]
        if not any(e):
            continue
        _, _, _, _, _, name = parse_entry(e)
        if name == name_wanted:
            idx = i
            break
    if idx is None:
        sys.exit("partition %r not found" % name_wanted)

    tail_path = opts.get("tail")
    tail = open(tail_path, "rb").read()
    # backup: entries then header, at the end of the tail buffer
    tail_entries_size = hdr.num * hdr.esize
    tail_entries = bytearray(tail[:tail_entries_size])
    tail_hdr_off = len(tail) - ss
    back_hdr = Header(ss).parse(tail[tail_hdr_off:])
    if bytes(tail_entries) != bytes(entries):
        raise SystemExit("head and tail partition entries differ; refusing to patch")
    if back_hdr.num != hdr.num or back_hdr.esize != hdr.esize:
        raise SystemExit("head/tail header geometry differs")

    off = idx * hdr.esize
    old_type = uuid.UUID(bytes_le=bytes(entries[off:off + 16]))
    esp = ESP_GUID.bytes_le
    entries[off:off + 16] = esp
    tail_entries[off:off + 16] = esp
    new_head = bytearray(head)
    new_head[hdr.entries_lba * ss:hdr.entries_lba * ss + len(entries)] = entries
    new_head[ss:2 * ss] = hdr.rebuild(bytes(entries))
    new_tail = bytearray(tail)
    new_tail[:len(tail_entries)] = tail_entries
    new_tail[tail_hdr_off:] = back_hdr.rebuild(bytes(tail_entries))

    open(opts["out-head"], "wb").write(bytes(new_head))
    open(opts["out-tail"], "wb").write(bytes(new_tail))
    print("partition %r (index %d): %s -> %s" % (name_wanted, idx, old_type, ESP_GUID))
    print("wrote %s (%d bytes) and %s (%d bytes)" % (opts["out-head"], len(new_head), opts["out-tail"], len(new_tail)))


if __name__ == "__main__":
    main()
