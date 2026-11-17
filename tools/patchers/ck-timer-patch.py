#!/usr/bin/env python3
"""ck-timer: make the kernel's real-time clock use the memory-mapped timer frame.

Why: the architected EL1 virtual timer interrupts on PPI 27, and on this phone that
interrupt is Group 0 - a Non-secure kernel can neither move it to Group 1 nor take
it, so no timer interrupt ever arrives. The first blocking wait in bsd_init then
hangs forever. The device tree describes a memory-mapped timer block at 0x17c90000
whose frame 0 (0x17ca0000) has its own comparators raising SPI 38 (virtual) and
SPI 39 (physical). Probe ck22 showed that writing the frame's CNTV_CVAL/CNTV_CTL
works (ISTATUS sets) and the interrupt shows up pending (GICD_ISPENDR1 bit 6),
i.e. this frame is ours and its SPI is deliverable. Use frame 0's virtual
comparator for the tick: program CVAL/CTL over MMIO, take SPI 38 as the tick
interrupt, and answer ml_get_timer_pending() from the frame's CNTV_CTL.
"""
import io
import sys

ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
MR = ROOT + "/osfmk/arm64/machine_routines.c"

MODULE = r'''
/*
 * trident bring-up: the real-time clock runs on the memory-mapped timer frame.
 *
 * The EL1 virtual timer's interrupt is PPI 27, which on this phone is a Group 0
 * (secure) interrupt: this Non-secure kernel can neither change its group nor
 * receive it, so the architected timer's condition is met and no interrupt ever
 * arrives. The memory-mapped timer block at 0x17c90000 (arm,armv7-timer-mem) has a
 * frame 0 at 0x17ca0000 with its own comparators, and their interrupts are SPIs -
 * which the distributor routes to us. Frame 0's virtual comparator becomes the
 * tick source; the timebase itself (CNTVCT) stays the same system counter.
 */
#define MT_FRAME_BASE           0x17ca0000ull
#define MT_CNTPCT               0x00
#define MT_CNTVCT               0x08
#define MT_CNTP_CVAL            0x20
#define MT_CNTP_CTL             0x2c
#define MT_CNTV_CVAL            0x30
#define MT_CNTV_CTL             0x3c
#define MT_CNTV_CTL_ISTATUS     0x4             /* read-only */
#define MT_INTID_VTIMER         38              /* SPI 6 of frame 0: 6 + 32 */

extern kern_return_t gic_v3_spi_attach(uint32_t intid, boolean_t edge,
    void (*handler)(void *context, uint32_t intid), void *context);
extern void loader_log_line(const char *text);

static vm_offset_t arm_timer_mem_frame;
static boolean_t arm_timer_mem_ready;

static inline uint32_t
arm_timer_mem_rd(uint32_t offset)
{
	return *(volatile uint32_t *)(arm_timer_mem_frame + offset);
}

static inline void
arm_timer_mem_wr(uint32_t offset, uint32_t value)
{
	*(volatile uint32_t *)(arm_timer_mem_frame + offset) = value;
}

static uint64_t
arm_timer_mem_read64(uint32_t offset)
{
	uint32_t hi = arm_timer_mem_rd(offset + 4);

	return ((uint64_t)hi << 32) | arm_timer_mem_rd(offset);
}

static void
arm_timer_mem_write64(uint32_t offset, uint64_t value)
{
	/* the low half's write latches, so it has to come second */
	arm_timer_mem_wr(offset + 4, (uint32_t)(value >> 32));
	arm_timer_mem_wr(offset, (uint32_t)value);
}

static void
arm_timer_mem_log(const char *tag, uint64_t value)
{
	char line[64];
	char *p = line;
	const char *d = "0123456789abcdef";

	while (*tag != 0) {
		*p++ = *tag++;
	}
	for (int i = 15; i >= 0; i--) {
		*p++ = d[(value >> (i * 4)) & 0xf];
	}
	*p++ = '\n';
	*p = 0;
	loader_log_line(line);
}

/* Level-triggered: drop the condition before the interrupt is ended, then tick. */
static void
arm_timer_mem_intr(__unused void *context, __unused uint32_t intid)
{
	arm_timer_mem_wr(MT_CNTV_CTL, 0);
	getCpuDatap()->cpu_decrementer = -1;
	rtclock_intr(TRUE);
}

static uint32_t
arm_timer_mem_get_decrementer(void)
{
	uint64_t now, cval, left;

	now = arm_timer_mem_read64(MT_CNTVCT);
	cval = arm_timer_mem_read64(MT_CNTV_CVAL);
	left = (cval <= now) ? 0 : (cval - now);
	return (left > 0xffffffffull) ? 0xffffffffu : (uint32_t)left;
}

static void
arm_timer_mem_set_decrementer(uint32_t dec_value)
{
	uint64_t now = arm_timer_mem_read64(MT_CNTVCT);

	arm_timer_mem_write64(MT_CNTV_CVAL, now + dec_value);
	arm_timer_mem_wr(MT_CNTV_CTL, 1);       /* enable, interrupt not masked */
}

static void
arm_timer_mem_init(void)
{
	static boolean_t tried;
	vm_offset_t frame;
	kern_return_t kr;

	if (tried) {
		return;
	}
	tried = TRUE;
	frame = ml_io_map(MT_FRAME_BASE, 0x1000);
	if (frame == 0) {
		arm_timer_mem_log("tmem: no frame", 0);
		return;
	}
	arm_timer_mem_frame = frame;
	kr = gic_v3_spi_attach(MT_INTID_VTIMER, FALSE, arm_timer_mem_intr, NULL);
	if (kr != KERN_SUCCESS) {
		arm_timer_mem_frame = 0;
		arm_timer_mem_log("tmem: no irq", (uint64_t)kr);
		return;
	}
	arm_timer_mem_ready = TRUE;
	arm_timer_mem_log("tmem: frame", (uint64_t)frame);
}
'''

