#!/usr/bin/env python3
"""ck14: timer-interrupt diagnostic.

1. osfmk/arm64/gic_v3_irq.c: count IRQs (all, and VTIMER PPI 27), and add
   gic_v3_diag_timer() which arms the EL1 virtual timer for 1 ms, lets it
   run for 10 ms, and writes a one-line report into the loader log.
2. iokit/bsddev/IOKitBSDInit.cpp: call gic_v3_diag_timer() at IOFindBSDRoot
   entry, just before loader_checkpoint(160) (so the checkpoint stop returns
   the report).
"""
import sys

ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"


def patch(path, old, new, name):
    p = ROOT + "/" + path
    s = open(p).read()
    if s.count(old) != 1:
        print("ANCHOR FAIL %s %s count=%d" % (path, name, s.count(old)))
        sys.exit(1)
    s = s.replace(old, new)
    open(p, "w").write(s)
    print("patched %s (%s)" % (path, name))


# ---------------------------------------------------------------- gic_v3_irq.c
DECLS = """#if defined(GENERIC_GIC_V3_IRQ)

/* ck14 diagnostic: interrupt counters and a timer probe */
uint64_t gic_diag_irq_count;
uint64_t gic_diag_vtimer_count;
extern void loader_log_line(const char *line);
"""

old = "#if defined(GENERIC_GIC_V3_IRQ)\n\n#define GICD_CTLR               0x0000\n"
new = DECLS + "\n#define GICD_CTLR               0x0000\n"
patch("osfmk/arm64/gic_v3_irq.c", old, new, "decls")

old = """		uint32_t intid = (uint32_t)(iar & 0xffffff);

		if (intid >= GIC_INTID_SPURIOUS_MIN) {"""
new = """		uint32_t intid = (uint32_t)(iar & 0xffffff);

		gic_diag_irq_count++;

		if (intid >= GIC_INTID_SPURIOUS_MIN) {"""
patch("osfmk/arm64/gic_v3_irq.c", old, new, "count all irqs")

old = """		if (intid == GIC_INTID_VTIMER) {
			/* same sequence as the FIQ path in sleh_fiq() */
			getCpuDatap()->cpu_decrementer = -1; /* Large */
			rtclock_intr(TRUE);"""
new = """		if (intid == GIC_INTID_VTIMER) {
			/* same sequence as the FIQ path in sleh_fiq() */
			gic_diag_vtimer_count++;
			getCpuDatap()->cpu_decrementer = -1; /* Large */
			rtclock_intr(TRUE);"""
patch("osfmk/arm64/gic_v3_irq.c", old, new, "count vtimer irqs")

