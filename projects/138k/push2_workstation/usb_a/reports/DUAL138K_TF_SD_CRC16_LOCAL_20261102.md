# Task3：真实 TF 数据 CRC16 的局部实现与 wire 验证

本阶段为维护中的 TF 直读链增加显式选择的 SD 数据 CRC16 检查，保留原 SPI payload、两个 CRC 字节和 CS 高释放的完整排空。四层 `VERIFY_DATA_CRC` 均默认 `0`；本阶段没有改 top/profile 的选择、FAST12 分频或音频全局复位，也没有把本结果标为整机 TF 播放验收。后续 DIRECT 候选必须显式选 `1`、纳入新 checker 并生成新的来源身份。

## 行为与来源

真实 session 的索引 `513..2` 对应 512 个 payload 字节，`1`、`0` 对应 CRC 高、低字节。新 checker 以 `0x1021`、初值 0、MSB-first、无最终 XOR 计算 payload CRC，同时检查严格递减顺序。每个实际接受的新 sector 请求清除旧 verdict。sector owner 仅在原 `spidone` 应用 verdict：正确时沿用原 `done`；错误或不完整时进入 sticky `read_error` / code `3` / `FAULT`，无成功 `done`、无自动重放。既有 R1/token 错误码不变。

STOP 仍由真实 file owner 接受，立即阻断文件输出和新数据请求，等在途 payload、CRC 和 CS 释放后才终结。CRC 错误期间 STOP 必须走失败终态，不能返回成功取消 ACK。恢复仍需显式复位 direct-native/file owner、重新挂载和新请求；本阶段没有新增整机公共 remount 命令，也没有借取消复位基础音频采样链。

保留 sector/file 两份原 provenance manifest、vendor 和冻结输入的原字节。新增 `workstation_tf_sd_crc16_v1.adaptation.json` 独立记录四层精确可逆修改，helper 在内存中还原原来源并核对旧 derivation，再正向重建校验当前来源；生产仍直接使用维护源码，没有历史私有输入回退。旧 sector/file wire runner 只有显式 `--direct-crc-source-adaptation` 才接受此来源链，DUT 仍为 CRC 默认关闭，旧假 CRC 不能成为新 CRC 验收证据。原注释中的“CRC drained, not checked”对应默认关闭分支。

## 验证结果

| 验证范围 | 通过结果 | 本地证据 |
| --- | --- | --- |
| 来源链与 fail-closed | 3 个 unittest；12 个内存来源漂移负控全部拒绝 | `~/.cache/gw138k-task3-20261101/crc16-source-provenance-v1.json` |
| 旧默认 sector wire | 10 个正常场景及 11 个预期拒绝，原完整矩阵通过 | `crc16-default-sector-retention-v1/verification.json` |
| 旧默认 file wire | FAT16、FAT32、空目录、非法曲目及两种 transport failure，共 6 个选定场景通过 | `crc16-default-file-retention-v1/verification.json` |
| 新 CRC 真实 SPI wire | 10 场景及 4 个破坏性源码负控通过 | `tf-sd-crc-wire-v2/verification.json`、`verification.seal.json` |
| CRC 与真实 STOP 链 | 8 场景及 2 个破坏性源码负控通过 | `tf-sd-crc-stop-wire-v2/verification.json`、`verification.seal.json` |

表中后四行相对上述 cache 目录。wire seal 独立读取每例真实编译的 VVP，检查唯一 controller/session；CRC 开启时检查唯一 checker，显式默认关闭时不生成 checker。输入在运行前后以及阶段封存时哈希一致。原始试验、失败日志及 v1 证据保留。

新 sector 场景以 Python `binascii.crc_hqx(payload, 0)` 作独立 oracle，包含已知答案、pattern/全零/全 FF、SDv1/SDv2、FAST12、payload 位错、CRC 高字节错、低字节错、CRC 时隙 pull-up FF，以及显式默认关闭兼容。4 个源码负控分别破坏多项式、reset/clear 初值、一个 payload 字节参与和 CRC 比较，均由真实 wire verdict 断言拒绝。

STOP 通过 direct-native → file → sector → session 的真实 FAT/WAV/SPI 链，在 payload 末端、CRC 高/低字节及 CS 释放前四阶段分别测试正确/错误 CRC。正确 CRC 均只出现一次 cancelled 和 completed，错误 CRC 均只出现一次 stop_failed、sticky file_error，无成功 ACK/EOF。终态前核对完整 `512+2` 字节及至少 8 个 CS 高 clocks，终态后无额外 CMD17；显式恢复后逐帧核对 97 个真实 PCM 帧和新 generation/LAST。两个负控分别绕过 CRC 比较和移除 STOP 等待排空，均被断言拒绝。

