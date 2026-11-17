import sys
p = sys.argv[1]
h = open(p, 'rb').read()
be = lambda o, n: int.from_bytes(h[o:o+n], 'big')
print("file            :", p, len(h), "bytes")
print("magic           :", h[0:4])
print("version         : %d.%d" % (be(4,4), be(8,4)))
auth = be(12,8); aux = be(20,8); algo = be(28,4)
print("auth_block_size :", auth)
print("aux_block_size  :", aux)
print("algorithm_type  :", algo)
print("hash            : off=%d size=%d" % (be(32,8), be(40,8)))
print("signature       : off=%d size=%d" % (be(48,8), be(56,8)))
print("public_key      : off=%d size=%d" % (be(64,8), be(72,8)))
print("descriptors     : off=%d size=%d" % (be(96,8), be(104,8)))
flags = be(120,4)
print("rollback_index  :", be(112,8))
print("flags           : 0x%x  (bit0 hashtree_disabled=%d, bit1 verification_disabled=%d)" % (flags, flags & 1, (flags >> 1) & 1))
print("rollback_loc    :", be(124,4))
# descriptor types
doff, dsize = be(96,8), be(104,8)
o = doff
while o < doff + dsize:
    tag = be(o,8); dlen = be(o+8,8)
    print("  descriptor tag=0x%x len=%d" % (tag, dlen))
    if dlen == 0: break
    o += 8 + dlen