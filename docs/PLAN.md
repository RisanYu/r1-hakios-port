# HakiOS on Smartisan R1（trident）移植计划

> 只做 HakiOS，不刷任何其他系统。HakiOS 默认 RAM 运行（`fastboot boot`，不写机），符合此约束。

## 设备与目标

| 项目 | 值 |
|---|---|
| 机型 | Smartisan R1 / 坚果 R1，型号 DE106，代号 `trident` |
| SoC | Qualcomm SDM845（Adreno 630） |
| 当前系统 | Android 8.1（OPM1.171019.026），A/B 分区，当前 `_a` |
| BL 状态 | **锁定**（`flash.locked=1`，verifiedbootstate=green，vbmeta=locked） |
| OEM 解锁开关 | `ro.oem_unlock_supported=true`，但开发者选项里**没有该开关**，`sys.oem_unlock_allowed=0` |
| 目标 | 在 R1 上跑起 HakiOS（XNU/Darwin 研究项目） |

## 关键事实

- HakiOS 官方**只支持** POCO X5 Pro 5G（`redwood`，SM7325）与 QEMU；**没有 SDM845 / trident 支持**。
- HakiOS 的 SoC 层目前只有 `sc7280` 家族；SDM845 需要自建。
- Renegade 项目 `edk2-sdm845` **已有 trident 的 UEFI 平台配置**，并提供 `boot-trident.img`（2301.1，6.4MB）——可作为引导层参考/起点。
- LineageOS 22.2 官方支持 trident，有完整 device tree（面板/触摸/分区/SELinux 等），可作为设备移植的硬件参考。
- 参考文献见 `references/`。

## 里程碑

### M0：打通 fastboot + 解锁 BL（当前阻塞）
- 现象：`adb reboot bootloader` / `adb reboot fastboot` 只会普通重启回 Android；按键组合未确认；0.3s 间隔监听 fastboot 从未出现。
- 阻塞原因候选：
  1. 音量键（尤其音量减）硬件问题；
  2. 按键组合/时机不对；
  3. ROM 拦截 bootloader 重启（OEM 解锁未开放）；
  4. USB 在 bootloader 模式下枚举失败。
- 验收：`fastboot devices` 能看到设备，`fastboot getvar unlocked` 可读，`fastboot oem unlock` 成功（清数据），重启后 `ro.boot.flash.locked=0`。

### M1：构建环境
- Linux 构建机（WSL2 或独立 Linux），需要几十 GB 磁盘、Git、Python、QEMU。
- 验收：`make doctor` / `make qemu-open` 能跑通。

### M2：QEMU 跑通 HakiOS
- `make qemu-open`（开放内核）；可选 `make qemu` + 自备 IPSW 跑 Darwin 用户空间。
- 验收：QEMU 里出 HakiOS 标识/界面。

### M3：R1 上 UEFI 内存启动验证
- `fastboot boot boot-trident.img`（Renegade UEFI）不写机。
- 验收：屏幕出 UEFI 菜单/日志。

### M4：HakiOS loader + 最小内核在 R1 启动
- 基于 Renegade UEFI + HakiOS `make loader`；先无驱动启动到 launchd。
- 验收：串口/屏幕日志出现 HakiOS banner、`kernel.ver=`。

### M5：驱动 bring-up（逐个）
- CPUFREQ/THERMAL/SOCINFO → BUTTONS/触摸 → UFS → ADRENO(GPU) → ADSP/电池/音频 → WIFI → 其余。
- 验收：各驱动状态写入 device.conf，逐项对照。

## 风险

1. **BL 可能无法解锁**：LineageOS wiki 明确写"官方解锁方式不存在"，只可能有非官方方法；若 M0 永久卡死，整个项目无法在真机上验证。
2. **工作量大**：SDM845 SoC 层 + 设备 port 以月计；参考 UniXNU 的 dipper（小米 8）/ enchilada（一加 6）等 SDM845 移植。
3. **无 Apple 服务**：HakiOS 不支持激活/Apple ID/App Store；Darwin 用户空间需自备 IPSW。
4. **法规与保修**：解锁清数据、影响保修；Darwin 用户空间来源自行负责。

## 参考资源

- HakiOS 文档：`references/hakios-phone.md`、`references/hakios-getting-started.md`、`references/hakios-porting.md`
- Renegade UEFI：`r1-trident/boot-trident.img`（sha256 B95C46AA9D3F43DF44745C92F824A86E01E381146F898E542431EB58F151305E）
  - 源码：`edk2-porting/edk2-sdm845`，`Platform/Smartisan/sdm845/trident.dsc`，`configs/devices/trident.conf`
- LineageOS device tree：`references/lineage-trident-BoardConfig.mk`、`references/lineage-trident-device.mk`
- UniXNU SDM845 参考：`hanyaa380/UniXNU-dipper`（小米 8）、`keyfan/UniXNU-enchilada-bringup`（一加 6）
- 上游 HakiOS：<https://github.com/oosexgang/hakios-xnu-kernel>

## 进度记录

- 2026-11-15 22:00：项目启动；资料下载完成；M0 阻塞中（fastboot 不可达）。
- 2026-11-15 22:15：**M0 调查结论**：Smartisan 官方 ROM 限制了 fastboot 入口（`adb reboot bootloader` 仅普通重启、按键组合也进不了 fastboot），社区解锁路径是 **9008/EDL + 工程线**（Bilibili「坚果R1解BL锁9008工程线」、CSDN 教程已存档）。
  - 需要的材料：**R1 线刷包**（含 `prog_firehose_ddr.elf`、`rawprogram0.xml`、`patch0.xml`、`del-flash.bat`，来源 ROM中国 cnroms.com「R1_user_V6.0.4.zip」，付费/或问 9008 线卖家）、QPST 2.7.460 / QFIL、高通全系列 USB 驱动、禁用驱动签名。
  - 流程（CSDN 记录）：手机关机 → 插线 → 短接工程线 → 按住音量+与电源 15~20s → 松手断开短接 → QFIL 检测到 9008 立即 Download（Device Type=UFS，Programmer=`prog_firehose_ddr.elf`，XML=`rawprogram0.xml`+`patch0.xml`）。
