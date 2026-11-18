# 时间线（2026-11-15 ~ 2026-11-17）

> 记录在这台坚果 R1 上从"BL 锁 + 无法进入任何特殊模式"到"XNU 内核在真机跑到 launchd 启动阶段"的完整路径。
> 所有时间均为本地时间（UTC+8）。

## 11-15 之前：前期（更早的会话）

- 确认设备与目标：Smartisan 坚果 R1（DE106，`trident`，SDM845 v2.1，BL 锁，官方 ROM 拦截 `adb reboot bootloader/fastboot/edl`）
- 目标 HakiOS（XNU/Darwin-on-Android），用户要求"只刷 HakiOS"
- 准备材料：官方 ROM 里的 firehose、GPT、分区块备份、Renegade UEFI、HakiOS 源码

## 11-16：EDL、UEFI、第一版内核

| 时间 | 事件 |
|---|---|
| 傍晚 | 首次成功进入 EDL（`VID_05C6&PID_9008`）：关机 15s → 插 9008 线 → 按住按钮短接 → 按电源 → 黑屏后松开短接 |
| 18:18 | WinUSB（Zadig）+ bkerler edl 客户端打通；`printgpt` 成功，备份 devinfo/boot/vbmeta/xbl/abl 等全部分区 |
| 19:0x | M3 尝试：EDL 写 Renegade UEFI 进 boot + 改 vbmeta (flags=0x2) → 开机显示 "Your device has failed verification"（锁 BL 下非 OEM 签名仍被 ABL 拒绝）；恢复原厂 |
| 19:2x | 对比测试 QPST TWRP 包 boot.img（64MB 整分区 + AVB footer）→ 同样校验失败 |
| 20:0x | 刷入整个 QPST_TWRP 包 12 个分区（xbl/xbl_config/abl/boot/dtbo/vbmeta 双槽）→ ABL 变成 **QC_Reference_Phone**（`fastboot` 可用，product=QC_Reference_Phone，但 `unlocked:no`） |
| 20:3x | 自写 `fastboot-lite.py`（pyusb 直说 fastboot USB 协议）；发现 `oem reboot-edl` 可以远程进 EDL，从此免短接 |
| 21:0x | 发现 `fastboot boot` 需 Android boot **v0 / page4096** 格式；UEFI 真机启动成功，从 system_b 的 ESP 引导 XNU loader，首次输出 `== XNULOADER v3 ==` |
| 21:5x | loader 首次崩溃于 QEMU 专用 ramfb 写 fw_cfg 地址（真机未映射）→ 补丁：ramfb 仅 QEMU |
| 22:5x | 内核首次在真机打出 verbose（Darwin 22.5.0、IOKit/BSD init），随后停住 |
| 深夜 | 定位"热启动残留 payload"（loader 跳过从 ESP 重载）；确认 fastboot 写大文件损坏（改 EDL）；开始真机自动化循环 `trident_cycle.py` |

## 11-17：检查点调试、MPIDR、定时器