PROBE = r"""
/* ck14 diagnostic: does the EL1 virtual timer PPI (27) reach this processor? */
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

void
gic_v3_diag_timer(void)
{
	char b[420];
	char *p = b;
	int cpu = (int)ml_get_cpu_number_local();
	vm_offset_t red = gicr_cpu_base[cpu];

	uint64_t cntfrq = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t cntvct = __builtin_arm_rsr64("CNTVCT_EL0");
	uint64_t daif = __builtin_arm_rsr64("DAIF");
	uint64_t ctl = __builtin_arm_rsr64("CNTV_CTL_EL0");
	uint64_t cval = __builtin_arm_rsr64("CNTV_CVAL_EL0");
	uint64_t hppir1 = __builtin_arm_rsr64("ICC_HPPIR1_EL1");
	uint64_t igrpen1 = __builtin_arm_rsr64("ICC_IGRPEN1_EL1");
	uint64_t pmr = __builtin_arm_rsr64("ICC_PMR_EL1");
	uint64_t sre = __builtin_arm_rsr64("ICC_SRE_EL1");
	uint64_t ctlr = __builtin_arm_rsr64("ICC_CTLR_EL1");
	uint32_t rpend = red ? gic_read32(red + GICR_ISPENDR0) : 0xdeadbeefu;
	uint32_t ren = red ? gic_read32(red + GICR_ISENABLER0) : 0xdeadbeefu;
	uint32_t rgrp = red ? gic_read32(red + GICR_IGROUPR0) : 0xdeadbeefu;
	uint64_t irq0 = gic_diag_irq_count;
	uint64_t vt0 = gic_diag_vtimer_count;

	/* arm the EL1 virtual timer 1 ms out, then let it run for 10 ms */
	__builtin_arm_wsr64("CNTV_TVAL_EL0", cntfrq / 1000);
	__builtin_arm_wsr64("CNTV_CTL_EL0", 1);
	__builtin_arm_isb(ISB_SY);
	uint64_t deadline = cntvct + cntfrq / 100;
	while (__builtin_arm_rsr64("CNTVCT_EL0") < deadline) {
		/* spin */
	}
	uint64_t ctl2 = __builtin_arm_rsr64("CNTV_CTL_EL0");
	uint64_t cval2 = __builtin_arm_rsr64("CNTV_CVAL_EL0");
	uint64_t hppir1b = __builtin_arm_rsr64("ICC_HPPIR1_EL1");
	uint32_t rpend2 = red ? gic_read32(red + GICR_ISPENDR0) : 0xdeadbeefu;
	uint64_t irq1 = gic_diag_irq_count;
	uint64_t vt1 = gic_diag_vtimer_count;

	/* put the timer back the way it was */
	__builtin_arm_wsr64("CNTV_CVAL_EL0", cval);
	__builtin_arm_wsr64("CNTV_CTL_EL0", ctl);
	__builtin_arm_isb(ISB_SY);

#define PUTS(x) do { const char *q = (x); while (*q) { *p++ = *q++; } } while (0)
	PUTS("tmr: daif=");
	p = gic_diag_hex(p, daif, 4);
	PUTS(" frq=");
	p = gic_diag_dec(p, cntfrq);
	PUTS(" ctl=");
	p = gic_diag_hex(p, ctl, 2);
	PUTS(" cval=");
	p = gic_diag_hex(p, cval, 16);
	PUTS(" ctl2=");
	p = gic_diag_hex(p, ctl2, 2);
	PUTS(" cval2=");
	p = gic_diag_hex(p, cval2, 16);
	PUTS(" irq=");
	p = gic_diag_dec(p, irq1 - irq0);
	PUTS(" vt=");
	p = gic_diag_dec(p, vt1 - vt0);
	PUTS(" hppir1=");
	p = gic_diag_hex(p, hppir1, 6);
	PUTS(" hppir1b=");
	p = gic_diag_hex(p, hppir1b, 6);
	PUTS(" pend=");
	p = gic_diag_hex(p, rpend, 8);
	PUTS(" pend2=");
	p = gic_diag_hex(p, rpend2, 8);
	PUTS(" en=");
	p = gic_diag_hex(p, ren, 8);
	PUTS(" grp=");
	p = gic_diag_hex(p, rgrp, 8);
	PUTS(" igrpen1=");
	p = gic_diag_dec(p, igrpen1);
	PUTS(" pmr=");
	p = gic_diag_hex(p, pmr, 2);
	PUTS(" sre=");
	p = gic_diag_hex(p, sre, 2);
	PUTS(" ctlr=");
	p = gic_diag_hex(p, ctlr, 4);
	PUTS(" cpu=");
	p = gic_diag_dec(p, (uint64_t)cpu);
	*p++ = '\n';
	*p = 0;
	loader_log_line(b);
#undef PUTS
}
"""

old = "#endif /* GENERIC_GIC_V3_IRQ */"
new = PROBE + "\n#endif /* GENERIC_GIC_V3_IRQ */"
patch("osfmk/arm64/gic_v3_irq.c", old, new, "probe function")

# --------------------------------------------------- IOKitBSDInit.cpp call site
old = """	int xchar, dchar;
	loader_checkpoint(160);"""
new = """	int xchar, dchar;
	{
		extern "C" void gic_v3_diag_timer(void);
		gic_v3_diag_timer();
	}
	loader_checkpoint(160);"""
patch("iokit/bsddev/IOKitBSDInit.cpp", old, new, "probe call")

print("ALL PATCHES OK")
