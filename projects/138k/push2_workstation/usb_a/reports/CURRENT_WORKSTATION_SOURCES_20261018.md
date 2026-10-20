# 当前整机入口的 CNN 输入核对

更新：2026-10-18。远程main与本地HEAD均为`abe43c7`。本次处理首批接口实施后遇到的`accepted CNN source drift`，沿用当前完整整机入口的full83基准。未修改CNN源码、DDR冻结文件、验收目录、引脚或硬件，未烧录。

## 原因与取用规则

`tools/build_current_workstation.py`原本复制full83完整暂存工程，再覆盖明确列出的整机控制文件。旧检查却以活动`rtl/music`的文件清单及哈希要求full83与其相同，导致未参与该入口的后续CNN修改也阻止暂存；新增文件也不属于full83清单。

| 输入 | 本次核对 | 构建时如何使用 |
|---|---|---|
| full83完整输入清单 | 594个文件逐项核对SHA256 | 任何文件损坏或缺失即停止 |
| full83的`rtl/music` | 73个文件 | 按验收清单复制；暂存后及综合后再核对文件集合与哈希 |
| 活动`rtl/music` | 84个文件；相对full83为9个修改、11个新增、0个缺失 | 记录差异，不覆盖验收CNN |
| DDR冻结输入 | 原有`FROZEN`清单 | 同时核对活动文件和验收文件，保护条件保留 |
| 本批整机控制 | 明确列出的RTL、scope及新编译USB固件 | 按原入口覆盖，记录每个暂存输入的哈希 |

新增`tools/workstation_sources.py`负责上述CNN选择、差异记录与暂存核对。`music_sha256`继续记录实际构建输入，供现有回归读取。每次构建另写`cnn_source_audit.json`，包含验收／活动哈希及修改、新增、缺失清单；`build_metadata.json`记录`cnn_source_policy=accepted_full83`与审计文件哈希。输入检查使用显式异常，`python3 -O`也不会跳过。

这份候选使用full83的CNN缓存与算法路径。后续CQT／卷积时序优化及Flash模型启动源码保留在活动目录，不在本入口中集成；它们仍由各自构建与验证记录约束。不得把本次通过解释成后续CNN代码已完成整机验收或Flash自动加载已发布。

## 验证

- 源码边界6项测试通过，覆盖活动修改／新增／缺失、验收CNN及其他输入损坏／缺失、未登记验收文件、暂存CNN被增加／修改／删除。优化Python模式重复6项通过。
- USB固件暂存6项测试通过，包含缺失full83时在编译前拒绝，以及ROM替换、静态RAM与栈余量检查。
- 完整整机`--prepare-only`通过：暂存目录`results/workstation_scope83_20261018_021524_310542`，19个输入相对基准改变，CNN改变数为0。固件19288字节，静态RAM25003字节，栈余量40532字节。
- 完整整机`--synthesis-only`通过，目录`results/workstation_scope83_20261018_021532_266586`。SYN BSRAM为216/340，Basic Pitch、TF、共享DDR、音源、显示与6个scope合并实例均已展开；暂存输入与用于回归的prepare目录逐项相同，工具运行前后输入未变。
- 18道现有整机回归门禁通过，结果为`current_regression_20261018_022033_474844`：8项scope、7项Push／曲谱、16项TF音频套件、delay DDR等价、172帧Viterbi／delay地址隔离。旧地址负例按预期在第1帧失败，当前地址下28音及全部分数／回溯通过。

首次scope回归暴露测试脚本过滤整个`src/usb_a/`而漏掉新增的生命周期仲裁模块。已在`sim/scope_vec/run_merge.py`从工程文件表补入该模块，保持旧暂存目录兼容；复跑8项scope测试通过。首次失败报告仍保留在本机结果目录。DDR隔离脚本新增`--project`，整机回归显式传入本次暂存工程的Viterbi与DDR地址表；最终18道门禁已使用该路径，独立暂存隔离复验也通过。

未执行P&R、生成新位流或烧录。本次综合不分配UserCode；`LATEST_WORKSTATION.json`不变。本批25K板间热插拔、触摸与SPI屏闭环仍未实测。综合仍有已有锁存器等警告。音频／USB综合估算分别43.635／38.267 MHz，低于76.8／48 MHz目标；这是综合估算，时序仍未闭合。本次未重跑CNN卷积算术的完整数值等价测试，源码哈希和Viterbi隔离回归不替代它。

## 复现与证据

在`migration/gw138k_audio/push2_workstation/usb_a`执行，均不访问板卡：

```sh
python3 -m unittest discover -s sim -p test_current_workstation_sources.py -v
python3 -O -m unittest discover -s sim -p test_current_workstation_sources.py -v
python3 -m unittest discover -s sim -p test_stage_usb_firmware.py -v
python3 build.py --current-workstation --prepare-only
python3 sim/scope_vec/run_current.py results/<本次workstation_scope83目录>
python3 build.py --current-workstation --synthesis-only
```

本机需保留原验收目录`results/song_guide_full83_20261006_203125_607466`及其`workstation_inputs.json`；缺失即失败，不会退回普通构建或旧网表。

精确差异见[CNN源码审计](current_workstation_sources_20261018/cnn_source_audit.json)，清单复核见[源码验证记录](current_workstation_sources_20261018/source_verification.json)，另附[综合审计](current_workstation_sources_20261018/synthesis.json)、[18道门禁结果](current_workstation_sources_20261018/regression.json)和[暂存DDR隔离输入](current_workstation_sources_20261018/staged_ddr_inputs_sha256.json)。首批接口实现与原阻塞日志见[首批记录](INTERFACE_BATCH_20261018.md)。本次未提交或推送工作区改动。

## 后续时序候选

本页记录默认full83来源修复及其当时的SYN结果。后续`--cnn-timing85`为独立、显式策略：
从固定full85快照选择6处时序修复，其余67个CNN目录文件仍采用full83。当前活动CNN／Flash
修改不覆盖候选。完整布线状态及新回归见[时序修复记录](WORKSTATION_TIMING_20261018.md)。
