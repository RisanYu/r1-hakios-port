#!/usr/bin/env python3
"""ck16: read-only GIC/timer state probe (no GIC writes, no Group0 regs)."""
import sys

ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
path = ROOT + "/osfmk/arm64/gic_v3_irq.c"
s = open(path).read()

NEW = r"""/* ck16 diagnostic: read-only view of the GIC and timer state this kernel sees */
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
	uint64_t ctl = __builtin_arm_rsr64("CNTV_CTL_EL0");
	uint64_t cval = __builtin_arm_rsr64("CNTV_CVAL_EL0");
	uint64_t cntpctl = __builtin_arm_rsr64("CNTP_CTL_EL0");
	uint64_t cntpcval = __builtin_arm_rsr64("CNTP_CVAL_EL0");
	uint64_t cntpct = __builtin_arm_rsr64("CNTPCT_EL0");
	uint64_t sre = __builtin_arm_rsr64("ICC_SRE_EL1");
	uint64_t iccctlr = __builtin_arm_rsr64("ICC_CTLR_EL1");
	uint64_t igrp1 = __builtin_arm_rsr64("ICC_IGRPEN1_EL1");
	uint64_t pmr = __builtin_arm_rsr64("ICC_PMR_EL1");
	uint64_t hppir1 = __builtin_arm_rsr64("ICC_HPPIR1_EL1");

	uint32_t gicd_ctlr = gic_diag_rd(gicd_base, GICD_CTLR);
	uint32_t gicd_iidr = gic_diag_rd(gicd_base, 0x0008);
	uint32_t gicr_ctlr = gic_diag_rd(red, 0x0000);
	uint32_t gicr_waker = gic_diag_rd(red, 0x0014);
	uint32_t gicr_typer_lo = gic_diag_rd(red, 0x0008);
	uint32_t grp = gic_diag_rd(red, GICR_IGROUPR0);
	uint32_t en = gic_diag_rd(red, GICR_ISENABLER0);
	uint32_t pend = gic_diag_rd(red, (GICR_SGI_BASE + 0x0280));

	uint64_t irq0 = gic_diag_irq_count;
	uint64_t vt0 = gic_diag_vtimer_count;

	/* arm the EL1 virtual timer 1 ms out, let it run for 10 ms, count IRQs */
	__builtin_arm_wsr64("CNTV_TVAL_EL0", cntfrq / 1000);
	__builtin_arm_wsr64("CNTV_CTL_EL0", 1);
	__builtin_arm_isb(ISB_SY);
	uint64_t deadline = cntvct + cntfrq / 100;
	while (__builtin_arm_rsr64("CNTVCT_EL0") < deadline) {
		/* spin */
	}
	uint64_t ctl2 = __builtin_arm_rsr64("CNTV_CTL_EL0");
	uint64_t hppir1b = __builtin_arm_rsr64("ICC_HPPIR1_EL1");
	uint32_t pend2 = gic_diag_rd(red, (GICR_SGI_BASE + 0x0280));
	uint64_t irq1 = gic_diag_irq_count;
	uint64_t vt1 = gic_diag_vtimer_count;

	__builtin_arm_wsr64("CNTV_CVAL_EL0", cval);
	__builtin_arm_wsr64("CNTV_CTL_EL0", ctl);
	__builtin_arm_isb(ISB_SY);

#define PUTS(x) do { const char *q = (x); while (*q) { *p++ = *q++; } } while (0)
	PUTS("tmr3: initcalls=");
	p = gic_diag_dec(p, gic_diag_init_calls);
	PUTS(" gicd=");
	p = gic_diag_hex(p, (uint64_t)gicd_base, 16);
	PUTS(" gicr=");
	p = gic_diag_hex(p, (uint64_t)red, 16);
	PUTS(" gicdctlr=");
	p = gic_diag_hex(p, gicd_ctlr, 8);
	PUTS(" gicdiidr=");
	p = gic_diag_hex(p, gicd_iidr, 8);
	PUTS(" gicrctlr=");
	p = gic_diag_hex(p, gicr_ctlr, 8);
	PUTS(" waker=");
	p = gic_diag_hex(p, gicr_waker, 8);
	PUTS(" typer=");
	p = gic_diag_hex(p, gicr_typer_lo, 8);
	PUTS(" grp=");
	p = gic_diag_hex(p, grp, 8);
	PUTS(" en=");
	p = gic_diag_hex(p, en, 8);
	PUTS(" pend=");
	p = gic_diag_hex(p, pend, 8);
	PUTS(" pend2=");
	p = gic_diag_hex(p, pend2, 8);
	PUTS(" daif=");
	p = gic_diag_hex(p, daif, 4);
	PUTS(" ctl=");
	p = gic_diag_hex(p, ctl, 2);
	PUTS(" ctl2=");
	p = gic_diag_hex(p, ctl2, 2);
	PUTS(" cntpctl=");
	p = gic_diag_hex(p, cntpctl, 2);
	PUTS(" cntpcval=");
	p = gic_diag_hex(p, cntpcval, 16);
	PUTS(" cntpct=");
	p = gic_diag_hex(p, cntpct, 16);
	PUTS(" cntvct=");
	p = gic_diag_hex(p, cntvct, 16);
	PUTS(" irq=");
	p = gic_diag_dec(p, irq1 - irq0);
	PUTS(" vt=");
	p = gic_diag_dec(p, vt1 - vt0);
	PUTS(" hppir1=");
	p = gic_diag_hex(p, hppir1, 6);
	PUTS(" hppir1b=");
	p = gic_diag_hex(p, hppir1b, 6);
	PUTS(" igrp1=");
	p = gic_diag_dec(p, igrp1);
	PUTS(" pmr=");
	p = gic_diag_hex(p, pmr, 2);
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

i = s.index("/* ck15 diagnostic: what does the GIC let this security state see")
j = s.index("#endif /* GENERIC_GIC_V3_IRQ */")
s = s[:i] + NEW + s[j:]
open(path, "w").write(s)
print("ck16 probe installed")
