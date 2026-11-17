# 专题：SDM845（坚果 R1）上的定时器中断为什么不可用，以及怎么绕过去

## 症状

内核在 `bsd_init` 的 `IOFindBSDRoot()` 里第一次做"带超时的等待"（`waitForMatchingService(matching, 0.1s)`）就永久挂死。
loader 的监视循环每 2 秒打印 `N s: the kernel has logged 0 bytes, heartbeat 1`——**心跳恒为 1**，
说明 `hv_wdt_pet` 里每 10 秒一次的延迟 thread_call 从未触发：**定时器中断根本没来**。

## 取证过程（全部通过检查点内核 + logdump 完成，没有串口）

| 探针 | 观察 | 结论 |
|---|---|---|
| ck14/ck16 | `CNTV_CTL` 写 1ms 后 `ISTATUS=1`（ctl2=0x5），但 `irq=0`；`GICR_IGROUPR0` 读回 0（PPI27 = Group 0）；`GICD_ISPENDR1=0x10000000`（PPI28 pending，疑似 hypervisor） | 定时器条件满足，但没有中断送到 CPU |
| ck17 | 尝试写 `GICR_IGROUPR0 |= 1<<27` 无效（读回不变）；使能 bit 可以 `ISENABLER`，但 ISSTATUS 永远不 pending | PPI27 被固件/安全侧锁在 Group 0，NS 改不动 |
| ck17 | 物理定时器测试：写 `CNTP_CVAL/CNTP_CTL` 后 ISTATUS=1，但 PPI 30 **从未 pending** | CNTP 被高通 hypervisor 拦截/仿真，不能用作中断源 |
| ck18 | 软件置 `GICD_ISPENDR(38)` 后 `irq=2` | SPI 中断递送通道本身没问题 |
| ck19 | handler 记录的 `gic_last_unhandled = 38` | **SPI 38 确实作为 IRQ 送达**，可以作为 tick 中断 |

源码旁证（HakiOS 自己的注释，`osfmk/arm64/machine_routines.c`）：

> "When running at EL1 under a third-party hypervisor (e.g. Qualcomm's), the EL1 physical timer
> registers are trapped and the access faults. The guest only owns the virtual timer."

但"guest 只拥有虚拟定时器"在这台机器上也不成立——虚拟定时器的中断是 PPI 27，它是安全中断。

## 解法：改用内存映射定时器（arm,armv7-timer-mem）

本机原厂设备树里有（`/soc/timer@0x17C90000`，compatible `arm,armv7-timer-mem`）：

```
reg = <0x17C90000 0x1000>            # CNTControl base
frame@0x17CA0000 {
    reg = <0x17ca0000 0x1000>, <0x17cb0000 0x1000>;
    frame-number = <0>;
    interrupts = <0 7 4>, <0 6 4>;   # 物理定时器 SPI7, 虚拟定时器 SPI6
};
frame@0x17CC0000 ... 7 个 frame
```

GICv3 设备树规则：**SPI intid = DT param + 32** ⇒ frame0 的虚拟定时器中断 = **intid 38**，
正是 ck19 证明能送达的那个 SPI。

寄存器布局（与 Linux `drivers/clocksource/arm_arch_timer.c` 一致）：

| 地址 | 寄存器 | 说明 |
|---|---|---|
| 0x17C90008 | CNTTIDR | frame 能力位 |
| 0x17C90040 + 4n | CNTACR(n) | 第 n 个 frame 的访问权限（RPCT/RVCT/RFRQ/RVOFF/RWVT/RWPT = bit0..5） |
| 0x17CA0000 | CNTPCT_LO | 物理计数器 |
| 0x17CA0008 | CNTVCT_LO | 虚拟计数器（与系统计数器同源） |
| 0x17CA0010 | CNTFRQ | 19,200,000 Hz（实测 0x0124f800） |
| 0x17CA0020 | CNTP_CVAL_LO | 物理比较值 |
| 0x17CA002C | CNTP_CTL | bit0 ENABLE, bit1 IMASK, bit2 ISTATUS |
| 0x17CA0030 | CNTV_CVAL_LO | 虚拟比较值 |
| 0x17CA003C | CNTV_CTL | 同上 |

探针实测（ck21/ck22）：
- `CNTTIDR=0x01111117`，`CNTACR0` 写 `0x3f` 读回 `0x3f` ⇒ **frame0 归非安全态编程**
- 写 `CNTV_CVAL = 过去 1ms` + `CNTV_CTL=1` ⇒ `CNTV_CTL=0x5`（ISTATUS 置位），`GICD_ISPENDR1=0x40`（intid 38 pending）⇒ 硬件中断真的产生了
- ck23 的 handler ring 记录到 intid 38 ⇒ 中断确实进入我们的 handler

## 实现（`patches/kernel-timer-memtimer.patch`）

在 `osfmk/arm64/machine_routines.c` 中：

1. `arm_timer_mem_init()`：`ml_io_map(0x17CA0000, 0x1000)`，`gic_v3_spi_attach(38, FALSE, arm_timer_mem_intr, NULL)`（电平触发）
2. `arm_timer_mem_set_decrementer(dec)`：读 `CNTVCT` → 写 `CNTV_CVAL = now + dec`（先高 32 位后低 32 位）→ `CNTV_CTL = 1`
3. `arm_timer_mem_intr()`：先写 `CNTV_CTL = 0` 撤掉电平（电平触发必须这样做），再 `cpu_decrementer = -1; rtclock_intr(TRUE);`
4. 钩子：`ml_set_decrementer` / `ml_get_decrementer` / `ml_get_timer_pending` 在 memtimer 可用时走 MMIO；`_enable_virtual_timer()` 初始化失败才退回系统寄存器 CNTV。

## 验证结果

timer 内核（`hakios-kernel-trident-timer`，14,918,856 B）真机运行：

- loader 日志出现 `tmem: framefffffff120cd0000`（初始化成功）
- 内核日志从"0 字节 / 心跳恒 1"变成 **23,110 字节完整 verbose**
- `bsd_init` 一路走到底：`bsd_autoconf` → `inittodr` → `setconf` → `Added memory device md0` → **`BSD root: md0, major 1, minor 0`**
- 最后执行到 launchd 才按预期 panic（`initproc failed to start`）——因为临时 ramdisk 里放的不是真的 launchd
- 顺带第一次看到显示驱动探测：`MiniIOMobileFramebuffer: IOMFBDisplayRefresh: 60 Hz`

至此内核启动链完整跑通。

## 复盘

- 任何时候先写**只读探针**确认硬件状态，再决定写操作。盲目写 GIC 组寄存器（ck15）导致过静默崩溃。
- 设备树是金矿：我们需要的"另一条中断路径"就写在原厂 DT 里，只是 Android 内核没用它。
- 无串口/无显示时的调试基础设施（logdump + checkpoint）值得在移植一开始就搭好，它省下的时间以天计。
