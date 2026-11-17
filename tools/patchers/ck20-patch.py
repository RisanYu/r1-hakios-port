#!/usr/bin/env python3
"""ck20: dump the R1's memory-mapped timer frame registers (read-only)."""
ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
path = ROOT + "/osfmk/arm64/gic_v3_irq.c"
s = open(path).read()

NEW = r"""/* ck20 diagnostic: read the memory-mapped timer frame (read-only) */
static char *
gic_diag_hex(char *p, uint64_t v, int digits)
{
	const char *d = "0123456789abcdef";
	for (int i = digits - 1; i >= 0; i--) {
		*p++ = d[(v >> (i * 4)) & 0xf];
	}
	return p;
}

static uint32_t
gic_diag_rd(vm_offset_t base, uint32_t off)
{
	return base ? gic_read32(base + off) : 0xdeadbeefu;
}

static void
gic_diag_frame_line(const char *tag, vm_offset_t base)
{
	char b[620];
	char *p = b;
	while (*tag) {
		*p++ = *tag++;
	}
	for (uint32_t off = 0; off < 0x40; off += 4) {
		p = gic_diag_hex(p, gic_diag_rd(base, off), 8);
		*p++ = ' ';
	}
	*p++ = '\n';
	*p = 0;
	loader_log_line(b);
}

void
gic_v3_diag_timer(void)
{
	static vm_offset_t fa;
	static vm_offset_t fb;
	char h[96];
	char *q = h;
	const char *t;
	uint64_t cntpct = __builtin_arm_rsr64("CNTPCT_EL0");
	uint64_t cntvct = __builtin_arm_rsr64("CNTVCT_EL0");

	if (!fa) {
		fa = ml_io_map(0x17ca0000ULL, 0x1000);
		fb = ml_io_map(0x17cb0000ULL, 0x1000);
	}
	gic_diag_frame_line("mtA: ", fa);
	gic_diag_frame_line("mtB: ", fb);

	t = "mtC: cntpct=";
	while (*t) {
		*q++ = *t++;
	}
	q = gic_diag_hex(q, cntpct, 16);
	t = " cntvct=";
	while (*t) {
		*q++ = *t++;
	}
	q = gic_diag_hex(q, cntvct, 16);
	*q++ = '\n';
	*q = 0;
	loader_log_line(h);
}

"""

i = s.index("/* ck19 diagnostic: which intid does the handler see for a software-pended SPI? */")
j = s.index("#endif /* GENERIC_GIC_V3_IRQ */")
s = s[:i] + NEW + s[j:]
open(path, "w").write(s)
print("ck20 probe installed")
