# M8后续时钟释放与显示请求控制修复

日期：2026-10-31。维护源变更，尚未转授为新候选综合、P&R或实板通过。原M8来源保持不变，后续候选必须另立身份。

## 时钟监测复位释放

M8实际routed路径中，reference48 `source_reset_n/Q`到计数器／Gray CLEAR有35条removal违例，最差−0.274 ns。没有切断这些路径或放松参考时钟。维护`workstation_audio_clock_monitor.sv`将pre级由2改为3，在source下降沿释放`source_reset_n`，使计数器首次活动的上升沿与旧实现相同，并为实际reset树增加半周期的removal／recovery裕量。公共reset仍异步立即断言，源停钟时不提前释放。

离线证据[clock_release.json](dual138k_clock_display_control_20261031/clock_release.json)：两个`SEPARATE_COMMON_RESET=0/1`配置各308,253次全部公共输出逐周期一致，各19次计数回绕；覆盖停钟高／低电平公共复位、独立startup、错频／切率／缺钟／恢复。原上升沿释放作为负控，在精确的opposite-edge检查被拒绝。完整clock domain回归两项通过，含三个异步相位、官方DCS模型及生产50,000周期监测窗口。固定旧参照来自`2e273da`，字节SHA由runner强校验，生产不消费fixture。输入hash末尾与提交前均复核无漂移。新物理裕量尚待新P&R实测。

## 显示导出请求寄存

M8实际epoch比较→runtime请求→producer释放分析帧的往返路径最差−1.651 ns。维护`workstation_display_runtime.sv`增加`export_request`，资格判断先寄存再交producer；不阻塞PCM采样。增加一拍私有export请求延迟。producer在实际接受时仍复核ready／context，真实writer在SNAPSHOT及最终发布前继续验证。资格通过后context取消可能启动一个最终被拒绝的私有export，不能发布旧图；disable立即禁止、清请求，重新使能不会复活。

[真实writer／reader边界](dual138k_clock_display_control_20261031/display_export_boundary.json)通过14场景、52检查、10加载、3,286次读与3次summary；增加资格寄存恰好一拍、资格后context revoke、资格后disable和重新使能检查。绕过新寄存器及原四种发布／取消错误共5个真实行为负控全部拒绝。

[完整display runtime](dual138k_clock_display_control_20261031/display_runtime.json)通过8次发布、13次commit、166,525次原子tuple、1,024波形样本、131,072 XY像素、1,024谱列、60次CDC丢帧及5,528,428次Gray撤销逐拍检查；default／runtime／owner8三个完整HDMI装配均使用官方GW5A原语elaborate通过。参考支持源为固定Classic完整准备工程，显式选择维护的native counter，不改任何历史候选。所有输入提交前再次hash复核一致。

默认输入边界`sim/test_current_workstation_sources.py`17项通过。原有48k／44.1k波形、FFT、XY和参数实际状态的离线关系保持；没有声画实板证据。新候选的资源、routed CDC／PLL和时序必须全量重测，不预记收益。未下载SRAM、未写Flash；回滚为保留板上既有镜像。
