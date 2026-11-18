## 2026-11-18 12:49 iOS 16.5 SpringBoard 主屏幕（证据）

同一颗 timer 内核，加上真正的 Darwin 16.5 用户态（`system.apfs` 作为 resident md0、`root.apfs` 作为 md1 挂在 `/redwood`）后，系统不再在 launchd 阶段 panic：libignition 用真实设备身份跑完，launchd（Darwin Bootstrapper 7.0.0）启动，`backboardd` 起了 window server，SpringBoard 以 pid 8 运行并把主屏幕画到面板上。

- 运行方式：loader `--usb` payload → `fastboot boot` UEFI → loader USB 命令循环 → `oem ramdisk system.apfs`（2.36 GB）→ `oem run`
- 屏幕内容（`evidence/springboard-home-2026-11-18.png`）：状态栏 8:15 + 电池、Weather/Calendar 小组件、应用图标网格（FaceTime、Calendar、Photos、Mail、Notes、Reminders、Clock、News、TV、Podcasts、App Store、Maps、Health、Wallet、Settings）、Search 胶囊、Dock（Phone/Safari/Messages/Music）
- 日志证据（`evidence/springboard-log-2026-11-18.txt`）：`Darwin Ignition Sequence ... Version 1.0.0`、`Darwin Bootstrapper 7.0.0`、`Successfully spawned backboardd[13]`、`start window server`、`IOMobileFramebufferCreateDisplayList_block_invoke`、`iomfb_match_callback: primary`、`HID system ready`、`SpringBoard[8]`、`updateOverlay: Dismissing overlay: shell launched`
- 当前渲染路径是软件渲染（日志 `hakios: SpringBoard: no GPU draws, vibrant views are plain`），GPU 加速（Mesa/freedreno A630）与触摸驱动是下一步
- 内核跑满 150 秒仍稳定（日志 688 KB），由 loader `oem stop` 主动结束

---

## 2026-11-17 22:47 内核控制台上屏（证据）

用带 `--usb` 的 payload 让 loader 停在 USB 命令循环，`oem run` 启动内核后在运行期间用
`oem screenshot` + `upload` 抓到真实面板画面（`evidence/screen-console-2026-11-17.png`，
`getvar screen` = 1080x2242，stride 4320）。画面里能看到：

- 完整的 XNU verbose 启动日志（从 zone init 到 `BSD root: md0`）
- `Hello from user space on Darwin!` / `I am process 1, uid 0, console fd 0.`（临时 ramdisk 的 init）
- `panic: initproc failed to start`（预期，因为 ramdisk 里不是真的 launchd）
- 栈回溯与 stackshot 全部画在屏幕上，末尾光标停在屏幕左下角

⇒ 内核 framebuffer / 文本控制台链路在真机上工作正常（这一点此前只有 logdump 才能确认）。

# 当前状态（2026-11-17 22:00 左右）

## 一句话

**XNU 内核已在坚果 R1 真机上完整跑通启动链**：`arm_init` → `kernel_bootstrap` → `bsd_init` → 挂载 ramdisk 根（`BSD root: md0`）→ 执行到 `/sbin/launchd`（因临时 ramdisk 不是真的 launchd 而按预期 panic）。显示驱动已开始探测，屏幕尚未点亮。

## 启动链实际输出（节选，完整见 `evidence/timer-test-01-logdump.txt`）

```
Kernel version: Darwin Kernel Version 22.5.0 ...
[   51.793011]: [0]ml_processor_register>pset_find(cluster_id=0) returned pset 0
[   51.793236]: bsd_init: calling kauth_init
[   51.793443]: bsd_init: calling bsd_bufferinit
[   51.794784]: bsd_init: calling IOKitInitializeTime
[   51.794897]: bsd_init: calling vfsinit
[   51.800126]: bsd_init: calling bsd_autoconf
[   51.803052]: bsd_init: calling inittodr
[   51.803054]: bsd_init: calling setconf
[   51.803839]: MiniIOMobileFramebuffer: IOMFBDisplayRefresh: 60 Hz (the panel: 60), an interval of 71582788 (2^-32 s), 319999 ticks
[   51.905286]: Added memory device md0/rmd0 (01000000/0D000000) at FFFFFFF0081D0000 for 0000000000008000
[   51.905292]: BSD root: md0, major 1, minor 0
[   51.905317]: bsd_init: vfs_mountroot
...
Panicked task ...: pid 1: launchd
panic(cpu 0 ...): initproc failed to start -- no exit reason available
```

## 本轮（timer 内核）解决的核心问题

1. **MPIDR 映射错误**：loader 用错误的 CPU 编号列表填设备树，内核 `ml_get_cpu_number()` 返回 -1 → `cpu_init` 早期断言 panic（表现为"内核返回 31 字节空日志"）。已按原厂设备树修正为 `0x000/0x100/…/0x700`。
2. **定时器中断不可用**：PPI 27 是 Group 0 安全中断、CNTP 被 hypervisor 拦截。改用设备树里的**内存映射定时器** frame0（`0x17CA0000`）虚拟比较器 + **SPI 38**，内核第一次产出完整 23KB 日志。
3. **fastboot 大文件写入损坏**：ESP 改走 EDL firehose 写入 + 回读校验。
4. **checkpoint/logdump 调试基础设施**：无串口、无显示条件下定位死点的关键。

## 还没做（TODO，欢迎认领）

| 项 | 现状 | 下一步 |
|---|---|---|
| 显示上屏 | `MiniIOMobileFramebuffer` 已探测出 60Hz 参数 | Novatek TD4362 面板初始化时序、写入帧缓冲 |
| 触摸 | 未开始 | Synaptics TCM（i2c a98000 @0x4b）驱动 |
| 存储 | ramdisk 根可用 | UFS 驱动（`bsd/dev/hakios.ufs.c` 未 built-in），之后用真实分区做根 |
| 用户态 | 未开始 | 提取 iOS 16.5 root.apfs（`dipper-xnu` 的 prepare-ios 流程），复用 Mesa/freedreno A630 |
| 图形界面 | 未开始 | 用户态稳定 + GPU 渲染 + 触摸 |
| 持久化启动 | 未解决 | 目前每次需 PC `fastboot boot` RAM 加载 UEFI |

## 设备当前状态

- ABL：`QC_Reference_Phone`（`unlocked:no`，但可 fastboot 刷分区；从 flash 启动自定义镜像仍会被校验拒绝）
- 手机处于 fastboot（或 EDL，取决于最后一次循环是否跑完）
- 原厂分区备份存放在开发机上（未包含在本仓库）
