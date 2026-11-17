# NOTICE — 许可、来源与不含的内容

## 本仓库自身

- 本仓库中的**脚本、工具、文档、设备配置**（除明确来自第三方的部分）采用 **MIT License**，见 `LICENSE`。
- 补丁/修改若作用于 Apple XNU 或 HakiOS 上游源码，则该修改部分按上游许可发布：
  - **Apple XNU**：Apple Public Source License 2.0（APSL-2.0）
  - **HakiOS**（https://github.com/oosexgang/hackios-xnu-kernel）：内核补丁目录为 APSL-2.0，其余（loader、工具、脚本、设备层）为 MIT
- 所有 Apple 原始版权声明在其被修改的文件中保留，未作删除。

## 本仓库**不包含**

- 任何 Apple 的 XNU 源码副本、iOS IPSW、Apple 固件或 Apple 商标素材
- Smartisan 官方 ROM、系统镜像、GPT/分区表镜像、`prog_firehose_ddr.elf` 等厂商/高通私有文件
- 任何可用于绕过他人设备安全措施的工具或密钥
- 完整内核二进制（它由 Apple 源代码派生，请自行从上游源码构建）

获取上述材料请通过你合法拥有的设备与渠道。

## 第三方组件与参考

| 组件 | 用途 | 许可/来源 |
|---|---|---|
| HakiOS（oosexgang/hackios-xnu-kernel） | XNU/Darwin-on-Android 上游；loader、设备层 | MIT + APSL-2.0 |
| Renegade Project（edk2-porting） | SDM845 UEFI 固件（仅作为外部依赖使用） | 按其上游许可 |
| bkerler/edl | EDL（Sahara/Firehose）客户端 | GPL-3.0（外部依赖，未包含在本仓库） |
| dipper-xnu（youzjuzi） | 小米 8 的 SDM845 移植，GPU/用户态路线参考 | 按其上游许可 |
| Linux 内核 `drivers/clocksource/arm_arch_timer.c` | 内存映射定时器寄存器布局参考 | GPL-2.0（仅作参考，未复制代码） |
| pyfatfs | FAT32 镜像构建参考 | MIT（外部依赖） |

## 商标

"Smartisan"、"坚果"、"Apple"、"iOS"、"XNU" 等均为各自所有者的商标。本仓库与这些公司无隶属或背书关系，仅用于技术研究。

## 免责声明

本项目用于**在自己拥有的设备上**进行系统移植研究。按现状（AS IS）提供，不附带任何担保。刷机有风险，操作者自行承担设备损坏的后果。
