# W 返回邮箱审计依赖兼容修正

404926b8的strict auditor起止两次封存曾无条件要求新helper与bluetooth源文件；旧策略虽不导入helper，仍存在读取依赖。本次仅按W-v3 metadata选择一次局部来源tuple，起止复用同一tuple；M及旧W的None/v1/v2均不要求这两项。W-v3依然必须封存二者，原role／未知policy／mapped timing gate不变。

16项既有及定向回归通过：M/W旧策略在两新依赖均缺失时到达prepare验证入口，W-v3分别缺helper、缺bluetooth均拒绝，二者存在时确认实际参与hash。独立子代理只读复核通过。初始7文件seal保留，本次最终hash与验证范围见[机器报告](DUAL138K_W_RETURN_AUDIT_COMPAT_20261101.json)；未改RTL、时钟或约束，未启动EDA或操作硬件。
