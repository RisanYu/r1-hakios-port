#!/usr/bin/env python3
"""ck15: GIC control-state probe.

- count gic_v3_irq_cpu_init() calls
- replace the ck14 timer probe with one that also reports (and tries to fix)
  GICD_CTLR / GICR_IGROUPR0, i.e. what the GIC lets this security state see.
"""
import sys

ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
path = ROOT + "/osfmk/arm64/gic_v3_irq.c"
s = open(path).read()

# 1. init-call counter
old = """	gic_diag_vtimer_count = gic_diag_vtimer_count;"""
# not used; use direct anchors below

old = """uint64_t gic_diag_irq_count;
uint64_t gic_diag_vtimer_count;"""
new = """uint64_t gic_diag_irq_count;
uint64_t gic_diag_vtimer_count;
uint64_t gic_diag_init_calls;"""
assert s.count(old) == 1
s = s.replace(old, new)

old = """gic_v3_irq_cpu_init(void)
{
	int cpu = cpu_number();"""
new = """gic_v3_irq_cpu_init(void)
{
	int cpu = cpu_number();

	gic_diag_init_calls++;"""
assert s.count(old) == 1
s = s.replace(old, new)

# 2. replace the ck14 probe block with the ck15 probe
NEW = r"""/* ck15 diagnostic: what does the GIC let this security state see, and does
 * the EL1 virtual timer PPI (27) reach this processor at all? */
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
	char b[520];
	char *p = b;
	int cpu = (int)ml_get_cpu_number_local();
	vm_offset_t red = gicr_cpu_base[cpu];

	uint64_t cntfrq = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t cntvct = __builtin_arm_rsr64("CNTVCT_EL0");
	uint64_t daif = __builtin_arm_rsr64("DAIF");
	uint64_t ctl = __builtin_arm_rsr64("CNTV_CTL_EL0");
	uint64_t cval = __builtin_arm_rsr64("CNTV_CVAL_EL0");
	uint64_t sre = __builtin_arm_rsr64("ICC_SRE_EL1");
	uint64_t iccctlr = __builtin_arm_rsr64("ICC_CTLR_EL1");

	uint32_t ctlr0 = gicd_base ? gic_read32(gicd_base + GICD_CTLR) : 0xdeadbeefu;
	uint32_t gicr_ctlr0 = red ? gic_read32(red + 0x0000) : 0xdeadbeefu;
	uint32_t grp0 = red ? gic_read32(red + GICR_IGROUPR0) : 0xdeadbeefu;
	uint32_t en0 = red ? gic_read32(red + GICR_ISENABLER0) : 0xdeadbeefu;
	uint32_t pend0 = red ? gic_read32(red + (GICR_SGI_BASE + 0x0280)) : 0xdeadbeefu;

	/* what does this security state let us turn on? */
	if (gicd_base) {
		gic_write32(gicd_base + GICD_CTLR, ctlr0 | 0x3fu);
	}
	uint32_t ctlr1 = gicd_base ? gic_read32(gicd_base + GICD_CTLR) : 0xdeadbeefu;
	if (red) {
		gic_write32(red + GICR_IGROUPR0, grp0 | (1u << GIC_INTID_VTIMER));
	}
	uint32_t grp1 = red ? gic_read32(red + GICR_IGROUPR0) : 0xdeadbeefu;
	__builtin_arm_isb(ISB_SY);

	uint64_t igrp0 = __builtin_arm_rsr64("ICC_IGRPEN0_EL1");
	uint64_t igrp1 = __builtin_arm_rsr64("ICC_IGRPEN1_EL1");
	uint64_t pmr = __builtin_arm_rsr64("ICC_PMR_EL1");
	uint64_t hppir1 = __builtin_arm_rsr64("ICC_HPPIR1_EL1");

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
	uint64_t hppir1b = __builtin_arm_rsr64("ICC_HPPIR1_EL1");
	uint64_t pmr2 = __builtin_arm_rsr64("ICC_PMR_EL1");
	uint32_t rpend2 = red ? gic_read32(red + (GICR_SGI_BASE + 0x0280)) : 0xdeadbeefu;
	uint64_t irq1 = gic_diag_irq_count;
	uint64_t vt1 = gic_diag_vtimer_count;

	__builtin_arm_wsr64("CNTV_CVAL_EL0", cval);
	__builtin_arm_wsr64("CNTV_CTL_EL0", ctl);
	__builtin_arm_isb(ISB_SY);

#define PUTS(x) do { const char *q = (x); while (*q) { *p++ = *q++; } } while (0)
	PUTS("tmr2: initcalls=");
	p = gic_diag_dec(p, gic_diag_init_calls);
	PUTS(" gicd=");
	p = gic_diag_hex(p, (uint64_t)gicd_base, 16);
	PUTS(" gicr=");
	p = gic_diag_hex(p, (uint64_t)red, 16);
	PUTS(" ctlr0=");
	p = gic_diag_hex(p, ctlr0, 8);
	PUTS(" ctlr1=");
	p = gic_diag_hex(p, ctlr1, 8);
	PUTS(" gicrctlr0=");
	p = gic_diag_hex(p, gicr_ctlr0, 8);
	PUTS(" grp0=");
	p = gic_diag_hex(p, grp0, 8);
	PUTS(" grp1=");
	p = gic_diag_hex(p, grp1, 8);
	PUTS(" en0=");
	p = gic_diag_hex(p, en0, 8);
	PUTS(" pend0=");
	p = gic_diag_hex(p, pend0, 8);
	PUTS(" pend2=");
	p = gic_diag_hex(p, rpend2, 8);
	PUTS(" daif=");
	p = gic_diag_hex(p, daif, 4);
	PUTS(" ctl2=");
	p = gic_diag_hex(p, ctl2, 2);
	PUTS(" irq=");
	p = gic_diag_dec(p, irq1 - irq0);
	PUTS(" vt=");
	p = gic_diag_dec(p, vt1 - vt0);
	PUTS(" hppir1=");
	p = gic_diag_hex(p, hppir1, 6);
	PUTS(" hppir1b=");
	p = gic_diag_hex(p, hppir1b, 6);
	PUTS(" igrp0=");
	p = gic_diag_dec(p, igrp0);
	PUTS(" igrp1=");
	p = gic_diag_dec(p, igrp1);
	PUTS(" pmr=");
	p = gic_diag_hex(p, pmr, 2);
	PUTS(" pmr2=");
	p = gic_diag_hex(p, pmr2, 2);
	PUTS(" sre=");
	p = gic_diag_hex(p, sre, 2);
	PUTS(" iccctlr=");
	p = gic_diag_hex(p, iccctlr, 4);
	PUTS(" cpu=");
	p = gic_diag_dec(p, (uint64_t)cpu);
	*p++ = '\n';
	*p = 0;
	loader_log_line(b);
#undef PUTS
}

"""

i = s.index("/* ck14 diagnostic: does the EL1 virtual timer PPI")
j = s.index("#endif /* GENERIC_GIC_V3_IRQ */")
s = s[:i] + NEW + s[j:]
open(path, "w").write(s)
print("ck15 probe installed")
