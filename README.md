# Minecraft Server Manager

一个功能完善的 Minecraft 服务器管理工具，提供基于命令行的服务器状态查询、监控和管理功能。支持 Java 版和基岩版服务器，具备丰富的查询选项和可视化输出。

## 功能特性

- ✅ 多版本支持：同时支持 Minecraft Java 版和基岩版服务器
- ✅ 实时状态查询：获取服务器在线状态、玩家数量、版本信息等
- ✅ 美观输出：带颜色的终端输出，支持 Minecraft 格式代码解析
- ✅ 服务器管理：添加、删除、编辑服务器信息
- ✅ 智能扫描：端口扫描功能，自动发现 Minecraft 服务器，支持常用端口和全端口批量扫描
- ✅ Mod 列表探测与缓存：自动探测 Forge/FML 服务器的 Mod 列表并本地缓存，支持手动配置
- ✅ 实时监控：服务器状态变化监控、玩家加入/退出事件检测、多服务器同时监控
- ✅ 日志查看器：类似文本编辑器的日志界面，支持滚动、搜索、按服务器过滤和导出功能
- ✅ 历史统计：自动记录服务器延迟、玩家数量等历史数据，支持趋势分析
- ✅ 筛选与排序：支持按类型筛选、按名称/IP/端口/类型排序服务器
- ✅ 玩家/延迟统计：支持查看完整玩家列表、延迟历史、平均/最高/最低统计
- ✅ 数据持久化：JSON 格式保存服务器列表和查询历史
- ✅ 多平台支持：兼容 Termux、PowerShell 及主流 Linux/Unix 终端
- ✅ 并发查询：多线程同时查询多个服务器状态

## 安装要求

- Python 3.7 或更高版本
- 网络连接（用于查询服务器状态）

### Termux 安装

```bash
pkg update
pkg install python
git clone "https://github.com/ChuanYuanNotBoat/Minecraft-Server-Manager.git"
cd Minecraft-Server-Manager
```

### PowerShell/Windows 安装

```bash
git clone "https://github.com/ChuanYuanNotBoat/Minecraft-Server-Manager.git"
cd Minecraft-Server-Manager
python -m pip install -r requirements.txt
```

## 使用方法

### 基本命令

```bash
# 启动管理器
python server.py

# 直接查询服务器
python -c "from server import MinecraftPing; print(MinecraftPing.ping('server.address'))"
```

### 交互式命令

在管理器中可使用以下命令：

- `n` - 下一页
- `p` - 上一页
- `a` - 添加服务器
- `d` - 删除服务器
- `players <序号>` - 查看玩家列表
- `info <序号>` - 查看服务器详情
- `monitor <序号>` - 监控单个服务器状态变化
- `monitor <序号1> <序号2> ...` - 同时监控多个服务器
- `chat <序号>` - 连接到服务器聊天（实验性功能）
- `scan` - 扫描服务器常用端口
- `scanall` - 扫描所有端口 (1-65535)
- `h` - 显示帮助
- `q` - 退出

### 监控功能说明

监控模式提供以下功能：

- 实时监控服务器状态变化
- 检测玩家加入/退出事件和玩家数量变化
- 按 '+' 增加刷新间隔，'-' 减少刷新间隔
- 按 'r' 手动刷新，'t' 切换事件排序方式
- 按 'l' 查看完整日志，支持滚动、搜索、过滤和导出
- 按 'q' 或 Ctrl+C 退出监控模式

## 项目结构

```
Minecraft-Server-Manager/
├── server.py          # 主管理程序
├── server_monitor.py  # 服务器监控模块
├── server_info.py     # 服务器查询核心模块（可选）
├── servers.json       # 服务器列表数据（自动生成）
├── config.json        # 配置文件（自动生成）
├── mods_config/       # Mod配置缓存目录
├── requirements.txt   # Python依赖项
└── README.md          # 项目说明
```

## 扩展功能计划

- [ ] Web 界面支持
- [ ] 服务器状态告警通知
- [ ] 自动化定时查询
- [ ] 插件/模组检测增强
- [ ] 性能图表生成
- [ ] API 接口提供
- [ ] 数据库支持替代 JSON 存储
- [ ] Docker 容器化部署
- [ ] 可选调用 Minecraft-Console-Client (MCC) 替代自制客户端功能

## 兼容性说明

本项目已在以下环境中测试：

- Termux (Android)
- PowerShell (Windows 10/11)


## 注意事项

- 某些网络环境可能阻止 UDP 查询，影响基岩版服务器检测
- 查询速度受网络条件和服务器响应时间影响
- 建议使用最新版 Python 以获得最佳性能
- 聊天功能为实验性功能，可能需要额外的 server_info.py 模块支持
- 监控功能需要 server_monitor.py 模块，已包含在项目中

## 未来计划

计划在未来版本中集成对 [Minecraft-Console-Client](https://github.com/MCCTeam/Minecraft-Console-Client) 的可选调用支持，以替代当前实验性的聊天功能和其他未实现的客户端功能。这将提供更稳定和功能完整的 Minecraft 客户端集成体验。
