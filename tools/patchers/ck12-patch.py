import sys
p = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2/bsd/kern/bsd_init.c"
s = open(p, encoding="utf-8").read()
CP = lambda n: "\n\t\tloader_checkpoint({});\n".format(n)
edits = [
    ("\t\tsetconf();", CP(156), "before"),
    ("\t\tsetconf();", CP(153), "after"),
    ("\t\trootdevice[0] = '\\0';", CP(154), "after"),
    ('\t\tprintf("cannot mount root, errno = %d\\n", err);', CP(155), "after"),
]
for anchor, ins, where in edits:
    c = s.count(anchor)
    print(repr(anchor[:30]), "count=", c)
    if c != 1:
        continue
    s = s.replace(anchor, (ins + anchor) if where == "before" else (anchor + ins), 1)
open(p, "w", encoding="utf-8").write(s)
print("patched")