协调者另在当前树独立确认 provenance 3 tests、`test_current_workstation_sources.py` 17 tests、TF policy 7 tests 和 diff 检查通过；这属于来源及局部回归证据，不扩大本阶段的物理验收范围。

## 精确文件清单

以下路径相对 `projects/138k/push2_workstation/usb_a/`。前 16 个是本阶段代码、契约和必要测试依赖；本报告是第 17 个文件。协调者负责与 W full-profile 依赖共同提交、推送及更新 `task3.md`。

| 文件 | 状态/用途 |
| --- | --- |
| `rtl/tf_audio/storage/workstation_tf_sd_sector_reader.sv` | 修改；默认关闭、按原完成边界应用 CRC verdict |
| `rtl/tf_audio/storage/workstation_tf_file_reader.sv` | 修改；转发显式参数 |
| `rtl/tf_audio/workstation_tf_direct_native_v1.sv` | 修改；转发显式参数 |
| `rtl/tf_audio/workstation_tf_direct_runtime_service.sv` | 修改；转发显式参数 |
| `rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.sv` | 新增；第一方数据 CRC checker |
| `rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.adaptation.json` | 新增；独立可逆来源链 |
| `rtl/tf_audio/storage/WORKSTATION_TF_SD_CRC16_V1_CONTRACT.md` | 新增；默认、错误、排空与限制契约 |
| `tools/workstation_tf_sd_crc16_provenance.py` | 新增；精确来源 verifier |
| `sim/test_workstation_tf_sd_crc16_provenance.py` | 新增；来源回归及 12 个漂移负控 |
| `sim/tf_audio/run_workstation_tf_sd_sector_wire.py` | 修改；显式接受新来源链，旧默认矩阵不变 |
| `sim/tf_audio/run_workstation_tf_file_reader_wire.py` | 修改；显式接受新来源链，旧默认 DUT 不变 |
| `sim/tf_audio/workstation_tf_sd_crc_wire_card.sv` | 新增；真实 SPI 边沿与逐 sector 正确/损坏 CRC |
| `sim/tf_audio/tb_workstation_tf_sd_crc_wire.sv` | 新增；sector 完整排空及 CRC verdict 检查 |
| `sim/tf_audio/run_workstation_tf_sd_crc_wire.py` | 新增；独立 CRC oracle、场景及 4 负控 |
| `sim/tf_audio/tb_workstation_tf_sd_crc_stop_wire.sv` | 新增；真实 STOP 与恢复 PCM 检查 |
| `sim/tf_audio/run_workstation_tf_sd_crc_stop_wire.py` | 新增；四阶段好/坏 CRC 与 2 负控 |

综合封存：`~/.cache/gw138k-task3-20261101/crc16-local-stage-final-seal-v1.json`，SHA256 `8bf530e4b47baa5e87c34b5330b28597f4b5ffe2f87d9b978924e20e0d5037cb`。包含全部 16 个输入的精确 SHA256、原 provenance 重验和四套 wire 证据身份；它没有改写既有证据。

| 证据 | SHA256 |
| --- | --- |
| sector v2 verification | `f9bd2b4150bc1ee5744f38b987db4e85caca3ba284712bae0873232781521b12` |
| sector v2 seal | `24726b44583f7ae71192ba594fc87188d26343ca25b1e457a49d8da7e806f124` |
| STOP v2 verification | `c1e691156d4069f21266542049114b05b63bc7455769b7091cf6ed909ce7a1f1` |
| STOP v2 seal | `4428d2c6332b4e5bd625a5873b28b44747efc6b25dc837affc49147223e2bbfc` |

## 保留的实际缺口

payload 仍在 CRC 终判前流出，错误前缀可能已进入或被下游 PCM 消费；这是完整性检测与失败隔离，不是 validated-sector 原子发布，也不能证明坏样本从未发声。missing-CRC 仅验证两个已 clock 的 CRC 时隙读到 FF、且正确 CRC 为 B1CF 而非 FFFF；没有宣称所有物理缺失情形必被发现。

STOP 的连续 48 kHz 证据来自独立 TB phase accumulator 在 2000-clock parked interval 继续推进，不能替代整机基础合成调度或实际 DAC 声音验收。STOP 数据链用显式数字 SPI divider=2 加速场景；单 sector FAST12 CRC 正确也不代表持续供给通过。已知历史默认 FAST12 在 7790 帧后触发 supply underflow 的证据仍有效；不以修改 divider、prefill 或 cache 宣称解决。

本阶段无新综合/P&R、无位流、无板上 CRC/TF/时延证据。两块目标板未连接电脑；当前电脑连接板归另一分支使用，未操作。TF 实际在 M，反序 LCD 线与跨板流尚待测量。`release_ready=false`、`deployment_allowed=false`；未下载 SRAM 或写 Flash。