| 时间 | 事件 |
|---|---|
| 00:27 | 夜间实验收尾、自动关机（手机随 USB 断电） |
| 08:0x | 重启；WSL2 + Ubuntu 22.04 落地，构建环境：theos clang 11.1.0 + iPhoneOS16.5 SDK + macOS 13.3 SDK（网络受限，走 gh-proxy 下载） |
| 08:36 | `xnu/apply.sh` 拉下 Apple XNU 8796.121.2 成功 |
| 08:41 | 修 `xnu-deps` 的 `strlcat`、clang `-ftrivial-auto-var-init` 门控、缺 `python` 三个坑 |
| 08:53 | **trident 内核首次编译成功**（14,901,688 B） |
| 09:0x | 首个真机循环：loader 起 kernel 后无日志（后查明是 CPU 编号问题） |
| 09:2x | 确认 loader 打印 `platform trident`、`gop fb=9d400000 1080x2242`；QEMU 对照证明编译链/内核镜像没问题 |
| 09:3x | 检查点体系上线：`ck_sweep.py` + `trident_cycle.py`（先清 logdump，再写 ESP，再 RAM 启动） |
| 14:3x | 检查点扫描：CP10/11/15 命中、CP16 不命中 → 死点在 `timer_call_init(); cpu_init();` |
| 15:2x | 细分到 `cpu_init()` 内 `do_cacheid()` |
| 16:0x | ck4/ck5/ck6：发现在 `do_cacheid` 前沿 code path 上，`ml_get_cpu_number()` 返回 -1 |
| 16:29 | **ck6 诊断内核打出决定性一行**：`dbg: mpidr=0000000081000200 ... n=-1 ... phys0=00000002` |
| 16:3x | 从原厂设备树读出真实 MPIDR（0x000/0x100/…/0x700），修 loader 的 `trident_cpu_mpidrs[]` + PSCI CPU_ON fallback；重建 loader（67,584 B） |
| 16:41 | 修复后内核第一次 `n=0`（CPU 查表成功），但随后挂死；CP60 命中 |
| 17:0x | CP61..64、CP16 全命中 → do_cacheid / cpu_init 通过 |
| 17:3x | 正式内核心跳仍恒 1、kernel_bootstrap 段检查点 99..110 全命中 |
| 18:2x | kernel_bootstrap_thread 段 111..133 全命中；cp134 未编译（`#ifndef BCM2837`） |
| 19:0x | bsd_init 检查点 135..146 全命中；**147 不命中** → 死点在 `setconf()→IOFindBSDRoot()` |
| 20:2x | 细分 IOFindBSDRoot：160 命中、161 不命中 → 卡在 `waitForMatchingService()` |
| 20:3x~21:1x | 定时器探针 ck14~ck19：确认 PPI27 是 Group0、CNTP 被 trap、SPI 38 可以送达 |
| 21:2x~21:4x | ck20~ck23：读出内存映射定时器寄存器布局、确认 frame0 可编程、SPI38 真的 pending |
| 21:4x | 写 `machine_routines.c` 的 memtimer 补丁并构建 **timer 内核**（14,918,856 B） |
| 21:5x | **timer 内核真机跑通**：内核日志 23,110 字节、`bsd_init` 全过、`BSD root: md0`、到 launchd 才按预期 panic |

## 当前状态（11-17 深夜）

- 内核启动链已在真机完整跑通（到 launchd 启动阶段）
- 显示驱动已探测（60Hz 参数算出），面板初始化与上屏未做
- 触摸、UFS、iOS 用户态、持久化启动：未开始

## 2026-11-17 22:47 — first kernel console on the R1 panel

- loader 增加 `--usb` payload 模式后，可在真机上反复 `oem run` / `oem screenshot` / `upload`
- `getvar screen` = `1080 2242 4320`；`oem screenshot` + `upload` 抓到面板真实画面
- 画面显示完整 XNU verbose 日志、`BSD root: md0`、`Hello from user space on Darwin!`、
  `panic: initproc failed to start`（预期）、栈回溯与 stackshot
- 证据：`evidence/screen-console-2026-11-17.png`

## 2026-11-18 12:49 — iOS 16.5 SpringBoard 主屏幕出现在 R1 面板上

- 11-17 夜间：Darwin 16.5 用户态镜像构建成功（`root.apfs` 4 MB / `system.apfs` 2.36 GB）
- 11-18 清晨：GUI payload（timer 内核 + root.apfs 作 md1）首次启动；APFS 根挂载/`devfs`/`/redwood/etc/rc` 全通，卡在 `libignition` 查询 `hw.target`（EINVAL 22）
- 12:0x：根因是 loader 用占位身份构建（`mkidentity.py --placeholder`）；用 IPSW 的 `DeviceTree.d22ap.im4p` 重建 `identity.h` 并重编 loader（72,192 B）
- 12:40：UEFI → loader → `oem ramdisk system.apfs`（13.6 MB/s）→ `oem run`；launchd/backboardd/SpringBoard 全部起来
- 12:49：`guirun 150` 干净图形化运行（去掉 `-v`），`shot-013` 即 iOS 16.5 主屏幕；内核稳定跑满 150 s，日志 688 KB
- 证据：`evidence/springboard-home-2026-11-18.png`、`evidence/springboard-first-draw-2026-11-18.png`、`evidence/springboard-log-2026-11-18.txt`
- 仍待解决：触摸（Synaptics TCM）、GPU 加速（Mesa/freedreno A630）、cellular/biometry、持久化启动
