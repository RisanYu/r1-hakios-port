import io, sys

def patch(path, edits, decl=None):
    s = open(path, encoding="utf-8").read()
    report = []
    if decl is not None and decl not in s:
        s = decl + s
        report.append(("decl", 1))
    for anchor, ins, where in edits:
        c = s.count(anchor)
        if c != 1:
            report.append((anchor[:40], "COUNT=%d" % c))
            continue
        if where == "after":
            s = s.replace(anchor, anchor + ins, 1)
        else:
            s = s.replace(anchor, ins + anchor, 1)
        report.append((anchor[:40], "ok"))
    open(path, "w", encoding="utf-8").write(s)
    return report

base = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
CP = lambda n: "\n\tloader_checkpoint({});\n".format(n)

startup_edits = [
    ("kernel_startup_initialize_upto(STARTUP_SUB_LOCKDOWN);", CP(135), "after"),
    ("OSKextRemoveKextBootstrap();", CP(136), "after"),
    ("machine_lockdown();", CP(137), "after"),
    ("PE_lockdown_iokit();", CP(138), "after"),
    ("\tbsd_init();", CP(139), "before"),
]
bsd_edits = [
    ("\tthrottle_init();", CP(140), "after"),
    ("\tkauth_init();", CP(141), "after"),
    ("\tbsd_bufferinit();", CP(142), "after"),
    ("\tvfsinit();", CP(143), "after"),
    ("\tmbinit();", CP(144), "after"),
    ("\tbsd_autoconf();", CP(145), "after"),
    ("\tinittodr(0);", CP(146), "after"),
    ("\tIOSecureBSDRoot(rootdevice);", CP(147), "before"),
    ("\tlck_rw_lock_exclusive(&rootvnode_rw_lock);", CP(148), "before"),
    ("\t\tdevfs_kernel_mount(mounthere);", CP(149), "after"),
    ("\t\thakios_sparse_init();", CP(150), "after"),
    ("\tbsd_utaskbootstrap();", CP(151), "after"),
    ('\tbsd_init_kprintf("done\\n");', CP(152), "before"),
]
decl = "extern void loader_checkpoint(uint64_t n);\n"
r1 = patch(base + "/osfmk/kern/startup.c", startup_edits, decl)
r2 = patch(base + "/bsd/kern/bsd_init.c", bsd_edits, decl)
for tag, r in (("startup.c", r1), ("bsd_init.c", r2)):
    print("== " + tag)
    for k, v in r:
        print("   ", v, k)