SUBS = [
    (
        "kern_return_t\nml_interrupt_prewarm(__unused uint64_t deadline)\n{\n\treturn KERN_FAILURE;\n}\n",
        "kern_return_t\nml_interrupt_prewarm(__unused uint64_t deadline)\n{\n\treturn KERN_FAILURE;\n}\n" + MODULE,
    ),
    (
        "\tif (cdp->cpu_set_decrementer_func) {\n\t\tcdp->cpu_set_decrementer_func(dec_value);\n\t} else {\n"
        "\t\t__builtin_arm_wsr64(\"CNTV_TVAL_EL0\", (uint64_t)dec_value);\n\t}\n",
        "\tif (arm_timer_mem_ready) {\n\t\tarm_timer_mem_set_decrementer(dec_value);\n"
        "\t} else if (cdp->cpu_set_decrementer_func) {\n\t\tcdp->cpu_set_decrementer_func(dec_value);\n\t} else {\n"
        "\t\t__builtin_arm_wsr64(\"CNTV_TVAL_EL0\", (uint64_t)dec_value);\n\t}\n",
    ),
    (
        "\tif (cdp->cpu_get_decrementer_func) {\n\t\tdec = cdp->cpu_get_decrementer_func();\n\t} else {\n",
        "\tif (arm_timer_mem_ready) {\n\t\tdec = arm_timer_mem_get_decrementer();\n"
        "\t} else if (cdp->cpu_get_decrementer_func) {\n\t\tdec = cdp->cpu_get_decrementer_func();\n\t} else {\n",
    ),
    (
        "boolean_t\nml_get_timer_pending(void)\n{\n\tuint64_t cntv_ctl = __builtin_arm_rsr64(\"CNTV_CTL_EL0\");\n"
        "\treturn ((cntv_ctl & CNTV_CTL_EL0_ISTATUS) != 0) ? TRUE : FALSE;\n}\n",
        "boolean_t\nml_get_timer_pending(void)\n{\n\tuint64_t cntv_ctl;\n\n"
        "\tif (arm_timer_mem_ready) {\n\t\treturn ((arm_timer_mem_rd(MT_CNTV_CTL) & MT_CNTV_CTL_ISTATUS) != 0) ? TRUE : FALSE;\n\t}\n"
        "\tcntv_ctl = __builtin_arm_rsr64(\"CNTV_CTL_EL0\");\n"
        "\treturn ((cntv_ctl & CNTV_CTL_EL0_ISTATUS) != 0) ? TRUE : FALSE;\n}\n",
    ),
    (
        "\tuint64_t cntvctl = CNTV_CTL_EL0_ENABLE; /* One wants to use 32 bits, but \"mrs\" prefers it this way */\n\n"
        "\t__builtin_arm_wsr64(\"CNTV_CTL_EL0\", cntvctl);\n",
        "\tuint64_t cntvctl = CNTV_CTL_EL0_ENABLE; /* One wants to use 32 bits, but \"mrs\" prefers it this way */\n\n"
        "\t/*\n"
        "\t * trident bring-up: prefer the memory-mapped frame's virtual comparator (SPI 38) over\n"
        "\t * the architected PPI 27, which is Group 0 on this phone and never reaches us.\n"
        "\t */\n"
        "\tarm_timer_mem_init();\n"
        "\tif (arm_timer_mem_ready) {\n"
        "\t\treturn;\n"
        "\t}\n"
        "\t__builtin_arm_wsr64(\"CNTV_CTL_EL0\", cntvctl);\n",
    ),
]


def main():
    s = io.open(MR, encoding="utf-8").read()
    if "arm_timer_mem_ready" in s:
        print("machine_routines.c already patched")
        return
    for old, new in SUBS:
        n = s.count(old)
        if n != 1:
            sys.exit("anchor found %d times (expected 1): %r" % (n, old[:80]))
        s = s.replace(old, new)
    io.open(MR, "w", encoding="utf-8", newline="").write(s)
    print("patched", MR)


main()
