#!/usr/bin/env python3
"""One UEFI/kernel boot cycle on the R1 with the locally built trident kernel.

Steps: build payload + 48 MB ESP -> fastboot (oem reboot-edl) -> EDL write
system_b (wverify 32 MB) -> reset -> fastboot -> RAM boot UEFI (boot-v0) ->
wait for the kernel to return or hang -> back in fastboot -> oem reboot-edl ->
read logdump -> save + analyse.

The kernel is copied out of WSL by tools/copy-kernel-from-wsl.sh; everything
else is the same as night_runner.py.
"""
import json
import os
import re
import subprocess
import sys
import time

WS = r"C:\Users\Risan-Yu\Documents\deepseek-harness\default-workspace"
ROOT = os.path.join(WS, "hakios-trident")
PY = r"C:\Users\Risan-Yu\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
LIB = os.path.join(ROOT, r"tools\edl-src\edl-master\Drivers\Windows\libusb\libusb-1.0.26-binaries\VS2015-x64\dll")
FBL = os.path.join(ROOT, "tools", "fastboot-lite.py")
EDL_BATCH = os.path.join(ROOT, "tools", "edl-batch.py")
MKPAYLOAD = os.path.join(WS, "hakios-xnu-kernel-main", "xnuloader", "mkpayload.py")
MKESP = os.path.join(ROOT, "tools", "mkespimg2.py")
FIREHOSE = os.path.join(ROOT, "lineflash", "prog_firehose_ddr.elf")
KERNEL = os.environ.get("HAKIOS_KERNEL", os.path.join(ROOT, "kernel", "hakios-kernel-trident"))
RAMDISK = os.path.join(WS, "hakios-xnu-kernel-main", "prebuilt", "userland", "hello")
LOADER = os.path.join(ROOT, "qemu-run", "loader-trident.efi")
PAYLOAD = os.environ.get("HAKIOS_PAYLOAD", os.path.join(ROOT, "kernel", "payload-trident.bin"))
ESP = os.environ.get("HAKIOS_ESP", os.path.join(ROOT, "kernel", "system_b-esp-trident.img"))
BOOTIMG = os.path.join(WS, "r1-trident", "variants", "boot-v0-p4096-u10000000.img")
CYCLES = os.path.join(ROOT, "backup", "cycles")
LOG = os.path.join(ROOT, "trident-cycle.log")

env = dict(os.environ)
env["PATH"] = LIB + os.pathsep + env.get("PATH", "")
env["TMP"] = os.path.join(WS, "tmp")
env["TEMP"] = env["TMP"]


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT after %ss" % timeout
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def dev_state():
    try:
        p = subprocess.run(["pnputil", "/enum-devices", "/connected"], capture_output=True, text=True, timeout=30)
        out = (p.stdout or "") + (p.stderr or "")
    except Exception:  # noqa: BLE001
        return None
    if "VID_05C6&PID_9008" in out:
        return "edl"
    if "VID_18D1&PID_D00D" in out:
        return "fastboot"
    return None


def wait_state(state, seconds, stable=2):
    end = time.time() + seconds
    hits = 0
    while time.time() < end:
        if dev_state() == state:
            hits += 1
            if hits >= stable:
                return True
        else:
            hits = 0
        time.sleep(1)
    return False


def wait_device_gone(seconds=40):
    end = time.time() + seconds
    gone = 0
    while time.time() < end:
        if dev_state() is None:
            gone += 1
            if gone >= 3:
                return True
        else:
            gone = 0
        time.sleep(1)
    return False


def fastboot(*args, timeout=90):
    return run([PY, FBL] + list(args), timeout)


def make_esp(cmdline):
    os.makedirs(os.path.dirname(PAYLOAD), exist_ok=True)
    extra = []
    checkpoint = os.environ.get("HAKIOS_CHECKPOINT", "")
    if checkpoint:
        # loader checkpoints (osfmk/arm/arm_init.c): the kernel stops there and hands its
        # log back, which is how a boot is bisected on a phone without a serial port.
        extra += ["--checkpoint", checkpoint]
    rc, out = run([PY, MKPAYLOAD, "-o", PAYLOAD,
                   "kernel=" + KERNEL, "ramdisk=" + RAMDISK,
                   "--cmdline", cmdline, "--platform", "trident"] + extra, 180)
    if rc != 0:
        return False, out
    rc, out = run([PY, MKESP, ESP, "48", LOADER, PAYLOAD], 240)
    return rc == 0, out


def edl_batch(plan_path, timeout):
    return run([PY, EDL_BATCH, "--loader", FIREHOSE, "--plan", plan_path], timeout)


def firehose_reset():
    plan = os.path.join(ROOT, "kernel", "reset-plan.json")
    with open(plan, "w", encoding="utf-8") as f:
        json.dump({"ops": [{"op": "reset", "mode": "reset"}]}, f)
    return edl_batch(plan, 120)


def to_fastboot():
    st = dev_state()
    if st == "fastboot":
        return True
    if st == "edl":
        firehose_reset()
        time.sleep(2)
    elif st is None:
        time.sleep(5)
    return wait_state("fastboot", 240)


def to_edl_from_fastboot():
    if dev_state() != "fastboot":
        return False
    fastboot("raw", "oem reboot-edl", timeout=30)
    return wait_state("edl", 120)


