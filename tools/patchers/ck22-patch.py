#!/usr/bin/env python3
"""ck22: repeat the memory-mapped timer probe with a deadline already in the past.

ck21 showed the frame's CNTACR is fully open (0x3f), CNTFRQ reads 19.2 MHz, and
CNTV_CTL took our "enable" bit - but its one-millisecond spin lasted only ~0.25 ms,
so the comparator had not expired yet. This run programs the comparator one
millisecond in the past and spins long enough, so the interrupt condition is true
from the start. Both comparators of frame 0 are tried: CNTV on SPI 38, CNTP on SPI 39.
"""
import io
import sys

GIC = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2/osfmk/arm64/gic_v3_irq.c"

FUNC = r'''void
gic_v3_diag_memtimer(void)
{
	static int done;
	uint32_t tidr, acr0, frq, ctl, pend, hits0, irq0, last;
	uint64_t t0, now, cval;
	kern_return_t rc;

	if (done) {
		return;
	}
	done = 1;
	if (!mt_base) {
		mt_ctl = ml_io_map(0x17c90000ULL, 0x1000);
		mt_base = ml_io_map(0x17ca0000ULL, 0x1000);
	}

	/* control frame: implemented frames (CNTTIDR), our rights on frame 0 (CNTACR0) */
	tidr = mt_rd(mt_ctl, 0x08);
	acr0 = mt_rd(mt_ctl, 0x40);
	frq = mt_rd(mt_base, 0x10);
	mt_line("mt1: ", tidr, acr0, frq, 0, 0, 0);

	/* frame 0, virtual comparator, SPI 38: deadline one millisecond in the past */
	rc = gic_v3_spi_attach(38, FALSE, mt_handler, NULL);
	if (rc != KERN_SUCCESS) {
		mt_line("mt2: ", (uint32_t)rc, 0, 0, 0, 0, 0);
		return;
	}
	hits0 = mt_hits;
	irq0 = (uint32_t)gic_diag_irq_count;
	t0 = mt_rd64(mt_base, 0x08);            /* CNTVCT */
	mt_wr64(mt_base, 0x30, t0 - 19200);     /* CNTV_CVAL: expired */
	mt_wr(mt_base, 0x3c, 1);                /* CNTV_CTL: enable, unmasked */
	cval = mt_rd64(mt_base, 0x30);
	for (volatile int i = 0; i < 2000000; i++) {
		if (mt_hits != hits0) {
			break;
		}
	}
	now = mt_rd64(mt_base, 0x08);
	ctl = mt_rd(mt_base, 0x3c);
	pend = gic_read32(gicd_base + 0x0200 + 4);      /* GICD_ISPENDR1: intids 32..63 */
	last = gic_last_unhandled;
	mt_line("mt2: ", ctl, pend, mt_hits - hits0, (uint32_t)(gic_diag_irq_count - irq0), last, cval - t0);
	mt_line("mt2b: ", (uint32_t)(now - t0), 0, 0, 0, 0, 0);
	mt_wr(mt_base, 0x3c, 0);
	gic_write32(gicd_base + GICD_ICPENDR(1), 1u << 6);
	gic_v3_spi_detach(38);

	/* frame 0, physical comparator, SPI 39 */
	rc = gic_v3_spi_attach(39, FALSE, mt_handler, NULL);
	if (rc != KERN_SUCCESS) {
		mt_line("mt3: ", (uint32_t)rc, 0, 0, 0, 0, 0);
		return;
	}
	hits0 = mt_hits;
	irq0 = (uint32_t)gic_diag_irq_count;
	t0 = mt_rd64(mt_base, 0x00);            /* CNTPCT */
	mt_wr64(mt_base, 0x20, t0 - 19200);     /* CNTP_CVAL: expired */
	mt_wr(mt_base, 0x2c, 1);                /* CNTP_CTL: enable, unmasked */
	cval = mt_rd64(mt_base, 0x20);
	for (volatile int i = 0; i < 2000000; i++) {
		if (mt_hits != hits0) {
			break;
		}
	}
	now = mt_rd64(mt_base, 0x00);
	ctl = mt_rd(mt_base, 0x2c);
	pend = gic_read32(gicd_base + 0x0200 + 4);
	last = gic_last_unhandled;
	mt_line("mt3: ", ctl, pend, mt_hits - hits0, (uint32_t)(gic_diag_irq_count - irq0), last, cval - t0);
	mt_line("mt3b: ", (uint32_t)(now - t0), 0, 0, 0, 0, 0);
	mt_wr(mt_base, 0x2c, 0);
	gic_write32(gicd_base + GICD_ICPENDR(1), 1u << 7);
	gic_v3_spi_detach(39);
}
'''


def find_function(s):
    start = s.index("void\ngic_v3_diag_memtimer(void)\n{")
    i = s.index("{", start)
    depth = 0
    while i < len(s):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    else:
        sys.exit("unbalanced function")
    return start, end


def main():
    s = io.open(GIC, encoding="utf-8").read()
    start, end = find_function(s)
    s = s[:start] + FUNC + s[end:]
    io.open(GIC, "w", encoding="utf-8", newline="").write(s)
    print("replaced gic_v3_diag_memtimer: %d -> %d bytes" % (end - start, len(FUNC)))


main()
