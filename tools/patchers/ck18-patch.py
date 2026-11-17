#!/usr/bin/env python3
"""ck18: are SPIs (the memory-mapped timer interrupts) deliverable as Group 1 NS?"""
ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
path = ROOT + "/osfmk/arm64/gic_v3_irq.c"
s = open(path).read()

NEW = r"""/* ck18 diagnostic: can a distributor SPI be made Group 1 NS and delivered? */
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
	uint64_t cur_el = __builtin_arm_rsr64("CurrentEL");
	uint64_t mpidr = __builtin_arm_rsr64("MPIDR_EL1");
	uint64_t gicdctlr0 = gic_diag_rd(gicd_base, GICD_CTLR);
	uint32_t grp_d1 = gic_diag_rd(gicd_base, GICD_IGROUPR(1));
	uint32_t grp_d2 = gic_diag_rd(gicd_base, GICD_IGROUPR(2));
	uint32_t en0 = gic_diag_rd(gicd_base, GICD_ISENABLER(1));
	uint32_t pend0 = gic_diag_rd(gicd_base, GICD_ISPENDR(1));

	const uint32_t intid = 38;              /* memory-mapped timer frame 0, per the phone's DT */
	uint64_t irq0 = gic_diag_irq_count;
	uint64_t vt0 = gic_diag_vtimer_count;
	uint64_t aff = mpidr & 0xffffff;

	/* route it to this processor, make it Group 1 NS, then software-pend it */
	gic_write32(gicd_base + GICD_IROUTER(intid), aff);
	gic_write32(gicd_base + GICD_IGROUPR(intid / 32), gic_diag_rd(gicd_base, GICD_IGROUPR(intid / 32)) | (1u << (intid % 32)));
	gic_write32(gicd_base + GICD_IGRPMODR(intid / 32), gic_diag_rd(gicd_base, GICD_IGRPMODR(intid / 32)) & ~(1u << (intid % 32)));
	gic_write32(gicd_base + GICD_ICENABLER(intid / 32), 1u << (intid % 32));
	gic_write32(gicd_base + GICD_ICPENDR(intid / 32), 1u << (intid % 32));
	gic_write32(gicd_base + GICD_ISENABLER(intid / 32), 1u << (intid % 32));
	gic_distributor_settle();
	uint32_t grp_after = gic_diag_rd(gicd_base, GICD_IGROUPR(intid / 32));
	uint32_t router_after = gic_diag_rd(gicd_base, GICD_IROUTER(intid));

	gic_write32(gicd_base + GICD_ISPENDR(intid / 32), 1u << (intid % 32));
	gic_distributor_settle();

	uint64_t cntvct = __builtin_arm_rsr64("CNTVCT_EL0");
	uint64_t deadline = cntvct + 19200000 / 100;
	while (__builtin_arm_rsr64("CNTVCT_EL0") < deadline) {
		/* spin */
	}

	uint64_t irq1 = gic_diag_irq_count;
	uint64_t vt1 = gic_diag_vtimer_count;
	uint64_t hppir1b = __builtin_arm_rsr64("ICC_HPPIR1_EL1");
	uint32_t pend_after = gic_diag_rd(gicd_base, GICD_ISPENDR(intid / 32));
	uint32_t en_after = gic_diag_rd(gicd_base, GICD_ISENABLER(intid / 32));

	/* clean up */
	gic_write32(gicd_base + GICD_ICPENDR(intid / 32), 1u << (intid % 32));
	gic_write32(gicd_base + GICD_ICENABLER(intid / 32), 1u << (intid % 32));
	gic_distributor_settle();

#define PUTS(x) do { const char *q = (x); while (*q) { *p++ = *q++; } } while (0)
	PUTS("tmr5: el=");
	p = gic_diag_dec(p, (cur_el >> 2) & 3);
	PUTS(" gicdctlr=");
	p = gic_diag_hex(p, gicdctlr0, 8);
	PUTS(" grpd1=");
	p = gic_diag_hex(p, grp_d1, 8);
	PUTS(" grpd2=");
	p = gic_diag_hex(p, grp_d2, 8);
	PUTS(" end0=");
	p = gic_diag_hex(p, en0, 8);
	PUTS(" pendd0=");
	p = gic_diag_hex(p, pend0, 8);
	PUTS(" grp38=");
	p = gic_diag_hex(p, grp_after, 8);
	PUTS(" router=");
	p = gic_diag_hex(p, router_after, 8);
	PUTS(" mpidr=");
	p = gic_diag_hex(p, mpidr, 16);
	PUTS(" irq=");
	p = gic_diag_dec(p, irq1 - irq0);
	PUTS(" vt=");
	p = gic_diag_dec(p, vt1 - vt0);
	PUTS(" hppir1=");
	p = gic_diag_hex(p, hppir1b, 6);
	PUTS(" pend38=");
	p = gic_diag_hex(p, pend_after, 8);
	PUTS(" en38=");
	p = gic_diag_hex(p, en_after, 8);
	PUTS(" cpu=");
	p = gic_diag_dec(p, (uint64_t)cpu);
	*p++ = '\n';
	*p = 0;
	loader_log_line(b);
#undef PUTS
}

"""

i = s.index("/* ck17 diagnostic: can the EL1 physical timer (PPI 30) be delivered as a Group 1 IRQ? */")
j = s.index("#endif /* GENERIC_GIC_V3_IRQ */")
s = s[:i] + NEW + s[j:]
open(path, "w").write(s)
print("ck18 probe installed")