def analyse_logdump(name):
    src = os.path.join(ROOT, "backup", "logdump-kernel.img")
    if not os.path.exists(src):
        return "no logdump file"
    data = open(src, "rb").read()
    # trident_cycle zeroes the first 1 MiB of logdump before every run, so only that head
    # belongs to this run; the rest of the partition is the previous run's text.
    area = data[:1 * 1024 * 1024]
    runs = [m.group().decode("ascii", "replace") for m in re.finditer(rb"[\x20-\x7e\n\r\t]{6,}", area)]
    text = "".join(runs)
    os.makedirs(CYCLES, exist_ok=True)
    with open(os.path.join(CYCLES, name + "-logdump.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.replace(src, os.path.join(CYCLES, name + "-logdump.img"))
    except OSError:
        pass
    flags = []
    loader_runs = text.count("== XNULOADER v3 ==")
    if loader_runs == 0:
        flags.append("no-loader-log")
    m = re.findall(r"kernel returned: log at [0-9a-f]+, (\d+) bytes", text)
    if m:
        flags.append("returned(%s bytes)" % m[0])
    m = re.findall(r"STOPPED AT CHECKPOINT (\d+)", text)
    if m:
        flags.append("checkpoint(%s)" % m[0])
    m = re.findall(r"EARLY KERNEL EXCEPTION: esr=([0-9a-f]+) elr=([0-9a-f]+) far=([0-9a-f]+)", text)
    if m:
        flags.append("early-exception(esr=%s elr=%s far=%s)" % m[0])
    if "THE KERNEL HUNG" in text:
        flags.append("hung")
    if "== KERNEL LOG ==" in text:
        flags.append("kernellog")
    tail = text[text.rfind("jumping"):] if "jumping" in text else text[-2000:]
    tail = re.sub(r"log: \d+ bytes written[^\n]*\n", "", tail).strip()[:2000]
    return "loader-runs=%d flags=%s tail=%s" % (loader_runs, "+".join(flags) if flags else "none",
                                               tail.replace("\n", " | "))


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "cycle"
    if len(sys.argv) > 2:
        cmdline = sys.argv[2]
    else:
        cmdline = " ".join(sys.argv[3:]) or "-v debug=0x144 keepsyms=1 loader_return_after=30"
    os.makedirs(CYCLES, exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    open(LOG, "a", encoding="utf-8").close()
    log("=== %s start; kernel=%s (%d bytes)" % (name, KERNEL, os.path.getsize(KERNEL) if os.path.exists(KERNEL) else -1))
    log("cmdline: %s" % cmdline)

    ok, out = make_esp(cmdline)
    if not ok:
        log("ESP build failed: %s" % out[-400:])
        return 1
    log("payload+ESP built: %d / %d bytes" % (os.path.getsize(PAYLOAD), os.path.getsize(ESP)))

    # Zero the head of logdump before every run: the loader appends its log there and the
    # partition keeps the previous run's text, which made earlier analyses read a stale
    # "kernel returned" line.  1 MiB is well past the loader's largest log.
    zero = os.path.join(ROOT, "kernel", "logdump-zero.bin")
    if (not os.path.exists(zero)) or os.path.getsize(zero) != (1 << 20):
        with open(zero, "wb") as f:
            f.write(b"\x00" * (1 << 20))

    plan_write = os.path.join(ROOT, "kernel", "edl-write-esp.json")
    with open(plan_write, "w", encoding="utf-8") as f:
        json.dump({"ops": [
            {"op": "w", "part": "logdump", "lun": 4, "file": zero},
            {"op": "wverify", "part": "system_b", "lun": 0, "file": ESP,
             "bytes": int(os.environ.get("HAKIOS_VERIFY_BYTES", "33554432"))},
            {"op": "reset", "mode": "reset"},
        ]}, f)
    plan_read = os.path.join(ROOT, "kernel", "edl-read-logdump.json")
    with open(plan_read, "w", encoding="utf-8") as f:
        json.dump({"ops": [
            {"op": "r", "part": "logdump", "lun": 4, "file": os.path.join(ROOT, "backup", "logdump-kernel.img")},
        ]}, f)

    if not to_fastboot():
        log("no fastboot at start (state=%s)" % dev_state())
        return 2
    if not to_edl_from_fastboot():
        log("cannot switch to EDL")
        return 3
    rc, out = edl_batch(plan_write, 300)
    log("esp write rc=%s" % rc)
    for line in out.splitlines():
        if "system_b" in line or "reset" in line or "wverify" in line:
            log("  " + line.strip())
    if not wait_state("fastboot", 360):
        log("no fastboot after write (state=%s)" % dev_state())
        return 4

    rc, out = fastboot("boot", BOOTIMG, timeout=180)
    log("RAM boot rc=%s %s" % (rc, out.strip()[-160:]))
    if "OKAY" not in out:
        return 5
    if not wait_device_gone(60):
        log("device did not leave fastboot after the RAM boot")
        return 6
    t0 = time.time()
    if not wait_state("fastboot", 420):
        log("kernel did not return (state=%s, %.0fs)" % (dev_state(), time.time() - t0))
        return 7
    log("back in fastboot after %.0fs" % (time.time() - t0))

    if not to_edl_from_fastboot():
        log("cannot switch to EDL for log")
        return 8
    rc, out = edl_batch(plan_read, 300)
    log("logdump read rc=%s" % rc)
    summary = analyse_logdump(name)
    log("%s: %s" % (name, summary[:400]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
