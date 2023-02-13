# 1.0.4版本

1. 修复pos_data/target_data从缓存文件恢复数据，导致defaultdict变成dict的问题
2. 

# 1.0.3版本

1. 组合策略模板，增加持仓目标调仓交易模式
2. 修复部分情况下由于K线切片行情缺失，导致的回测计算盈亏错误

# 1.0.2版本

1. 使用zoneinfo替换pytz库
2. 调整安装脚本setup.cfg，添加Python版本限制

# 1.0.1版本

1. 将模块的图标文件信息，改为完整路径字符串
2. 改为使用PySide6风格的信号QtCore.Signal