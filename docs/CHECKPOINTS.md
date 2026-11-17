# 方法：没有串口和显示时，用 logdump + 检查点定位内核死点

## 为什么要这个

这台手机没有 UART 输出可用，显示控制台在启动早期还没初始化。内核一旦在 `bsd_init` 之前崩溃或挂死：

- 屏幕全黑，什么信息都没有
- panic 日志的缓冲区可能还没初始化（panic 时 msgbuf 为空，loader 只拿到 31 字节的 `--- kernel message buffer ---` 头）

第一次踩坑就发生在这里：内核"返回了"，但日志 0 字节。后来查清是内核在 `cpu_init` 里因为 CPU 拓扑查不到当前核而断言 panic，panic 早于日志缓冲区初始化。

## 它怎么工作

**数据通道（hakiOS loader 自带）：**

1. loader 把日志写进 `logdump` 分区（LUN4，LBA 881904..898287，64MB）。
2. PC 端用 EDL firehose 读回整个分区：`tools/edl-batch.py --plan edl-read-logdump.json`。
3. 日志里同时含 loader 日志和内核日志（以 `== KERNEL LOG ==` / `== END OF LOG ==` 分隔）。

**检查点（checkpoint）：**

HakiOS 的内核里有一套现成机制（`osfmk/arm64/start.s` 的 `LOADER_CHECKPOINT` 宏与 `osfmk/arm64/loader_return.c`）：

- 在源码里插入 `loader_checkpoint(N);`。
- 内核执行到那里时，如果"要停的检查点 == N"，就把当前日志（含 reason=2 / checkpoint 编号）交给 loader 的返回 stub，直接跳回 loader。
- loader 把结果写进 logdump，PC 读回后 grep `STOPPED AT CHECKPOINT (\d+)`。

于是：**命中 = 内核走到了这里；不命中 = 死在这之前**。在可疑区间上二分，几轮就能把死点缩到很小的范围。

**其他返回原因**（也都能从 logdump 分辨）：

| logdump 里出现 | 含义 |
|---|---|
| `STOPPED AT CHECKPOINT N` | 命中检查点 N |
| `EARLY KERNEL EXCEPTION: esr=… elr=… far=… lr=… sp=…` | 启动早期异常 |
| `kernel returned: log at …, N bytes` | 正常返回（`loader_return_after` 定时器 / panic / halt 路径） |
| `THE KERNEL HUNG on core X: no sign of life for 50 seconds` | loader 的看门狗判定挂死 |

## 使用要点（踩过的坑）

1. **每次跑之前清空 logdump**：热启动不清 RAM，logdump 里会残留上一次的日志，会让"内核返回 31 字节"这类判断被污染。做法：EDL 会话里先写 1MiB 全零到 logdump，再写 ESP。
2. **`ck_sweep` 默认命中即停**：想逐个扫描要一次只传一个检查点。
3. **检查点编号不要冲突**：HakiOS 自带的检查点（`start.s` 1..5、`arm_init` 10..21、`kernel_bootstrap` 99+）不要复用，我们扩展时用 47..64（内存/缓存）、99..134（kernel_bootstrap）、135..156（bsd_init）、160..168（IOFindBSDRoot）。
4. **构建命令**（WSL）：`make trident_defconfig JOBS=4 && make kernel JOBS=4`；退出码 2 是 kext symbol-set 检查的已知失败，产物仍会生成（见 `tools/make-kernel.sh`）。
5. **每个检查点一轮真机循环约 3.5~4 分钟**（EDL 写 48MB ESP + 回读校验占大头）。把校验字节数调小（`HAKIOS_VERIFY_BYTES=8388608`）可以明显提速。
6. **每轮结束手机会停在 EDL**：下一轮前先 `edl-batch.py --plan kernel/reset-plan.json` 复位，等 fastboot 回来。

## 检查点表（我们实际用过的）

| 编号 | 位置 |
|---|---|
| 1..5 | `osfmk/arm64/start.s`（VBAR/早期异常相关，HakiOS 自带） |
| 10..21 | `osfmk/arm/arm_init.c`（slide rebase、PE_init_platform、serial、kprintf、PE console、dram-base） |
| 47..50 | `osfmk/kern/timer_call.c`（timer_call_init 内部） |
| 51..58 | `osfmk/arm64/cpu.c`（cpu_init 内：assert/do_cpuid/do_mvfpid/do_cacheid） |
| 59..64 | `osfmk/arm/cpuid.c`（do_cacheid 内） |
| 98..99 | `osfmk/arm64/machine_routines.c`（machine_conf / machine_startup） |
| 100..134 | `osfmk/kern/startup.c`（kernel_bootstrap 与 kernel_bootstrap_thread） |
| 135..139 | `osfmk/kern/startup.c`（LOCKDOWN 段到 bsd_init 前） |
| 140..156 | `bsd/kern/bsd_init.c`（bsd_init 全流程与 mountroot 循环） |
| 160..168 | `iokit/bsddev/IOKitBSDInit.cpp`（IOFindBSDRoot 内部） |

## 结果

这一套把死点从"整个内核启动链"缩到：

- `cpu_init()` 里 `do_cacheid()` 第一行的 `ml_get_cpu_number_local()`（根因：MPIDR 映射错误）
- `bsd_init` 的 `IOFindBSDRoot()` → `waitForMatchingService()`（根因：定时器中断不来）

两个根因都修掉后，内核完整跑到 launchd 启动阶段。