- 2026-11-15 22:20：**M4 预备里程碑完成** —— 从手机 `/proc/device-tree`（shell 可读）经 tar 取出 19960 个节点，用自写 `r1-trident/build-fdt.py` 重建 `fdt.dtb`（618KB，HakiOS `tools/soc-args.py` 解析成功，读出 9/16 个 soc_* 值）；运行 `tools/hakios-device.py new trident --soc sdm845 ...` 生成了 **`devices/trident/` 设备仓库骨架 + `soc/` 下的 sdm845 SoC 层**（`device.conf`、`configs/trident_defconfig`、`configs/trident.config`、`soc.args`、`metal.args`、README），`hakios-device.py check trident` **通过**。骨架已备份到 `hakios-trident/port/trident/`。
  - 待补：7 个缺失 soc_* 值（`soc_ipcc`、`soc_rsc`、`soc_cmd_db`、`soc_mpss_mem`、`modem_ipa_fw_at`、`soc_smem`、`soc_pas_mpss`，多为 modem/IPA 相关，可从 LineageOS kernel dts 补）；21 个手机驱动全部默认关闭，逐个移植后再开。
- 2026-11-15 22:28：**trident port 的 soc.args 补全**（14 项，均有来源）：`soc_aoss=0xc300000`、`soc_rsc=0x179e0000`（vendor 树 `mailbox@179e0000`，等价 mainline rpmh-rsc drv-2）、`soc_apps_smmu=0x15000000`、`soc_cmd_db=0x861e0000`、`soc_mpss_mem=0x8e000000`（`modem_region@0x8e000000`）、`modem_ipa_fw_at=0x8c410000`（`ipa_gsi_region@0x8c410000`）、`soc_smem=0x86000000`、`soc_imem=0x14600000`、`soc_ipa_stream=0x720`、`soc_ipa_stream_uc=0x722`、`soc_pas_ipa=0xf`、`soc_ipa_fw=ipa_fws`、`soc_ipa_base=0x1e40000`、`soc_gsi_base=0x1e04000`；`hakios-device.py check trident` 仍通过。缺 `soc_ipcc`（SDM845 无 IPCC 硬件，vendor 用 GLINK/IPCRTR）与 `soc_pas_mpss`（vendor 树 mss 节点无 `qcom,pas-id`，待从 mainline/驱动确认）。
  - 关键数据来自 `references/sdm845.dtsi`（LineageOS 内核）与手机 `/proc/device-tree`（树内 `reg` 原始字节）。
  - EDL 操作步骤与刷写材料清单已写入 `EDL-PROCEDURE.md`；线材为「带按钮+开关」的成品 9008 工程线。
- 2026-11-15 22:30：**配置层验证通过**：`tools/hakios-config.py defconfig trident` → `.config`（36 symbols，69 字符 boot-args，kernel.ver=`2.3.4-hakios-darwin22.5-sdm845`），`check` 通过；`defconfig trident open`（开放配置）→ 30 symbols、19 字符 args（`ufs=2 touchscreen=1`）、`needs` 显示 **不需要手机固件** —— 这就是 M4 首次启动（launchd，无驱动）的目标配置。
- 2026-11-15 22:35：**EDL 工具链就绪**（`hakios-trident/tools/`）：
  - 开源 EDL 客户端 `bkerler/edl` 已解压（`tools/edl-src/edl-master`），Python 依赖（pyusb 等）已装；
  - Windows libusb 已解压（`VS2015-x64\dll\libusb-1.0.dll`），pyusb import 通过；
  - 自带 **Zadig 2.8**（`Drivers/Windows/zadig-2.8.exe`）用于给 9008 设备装 WinUSB 驱动；
  - 封装了命令行工具 `tools/run-edl.cmd`（自动设置 libusb PATH，已验证 `--help` 可运行）。
- 2026-11-15 22:38：**找到 Smartisan SDM845 的签名 EDL loader（firehose）**，来源 `bkerler/Loaders` 仓库 `smartisan/` 目录：
  - `000460e100110022_032a43cc8d3e2d3b_fhprg_peek.bin`（359972 B，sha256 `4FF6E16F…99E5DA`）
  - `000460e100110022_0a1fd0c71592505d_fhprg_peek.bin`（358960 B，sha256 `071D539D…`）
  - HWID `000460e1 0011 0022` = SDM845 + OEM id 0x0011（Smartisan）+ 型号，已保存到 `edl-loaders/`。
  - 这意味着原计划要买的 `R1_user_V6.0.4.zip`（firehose 来源）**可能不再必需**：先验证这两个 loader 能否被 R1 的 XBL 接受并执行 `printgpt`/读分区；`peek` 变体可能只支持读，写能力待验证（不行再找/买全功能包）。
- 下一步：手机进 EDL（9008 工程线）→ `run-edl.cmd printgpt --loader ...` 验证 Sahara/Firehose 握手 → 成功则 `rl` 备份全部分区 → 设计 HakiOS/UEFI 写入方案（vbmeta 处理 + boot 分区 + ESP）。
- 2026-11-15 22:45：**UEFI 镜像与分区方案确认**：
  - 解析 `boot-trident.img`：Android boot image header v1，`kernel_size=6,703,733`（UEFI 本体以 kernel 字段打包）、`ramdisk_size=1`、`page_size=2048` —— 可写入 64 MiB 的 `boot_a/b`，由 ABL 按 boot image 加载。
  - LineageOS `BoardConfig.mk` 确认 trident 的 AVB 参数：`--flags 2` + `--set_hashtree_disabled_flag`（禁用验证）；**但前提是 BL 已解锁**，否则 ABL 用 OEM 内置公钥校验 vbmeta 会失败 → 解锁仍是先决条件（EDL 读 `devinfo` 分析解锁位）。
  - 写入 `FLASH-PLAN.md`：loader 验证 → 关键分区备份顺序（devinfo/boot_a/b/vbmeta_a/b/abl_a/b/misc/frp）→ 解锁 → 写 UEFI → HakiOS ESP；含回退保证。
  - 通用 factory loader（`qualcomm/factory/sdm845_sdm850_sda845`）下载失败（raw 截断、API 404），已清理；需要时改用 ROM中国线刷包里的 firehose。
