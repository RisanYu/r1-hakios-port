#!/usr/bin/env python3
"""ck23: find out why the frame's pending SPI does not become a handler call.

ck22: the memory-mapped frame's virtual comparator expired (CTL ISTATUS=1),
the interrupt showed up as pending in GICD_ISPENDR1 bit 6 (intid 38), but our
attached handler was never called while the spin saw thousands of interrupts.
That smells like spurious interrupts from an interrupt the CPU interface cannot
take (wrong group), so this run records the intids the handler actually returns
from ICC_IAR1 and dumps the distributor's configuration for intid 38.
"""
import io
import sys

GIC = "/root/hakios-xnu-kernel-main/xnu-src/xnu-8796.121.2/osfmk/arm64/gic_v3_irq.c"

FUNC = r'''void
gic_v3_diag_memtimer(void)
{
	static int done;
	uint32_t tidr, acr0, frq, ctl, pend, hits0, irq0, last;
	uint32_t ctlr, grp, isen;
	uint64_t t0, now, cval, router;
	kern_return_t rc;

	if (done) {
		return;
	}
	done = 1;
	if (!mt_base) {
		mt_ctl = ml_io_map(0x17c90000ULL, 0x1000);
		mt_base = ml_io_map(0x17ca0000ULL, 0x1000);
	}

	tidr = mt_rd(mt_ctl, 0x08);
	acr0 = mt_rd(mt_ctl, 0x40);
	frq = mt_rd(mt_base, 0x10);
	ctlr = gic_read32(gicd_base + GICD_CTLR);
	mt_line("mt1: ", tidr, acr0, frq, ctlr, 0, 0);

	rc = gic_v3_spi_attach(38, FALSE, mt_handler, NULL);
	if (rc != KERN_SUCCESS) {
		mt_line("mt2: ", (uint32_t)rc, 0, 0, 0, 0, 0);
		return;
	}
	/* what the distributor holds for intid 38 now: group, enable, route */
	grp = gic_read32(gicd_base + GICD_IGROUPR(1));
	isen = gic_read32(gicd_base + GICD_ISENABLER(1));
	router = *(volatile uint64_t *)(gicd_base + GICD_IROUTER(38));
	gic_diag_recent_n = 0;
	mt_line("mt1b: ", grp, isen, (uint32_t)router, 0, 0, 0);

	hits0 = mt_hits;
	irq0 = (uint32_t)gic_diag_irq_count;
	t0 = mt_rd64(mt_base, 0x08);            /* CNTVCT */
	mt_wr64(mt_base, 0x30, t0 - 19200);     /* CNTV_CVAL: already expired */
	mt_wr(mt_base, 0x3c, 1);                /* CNTV_CTL: enable, unmasked */
	cval = mt_rd64(mt_base, 0x30);
	for (volatile int i = 0; i < 400000; i++) {
		if (mt_hits != hits0) {
			break;
		}
	}
	now = mt_rd64(mt_base, 0x08);
	ctl = mt_rd(mt_base, 0x3c);
	pend = gic_read32(gicd_base + 0x0200 + 4);      /* GICD_ISPENDR1 */
	last = gic_last_unhandled;
	mt_line("mt2: ", ctl, pend, mt_hits - hits0, (uint32_t)(gic_diag_irq_count - irq0), last, cval - t0);
	/* the intids the CPU interface actually returned, in order */
	mt_line("mt2r: ", gic_diag_recent[0], gic_diag_recent[1], gic_diag_recent[2],
	    gic_diag_recent[3], gic_diag_recent[4], gic_diag_recent_n);
	mt_line("mt2s: ", gic_diag_recent[5], gic_diag_recent[6], gic_diag_recent[7],
	    (uint32_t)(now - t0), (uint32_t)(gic_unhandled_count & 0xffffffffu), 0);
	mt_wr(mt_base, 0x3c, 0);
	gic_write32(gicd_base + GICD_ICPENDR(1), 1u << 6);
	gic_v3_spi_detach(38);
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
                return start, i + 1
        i += 1
    sys.exit("unbalanced function")


def main():
    s = io.open(GIC, encoding="utf-8").read()

    glob_anchor = "uint64_t gic_diag_init_calls;\n"
    if "gic_diag_recent[8]" not in s:
        assert s.count(glob_anchor) == 1, "init_calls anchor"
        s = s.replace(glob_anchor, glob_anchor +
                      "uint32_t gic_diag_recent[8];\n"
                      "uint32_t gic_diag_recent_n;\n")

    # the spin has to see a handler that runs behind its back
    if "static volatile uint32_t mt_hits;" not in s:
        assert s.count("static uint32_t mt_hits;") == 1, "mt_hits anchor"
        s = s.replace("static uint32_t mt_hits;", "static volatile uint32_t mt_hits;")

    ring_anchor = "\t\tgic_diag_irq_count++;\n"
    if "gic_diag_recent[gic_diag_recent_n++]" not in s:
        assert s.count(ring_anchor) == 1, "handler anchor"
        s = s.replace(ring_anchor, ring_anchor +
                      "\t\tif (gic_diag_recent_n < 8) {\n"
                      "\t\t\tgic_diag_recent[gic_diag_recent_n++] = (uint32_t)intid;\n"
                      "\t\t}\n")

    start, end = find_function(s)
    s = s[:start] + FUNC + s[end:]
    io.open(GIC, "w", encoding="utf-8", newline="").write(s)
    print("patched gic_v3_irq.c for ck23")


main()
