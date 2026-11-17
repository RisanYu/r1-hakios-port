"""Wrap a FAT32 filesystem image in a GPT disk image with one EFI System
Partition, so a UEFI firmware (AAVMF in QEMU, Renegade on the R1) sees it as an
ESP and boots \\EFI\\BOOT\\BOOTAA64.EFI from it.

usage: mkgptesp.py <out.img> <fat.img> <volume-name>
"""
import binascii
import struct
import sys
import uuid

SECTOR = 512
ENTRY_SIZE = 128
NUM_ENTRIES = 128
ENTRIES_SECTORS = (NUM_ENTRIES * ENTRY_SIZE) // SECTOR

ESP_TYPE = uuid.UUID("C12A7328-F81F-11D2-BA4B-00A0C93EC93B")


def guid_bytes(u):
    b = u.bytes_le
    return b


def crc32(data):
    return binascii.crc32(data) & 0xFFFFFFFF


def build_mbr(total_sectors):
    mbr = bytearray(SECTOR)
    # partition entry 1: type 0xEE protective, LBA 1 .. total-1
    e = 446
    mbr[e + 4] = 0xEE
    struct.pack_into("<I", mbr, e + 8, 1)
    struct.pack_into("<I", mbr, e + 12, min(total_sectors - 1, 0xFFFFFFFF))
    mbr[510] = 0x55
    mbr[511] = 0xAA
    return bytes(mbr)


def build_header(current, backup, first_usable, last_usable, disk_guid, entries_crc, part_start):
    h = bytearray(92)
    h[0:8] = b"EFI PART"
    struct.pack_into("<I", h, 8, 0x00010000)      # revision
    struct.pack_into("<I", h, 12, 92)             # header size
    struct.pack_into("<I", h, 16, 0)              # crc (filled later)
    struct.pack_into("<I", h, 20, 0)              # reserved
    struct.pack_into("<Q", h, 24, current)
    struct.pack_into("<Q", h, 32, backup)
    struct.pack_into("<Q", h, 40, first_usable)
    struct.pack_into("<Q", h, 48, last_usable)
    h[56:72] = guid_bytes(disk_guid)
    struct.pack_into("<Q", h, 72, part_start)     # entries start LBA
    struct.pack_into("<I", h, 80, NUM_ENTRIES)
    struct.pack_into("<I", h, 84, ENTRY_SIZE)
    struct.pack_into("<I", h, 88, entries_crc)
    struct.pack_into("<I", h, 16, crc32(bytes(h)))
    return bytes(h) + b"\0" * (SECTOR - 92)


def main():
    out, fat_path, name = sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "HAKIOS"
    type_guid_arg = sys.argv[4] if len(sys.argv) > 4 else ""
    fat = open(fat_path, "rb").read()
    if len(fat) % SECTOR:
        raise SystemExit("FAT image is not a multiple of 512 bytes")
    fat_sectors = len(fat) // SECTOR
    part_start = 2048
    part_end = part_start + fat_sectors - 1
    total_sectors = part_end + 1 + 2048
    disk_guid = uuid.uuid4()
    part_guid = uuid.uuid4()

    entries = bytearray(NUM_ENTRIES * ENTRY_SIZE)
    e = entries
    tguid = uuid.UUID(type_guid_arg) if type_guid_arg else ESP_TYPE
    e[0:16] = guid_bytes(tguid)
    e[16:32] = guid_bytes(part_guid)
    struct.pack_into("<Q", e, 32, part_start)
    struct.pack_into("<Q", e, 40, part_end)
    struct.pack_into("<Q", e, 48, 0)
    nm = name.encode("utf-16-le")[:72]
    e[56:56 + len(nm)] = nm
    entries_crc = crc32(bytes(entries))

    img = bytearray(total_sectors * SECTOR)
    img[0:SECTOR] = build_mbr(total_sectors)
    img[SECTOR:2 * SECTOR] = build_header(1, total_sectors - 1, 34, total_sectors - 34,
                                          disk_guid, entries_crc, 2)
    img[2 * SECTOR:2 * SECTOR + len(entries)] = entries
    # backup entries
    bstart = (total_sectors - 1 - ENTRIES_SECTORS) * SECTOR
    img[bstart:bstart + len(entries)] = entries
    # backup header
    back = build_header(total_sectors - 1, 1, 34, total_sectors - 34, disk_guid, entries_crc, 2)
    img[(total_sectors - 1) * SECTOR:total_sectors * SECTOR] = back
    # the filesystem
    img[part_start * SECTOR:part_start * SECTOR + len(fat)] = fat

    with open(out, "wb") as f:
        f.write(img)
    print("wrote %s: %d bytes, %d sectors; ESP at LBA %d..%d" % (out, len(img), total_sectors, part_start, part_end))


if __name__ == "__main__":
    main()