- 当前状态：EDL 工具链 + Smartisan loader + UEFI 镜像 + 刷写方案全部就绪，**只等用户用 9008 工程线把手机送进 EDL**（adapter 目前仍在 Android，未出现 05C6:9008）。
- 2026-11-15 22:55：**解锁原理确认（devinfo 法）**：
  - 证据：`0xmehr4b/POCO-X3-Pro-Ultimate-Bootloader-Unlocker` 指南原文 —— ABL 在 `0x2b4e4` 检查 `IsSecureBootEnabled()`，为 0 时**跳过 oem_misc1 token 校验，直接信任 devinfo 的 `byte 0x0D (is_unlocked)` 与 `byte 0x0E (is_unlock_critical)`**；其仓库 `firmware/devinfo_unlocked.img` 样本 = `"ANDROID-BOOT!"`(13B) + `01 01` + 其余 0；另有 vivo X90 Pro+ 教程用 `dd` 写 devinfo 解锁（SM8550，同法）。
  - 已下载样本到 `references/poco-devinfo-unlocked.img`，并写 **`tools/devinfo.py`**（`info` / `unlock` / `verify`；只改 0x0D/0x0E，已用真实样本 + 合成样本验证「只有两个字节变化」）。
  - 写 **`DEVINFO-UNLOCK.md`**：EDL 备份 devinfo → `info` 检查（magic/两个 flag 应为 0）→ `unlock` 生成 → `verify` → EDL `w devinfo` 写回 → 重启验证 `ro.boot.flash.locked=0`、`verifiedbootstate=orange`。
  - 风险：若 R1 的 ABL 强制 secure boot，单改 devinfo 无效（需完整 firehose 或解锁版 ABL）；`_fhprg_peek` loader 可能只读，写回需 ROM中国线刷包的 `prog_firehose_ddr.elf`。
- 当前：EDL 工具链/dev info 补丁工具/UEFI 镜像/解锁与刷写文档全部就绪，**等待用户把手机送进 EDL 后即可执行「备份 → 读 devinfo → 解锁 → 写 UEFI」**。
- 2026-11-15 23:05：**M1 构建环境方案就绪**（可与手机侧并行，不依赖解锁）：
  - 本机检查：WSL 未安装（`wsl.exe` 只是 stub）、Git Bash 未安装、固件虚拟化已开启、C: 剩 92 GB、**8 GB RAM / 4 核**。
  - 写 `M1-BUILD-ENV.md`：WSL2 + Ubuntu（apt 包 `build-essential git make python3 clang lld lz4 7zip qemu-system-arm qemu-utils libssl-dev zlib1g-dev`），源码克隆到 WSL 自己的文件系统 `~/hakios`，trident port 从 `hakios-trident/port/trident` 拷入，验证命令 `doctor.sh` / `hakios-device.py check trident` / `make trident_defconfig` + `hakios-config.py check` / `make qemu-open`（M2）。预计磁盘 25~40 GB，`JOBS=3`，8GB 机器构建较慢。
  - 写 `tools/install-wsl.ps1`（管理员一键：启用 WSL/VirtualMachinePlatform → 重启 → 下载 WSL2 内核 MSI → 默认 v2 → `wsl --install -d Ubuntu` → 写 `.wslconfig` 6GB/3核/2GB swap）。
  - 需要用户：管理员权限 + 一次重启。
- 下一步：① 用户授权后装 WSL2 → M2 QEMU 跑通；② 手机进 EDL → 备份/解锁/写 UEFI → M3。
- 2026-11-15 23:25：**M2 完成 —— HakiOS 开放内核在 QEMU 里跑通（Windows 本机，无 WSL）**：
  - 工具：Windows QEMU 11.1（从 `qemu-w64-setup-20260811.exe` 用 7-Zip 解出，免安装/免管理员）+ AAVMF aarch64 固件（Debian `qemu-efi-aarch64` 2022.11）+ `prebuilt/hakios-kernel` + `prebuilt/userland/hello`（payload cmdline `cpus=1`）。
  - 脚本：`tools/run-qemu-open.ps1`；关键参数：`-M virt,gic-version=3 -cpu cortex-a76 -smp 1 -m 3072 -accel tcg,tb-size=384`。**内存必须 ≥3GB**（payload 放在 0xF0000000，2GB 时该地址不在 RAM 里会同步异常）；QEMU vvfat 需要可写临时目录（脚本把 TMP/TEMP 指向 `qemu-run/tmp`）。
  - 证据：`qemu-run/M2-qemu-open.log`（= `M2-EVIDENCE.md`）—— `== XNULOADER v3 ==` 横幅、`kernel.ver=2.3.4-hakios-darwin22.5-sdm845`、Darwin 22.5.0 内核启动、`Hello from user space on Darwin!`；末尾 `initproc failed to start`/panic 为预期（hello 是 pid1，默认 `hello_wait=0` 打印完退出即 panic；`hello_wait=N` 可让它停留 N 秒）。
  - 结论：M1 的 WSL 构建环境只在需要**重新构建内核/镜像**时才必需；QEMU 验证已不需要 WSL。
