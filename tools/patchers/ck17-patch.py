#!/usr/bin/env python3
"""ck17: try PPI 30 (EL1 physical timer) as Group 1 NS, arm CNTP, count delivery."""
ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
path = ROOT + "/osfmk/arm64/gic_v3_irq.c"
s = open(path).read()

NEW = r"""/* ck17 diagnostic: can the EL1 physical timer (PPI 30) be delivered as a Group 1 IRQ? */
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
	char b[560];
	char *p = b;
	int cpu = (int)ml_get_cpu_number_local();
	vm_offset_t red = gicr_cpu_base[cpu];
	uint64_t cntfrq = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t cntvct = __builtin_arm_rsr64("CNTVCT_EL0");
	uint64_t daif = __builtin_arm_rsr64("DAIF");

	uint32_t grp0 = gic_diag_rd(red, GICR_IGROUPR0);
	uint32_t mod0 = gic_diag_rd(red, GICR_IGRPMODR0);
	uint32_t en0 = gic_diag_rd(red, GICR_ISENABLER0);
	uint32_t pend0 = gic_diag_rd(red, GICR_ICPENDR0);

	/* Try to claim PPI 30 (EL1 physical timer) as Non-secure Group 1 */
	gic_write32(red + GICR_IGROUPR0, grp0 | (1u << 30));
	gic_write32(red + GICR_IGRPMODR0, mod0 & ~(1u << 30));
	gic_write32(red + GICR_ISENABLER0, (1u << 30));
	__builtin_arm_isb(ISB_SY);

	uint32_t grp1 = gic_diag_rd(red, GICR_IGROUPR0);
	uint32_t mod1 = gic_diag_rd(red, GICR_IGRPMODR0);
	uint32_t en1 = gic_diag_rd(red, GICR_ISENABLER0);

	uint64_t irq0 = gic_diag_irq_count;
	uint64_t vt0 = gic_diag_vtimer_count;
	uint64_t cntpctl0 = __builtin_arm_rsr64("CNTP_CTL_EL0");
	uint64_t cntpcval0 = __builtin_arm_rsr64("CNTP_CVAL_EL0");

	/* arm the EL1 physical timer 1 ms out and let it run for 10 ms */
	__builtin_arm_wsr64("CNTP_TVAL_EL0", cntfrq / 1000);
	__builtin_arm_wsr64("CNTP_CTL_EL0", 1);
	__builtin_arm_isb(ISB_SY);
	uint64_t deadline = cntvct + cntfrq / 100;
	while (__builtin_arm_rsr64("CNTVCT_EL0") < deadline) {
		/* spin */
	}
	uint64_t cntpctl2 = __builtin_arm_rsr64("CNTP_CTL_EL0");
	uint64_t hppir1b = __builtin_arm_rsr64("ICC_HPPIR1_EL1");
	uint32_t pend2 = gic_diag_rd(red, GICR_ICPENDR0);
	uint64_t irq1 = gic_diag_irq_count;
	uint64_t vt1 = gic_diag_vtimer_count;

	__builtin_arm_wsr64("CNTP_CTL_EL0", 0);
	__builtin_arm_wsr64("CNTP_CVAL_EL0", cntpcval0);
	gic_write32(red + GICR_ICENABLER0, 1u << 30);
	__builtin_arm_isb(ISB_SY);

#define PUTS(x) do { const char *q = (x); while (*q) { *p++ = *q++; } } while (0)
	PUTS("tmr4: gicdctlr=");
	p = gic_diag_hex(p, gic_diag_rd(gicd_base, GICD_CTLR), 8);
	PUTS(" daif=");
	p = gic_diag_hex(p, daif, 4);
	PUTS(" grp0=");
	p = gic_diag_hex(p, grp0, 8);
	PUTS(" mod0=");
	p = gic_diag_hex(p, mod0, 8);
	PUTS(" en0=");
	p = gic_diag_hex(p, en0, 8);
	PUTS(" pend0=");
	p = gic_diag_hex(p, pend0, 8);
	PUTS(" grp1=");
	p = gic_diag_hex(p, grp1, 8);
	PUTS(" mod1=");
	p = gic_diag_hex(p, mod1, 8);
	PUTS(" en1=");
	p = gic_diag_hex(p, en1, 8);
	PUTS(" ctl0=");
	p = gic_diag_hex(p, cntpctl0, 2);
	PUTS(" ctl2=");
	p = gic_diag_hex(p, cntpctl2, 2);
	PUTS(" cval0=");
	p = gic_diag_hex(p, cntpcval0, 16);
	PUTS(" pend2=");
	p = gic_diag_hex(p, pend2, 8);
	PUTS(" irq=");
	p = gic_diag_dec(p, irq1 - irq0);
	PUTS(" vt=");
	p = gic_diag_dec(p, vt1 - vt0);
	PUTS(" hppir1=");
	p = gic_diag_hex(p, hppir1b, 6);
	PUTS(" igrp1=");
	p = gic_diag_dec(p, __builtin_arm_rsr64("ICC_IGRPEN1_EL1"));
	PUTS(" pmr=");
	p = gic_diag_hex(p, __builtin_arm_rsr64("ICC_PMR_EL1"), 2);
	PUTS(" sre=");
	p = gic_diag_hex(p, __builtin_arm_rsr64("ICC_SRE_EL1"), 2);
	PUTS(" cpu=");
	p = gic_diag_dec(p, (uint64_t)cpu);
	*p++ = '\n';
	*p = 0;
	loader_log_line(b);
#undef PUTS
}

"""

i = s.index("/* ck16 diagnostic: read-only view of the GIC and timer state this kernel sees */")
j = s.index("#endif /* GENERIC_GIC_V3_IRQ */")
s = s[:i] + NEW + s[j:]
open(path, "w").write(s)
print("ck17 probe installed")
