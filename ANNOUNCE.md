# 开源文案（三版，按场合取用）

> 把下面 `https://github.com/RisanYu/r1-hakios-port` 替换成最终仓库地址；文中时间与日志都可复现（见仓库 `evidence/`）。

---

## 版本 A：完整版（GitHub Release / 长文帖 / 知乎 / 酷安专栏）

**标题：把 HakiOS（XNU/Darwin）移植到坚果 R1——目前内核已跑到 BSD init 全通过、挂载 ramdisk 根、进入 launchd 启动阶段**

先说结论：**坚果 R1（Smartisan DE106，代号 trident，骁龙 845）上，XNU 内核真的跑起来了**——不是 QEMU 里跑，不是在别的手机上跑，是在这台真机上：

- 内核完整走完 `arm_init` → `kernel_bootstrap` → `bsd_init`
- 成功挂载 ramdisk 根文件系统：`BSD root: md0, major 1, minor 0`
- 执行到 `/sbin/launchd`，因为临时 ramdisk 里不是真的 launchd，按预期 panic（这正是 QEMU 里同样的行为）
- 显示驱动开始探测：`MiniIOMobileFramebuffer: IOMFBDisplayRefresh: 60 Hz`（还没做面板初始化，屏幕还不亮）

从"内核启动就黑屏/无输出"到"完整内核日志 + 挂载根文件系统"，我们在两天里修掉了五个看起来无解的死点：

1. **loader 的 CPU 编号是错的**。SDM845 八个核的真实 MPIDR 是 `0x000/0x100/.../0x700`，loader 按"每簇连续编号"填设备树，内核查拓扑时找不到自己 → 极早 panic，且 panic 时内核日志缓冲区还没初始化，表现为"内核返回了但日志 0 字节"。
2. **内核没串口、没显示控制台**，早期崩溃等于瞎。于是我们做了两件事：把 loader 日志写进 `logdump` 分区用 EDL 读回来；给内核插 **checkpoint 检查点**，每命中一个检查点就带着日志跳回 loader。用二分法把死点从"整个内核"缩到"某两行之间"。
3. **定时器中断根本不来**。这台机器上 EL1 虚拟定时器的中断（PPI 27）是 **Group 0 安全中断**，非安全态内核既改不了组也收不到；物理定时器 CNTP 被高通 hypervisor 拦截（寄存器能写、ISTATUS 会置、但永远不 pending）。后果是内核里第一个"带超时的等待"就永久挂死。
4. **解法**：设备树里还有一个**内存映射定时器**（`0x17C90000` 控制器 / frame0 `0x17CA0000`）。我们用只读探针确认它在非安全态可编程（CNTACR 授权成功），把内核 rtclock 切到它的虚拟比较器上，中断走 SPI 38。**这一改，内核立刻打出了完整日志**。
5. **fastboot 写大文件会静默损坏**：48MB 的 ESP 用 `fastboot flash` 写，回读一比对就发现从 4KB 处开始不对；改成 EDL firehose 写入 + 逐字节回读校验才可靠。`fastboot boot` 的镜像也必须按 Android boot v0 / page_size 4096 打包，否则 ABL 直接报 `BootImage is Incomplete`。

另外，这台机器 BL 锁没法真正解除（Smartisan 官方没有解锁通道），我们的方案是：EDL 刷高通参考 ABL 获得"能刷机"的状态，每次启动由 PC `fastboot boot` 加载 Renegade UEFI，再从 system_b 的 ESP 引导 XNU loader —— 也就是说**目前每次启动都要插电脑**，这一点还没解决。

接下来要做的：面板初始化让内核日志/图形上屏、Synaptics 触摸、UFS 驱动、iOS 16.5 用户态（复用小米 8 / dipper 的 Mesa + freedreno A630 路线），最后才是图形界面。

**仓库**：`https://github.com/RisanYu/r1-hakios-port`，包含全部脚本、补丁、调试方法与真机日志（已脱敏）。
**说明**：仓库不含任何 Apple 源码/固件/厂商 ROM/高通 firehose（这些请从你自己的设备获取），补丁与文档的许可见 `NOTICE.md`。

这个项目大概率要几周甚至更久，但方向已经通了。欢迎一起来填坑：
- 熟悉 Qualcomm SDM845 / GICv3 / ARM64 启动流程的同学
- 做过 HakiOS / XNU 移植（dipper、fajita 等）的同学
- 有坚果 R1 真机、愿意一起测试的同学

---

## 版本 B：短版（微博 / B 站动态 / 酷安短帖 / 朋友圈）

**坚果 R1（骁龙 845）上把 HakiOS 的 XNU 内核跑起来了。**
不是 QEMU——是真机：内核走完 `arm_init`、`kernel_bootstrap`、`bsd_init`，成功挂载 ramdisk 根（`BSD root: md0`），执行到 launchd 才按预期 panic；显示驱动也已开始探测（60Hz 面板参数算出来了，屏幕还没亮）。

两天修掉五个死点：loader 的 MPIDR 映射错误、内核无串口时用 logdump + checkpoint 二分、**SDM845 上 PPI27 是 Group0 安全中断而 CNTP 被 hypervisor 拦截导致定时器根本不来**（最后改用设备树里的内存映射定时器 + SPI 38 解决）、fastboot 大文件写入静默损坏（改 EDL 校验写入）等。

工具、补丁、调试方法、真机日志全部开源：`https://github.com/RisanYu/r1-hakios-port`
下一步：上屏、触摸、UFS、iOS 用户态，然后才是图形界面。路还长，欢迎一起搞。

---

## 版本 C：English

**HakiOS (XNU/Darwin-on-Android) on the Smartisan Nut R1 (trident, Snapdragon 845) — kernel now boots through BSD init on real hardware.**

On a real DE106 (not QEMU): the XNU kernel walks `arm_init` → `kernel_bootstrap` → `bsd_init`, mounts a ramdisk root (`BSD root: md0, major 1, minor 0`) and reaches `/sbin/launchd` (it panics there because our temporary ramdisk is not a real launchd — the expected QEMU behaviour). The display driver is probing too (`MiniIOMobileFramebuffer: IOMFBDisplayRefresh 60 Hz`), though the panel is not initialised yet.

Five blockers were solved in two days:
1. The loader had the wrong MPIDR list for SDM845 (real MPIDs are `0x000/0x100/.../0x700`), so the kernel's topology lookup failed very early and panicked before its log buffer existed.
2. No UART, no console: we log through the `logdump` partition (read back over EDL) and use boot-loader **checkpoints** to bisect the hang down to a couple of lines.
3. The architected EL1 virtual timer interrupt (PPI 27) is a **Group 0** interrupt on this SoC, and CNTP is trapped by Qualcomm's hypervisor — so no timer interrupt ever arrives.
4. Fix: drive the real-time clock from the **memory-mapped timer** block (`0x17C90000` / frame 0 `0x17CA0000`) with **SPI 38** as the tick interrupt.
5. `fastboot flash` silently corrupts large images (use EDL firehose writes with read-back verification); `fastboot boot` needs an Android boot **v0 / page_size 4096** image.

Everything (tools, patches, debugging method, sanitized device logs) is open source: `https://github.com/RisanYu/r1-hakios-port`.
Next: panel bring-up, touch (Synaptics TCM), UFS storage, then the iOS 16.5 userland (reusing the dipper Mesa/freedreno A630 work) and finally a GUI. Contributions welcome.
