#!/usr/bin/env python3
"""Scan the extracted /proc/device-tree dump for the hardware facts the HakiOS
trident port needs (panel, touch, UFS, USB, PMIC, sound, wifi/bt, fingerprint).

usage: dtscan.py <device-tree-root>
"""
import os
import struct
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"r1-trident\device-tree"


def prop(node, name):
    p = os.path.join(node, name)
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        return None


def u32be(b):
    if b is None or len(b) < 4:
        return None
    return struct.unpack(">I", b[:4])[0]


def sval(b):
    if b is None:
        return None
    return b.split(b"\0")[0].decode("utf-8", "replace")


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        yield dirpath, dirnames, filenames


def main():
    if not os.path.isdir(ROOT):
        sys.exit("no such directory: %s" % ROOT)
    # phandle -> node path
    phandles = {}
    for dirpath, _, filenames in walk(ROOT):
        if "phandle" in filenames:
            v = u32be(prop(dirpath, "phandle"))
            if v is not None:
                phandles[v] = dirpath
    print("nodes with phandle: %d" % len(phandles))

    def rel(p):
        return p[len(ROOT):].replace("\\", "/") or "/"

    # ---- active display node ----
    print("\n== display nodes with qcom,dsi-display-active ==")
    for dirpath, _, filenames in walk(ROOT):
        if "qcom,dsi-display-active" in filenames:
            print("  active display node:", rel(dirpath))
            panel = u32be(prop(dirpath, "qcom,dsi-panel"))
            print("    qcom,dsi-panel phandle:", panel, "->", rel(phandles.get(panel, "?")) if panel else "?")
            if panel and panel in phandles:
                pn = phandles[panel]
                print("    panel name :", sval(prop(pn, "qcom,mdss-dsi-panel-name")))
                print("    width x h  : %s x %s" % (u32be(prop(pn, "qcom,mdss-dsi-panel-width")),
                                                    u32be(prop(pn, "qcom,mdss-dsi-panel-height"))))
                print("    framerate  :", u32be(prop(pn, "qcom,mdss-dsi-panel-framerate")))
                print("    panel type :", sval(prop(pn, "qcom,mdss-dsi-panel-type")))
                print("    props      :", ", ".join(sorted(os.listdir(pn))[:40]))

    # ---- touch ----
    print("\n== touch nodes ==")
    for dirpath, _, filenames in walk(ROOT):
        base = os.path.basename(dirpath).lower()
        if "synaptics" in base or "touch" in base or "gt9" in base or "goodix" in base:
            print("  node:", rel(dirpath))
            for n in sorted(filenames):
                if n in ("compatible", "reg", "interrupt-parent", "interrupts", "synaptics,irq-gpio",
                         "qcom,irq-gpio", "qcom,reset-gpio", "vdd-supply", "synaptics,vdd-supply",
                         "status", "qcom,display-type"):
                    v = prop(dirpath, n)
                    print("    %-28s %r" % (n, v if len(v) < 80 else v[:80]))

    # ---- ufs ----
    print("\n== ufs host ==")
    for dirpath, dirnames, filenames in walk(ROOT):
        if os.path.basename(dirpath) in ("1d84000.ufshc",):
            print("  node:", rel(dirpath))
            for n in sorted(filenames):
                v = prop(dirpath, n)
                print("    %-34s %s" % (n, (v[:64].hex() if len(v) > 64 else repr(v))))

    # ---- pmic / spmi ----
    print("\n== pmic-ish nodes ==")
    for dirpath, dirnames, filenames in walk(ROOT):
        base = os.path.basename(dirpath).lower()
        if base.startswith(("qcom,pm8998", "qcom,pmi8998", "qcom,pm845", "qcom,pms405", "qcom,pm660")) or \
           base in ("spmi", "qcom,spmi@c440000"):
            print("  node:", rel(dirpath), " props:", ", ".join(sorted(filenames)[:12]))

    # ---- sound ----
    print("\n== sound / codec nodes ==")
    for dirpath, dirnames, filenames in walk(ROOT):
        base = os.path.basename(dirpath).lower()
        if "tavil" in base or "wcd" in base or base == "sound" or "snd" in base:
            print("  node:", rel(dirpath), " props:", ", ".join(sorted(filenames)[:12]))

    # ---- wifi / bt ----
    print("\n== wifi / bt nodes ==")
    for dirpath, dirnames, filenames in walk(ROOT):
        base = os.path.basename(dirpath).lower()
        if "wcn" in base or "wifi" in base or "bluetooth" in base or "bt" == base:
            print("  node:", rel(dirpath), " props:", ", ".join(sorted(filenames)[:12]))

    # ---- fingerprint ----
    print("\n== fingerprint nodes ==")
    for dirpath, dirnames, filenames in walk(ROOT):
        base = os.path.basename(dirpath).lower()
        if "fpc" in base or "fingerprint" in base or "goodix_fp" in base:
            print("  node:", rel(dirpath), " props:", ", ".join(sorted(filenames)[:12]))

    # ---- usb ----
    print("\n== usb nodes ==")
    for dirpath, dirnames, filenames in walk(ROOT):
        base = os.path.basename(dirpath).lower()
        if "dwc3" in base or "typec" in base or "usb" in base and base.count("@") == 1:
            print("  node:", rel(dirpath), " props:", ", ".join(sorted(filenames)[:14]))


if __name__ == "__main__":
    main()
