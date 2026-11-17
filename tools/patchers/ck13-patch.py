p = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2/iokit/bsddev/IOKitBSDInit.cpp"
s = open(p, encoding="utf-8").read()
CP = lambda n: "\tloader_checkpoint({});\n".format(n)
decl = 'extern "C" void loader_checkpoint(unsigned long long n);\n'
if decl not in s:
    s = decl + s
edits = [
    ("\tint xchar, dchar;\n", CP(160), "after"),
    ("\tmatching->release();\n\tmatching = NULL;\n", CP(161), "after"),
    ("\t\tIOSleep( 5 * 1000 );\n\t}\n", CP(162), "after"),
    ("\trdBootVar = str.data() + kMaxPathBuf;\n", CP(163), "after"),
    ("\t\tOSSafeReleaseNULL(regEntry);\n\t}\n", CP(164), "after"),
    ("\t\t\tregEntry->release();                                                            /* Toss the entry */\n\t\t}\n\t}\n", CP(165), "after"),
    ("\t\t\t*root = mdevlookup(xchar);", CP(166), "before"),
    ('\t\t\t\tIOLog("BSD root: %s, major %d, minor %d\\n", rootName, major(*root), minor(*root));\n', CP(167), "after"),
    ('\t\t\tpanic("IOFindBSDRoot: specified root memory device', CP(168), "before"),
]
for anchor, ins, where in edits:
    c = s.count(anchor)
    print("count=%d anchor=%r" % (c, anchor[:60]))
    if c != 1:
        continue
    s = s.replace(anchor, (ins + anchor) if where == "before" else (anchor + ins), 1)
open(p, "w", encoding="utf-8").write(s)
print("patched ok")