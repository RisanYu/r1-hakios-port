#!/usr/bin/env python3
"""Batch EDL operations in ONE firehose session.

The phone drops out of EDL after a session ends (and re-uploading the loader for every
partition takes ~10 s each), so this script connects once and runs a JSON plan:

  { "ops": [
      {"op":"r", "part":"devinfo", "lun":4, "file":"backup/devinfo.img"},
      {"op":"w", "part":"boot_a", "lun":4, "file":"r1-trident/boot-trident.img"},
      {"op":"wverify", "part":"boot_a", "lun":4, "file":"r1-trident/boot-trident.img"},
      {"op":"reset"}
  ]}

usage:
  python edl-batch.py --loader lineflash/prog_firehose_ddr.elf --plan backup-plan.json
"""
import argparse
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # hakios-trident
EDL_DIR = os.path.join(ROOT, "tools", "edl-src", "edl-master")


def load_edl_module():
    if EDL_DIR not in sys.path:
        sys.path.insert(0, EDL_DIR)
    edl_py = os.path.join(EDL_DIR, "edl.py")
    saved = sys.argv[:]
    sys.argv = ["edl.py", "printgpt"]              # docopt runs at import time
    try:
        spec = importlib.util.spec_from_file_location("edlroot", edl_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.argv = saved
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loader", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--memory", default="UFS")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding="utf-8-sig"))
    ops = plan["ops"]
    print("plan: %d operations" % len(ops))

    mod = load_edl_module()
    eargs = mod.args
    eargs["--loader"] = os.path.abspath(args.loader)
    eargs["--memory"] = args.memory
    eargs["--debugmode"] = bool(args.debug)
    for k in ("--vid", "--pid"):
        eargs[k] = eargs.get(k) or "-1"

    e = mod.main(eargs)                            # imported mode: parse_cmd() == ""
    print("connecting (Sahara + firehose) ...")
    rc = e.run()
    if rc != 0 or e.fh is None:
        print("connect failed, rc=%s" % rc)
        return 1
    print("connected to firehose")

    def fire(cmd):
        return e.fh.handle_firehose(cmd, e.args)

    results = []
    for i, op in enumerate(ops, 1):
        kind = op["op"]
        if kind == "rs":
            e.args["<start_sector>"] = str(op["start"])
            e.args["<sectors>"] = str(op["sectors"])
            e.args["<filename>"] = os.path.abspath(op["file"])
            e.args["--lun"] = str(op.get("lun", 0))
            ok = fire("rs")
            size = os.path.getsize(op["file"]) if os.path.exists(op["file"]) else -1
            print("[%d/%d] read  sectors %s+%s lun %s -> %s (%s bytes) %s" % (i, len(ops), op["start"], op["sectors"], op.get("lun", 0), op["file"], size, "OK" if ok else "FAIL"))
            results.append((op, ok))
            if not ok:
                break
            continue
        if kind in ("r", "w", "wverify"):
            e.args["<partitionname>"] = op["part"]
            e.args["<filename>"] = os.path.abspath(op["file"])
            e.args["--lun"] = str(op.get("lun", 0))
            e.args["--sectorsize"] = op.get("sectorsize")
            e.args["--skipwrite"] = False
            if kind == "r":
                os.makedirs(os.path.dirname(os.path.abspath(op["file"])) or ".", exist_ok=True)
                ok = fire("r")
                size = os.path.getsize(op["file"]) if os.path.exists(op["file"]) else -1
                print("[%d/%d] read  %-10s lun %s -> %s (%s bytes) %s" % (i, len(ops), op["part"], op.get("lun", 0), op["file"], size, "OK" if ok else "FAIL"))
                results.append((op, ok))
                if not ok:
                    print("read failed; stopping")
                    break
            else:
                ok = fire("w")
                print("[%d/%d] write %-10s lun %s <- %s %s" % (i, len(ops), op["part"], op.get("lun", 0), op["file"], "OK" if ok else "FAIL"))
                results.append((op, ok))
                if not ok:
                    print("write failed; stopping")
                    break
                if kind == "wverify":
                    src = open(op["file"], "rb").read()
                    limit = op.get("bytes")
                    if limit:
                        src = src[:int(limit)]
                    tmp = os.path.join(ROOT, "tmp", "verify-%s.img" % op["part"])
                    os.makedirs(os.path.dirname(tmp), exist_ok=True)
                    e.args["<filename>"] = tmp
                    rok = fire("r")
                    if rok and os.path.exists(tmp):
                        rb = open(tmp, "rb").read()
                        same = rb[:len(src)] == src
                        print("        readback %s: %s (%d bytes compared)" % (op["part"], "IDENTICAL" if same else "MISMATCH", len(src)))
                        if not same:
                            break
                    else:
                        print("        readback failed; stopping")
                        break
        elif kind == "reset":
            e.args["--resetmode"] = op.get("mode")
            fire("reset")
            print("[%d/%d] reset sent (mode=%s)" % (i, len(ops), op.get("mode")))
            break
        elif kind == "sleep":
            time.sleep(op.get("seconds", 1))
        else:
            print("unknown op:", kind)
            break

    print("closing")
    try:
        e.exit()
    except SystemExit:
        pass
    bad = [op for op, ok in results if not ok]
    print("done: %d/%d ok" % (len(results) - len(bad), len(results)))
    return 0 if not bad and len(results) == len([o for o in ops if o["op"] in ("r", "w", "wverify")]) else 1


if __name__ == "__main__":
    sys.exit(main())
