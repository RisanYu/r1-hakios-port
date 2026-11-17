
---

## 2026-11-17 深夜补记：定时器问题解决，内核启动链完整跑通

上面 17:30 版的结论"内核停在 kernel_bootstrap_thread 中段、心跳恒 1"在当天深夜被推翻/完善：

1. 心跳恒 1 的根因不是 `hv_wdt_pet` 本身，而是**没有任何定时器中断**：EL1 虚拟定时器的 PPI 27 在本机是 Group 0（安全中断），
   非安全态内核改不了组、也收不到；物理定时器 CNTP 被高通 hypervisor 拦截（ISTATUS 会置位但永远不 pending）。
2. 解法：设备树里有一个**内存映射定时器**（`/soc/timer@0x17C90000`，frame0 `0x17CA0000`）。它的虚拟比较器在非安全态可编程
   （`CNTACR0` 写 `0x3f` 读回 `0x3f`），中断是 **SPI 38**（GICv3 DT 规则：SPI intid = param + 32）。
3. 补丁：`osfmk/arm64/machine_routines.c` 把 rtclock 切到该 frame 的 `CNTV_CVAL/CNTV_CTL`，用 `gic_v3_spi_attach(38, ...)`
   接收 tick，`_enable_virtual_timer()` 成功后不再使能 sysreg CNTV。
4. 结果（timer 内核，真实设备）：loader 日志出现 `tmem: framefffffff120cd0000`，内核日志从 0 字节变成 **23,110 字节**，
   `bsd_init` 全流程走完并挂载 ramdisk 根（`BSD root: md0`），最后执行到 `/sbin/launchd` 按预期 panic。
5. 同一份日志里第一次看到显示驱动探测：`MiniIOMobileFramebuffer: IOMFBDisplayRefresh: 60 Hz ... 319999 ticks`。

细节见 `docs/TIMER.md`；完整日志见 `evidence/timer-test-01-logdump.txt`。
