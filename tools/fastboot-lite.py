#!/usr/bin/env python3
"""Minimal Windows fastboot client over libusb (pyusb).

Google's fastboot.exe needs its own WinUSB device-interface GUID; our device was
bound by Zadig with the libusb GUID, so fastboot.exe cannot see it. pyusb can
talk to the same WinUSB device directly, so this script speaks the fastboot
USB protocol itself.

usage:
  python fastboot-lite.py devices
  python fastboot-lite.py getvar product
  python fastboot-lite.py flash boot_a path/to/image.img
  python fastboot-lite.py reboot
"""
import sys
import time

import usb.core
import usb.util

VID = 0x18D1
# PIDs seen: D00D = fastboot (bootloader), D001 = fastbootd (userspace)
PIDS = (0xD00D, 0xD001, 0x4EE0)


def find_device():
    for pid in PIDS:
        dev = usb.core.find(idVendor=VID, idProduct=pid)
        if dev is not None:
            return dev
    return None


class Fastboot:
    def __init__(self, dev):
        self.dev = dev
        cfg = dev.get_active_configuration()
        self.intf = cfg[(0, 0)]
        self.ep_in = usb.util.find_descriptor(
            self.intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            self.intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        if self.ep_in is None or self.ep_out is None:
            raise RuntimeError("bulk endpoints not found")
        try:
            usb.util.claim_interface(dev, self.intf.bInterfaceNumber)
        except usb.core.USBError:
            pass

    def write(self, data, timeout=30000):
        self.dev.write(self.ep_out.bEndpointAddress, data, timeout=timeout)

    def read_header(self, timeout=30000):
        raw = self.dev.read(self.ep_in.bEndpointAddress, 64, timeout=timeout)
        hdr = bytes(raw)
        while len(hdr) < 64:
            hdr += b"\x00"
        return hdr

    def command(self, cmd, timeout=30000):
        """Send a command, returning (status, info)."""
        self.write(cmd, timeout=timeout)
        while True:
            hdr = self.read_header(timeout=timeout)
            status = hdr[:4].decode("ascii", "replace")
            info = hdr[4:].split(b"\x00")[0]
            if status == "INFO":
                print("INFO:" + info.decode("ascii", "replace"))
                continue
            return status, info

    def download(self, data, timeout=120000):
        status, info = self.command("download:%08x" % len(data), timeout=timeout)
        if status != "DATA":
            raise RuntimeError("download rejected: %s %s" % (status, info))
        # write in chunks; USB bulk transfer sizes must be padded to 512 for some loaders
        chunk = 1024 * 1024
        off = 0
        while off < len(data):
            piece = data[off:off + chunk]
            self.write(piece, timeout=timeout)
            off += len(piece)
            print("  sent %d/%d bytes" % (off, len(data)))
        while True:  # read final OKAY/FAIL without sending anything
            hdr = self.read_header(timeout=timeout)
            status = hdr[:4].decode("ascii", "replace")
            info = hdr[4:].split(b"\x00")[0]
            if status == "INFO":
                print("INFO:" + info.decode("ascii", "replace"))
                continue
            if status != "OKAY":
                raise RuntimeError("download failed: %s %s" % (status, info))
            break
        return True

    def flash(self, partition, path):
        data = open(path, "rb").read()
        print("flashing %s (%d bytes) ..." % (partition, len(data)))
        self.download(data)
        status, info = self.command("flash:%s" % partition, timeout=600000)
        if status == "OKAY":
            print("flash:%s OKAY" % partition)
            return True
        print("flash:%s FAILED: %s %s" % (partition, status, info.decode("ascii", "replace")))
        return False

    def getvar(self, name):
        status, info = self.command("getvar:%s" % name)
        text = info.decode("ascii", "replace")
        print("%s: %s" % (name, text if status == "OKAY" else "%s %s" % (status, text)))
        return status, text


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    dev = find_device()
    if cmd == "devices":
        if dev is None:
            print("no fastboot device found")
            return 1
        try:
            serial = usb.util.get_string(dev, dev.iSerialNumber)
        except Exception:
            serial = "?"
        print("%s\tfastboot" % serial)
        return 0
    if dev is None:
        print("no fastboot device found")
        return 1
    fb = Fastboot(dev)
    if cmd == "getvar":
        fb.getvar(argv[1] if len(argv) > 1 else "all")
        return 0
    if cmd == "flash":
        ok = fb.flash(argv[1], argv[2])
        return 0 if ok else 1
    if cmd in ("reboot", "reboot-bootloader", "reboot-fastboot"):
        status, info = fb.command(cmd)
        print(status, info)
        return 0
    if cmd == "raw":
        status, info = fb.command(" ".join(argv[1:]))
        print("raw %r -> %s %s" % (" ".join(argv[1:]), status, info.decode("ascii", "replace") if isinstance(info, bytes) else info))
        return 0 if status == "OKAY" else 1
    if cmd == "rawc":
        status, info = fb.command(":".join(argv[1:]))
        print("rawc %r -> %s %s" % (":".join(argv[1:]), status, info.decode("ascii", "replace") if isinstance(info, bytes) else info))
        return 0 if status == "OKAY" else 1
    if cmd == "erase":
        status, info = fb.command("erase:%s" % argv[1], timeout=120000)
        print("erase:%s -> %s %s" % (argv[1], status, info.decode("ascii", "replace") if isinstance(info, bytes) else info))
        return 0 if status == "OKAY" else 1
    if cmd == "boot":
        data = open(argv[1], "rb").read()
        print("RAM-booting %s (%d bytes) ..." % (argv[1], len(data)))
        fb.download(data)
        status, info = fb.command("boot", timeout=120000)
        print("boot -> %s %s" % (status, info.decode("ascii", "replace") if isinstance(info, bytes) else info))
        return 0 if status == "OKAY" else 1
    if cmd == "set_active":
        status, info = fb.command("set_active:%s" % argv[1])
        print("set_active:%s -> %s %s" % (argv[1], status, info.decode("ascii", "replace") if isinstance(info, bytes) else info))
        return 0 if status == "OKAY" else 1
    if cmd in ("oem", "flashing"):
        status, info = fb.command("%s %s" % (cmd, " ".join(argv[1:])))
        print(status, info.decode("ascii", "replace") if isinstance(info, bytes) else info)
        return 0
    print("unknown command: %s" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
