# Minecraft Server Manager

一个功能完善的 Minecraft 服务器管理工具，提供基于命令行的服务器状态查询、监控和管理功能。支持 Java 版和基岩版服务器，具备丰富的查询选项和可视化输出。

## 功能特性

- ✅ 多版本支持：同时支持 Minecraft Java 版和基岩版服务器
- ✅ 实时状态查询：获取服务器在线状态、玩家数量、版本信息等
- ✅ 美观输出：带颜色的终端输出，支持 Minecraft 格式代码解析
- ✅ 服务器管理：添加、删除、编辑服务器信息
- ✅ 智能扫描：端口扫描功能，自动发现 Minecraft 服务器
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
git clone (https://github.com/ChuanYuanNotBoat/Minecraft-Server-Manager.git)
cd minecraft-server-manager
```

### PowerShell/Windows 安装

```bash
git clone (https://github.com/ChuanYuanNotBoat/Minecraft-Server-Manager.git)
cd minecraft-server-manager
python -m pip install -r requirements.txt
```

## 使用方法

### 基本命令

```bash
# 启动管理器
python server.py

# 直接查询服务器
python -c "from server_info import MinecraftQuery; print(MinecraftQuery.ping('server.address'))"
```

### 交互式命令

在管理器中可使用以下命令：
- `n` - 下一页
- `p` - 上一页
- `a` - 添加服务器
- `d` - 删除服务器
- `players <序号>` - 查看玩家列表
- `info <序号>` - 查看服务器详情
- `scan` - 扫描服务器端口
- `h` - 显示帮助
- `q` - 退出

## 项目结构

```
minecraft-server-manager/
├── server.py          # 主管理程序
├── server_info.py     # 服务器查询核心模块
├── servers.json       # 服务器列表数据（自动生成）
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

## 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进这个项目。

## 许可证

MIT License - 详见 LICENSE 文件。

## 兼容性说明

本项目已在以下环境中测试：
- Termux (Android)
- PowerShell (Windows 10/11)



## 注意事项

- 某些网络环境可能阻止 UDP 查询，影响基岩版服务器检测
- 查询速度受网络条件和服务器响应时间影响
- 建议使用最新版 Python 以获得最佳性能
