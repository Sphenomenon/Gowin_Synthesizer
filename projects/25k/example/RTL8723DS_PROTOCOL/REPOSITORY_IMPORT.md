# 迁入蓝牙分支（2026-10-20）

来源为本机`GW_25K/example/RTL8723DS_PROTOCOL`，已验收A25D/Android0.2.10。迁入目标为`codex/android-bluetooth-control`。源码、冻结原始包、音频参考、50组RTL回归、当前协议文档和第十八轮证据进入仓库；历史各轮只保留摘要，完整原始捕获、旧源码快照、历史APK及位流留在来源工程。

公共APP源码只保留在根目录`clients/android`，本例`clients/android`使用相对符号链接；原工具/测试路径不变。已有分支的最小协议适配包含在这次完整APP升级中，迁入前未提交修改另保存在本机`/private/tmp/gw25k-bluetooth-before-import-20261020`。主仓库main上的其他修改没有纳入。

## 克隆后复验

```sh
python3 projects/25k/example/RTL8723DS_PROTOCOL/tools/check_repository_import.py
sh projects/25k/example/RTL8723DS_PROTOCOL/run_sim.sh
cd clients/android
sh gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

Android需要JDK17、SDK35、Build Tools35.0.0；RTL需要Python3和Icarus Verilog。新构建产物留在本机。原`reports/ready_build.json`及当前/历史硬件报告保留验收时的绝对路径和哈希，不是可移植编程指针；新克隆先`sh build.sh`，再使用生成的`reports/last_build.json`通过时序/器件/安全/哈希门禁后编程。原`verify_release.py`检查原交付产物；源码克隆一致性使用上面的`check_repository_import.py`。

## 已知边界

本次把当前成果纳入138K/25K共同仓库，未替换138K板级引脚、器件或主机业务顶层。A25D时序与速率结论来自25K实板，不能写到138K验收项。手机原生GATT/UI/实际速率、A25D物理断电上电尚未验收；历史boot_id重复问题保留，板卡重启/重配置后先删除旧未完成下载。录音源仍为内置测试音。

迁入后的验证记录见[REPOSITORY_VALIDATION.json](REPOSITORY_VALIDATION.json)。`SOURCE_IMPORT.json`保留原始哈希，并用`repository_sha256`标记仅因目录迁移而调整的文档；生产RTL/APP代码保持来源字节。