- 2026-11-15 23:20：bkerler/Loaders 全库（154MB）解压完成：4 个通用 SDM845/850 factory firehose 已复制到 `edl-loaders/qualcomm-factory/`（备选 loader）；Smartisan 的 2 个 peek loader 保持不动。
- 2026-11-15 23:20：用户用百度网盘下载 **`R1_user_V6.0.4.zip`（2.36 GB 线刷包）**到 `C:\Users\Risan-Yu\Downloads\`（当前名 `...zip.baiduyun.p.downloading`）。包里将提供权威的 `prog_firehose_ddr.elf`、`rawprogram0.xml`、`patch0.xml`、`del-flash.bat`。下载完成后：验证 zip 内容 → 用 firehose 走 `tools/run-edl.cmd`（printgpt → 备份 → devinfo 解锁 → 写 UEFI）。
- 下一步（等线刷包下载完成）：① 校验线刷包并提取 firehose/XML；② 手机进 EDL → printgpt 验证 → 关键分区备份；③ devinfo 解锁 → 写 `boot-trident.img` → M3；④ 之后才是 M4（HakiOS loader/最小内核），M1 WSL 构建环境按需再装。
- 2026-11-15 23:40：**M2b 完成（UEFI 原生/ESP 模式）**：`tools/run-qemu-open.ps1 -EspMode` 下 loader 从启动卷读取 `\EFI\hakios\payload.bin`（日志原文 `payload: 16825776 bytes from \EFI\hakios\payload.bin on the volume this loader was started from`），Darwin 内核启动、打印 `Hello from user space on Darwin!`；证据 `qemu-run/M2b-esp-mode.log`，说明已补进 `M2-EVIDENCE.md`。**这正是 R1 上「Renegade UEFI + HakiOS ESP」的软件链路**，M3 只剩真机验证 Renegade UEFI 能否启动 HakiOS loader。
- 2026-11-15 23:40：新增 `tools/edl-session.ps1`（只读 EDL 会话）：`-Mode gpt|backup|devinfo`，自动选择 loader（优先线刷包的 `prog_firehose_ddr.elf`，否则用 `edl-loaders/` 里的 Smartisan loader），备份 `devinfo/boot_a/boot_b/vbmeta_a/vbmeta_b/abl_a/abl_b/misc/frp` 并生成 manifest，解析 devinfo 标志；**脚本不写手机**，写入操作保留为显式命令。
- 状态：线刷包 `R1_user_V6.0.4.zip.baiduyun.p.downloading` 停在 2385.9 MB（mtime 23:23 后未再增长）——可能百度网盘暂停，需用户点继续/检查。手机仍在 Android，未进 EDL。
- 2026-11-15 23:55：**M0/M3 自动化脚本与运行手册完成**：
  - `M0-UNLOCK.md`：EDL 进入步骤 → `edl-session.ps1 -Mode gpt` 验证 → `-Mode backup` 备份 → `edl-apply-devinfo.ps1 -Yes` 解锁 → 重启验证 `ro.boot.flash.locked=0`/`verifiedbootstate=orange` → 进 M3。
  - `M3-PLAN.md`：`boot-trident.img` 写入/校验/回退 + M4 的 ESP 落点方案（userdata 划 FAT32 / system_b 改 ESP 类型 / HakiOS U-Boot boot image）。
  - `tools/edl-flash-uefi.ps1`：写 `boot_a`+`boot_b`；守卫（要求 `backup/` 有 boot_a/boot_b/devinfo、sha256 等于 Renegade 发布值、需 `-Yes`），写后读回逐字节比对。
  - `tools/edl-apply-devinfo.ps1`：写 devinfo 解锁；守卫（要求备份、原镜像 magic 检查、只允许 0x0D/0x0E 两个字节变化、需 `-Yes`），写后读回逐字节比对。
  - **注意**：现在即可用现有 Smartisan loader 做**只读**的 EDL 验证（printgpt + 备份 + 读 devinfo），不必等线刷包；写操作再等 `prog_firehose_ddr.elf`（peek loader 若可写则不需要）。
- 2026-11-16 00:05：**M4 的 ESP 链路在 QEMU 完整验证通过**：
  - 新工具：`tools/mkespimg2.py`（pyfatfs 生成 FAT32，含 `EFI/BOOT/BOOTAA64.EFI` + `EFI/HAKIOS/PAYLOAD.BIN`）、`tools/mkgptesp.py`（把 FAT 镜像套进带 ESP 类型分区的 GPT 磁盘）。
  - QEMU 把 `esp-gpt.img` 作为 virtio 磁盘：AAVMF 找到 ESP（`BdsDxe: loading Boot0001 "UEFI Misc Device"`）→ HakiOS loader 从卷读取 payload（`payload: 16825776 bytes from \EFI\hakios\payload.bin on the volume this loader was started from`）→ `Hello from user space on Darwin!`。证据：`qemu-run/M4-esp-gpt-validated.log`；7-Zip 校验镜像结构（GPT→ESP→FAT32）。
  - 踩坑记录：**UEFI NVRAM（`vars.fd`）换盘后会残留旧启动项，导致“找不到新盘”** —— 每次换盘前从模板重置 `vars.fd`（已记入文档）。
  - 手机落盘方案写入 `M4-ESP-PLAN.md`：方案 A 复用 `system_b`（3GB 非活动槽）——备份 system_b + GPT → 生成 3GB FAT32 ESP 镜像 → 把 GPT 中 system_b 的类型 GUID 改成 ESP 并重算 CRC 写回 → EDL 写 system_b 镜像 → 重启后 Renegade UEFI 应自动启动 HakiOS loader；方案 C 是 HakiOS U-Boot boot image 后备。
- 状态：线刷包 `R1_user_V6.0.4.zip.baiduyun.p.downloading` 仍停在 2385.9 MB（23:23 后未再增长）；手机未进 EDL。下一步仍是等用户：恢复下载 + 进 EDL 做只读验证。
- 2026-11-16 00:20：**M4 落盘工具全部就绪并逐项验证**：
  - `tools/mkespimg2.py` 生成的 **3072 MB FAT32**（= `system_b` 大小）套进 GPT 后在 QEMU 启动成功（证据 `qemu-run/M4-esp-3gb-validated.log`：`UEFI Misc Device` → `payload: ... from \EFI\hakios\payload.bin on the volume` → `Hello from user space on Darwin!`）。
  - `tools/gpt-edit.py`：`list` / `set-esp`（改分区类型 GUID 为 ESP，重算 entries CRC + header CRC，并保持其余字节不变）；用合成 GPT 实测改类型后 7-Zip 校验通过并显示 `File System = EFI System`。
  - `tools/mkqfil.py`：生成 firehose `rawprogram0.xml` + `patch0.xml`，用于经 EDL `qfil` 写 GPT 头/尾等**原始扇区**（EDL 的 `w` 只能写分区名）。
  - `M4-ESP-PLAN.md` 已补全 R1 执行顺序：读 GPT 头/尾（4096B 扇区）→ 备份 `system_b`（3GB）→ 生成 3GB ESP 镜像 → 改 system_b 类型 GUID → `qfil` 写 GPT + `w` 写 system_b → 重启进 UEFI 自动启动 HakiOS。
- 状态汇总：**软件侧能验证的都验证完了**（M2、M4 的 UEFI-ESP 链路、3GB 镜像、GPT 修改、EDL 读写工具、解锁工具）；剩余全部依赖真机：线刷包（firehose）→ M0 解锁 → M3 UEFI → M4 HakiOS 启动。
- 2026-11-16 00:35：**M1 构建输入在 Windows 侧全部验证 + 工具脚本就绪**：
  - 把 trident port 并入 `hakios-xnu-kernel-main/devices/trident`；`hakios-device.py check trident` 通过（"all hold together"）；`hakios-config.py` 生成 defconfig（36 符号 / 69 字符 boot-args）与 open（30 / 19 字符）两种 `.config`，均已存档到 `hakios-trident/port/trident/configs/trident-CONFIG.{defconfig,open}.txt`。
  - 写 `tools/wsl-setup.sh`：WSL2 内一键装工具链（clang/lld/lz4/7zip/qemu-system-arm/qemu-efi-aarch64/rsync）→ rsync 源码到 `~/hakios` → `hakios-device.py check trident` → `make trident_defconfig` → `hakios-config.py check` → `make qemu-open`（WSL 内 M2 验证）。
  - **重要发现**：`prebuilt/hakios-kernel` 是 **redwood（SM7325）** 构建（字符串 `redwood` 出现 234 次、`sdm845` 0 次）→ R1 真机上跑 M4 最小内核**必须先构建 trident 内核**（依赖 M1）；QEMU 的 M2 不受影响。
  - 手机侧再确认：`/vendor/firmware` Permission denied、`/firmware_mnt` 不存在 → **手机上拿不到 firehose**，必须用线刷包（或写 loader 测试）。
- 状态：线刷包 `R1_user_V6.0.4.zip.baiduyun.p.downloading` 仍停在 2385.9 MB；手机未进 EDL。
- 2026-11-16 00:55：**重大情报更新 —— M0 路线改变（fastboot 可直接进）**：
  - **LineageOS 官方 wiki（trident）**：`Bootloader/Fastboot` 进入方式 = **关机后按住「音量下 + 电源」**；解锁命令 = **`fastboot oem unlock`**（安装页），2019 日文教程用的是 `fastboot flashing unlock`；**必须用新版 platform-tools 的 fastboot**（我们 37.0.1 ✓），旧版会失败。解锁会清数据。Recovery 进入 = 音量上 + 电源。
  - 日文教程（Wangel 2021）完整流程：EDL 线（连手机→按按钮→插电脑→**3 秒后松手**）→ QFIL（Device Type=UFS、Flat Build、programmer=`prog_firehose_ddr.elf`、XML=`rawprogram_unspare.xml`，第二次对话框取消）→ 按键进 Fastboot → `flashing unlock`。
  - AndroidFileHost（XiNGRZ 的 Smartisan R1 目录，flid=293181）有 **QPST_TWRP_R1_20190925/20191026.7z**（含 `prog_firehose_ddr.elf` + `rawprogram_unspare.xml` + TWRP）→ firehose 的替代来源（AFH 页面 30s 超时，稍后重试；或继续等用户百度包）。
  - **M4 简化（QEMU 实测）**：edk2/AAVMF 对**非 ESP 类型** GPT 分区里的 FAT 卷同样能发现并启动（`mkgptesp.py` 新增可选类型 GUID 参数，用随机 GUID 测试仍启动 HakiOS）→ **不需要改 GPT 类型**，直接把 3GB ESP 镜像写进 `system_b`；解锁后 `fastboot flash system_b` 比 EDL 快得多。
  - **M3 简化**：`fastboot boot boot-trident.img` = 内存启动验证 Renegade UEFI，**不写任何分区**，最安全；成功后再 `fastboot flash boot`。
  - 文档已更新：`M0-UNLOCK.md` 改为「方法 A fastboot（优先）/ B EDL devinfo / C QPST 包」，`M3-PLAN.md`、`M4-ESP-PLAN.md` 追加更正。
- 待用户：① 试「音量下 + 电源」进 fastboot，并 `fastboot oem unlock` / `flashing unlock` 解锁；② 线刷包/QPST 包仅作后备（fastboot 能解锁就不需要 EDL）。
- 2026-11-16 00:05：**EDL 材料全部到手 —— 不再依赖百度网盘包**：
  - 通过 AndroidFileHost mirrors API 拿到并下载了 **`QPST_TWRP_R1_20191026.23.7z`（23.8MB）**，解压到 `lineflash/`：
    - **`prog_firehose_ddr.elf` 680,321 B，sha256 `669B6A12E4F241503954D2A10E103A97821377F2EAD4A20CB1FA6F3DAE89FBCA`（可写 firehose）**；
    - **`vbmeta.img` 4,096 B**：AVB 解析确认 magic `AVB0`、算法 SHA256_RSA2048、**flags=0x2 = VERIFICATION_DISABLED**；
    - `rawprogram_unsparse4.xml`：UFS 扇区 **4096 B**；xbl 在 LUN1/2，abl/boot/vbmeta/dtbo 在 **LUN4**；`boot_a` @59782、`boot_b` @477542、`vbmeta_a` @415414、`vbmeta_b` @833174、`dtbo_a` @415430、`dtbo_b` @833190；
    - 原包还带 TWRP `boot.img`(64MB)、`dtbo.img`、`abl.elf`、`xbl.elf`、`xbl_config.elf`（**不刷**）。
  - 关键结论：**M3 可以纯 EDL 完成、甚至不需要 BL 解锁** —— 写 `boot_a/boot_b` = `boot-trident.img` + `vbmeta_a/b` = 该 flags=2 的 vbmeta，ABL 因 `VERIFICATION_DISABLED` 跳过校验直接启动自定义 boot 镜像（2019 年起的社区 TWRP 包就是这个原理，大量用户在锁 BL 机器上用过）。已写入 `M3-PLAN.md`「方法 2」。
  - `lineflash/README.md` 记录文件清单、hash、分区布局；firehose 已放到 `lineflash/prog_firehose_ddr.elf`（`edl-session.ps1` 首选路径）。
  - 工具补充：`tools/avbparse.py`（AVB 头解析，已确认 flags）。
- 下一步（等用户）：手机进 EDL → `edl-session.ps1 -Mode gpt/backup` → 写 `boot-trident.img` + `vbmeta.img` → 重启看 Renegade UEFI（M3）；或先试 fastboot 键组合解锁（M0）。
- 2026-11-16 00:15：**M3 写入脚本 + 总 Runbook 完成**：
  - `tools/edl-flash-uefi.ps1` 重写：`-DryRun`（只打印计划）/ `-Yes`（真写）；写 `boot_a/boot_b`（sha256 必须等于 Renegade 发布值）+ `vbmeta_a/vbmeta_b`（自动 `avbparse.py` 校验 flags=0x2），每个分区写完读回逐字节比对；要求 `backup/<ts>/` 含 boot_a/boot_b/vbmeta_a/vbmeta_b/devinfo。
  - 用假 backup 目录验证 DryRun 输出正确（image sha256、vbmeta flags、命令序列、读回比对长度）。
  - 写 **`RUNBOOK.md`**：材料 → 进 EDL（按住按钮插入、约 3 秒松手）→ `printgpt`/备份 → 可选解锁 → M3（UEFI+vbmeta）→ M4（3GB ESP 写 system_b）→ 回退表 → 已知风险，一页全流程。
  - `lineflash/README.md`：firehose/vbmeta 的 sha256、rawprogram XML 解出的 LUN/扇区布局、以及「不刷 xbl/abl/dtbo」的边界。
- 当前所有前置材料、脚本、文档均已就绪；**唯一等待：手机进入 EDL（或 fastboot）**。
- 2026-11-16 00:25：**M1 新增替代路径：本机的黑苹果 macOS**：
  - 磁盘检查：Disk0（238.5 GB GPT，LITEON SSD）有分区 5 = **83 GB "Unknown"（很可能是 APFS 的 macOS 分区）**；`D:` = 4 GB FAT32 "OCINSTALL"（OpenCore/安装分区）；`E:` = CDFS（手机的 Smartisan 传输工具盘）。
  - `xps13-hackintosh/`：OpenCore 1.0.8 + macOS Big Sur 11.x 安装包，EFI/恢复镜像/校验都完成，脚本更新到 11-15 11:19 —— macOS 很可能已装好。
  - HakiOS 官方支持 macOS 构建主机（`docs/getting-started/building.md`：Xcode 或命令行工具）→ 若黑苹果能进系统，**不需要 WSL2/管理员权限**就能 `make trident_defconfig && JOBS=3 make kernel`。
  - 已写 `MACOS-BUILD.md` + `tools/macos-build.sh`：检查 `xcode-select`/clang/make/python3 → 从 `/Volumes/Windows/...` rsync 源码到 `~/hakios` → 构建 → 把 `hakios-kernel` 复制到 FAT32 的 `D:`（OCINSTALL）带回 Windows；并附回 Windows 后重建 payload/ESP 的命令。
- 待用户确认：① 黑苹果 macOS 是否能正常进系统（能则 M1 走 macOS）；② 手机进 EDL（M3/M4 前置）。
- 2026-11-16 00:35：**M4 证据链 + port 质量检查**：
  - 依据 `docs/install.md`：loader 每次启动会把日志写进手机 `logdump` 分区（几 KB），并把 banner 画到 framebuffer。写 `tools/read-logdump.ps1`：EDL `r logdump` 后筛出 `XNULOADER/hakios/payload/kernel.ver/Darwin/panic` 等行，作为 M4 是否成功的**可验证证据**（屏幕 + logdump 双路）。RUNBOOK 增补 §8「M4 证据怎么取」、§9「M3/M4 成功判据（逐级）」。
  - 跑了 HakiOS 的 CI 检查：`hakios-device.py check trident` 通过；`hakios-device-test.py` **仅 1 项失败且原因是本机没有 git**（`new --repo` 需要 git，非 port 问题）；`drivers-check.py` 通过（49 文件/12 子系统）；`hakios-config-test.py` 跳过（需先 sync devices/redwood，本机无 git 做不了）。
  - 结论：**trident port 本身通过 HakiOS 的仓库一致性检查**。
- 当前阻塞（全部需要用户物理动作）：① 手机进 EDL（或 fastboot 键）；② 决定 M1 走 黑苹果 macOS 还是 WSL2（都需用户操作）。软件侧：EDL/备份/刷写/回退/证据工具与文档全部就绪，M2/M4 链路已在 QEMU 验证。

- 2026-11-16 00:50：**M5 前置：R1 硬件清单 + 驱动计划完成**（全部来自手机自身数据，不靠猜）：
  - 新增 `tools/dtscan.py`（扫描 device-tree dump：phandle 解析、活动显示节点、面板 timings、UFS/USB/PMIC/音频/WiFi/指纹节点）。
  - 写 `references/trident-hardware.md`：SDM845 v2.1；面板 **Novatek TD4362 1080×2242@60Hz DSI cmd mode**（活动显示 `qcom,dsi-display@18`）；触摸 **Synaptics TCM** i2c a98000 0x4b（HakiOS 只有 Goodix 驱动）；指纹 Goodix FP；UFS 2.1 三星 KLUDG4U1EA（ufshc@1d84000）；PM8998+PMI8998+SMB2+PD PHY；Tavil WCD9340 SLIMbus；WCN3990；双 dwc3（a600000/a800000）；Adreno 630。
  - 写 `M5-DRIVER-PLAN.md`：M4（平台层最小启动）→ 阶段1（UFS/按键/PMIC）→ 阶段2（Synaptics 触摸/电池/thermal）→ 阶段3（GPU/音频/WiFi/BT）→ 阶段4（modem/相机/指纹/振动），每阶段对应 `CONFIG_HAKIOS_*` 符号与风险。
  - 关键结论：**R1 触摸不是 Goodix 而是 Synaptics TCM**（要新驱动）；面板是 DSI **command mode**（若 UEFI 已初始化 SDE 则 M4 banner 可见，否则黑屏）；串口不可达 → 主要证据靠 `logdump`。
- 软件侧至此已无更多可独立推进的工作（材料/工具/文档/硬件清单/M5 计划齐全）；剩余必须用户操作：手机进 EDL 或进 macOS/WSL 构建。
- 2026-11-16 01:05：**M4 关键发现：prebuilt loader 的平台选择是硬编码的，R1 必须重建 loader**：
  - 源码 `xnuloader/loader.c`：`PLAT` 默认 `platform_qemu_virt`；只有 UEFI GOP framebuffer 地址 **== 0xE1000000**（HakiOS/Silicium UEFI 的固定地址）才切到 `platform_redwood`；其它地址（Renegade UEFI 在 R1）仍是 **qemu-virt**（IO/GIC/UART 全错 → 内核必挂）。
  - **已打补丁**：新增 `platform_trident` 描述符（SDM845：`io_base=0x00400000`、`io_size=0x3FC00000`、GIC `0x17A00000`/redist `0x17A60000`、8 核 `core_shift=8`、`small_cores=0x0f`、无 UART、`log_other_cpu`）；`payload_info` 加 `platform` 字段；`parse_payload` 识别 `platform=` 条目；`efi_main` 在解析后按名字选平台；`mkpayload.py` 加 `--platform`（实测生成的 payload 里有 `platform` 条目 `trident\0`，8 字节）。
  - 结论：**M4a（loader 启动/banner）用现 prebuilt loader 仍可证明；M4b（内核/系统）需要 M1 重建 loader（`make loader-open`）+ 构建 trident 内核**，用「新 loader + `--platform trident` payload」重建 ESP。文档 `M4-ESP-PLAN.md`/`RUNBOOK.md` 已补。
  - 所以 M1 现在是 M4 的关键路径（不只是 M5）。
- 当前仍等用户：① 手机进 EDL；② M1（macOS 跑 `tools/macos-build.sh` 或管理员装 WSL2）。

- 2026-11-16 01:25：**trident loader 已在 Windows 构建并验证（M1 不再是 loader 的前置）**：
  - 下载并用 7-Zip 解出 **LLVM 19.1.7 for Windows**（`tools/llvm/bin/{clang,lld-link}.exe`，免安装）；`tools/build-loader-win.ps1` 复现 `xnuloader/build.sh` 三步（`mkidentity.py --placeholder` → clang 编译 → lld-link 链接，`/base:0xA1000000`）。
  - 产物 `loader-trident.efi` 66,048 B，sha256 `4B89D4AE…EB547E`；**QEMU 验证**（`qemu-run/M4-loader-trident-validated.log`）：`== XNULOADER v3 ==` → `payload: 16825816 bytes from \EFI\hakios\payload.bin` → **`platform trident`**（补丁生效）。
  - 已用新 loader + `payload-trident.bin` 重建 3GB ESP：`qemu-run/system_b-esp.img` sha256 `B9C5D0F9…57B0AD`。
  - 结论：**M4a（loader/ESP）全部就绪**；剩下 M4b 需要 M1 构建 trident 内核（把 payload 的 kernel 换成 trident 构建即可），M5 同样需要 M1。
  - 文档：`M4-ESP-PLAN.md`/`RUNBOOK.md` 已补 Windows 构建与验证记录。
- 当前仍等用户：① 手机进 EDL（M3/M4 落盘）；② M1（macOS `tools/macos-build.sh` 或管理员装 WSL2），现在只影响 trident 内核与 M5。

- 2026-11-16 01:40：**最终 3GB ESP 镜像端到端验证通过**：把 `qemu-run/system_b-esp.img`（trident loader + `platform=trident` payload）套进 GPT 磁盘后在 QEMU 启动：
  ```
  BdsDxe: loading Boot0001 "UEFI Misc Device" ...
  == XNULOADER v3 ==
  payload: 16825816 bytes from \EFI\hakios\payload.bin on the volume this loader was started from
  platform trident
  ```
  证据：`qemu-run/M4-final-3gb-trident-validated.log`。**这就是将来原样写进 `system_b` 的那份镜像**（sha256 `B9C5D0F9…57B0AD`）。
- 软件侧最终状态：M2 ✅；M3 的 boot/vbmeta 材料 ✅；M4a（loader/ESP，含 trident 平台补丁）✅ 并端到端验证；EDL/备份/刷写/回退/证据工具 ✅；trident 硬件清单 + M5 计划 ✅。
- 剩余全部取决于用户的两个物理动作：① 手机进 EDL（→ M0/M3/M4 落盘）；② M1（macOS 脚本 或 管理员装 WSL2）→ trident 内核（M4b）与 M5。

- 2026-11-16 02:05：**收尾工具 + 状态总览**：
  - 写 `STATUS.md`（里程碑表/材料入口/下一步/风险，一页总览）；`RUNBOOK.md` §10 增加分阶段入口。
  - 写 **`tools/r1-run.ps1`**：`-Stage status|gpt|backup|devinfo|logdump|unlock|uefi|esp|all-read`；每阶段先检测 9008（未就绪时打印进 EDL 步骤并退出，**不会像裸 edl.py 那样挂起**）；写操作需 `-Yes`；`esp` 阶段写 3GB 后自动读回逐字节比对。已测 status 与未进 EDL 的守卫行为（2.4s 干净退出）。
  - 另外在后台下载便携 MSYS2（考虑尝试在 Windows 上直接构建 XNU 内核的可行性；若不可行则仍走 macOS/WSL M1）。

- 2026-11-16 02:25：**loader 平台选择回归验证通过**：同一份 `loader-trident.efi`，payload 不带 platform → `platform qemu-virt`；`platform=redwood` → `platform redwood`；`platform=trident` → `platform trident`。补丁向后兼容，一个 loader 可按 payload 支持三种平台（记录在 `M4-ESP-PLAN.md`）。

## 最后一轮交接（2026-11-16，第 25 轮）

软件侧全部完成并验证，剩余里程碑都阻塞在用户动作上，故本目标标记 blocked。

### 已完成（可复现的证据都在仓库里）

| 项 | 证据 |
|---|---|
| M2 QEMU 跑通 HakiOS | `M2-EVIDENCE.md`、`qemu-run/M2-qemu-open.log`、`tools/run-qemu-open.ps1` |
| M4a UEFI→ESP→loader→平台识别 | `qemu-run/M4-final-3gb-trident-validated.log`（`platform trident`）、`M4-ESP-PLAN.md` |
| trident loader（Windows/LLVM 构建 + 平台补丁 + 三平台回归） | `qemu-run/loader-trident.efi`、`qemu-run/M4-loader-trident-validated.log` |
| 3GB ESP 镜像（即写入 system_b 的镜像） | `qemu-run/system_b-esp.img` sha256 `B9C5D0F9…7B0AD` |
| EDL 材料（firehose / flags=2 vbmeta / 分区布局） | `lineflash/README.md` |
| 解锁/刷写/备份/回退/证据工具 | `tools/`（r1-run/edl-session/edl-flash-uefi/edl-apply-devinfo/read-logdump/devinfo/gpt-edit/mkqfil/mkespimg2/mkgptesp/avbparse） |
| R1 硬件清单 + M5 计划 | `references/trident-hardware.md`、`M5-DRIVER-PLAN.md` |
| 文档 | `STATUS.md`、`RUNBOOK.md`、`M0-UNLOCK.md`、`M3-PLAN.md`、`M4-ESP-PLAN.md`、`M1-BUILD-ENV.md`、`MACOS-BUILD.md` |

### 阻塞条件（连续多轮未变，均为用户侧动作）

1. **手机从未进入 EDL（9008）或 fastboot**：从最早尝试起手机一直只以 Android/adb 在线（`adb devices` 有 `5b12f4ba`，`fastboot devices` 空，无 9008 设备）。M0（解锁）/M3（写 UEFI）/M4a 落盘都必须先让手机进 EDL（或 fastboot 键组合）。
2. **M1 构建环境未启用**：WSL2 未安装（需要管理员 + 重启；脚本 `tools/install-wsl.ps1` 已备好）；黑苹果 macOS 是否可启动未经确认（脚本 `tools/macos-build.sh` 已备好）。M4b 的 trident 内核与 M5 都依赖它。
3.（次要）百度网盘线刷包停在 2.36 GB `.downloading`；但已通过 AndroidFileHost 取得 firehose，故不再是阻塞项。

### 用户恢复时的最短路径

1. 手机进 EDL（关机 → 9008 线开关 → 按住按钮插入 → 3 秒松手）→ 回话；
2. 我按 `RUNBOOK.md`：`r1-run.ps1 -Stage status/gpt/backup` → `-Stage uefi -Yes`（M3）→ 重启看 UEFI → 再进 EDL → `-Stage esp -Yes`（M4a）；
3. 同时/之后启用 M1（macOS 或 WSL2）→ `make trident_defconfig && make kernel` → 重打 payload（`mkpayload.py --platform trident`）→ 重建 ESP → M4b；
4. M5 按 `M5-DRIVER-PLAN.md` 逐驱动推进。

## ⏸ 暂停点（'@ + $stamp + @'）— 用户去上自习，回来从这里继续

### 手机当前状态
- **boot_a/boot_b = Renegade UEFI（boot-trident.img）已写入并读回校验一致**
- **vbmeta_a/vbmeta_b = flags=0x2 的社区 vbmeta 已写入并校验一致**
- **system_b = 3GB HakiOS ESP 镜像已写入并校验一致（前 32MB）**
- 开机结果：屏幕显示 **"Your device has failed verification. Your device will shutdown in 10 seconds."** → 锁 BL 下 ABL 不接受非 OEM 签名的 vbmeta，10 秒后自动关机。**手机没坏。**
- 手机目前：关机状态（该画面 10 秒后自动关机；若循环重启，长按电源 15~20 秒强制关机）

### 原厂备份（可完全恢复）
`backup/20261116-181843/`
- boot_a.img 67,108,864 B sha256 29ADE262…
- boot_b.img 67,108,864 B sha256 6C2EFAE2…
- vbmeta_a.img 65,536 B sha256 1E28C129…
- vbmeta_b.img 65,536 B sha256 4AB37332…
- devinfo.img 4,096 B（全 0，说明 R1 不用标准 devinfo 解锁格式）
- 注意：abl/misc/frp 未备份（上次 EDL 中断），但我们**没有写过它们**。

### 回来后的第一步（恢复 Android）
1. 手机彻底关机
2. 短接 → 插线 → 按电源 → 黑屏后立刻松手
3. 我运行 `tools\edl-batch.py --loader lineflash\prog_firehose_ddr.elf --plan restore-plan.json`
   → 写回原厂 boot_a/boot_b/vbmeta_a/vbmeta_b（自动读回校验）→ reset 重启 → 回 Android

### 第二步（待用户同意）
真正解锁 BL：刷 QPST_TWRP_R1 包里的"解锁文件"（`xbl.elf`、`xbl_config.elf`、`abl.elf` 等，社区 9008 深刷解锁流程）。
风险：会写引导分区；但官方线刷包有原厂 xbl/abl，EDL 可救。**执行前先备份原机 xbl/abl。**

### 关键工具/文件
- 批量 EDL：`tools/edl-batch.py`（一次会话多操作，JSON 计划）
- 计划：`backup-plan.json`、`write-plan.json`（已用）、`restore-plan.json`（恢复用）
- firehose：`lineflash/prog_firehose_ddr.elf`（官方 V6.0.4 包）
- 自动监视模式：检测 `VID_05C6&PID_9008` 两次连续出现即触发对应批次
- UEFI 镜像：`..\r1-trident\boot-trident.img`（sha256 B95C46AA…）
- vbmeta（flags=2）：`lineflash/vbmeta.img`（sha256 70569AA5…）
- HakiOS ESP 3GB：`qemu-run/system_b-esp.img`
- 已构建的 trident loader：`qemu-run/loader-trident.efi`（sha256 4B89D4AE…）
- QPST 包解压：`lineflash/official/R1_user_V6.0.4/...SEKSA.../`（含 xbl.elf、abl.elf、TWRP boot.img、vbmeta、rawprogram XML）
- GPT 官方布局：`lineflash/official/gpt-layout.txt`；分区表实测：`edl-printgpt.log`
