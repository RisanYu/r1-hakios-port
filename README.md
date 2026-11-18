# 把 HakiOS（XNU / Darwin-on-Android）移植到坚果 R1

**设备**：Smartisan 坚果 R1（型号 DE106，代号 `trident`，高通骁龙 845 / SDM845，UFS 2.1，1080×2242 屏）
**系统**：HakiOS（基于 Apple 开源的 XNU 内核 + Darwin 用户态，跑在 Android 手机上）
**状态**：🔧 内核已在真机启动进到 BSD init 完成、ramdisk 挂载成功、进入 launchd 启动阶段（因临时 ramdisk 不是真的 launchd 而 panic，属预期）；显示驱动已探测但尚未完成面板初始化/上屏；用户态与图形界面尚未开始。

这个仓库记录到目前为止**全部可复现的东西**：工具链脚本、loader/内核补丁、调试方法、真机验证日志。目的不是发布可用系统，而是让后来者（以及未来的我）能按记录重新走通这条路径，并继续往下推进。

---

## 目前做到了什么

| 里程碑 | 状态 | 证据 |
|---|---|---|
| BL 锁状态下通过 EDL 获得可刷机状态（高通参考 ABL） | ✅ | `docs/EDL` 流程、fastboot 可用 |
| Renegade UEFI（edk2）从 RAM 启动，从 `system_b` 的 ESP 引导 XNU loader | ✅ | `evidence/` |
| HakiOS loader 识别新平台 `platform trident` | ✅ | `patches/loader.c` |
| XNU 内核在真机启动，越过 `arm_init` / `kernel_bootstrap` | ✅ | 检查点日志 |
| 定位并修复 loader 的 MPIDR 映射错误（内核拓扑断言崩溃） | ✅ | `docs/CHECKPOINTS.md` |
| 定位并解决 SDM845 上定时器中断不可用问题（PPI 27 Group0 / CNTP 被 hypervisor 拦截） | ✅ | `docs/TIMER.md` |
| `bsd_init` 全流程：驱动 attach、`bsd_autoconf`、`inittodr`、`setconf` | ✅ | `evidence/timer-test-01-logdump.txt` |
| 挂载 ramdisk 根文件系统：`BSD root: md0, major 1, minor 0` | ✅ | 同上 |
| 启动 `/sbin/launchd`（当前 ramdisk 不是真的 launchd → 预期 panic） | ✅（预期 panic） | 同上 |
| 显示驱动探测（`MiniIOMobileFramebuffer: IOMFBDisplayRefresh 60 Hz`） | 🟡 探测通过，未上屏 | 同上 |
| 用户态（iOS 16.5 root.apfs）与图形界面 | ⬜ 未开始 | — |
| 不依赖电脑的持久化启动 | ⬜ 未开始 | — |

## 为什么内核会卡住、我们怎么修的

这台手机没有串口、没有可用的显示控制台，内核早期崩溃时什么都不打印。我们的调试方式是：

1. **logdump 分区当"黑匣子"**：loader 把运行日志写进 `logdump` 分区，PC 通过 EDL 读回来。
2. **检查点（checkpoint）二分法**：给内核源码插入 `loader_checkpoint(N)` 调用；loader 把"N 号检查点"写进返回槽并直接跳回 loader，于是每个检查点是否命中都能从 logdump 里读出来。用这种方式把死点从"整个内核"缩到"某两行之间"。
3. 遇到需要看硬件状态的地方，写**只读探针**打印寄存器，再逐步加写操作——先用只读探针确认状态，避免盲目写寄存器把机器搞静默。

详见 `docs/CHECKPOINTS.md` 与 `docs/TIMER.md`。

## 硬件侧的关键发现

