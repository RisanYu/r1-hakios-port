#!/usr/bin/env python3
"""ck21: program the memory-mapped timer frame (0x17ca0000) and watch for its SPI.

Question: the EL1 virtual timer interrupt PPI 27 is Group 0 on this phone and never
reaches us; the same phone describes a memory-mapped timer block (arm,armv7-timer-mem)
at 0x17c90000 with frame 0 at 0x17ca0000, whose interrupts are SPIs 6 and 7 (= 38, 39).
An SPI can be routed and enabled (proven with a software-raised one), so this probe
checks whether the frame's own counters can be programmed (CNTACR permissions) and
whether its virtual then physical comparator raises the interrupt.
"""
import io
import sys

ROOT = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2"
GIC = ROOT + "/osfmk/arm64/gic_v3_irq.c"
BSDINIT = ROOT + "/iokit/bsddev/IOKitBSDInit.cpp"

PROBE = r'''
/* ck21 diagnostic: the memory-mapped timer frame (0x17ca0000) and its SPIs */
static vm_offset_t mt_base;
static vm_offset_t mt_ctl;
static uint32_t mt_hits;

static void
mt_handler(void *context, uint32_t intid)
{
	mt_hits++;
}

static uint32_t
mt_rd(vm_offset_t base, uint32_t off)
{
	return base ? gic_read32(base + off) : 0xdeadbeefu;
}

static void
mt_wr(vm_offset_t base, uint32_t off, uint32_t value)
{
	if (base) {
		gic_write32(base + off, value);
	}
}

static uint64_t
mt_rd64(vm_offset_t base, uint32_t off)
{
	uint64_t hi = mt_rd(base, off + 4);

	return ((hi << 32) | mt_rd(base, off));
}

static void
mt_wr64(vm_offset_t base, uint32_t off, uint64_t value)
{
	mt_wr(base, off + 4, (uint32_t)(value >> 32));  /* high first: the low write latches */
	mt_wr(base, off, (uint32_t)value);
}

static void
mt_hex(char **pp, uint64_t v, int digits)
{
	const char *d = "0123456789abcdef";
	char *p = *pp;

	for (int i = digits - 1; i >= 0; i--) {
		*p++ = d[(v >> (i * 4)) & 0xf];
	}
	*pp = p;
}

static void
mt_line(const char *tag, uint32_t a, uint32_t b, uint32_t c, uint32_t d, uint32_t e, uint64_t f)
{
	char buf[256];
	char *p = buf;

	while (*tag) {
		*p++ = *tag++;
	}
	mt_hex(&p, a, 8); *p++ = ' ';
	mt_hex(&p, b, 8); *p++ = ' ';
	mt_hex(&p, c, 8); *p++ = ' ';
	mt_hex(&p, d, 8); *p++ = ' ';
	mt_hex(&p, e, 8); *p++ = ' ';
	mt_hex(&p, f, 16); *p++ = '\n'; *p = 0;
	loader_log_line(buf);
}

void
gic_v3_diag_memtimer(void)
{
	static int done;
	uint32_t tidr, acr0a, acr0b, frq, ctl, pend, hits0, irq0;
	uint64_t t0, t1;
	kern_return_t rc;

	if (done) {
		return;
	}
	done = 1;
	if (!mt_base) {
		mt_ctl = ml_io_map(0x17c90000ULL, 0x1000);
		mt_base = ml_io_map(0x17ca0000ULL, 0x1000);
	}

	/* control frame: frames implemented (CNTTIDR) and our access rights (CNTACR0) */
	tidr = mt_rd(mt_ctl, 0x08);
	acr0a = mt_rd(mt_ctl, 0x40);
	mt_wr(mt_ctl, 0x40, 0x3f);
	acr0b = mt_rd(mt_ctl, 0x40);
	frq = mt_rd(mt_base, 0x10);
	mt_line("mt1: ", tidr, acr0a, acr0b, frq, 0, 0);
	if ((acr0b & 0x3f) != 0x3f) {
		return;         /* no access to the frame's counters: nothing more to try here */
	}

	/* frame 0, virtual comparator, SPI 38 (the second interrupt in the frame node) */
	rc = gic_v3_spi_attach(38, FALSE, mt_handler, NULL);
	if (rc != KERN_SUCCESS) {
		mt_line("mt2: ", (uint32_t)rc, 0, 0, 0, 0, 0);
		return;
	}
	irq0 = (uint32_t)gic_diag_irq_count;
	hits0 = mt_hits;
	t0 = mt_rd64(mt_base, 0x08);            /* CNTVCT */
	mt_wr64(mt_base, 0x30, t0 + 19200);     /* CNTV_CVAL: one millisecond ahead */
	mt_wr(mt_base, 0x3c, 1);                /* CNTV_CTL: enable, unmasked */
	for (volatile int i = 0; i < 100000; i++) {
		if (mt_hits != hits0) {
			break;
		}
	}
	ctl = mt_rd(mt_base, 0x3c);
	pend = gic_read32(gicd_base + 0x0200 + 4);      /* GICD_ISPENDR1: intids 32..63 */
	t1 = mt_rd64(mt_base, 0x08);
	mt_wr(mt_base, 0x3c, 0);                        /* CNTV_CTL: disabled again */
	gic_write32(gicd_base + GICD_ICPENDR(1), 1u << 6);
	mt_line("mt2: ", ctl, pend, mt_hits - hits0, (uint32_t)(gic_diag_irq_count - irq0), 0, t1 - t0);
	gic_v3_spi_detach(38);

	/* frame 0, physical comparator, SPI 39 */
	rc = gic_v3_spi_attach(39, FALSE, mt_handler, NULL);
	if (rc != KERN_SUCCESS) {
		mt_line("mt3: ", (uint32_t)rc, 0, 0, 0, 0, 0);
		return;
	}
	hits0 = mt_hits;
	t0 = mt_rd64(mt_base, 0x00);            /* CNTPCT */
	mt_wr64(mt_base, 0x20, t0 + 19200);     /* CNTP_CVAL */
	mt_wr(mt_base, 0x2c, 1);                /* CNTP_CTL */
	for (volatile int i = 0; i < 100000; i++) {
		if (mt_hits != hits0) {
			break;
		}
	}
	ctl = mt_rd(mt_base, 0x2c);
	pend = gic_read32(gicd_base + 0x0200 + 4);
	mt_wr(mt_base, 0x2c, 0);
	gic_write32(gicd_base + GICD_ICPENDR(1), 1u << 7);
	mt_line("mt3: ", ctl, pend, mt_hits - hits0, (uint32_t)(gic_diag_irq_count - irq0), 0, 0);
	gic_v3_spi_detach(39);
}
'''


def patch_file(path, subs):
    s = io.open(path, encoding="utf-8").read()
    for old, new, count in subs:
        n = s.count(old)
        if n != count:
            sys.exit("%s: anchor %r found %d times, expected %d" % (path, old, n, count))
        s = s.replace(old, new)
    io.open(path, "w", encoding="utf-8", newline="").write(s)
    print("patched", path)


def main():
    s = io.open(GIC, encoding="utf-8").read()
    if "gic_v3_diag_memtimer" in s:
        print("gic_v3_irq.c already patched")
    else:
        anchor = "\n#endif /* GENERIC_GIC_V3_IRQ */"
        if s.count(anchor) != 1:
            sys.exit("gic_v3_irq.c: end anchor count %d" % s.count(anchor))
        s = s.replace(anchor, PROBE + anchor)
        io.open(GIC, "w", encoding="utf-8", newline="").write(s)
        print("patched", GIC)

    patch_file(BSDINIT, [
        ('extern "C" void gic_v3_diag_timer(void);',
         'extern "C" void gic_v3_diag_memtimer(void);', 1),
        ("\tgic_v3_diag_timer();", "\tgic_v3_diag_memtimer();", 1),
    ])


main()
