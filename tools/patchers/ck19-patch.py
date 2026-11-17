#!/usr/bin/env python3
"""ck19: identify which interrupt the handler saw when we software-pend SPI 38."""
ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
path = ROOT + "/osfmk/arm64/gic_v3_irq.c"
s = open(path).read()

NEW = r"""/* ck19 diagnostic: which intid does the handler see for a software-pended SPI? */
static char *
gic_diag_hex(char *p, uint64_t v, int digits)
{
	const char *d = "0123456789abcdef";
	for (int i = digits - 1; i >= 0; i--) {
		*p++ = d[(v >> (i * 4)) & 0xf];
	}
	return p;
}

static char *
gic_diag_dec(char *p, uint64_t v)
{
	char tmp[24];
	int n = 0;
	if (v == 0) {
		*p++ = '0';
		return p;
	}
	while (v > 0 && n < (int)sizeof(tmp)) {
		tmp[n++] = (char)('0' + (v % 10));
		v /= 10;
	}
	while (n > 0) {
		*p++ = tmp[--n];
	}
	return p;
}

static uint32_t
gic_diag_rd(vm_offset_t base, uint32_t off)
{
	return base ? gic_read32(base + off) : 0xdeadbeefu;
}

void
gic_v3_diag_timer(void)
{
	char b[620];
	char *p = b;
	int cpu = (int)ml_get_cpu_number_local();
	uint64_t mpidr = __builtin_arm_rsr64("MPIDR_EL1");
	uint64_t aff = mpidr & 0xffffff;
	const uint32_t intid = 38;
	uint32_t n = intid / 32;
	uint32_t bit = 1u << (intid % 32);

	uint64_t uh0 = gic_unhandled_count;
	uint32_t last0 = gic_last_unhandled;
	uint64_t irq0 = gic_diag_irq_count;

	gic_write32(gicd_base + GICD_IROUTER(intid), aff);
	gic_write32(gicd_base + GICD_IGROUPR(n), gic_diag_rd(gicd_base, GICD_IGROUPR(n)) | bit);
	gic_write32(gicd_base + GICD_IGRPMODR(n), gic_diag_rd(gicd_base, GICD_IGRPMODR(n)) & ~bit);
	gic_write32(gicd_base + GICD_ICENABLER(n), bit);
	gic_write32(gicd_base + GICD_ICPENDR(n), bit);
	gic_distributor_settle();
	uint32_t grp_after = gic_diag_rd(gicd_base, GICD_IGROUPR(n));
	gic_write32(gicd_base + GICD_ISENABLER(n), bit);
	gic_distributor_settle();
	uint32_t en_after = gic_diag_rd(gicd_base, GICD_ISENABLER(n));

	gic_write32(gicd_base + GICD_ISPENDR(n), bit);
	gic_distributor_settle();
	uint32_t pend_after = gic_diag_rd(gicd_base, GICD_ISPENDR(n));

	uint64_t cntvct = __builtin_arm_rsr64("CNTVCT_EL0");
	uint64_t deadline = cntvct + 19200000 / 500;
	while (__builtin_arm_rsr64("CNTVCT_EL0") < deadline) {
		/* spin 2 ms */
	}

	uint64_t irq1 = gic_diag_irq_count;
	uint64_t uh1 = gic_unhandled_count;
	uint32_t last1 = gic_last_unhandled;
	uint32_t pend_end = gic_diag_rd(gicd_base, GICD_ISPENDR(n));
	uint64_t hppir1b = __builtin_arm_rsr64("ICC_HPPIR1_EL1");

	gic_write32(gicd_base + GICD_ICPENDR(n), bit);
	gic_write32(gicd_base + GICD_ICENABLER(n), bit);
	gic_distributor_settle();

#define PUTS(x) do { const char *q = (x); while (*q) { *p++ = *q++; } } while (0)
	PUTS("tmr6: grpa=");
	p = gic_diag_hex(p, grp_after, 8);
	PUTS(" ena=");
	p = gic_diag_hex(p, en_after, 8);
	PUTS(" penda=");
	p = gic_diag_hex(p, pend_after, 8);
	PUTS(" pendend=");
	p = gic_diag_hex(p, pend_end, 8);
	PUTS(" irq=");
	p = gic_diag_dec(p, irq1 - irq0);
	PUTS(" uh=");
	p = gic_diag_dec(p, uh1 - uh0);
	PUTS(" last0=");
	p = gic_diag_dec(p, last0);
	PUTS(" last1=");
	p = gic_diag_dec(p, last1);
	PUTS(" hppir1=");
	p = gic_diag_hex(p, hppir1b, 6);
	PUTS(" mpidr=");
	p = gic_diag_hex(p, mpidr, 16);
	PUTS(" cpu=");
	p = gic_diag_dec(p, (uint64_t)cpu);
	*p++ = '\n';
	*p = 0;
	loader_log_line(b);
#undef PUTS
}

"""

i = s.index("/* ck18 diagnostic: can a distributor SPI be made Group 1 NS and delivered? */")
j = s.index("#endif /* GENERIC_GIC_V3_IRQ */")
s = s[:i] + NEW + s[j:]
open(path, "w").write(s)
print("ck19 probe installed")