- **MPIDR 映射**：SDM845 上 8 个核的真实 MPIDR 是 `0x000, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700`（来自本机原厂设备树），不是"每簇 4 个连续编号"。loader 按旧列表填设备树 → 内核 `ml_get_cpu_number()` 查不到当前核 → 早期断言 panic（表现为"内核返回 31 字节空日志"）。
- **定时器**：EL1 虚拟定时器中断是 PPI 27，但这台机器上它是 **Group 0（安全侧）**，非安全态内核改不了组也收不到；物理定时器 CNTP 被高通 hypervisor 拦截（写了 ISTATUS 会置位但永远不 pending）。
  解决办法：用设备树里的**内存映射定时器**（`0x17C90000` 控制器 + frame0 `0x17CA0000`）的虚拟比较器当 tick，中断走 SPI 38（GICv3 DT 规则：SPI intid = DT param + 32）。这让人第一次跑出了完整的内核日志。
- **fastboot 大文件写入不可靠**：48MB 的 ESP 用 `fastboot flash system_b` 写会静默损坏；改用 EDL firehose 写入并逐字节回读校验。
- **`fastboot boot` 镜像格式**：必须按 Android boot **v0 / page_size 4096** 打包，否则 ABL 报 `BootImage is Incomplete`。

## 目录结构

```
docs/        调试记录、检查点方法、定时器专题、时间线
patches/     loader 源码（含 trident 平台补丁）与内核补丁脚本
tools/       刷机、EDL、ESP 构建、真机测试循环、QEMU 验证等脚本
device/      设备配置（HakiOS device layer + SoC 配置）
evidence/    真机验证日志（已脱敏）
```

## 快速开始（想复现的话）

1. 一台坚果 R1（DE106）+ 一条 9008 工程线（或拆机短接测试点）。
2. PC 上装好 WinUSB 驱动（Zadig）与 libusb 运行库；本项目工具默认 Windows + WSL2 双环境。
3. 按 `docs/TIMELINE.md` 的顺序执行；每一步我都记录了当时的确切命令与结果。
4. 需要 HakiOS 上游源码：见下方 Credits。

> ⚠️ 注意：本仓库**不包含**任何 Apple 的 XNU 源码、Apple 固件/IPSW、Smartisan ROM、高通 firehose 或 GPT 镜像。这些都需要你从自己合法拥有的设备/固件里获取。详见 `NOTICE.md`。

## 尚未完成（欢迎一起搞）

- 显示：Novatek TD4362 面板初始化、把内核控制台上屏（`docs/BOOT-DEBUG.md` 有痕迹）
- 触摸：Synaptics TCM（i2c-98000 @0x4b）
- 存储：UFS 驱动（把根文件系统放到真实分区）
- 用户态：iOS 16.5 root.apfs + Mesa/freedreno A630（复用 dipper 的移植成果）
- 持久化启动：在 BL 锁未真正解除的现状下，如何不靠 PC `fastboot boot` 每次启动

## 致谢 / 上游

- [HakiOS](https://github.com/oosexgang/hackios-xnu-kernel)（XNU/Darwin-on-Android 上游）
- [Renegade Project](https://github.com/edk2-porting)（UEFI for SDM845）
- [dipper-xnu](https://github.com/youzjuzi/dipper-xnu)（小米 8 的 SDM845 移植，GPU/用户态路线参考）
- [bkerler/edl](https://github.com/bkerler/edl)（EDL 客户端）
- Linux 内核 `drivers/clocksource/arm_arch_timer.c`（内存映射定时器寄存器布局参考）

## License

本仓库自己的代码/文档：MIT。涉及 Apple XNU / HakiOS 的补丁部分见 `NOTICE.md`（APSL 2.0）。

## Milestones

| Date | Milestone |
|---|---|
| 2026-11-17 22:47 | the XNU console draws on the R1 panel: first on-screen kernel log (loader `oem screenshot` capture, `evidence/screen-console-2026-11-17.png`) |
| 2026-11-18 12:49 | **iOS 16.5 SpringBoard home screen runs on the R1 panel** (real launchd + backboardd window server + software rendering; `evidence/springboard-home-2026-11-18.png`) |
