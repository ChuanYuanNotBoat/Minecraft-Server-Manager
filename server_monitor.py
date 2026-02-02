"""
server_monitor.py - Minecraft服务器监控模块
提供服务器状态监控、事件记录和日志查看功能
支持多服务器同时监控和按服务器分类查看
支持独立运行和从命令行参数启动
支持详细日志记录和查看
"""

import os
import time
import json
import threading
import queue
import sys
import argparse
import re
from collections import deque, defaultdict
from datetime import datetime
import select

# ========== 独立定义常量，避免循环导入 ==========
class Colors:
    BLACK = '\033[30m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    ITALIC = '\033[3m'
    STRIKETHROUGH = '\033[9m'

SERVER_TYPE_JAVA = "java"
SERVER_TYPE_BEDROCK = "bedrock"

# ========== 日志记录器类 ==========
class MonitorLogger:
    """监控日志记录器"""
    
    LOGS_DIR = "logs"
    MAX_LOG_FILES = 50  # 最大日志文件数量
    
    @staticmethod
    def ensure_logs_dir():
        """确保日志目录存在"""
        if not os.path.exists(MonitorLogger.LOGS_DIR):
            os.makedirs(MonitorLogger.LOGS_DIR)
            print(f"{Colors.GREEN}创建日志目录: {MonitorLogger.LOGS_DIR}{Colors.RESET}")
    
    @staticmethod
    def get_log_filename(server_name, timestamp=None):
        """获取日志文件名"""
        MonitorLogger.ensure_logs_dir()
        
        if timestamp is None:
            timestamp = datetime.now()
        
        # 清理服务器名称中的非法字符
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', server_name)
        date_str = timestamp.strftime("%Y%m%d")
        time_str = timestamp.strftime("%H%M%S")
        
        return f"{MonitorLogger.LOGS_DIR}/monitor_{safe_name}_{date_str}_{time_str}.log"
    
    @staticmethod
    def write_log(server_name, event_type, message, player_name=None, diff=None):
        """写入日志"""
        try:
            MonitorLogger.ensure_logs_dir()
            
            # 获取当前日期，每天一个日志文件
            today = datetime.now().strftime("%Y%m%d")
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', server_name)
            daily_log_file = f"{MonitorLogger.LOGS_DIR}/monitor_{safe_name}_{today}.log"
            
            # 创建日志条目
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            log_entry = {
                'timestamp': timestamp,
                'server_name': server_name,
                'event_type': event_type,
                'message': message,
                'player_name': player_name,
                'diff': diff
            }
            
            # 写入日志文件
            with open(daily_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            return True
        except Exception as e:
            print(f"{Colors.RED}日志写入失败: {str(e)}{Colors.RESET}")
            return False
    
    @staticmethod
    def read_logs(server_name=None, date=None, max_lines=100):
        """读取日志"""
        try:
            MonitorLogger.ensure_logs_dir()
            
            log_files = []
            if server_name and date:
                # 读取特定服务器特定日期的日志
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', server_name)
                log_file = f"{MonitorLogger.LOGS_DIR}/monitor_{safe_name}_{date}.log"
                if os.path.exists(log_file):
                    log_files.append(log_file)
            elif server_name:
                # 读取特定服务器的所有日志
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', server_name)
                pattern = f"monitor_{safe_name}_*.log"
                for filename in os.listdir(MonitorLogger.LOGS_DIR):
                    if filename.startswith(f"monitor_{safe_name}_"):
                        log_files.append(f"{MonitorLogger.LOGS_DIR}/{filename}")
            elif date:
                # 读取特定日期的所有日志
                pattern = f"monitor_*_{date}.log"
                for filename in os.listdir(MonitorLogger.LOGS_DIR):
                    if filename.endswith(f"_{date}.log"):
                        log_files.append(f"{MonitorLogger.LOGS_DIR}/{filename}")
            else:
                # 读取所有日志
                for filename in os.listdir(MonitorLogger.LOGS_DIR):
                    if filename.startswith("monitor_") and filename.endswith(".log"):
                        log_files.append(f"{MonitorLogger.LOGS_DIR}/{filename}")
            
            # 按修改时间排序（最新的在前）
            log_files.sort(key=os.path.getmtime, reverse=True)
            
            # 读取日志条目
            all_logs = []
            for log_file in log_files:
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        for line in lines[-max_lines:]:  # 只读取最后max_lines行
                            try:
                                log_entry = json.loads(line.strip())
                                all_logs.append(log_entry)
                            except json.JSONDecodeError:
                                pass
                except Exception as e:
                    print(f"{Colors.YELLOW}读取日志文件失败 {log_file}: {str(e)}{Colors.RESET}")
                
                # 如果已经读取了足够的日志，停止读取
                if len(all_logs) >= max_lines:
                    break
            
            # 按时间戳排序
            all_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return all_logs[:max_lines]
        except Exception as e:
            print(f"{Colors.RED}读取日志失败: {str(e)}{Colors.RESET}")
            return []
    
    @staticmethod
    def list_log_files(server_name=None):
        """列出日志文件"""
        try:
            MonitorLogger.ensure_logs_dir()
            
            log_files = []
            for filename in os.listdir(MonitorLogger.LOGS_DIR):
                if filename.startswith("monitor_") and filename.endswith(".log"):
                    # 解析文件名
                    parts = filename[8:-4].split('_')  # 移除"monitor_"和".log"
                    if len(parts) >= 3:
                        file_server_name = '_'.join(parts[:-2])  # 服务器名可能有下划线
                        date_str = parts[-2]
                        time_str = parts[-1]
                        
                        file_info = {
                            'filename': filename,
                            'server_name': file_server_name,
                            'date': date_str,
                            'time': time_str,
                            'full_path': f"{MonitorLogger.LOGS_DIR}/{filename}",
                            'size': os.path.getsize(f"{MonitorLogger.LOGS_DIR}/{filename}"),
                            'modified': datetime.fromtimestamp(
                                os.path.getmtime(f"{MonitorLogger.LOGS_DIR}/{filename}")
                            ).strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        if server_name is None or file_server_name == server_name:
                            log_files.append(file_info)
            
            # 按修改时间排序（最新的在前）
            log_files.sort(key=lambda x: x['modified'], reverse=True)
            
            return log_files
        except Exception as e:
            print(f"{Colors.RED}列出日志文件失败: {str(e)}{Colors.RESET}")
            return []
    
    @staticmethod
    def cleanup_old_logs(max_files=None):
        """清理旧的日志文件"""
        try:
            MonitorLogger.ensure_logs_dir()
            
            if max_files is None:
                max_files = MonitorLogger.MAX_LOG_FILES
            
            log_files = []
            for filename in os.listdir(MonitorLogger.LOGS_DIR):
                if filename.startswith("monitor_") and filename.endswith(".log"):
                    full_path = f"{MonitorLogger.LOGS_DIR}/{filename}"
                    log_files.append({
                        'filename': filename,
                        'full_path': full_path,
                        'modified': os.path.getmtime(full_path)
                    })
            
            # 按修改时间排序（最旧的在前）
            log_files.sort(key=lambda x: x['modified'])
            
            # 删除超过数量的文件
            if len(log_files) > max_files:
                files_to_delete = len(log_files) - max_files
                deleted_count = 0
                
                for i in range(files_to_delete):
                    try:
                        os.remove(log_files[i]['full_path'])
                        print(f"{Colors.YELLOW}删除旧日志文件: {log_files[i]['filename']}{Colors.RESET}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"{Colors.RED}删除日志文件失败 {log_files[i]['filename']}: {str(e)}{Colors.RESET}")
                
                return deleted_count
            
            return 0
        except Exception as e:
            print(f"{Colors.RED}清理旧日志失败: {str(e)}{Colors.RESET}")
            return 0
    
    @staticmethod
    def export_logs_to_file(server_name=None, date=None, output_file=None):
        """导出日志到文件"""
        try:
            MonitorLogger.ensure_logs_dir()
            
            # 读取日志
            logs = MonitorLogger.read_logs(server_name, date, max_lines=10000)
            
            if not logs:
                print(f"{Colors.YELLOW}没有找到日志数据{Colors.RESET}")
                return False
            
            # 生成输出文件名
            if output_file is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                if server_name and date:
                    output_file = f"{MonitorLogger.LOGS_DIR}/export_{server_name}_{date}_{timestamp}.json"
                elif server_name:
                    output_file = f"{MonitorLogger.LOGS_DIR}/export_{server_name}_{timestamp}.json"
                elif date:
                    output_file = f"{MonitorLogger.LOGS_DIR}/export_{date}_{timestamp}.json"
                else:
                    output_file = f"{MonitorLogger.LOGS_DIR}/export_all_{timestamp}.json"
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
            
            print(f"{Colors.GREEN}日志已导出到: {output_file}{Colors.RESET}")
            print(f"{Colors.CYAN}共导出 {len(logs)} 条日志记录{Colors.RESET}")
            return True
        except Exception as e:
            print(f"{Colors.RED}导出日志失败: {str(e)}{Colors.RESET}")
            return False

# ========== 动态导入 MinecraftPing ==========
class SimpleMinecraftPing:
    """简化版的MinecraftPing，用于独立运行"""
    
    @staticmethod
    def ping(host, port=25565, timeout=3, use_cache=False, server_type=SERVER_TYPE_JAVA):
        """简化版的ping方法"""
        # 模拟响应
        import random
        is_online = random.random() > 0.3  # 70%的几率在线
        
        if is_online:
            return {
                "server_type": server_type,
                "motd": f"{server_type.capitalize()}测试服务器",
                "players": {"online": random.randint(0, 50), "max": 100},
                "version": {"name": "1.20.1" if server_type == SERVER_TYPE_JAVA else "1.20.0"},
                "query_time": random.randint(20, 200),
                "connect_time": random.randint(10, 100)
            }
        else:
            return {
                "error": "连接超时",
                "server_type": server_type,
                "query_time": 0,
                "connect_time": 0
            }
    
    @staticmethod
    def clean_mc_formatting(text):
        import re
        return re.sub(r'§[0-9a-fklmnor]', '', text) if text else ""
    
    @staticmethod
    def safe_convert_mc_formatting(text, context_color='\033[0m'):
        return text + context_color if text else ""

# 全局变量，用于存储MinecraftPing实例
_MinecraftPing = None

def get_minecraft_ping():
    """获取MinecraftPing实例"""
    global _MinecraftPing
    
    if _MinecraftPing is not None:
        return _MinecraftPing
    
    try:
        # 尝试从server模块导入
        from server import MinecraftPing as ServerMinecraftPing
        _MinecraftPing = ServerMinecraftPing
        print(f"{Colors.GREEN}[监控] 使用完整版MinecraftPing{Colors.RESET}")
    except ImportError:
        # 使用简化版本
        _MinecraftPing = SimpleMinecraftPing
        print(f"{Colors.YELLOW}[监控] 使用简化版MinecraftPing{Colors.RESET}")
    
    return _MinecraftPing

# ========== 监控事件类 ==========
class MonitorEvent:
    """监控事件类"""
    
    EVENT_TYPES = {
        'status_change': '状态变化',
        'player_join': '玩家加入',
        'player_leave': '玩家退出',
        'player_count': '玩家数量变化',
        'info': '信息'
    }
    
    def __init__(self, event_type, message, timestamp=None, player_name=None, diff=None, server_name=None):
        """初始化监控事件"""
        self.event_type = event_type
        self.message = message
        self.timestamp = timestamp or time.time()
        self.player_name = player_name
        self.diff = diff  # 变化量
        self.server_name = server_name  # 服务器名称
        self.color = self._get_color()
    
    def _get_color(self):
        """根据事件类型获取颜色"""
        color_map = {
            'status_change': Colors.YELLOW,
            'player_join': Colors.GREEN,
            'player_leave': Colors.RED,
            'player_count': Colors.CYAN,
            'info': Colors.BLUE
        }
        return color_map.get(self.event_type, Colors.WHITE)
    
    def format_time(self, include_milliseconds=True):
        """格式化时间戳"""
        dt = datetime.fromtimestamp(self.timestamp)
        if include_milliseconds:
            return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 毫秒精度
        else:
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def get_type_display(self):
        """获取事件类型显示文本"""
        return self.EVENT_TYPES.get(self.event_type, '未知')
    
    def to_dict(self):
        """转换为字典（用于JSON序列化）"""
        return {
            'event_type': self.event_type,
            'message': self.message,
            'timestamp': self.timestamp,
            'player_name': self.player_name,
            'server_name': self.server_name,
            'type_display': self.get_type_display(),
            'time_display': self.format_time()
        }
    
    def to_plain_text(self, include_color=True):
        """转换为纯文本"""
        server_prefix = f"[{self.server_name}] " if self.server_name else ""
        if include_color:
            return f"{Colors.CYAN}[{self.format_time()}]{Colors.RESET}{server_prefix}{self.color} {self.message}{Colors.RESET}"
        else:
            return f"[{self.format_time()}] {server_prefix}{self.get_type_display()}: {self.message}"
    
    def __str__(self):
        # 如果有服务器名称，在消息前添加服务器标识
        server_prefix = f"{Colors.MAGENTA}[{self.server_name}]{Colors.RESET} " if self.server_name else ""
        
        # 如果有变化量，在消息后添加变化量显示
        if self.diff is not None:
            diff_color = Colors.GREEN if self.diff > 0 else Colors.RED
            diff_sign = "+" if self.diff > 0 else ""
            return f"{Colors.CYAN}[{self.format_time()}]{Colors.RESET}{server_prefix}{self.color} {self.message} {diff_color}({diff_sign}{self.diff}){Colors.RESET}"
        else:
            return f"{Colors.CYAN}[{self.format_time()}]{Colors.RESET}{server_prefix}{self.color} {self.message}{Colors.RESET}"
    
    def __lt__(self, other):
        """用于排序：按时间戳比较"""
        return self.timestamp < other.timestamp

# ========== 多服务器日志查看器 ==========
class MultiServerLogViewer:
    """多服务器日志查看器，提供按服务器分类的界面"""
    
    def __init__(self, monitor_instances):
        """
        初始化多服务器日志查看器
        
        Args:
            monitor_instances: ServerMonitor实例列表
        """
        self.monitors = monitor_instances
        self.server_names = [m.server['name'] for m in monitor_instances]
        self.title = f"多服务器监控日志 - {len(self.server_names)}个服务器"
        self.current_line = 0
        self.page_size = 0
        self.is_running = False
        self.sort_by_time = True  # 默认按时间排序
        self.auto_scroll = True    # 是否自动滚动到底部
        self.last_update_time = time.time()  # 最后更新时间
        self.filter_server = None  # 当前过滤的服务器名称
        self.view_mode = 'combined'  # 查看模式: 'combined'=合并, 'server'=按服务器分类
        self.last_event_count = 0  # 上次事件总数，用于检测新事件
    
    def start(self):
        """启动日志查看器"""
        self.is_running = True
        self.current_line = 0
        
        # 获取终端尺寸
        try:
            terminal_size = os.get_terminal_size()
            self.page_size = terminal_size.lines - 12  # 留出空间显示控制信息
        except:
            self.page_size = 20
        
        # 记录开始时的日志数量
        self.last_event_count = self._get_total_event_count()
        
        while self.is_running:
            self.display()
            if not self.handle_input():
                break
        
        return True
    
    def _get_total_event_count(self):
        """获取总事件数"""
        total = 0
        for monitor in self.monitors:
            with monitor.event_lock:
                total += len(monitor.all_events)
        return total
    
    def display(self):
        """显示日志内容"""
        # 清屏
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # 获取所有事件（线程安全）
        all_events = []
        for monitor in self.monitors:
            with monitor.event_lock:
                all_events.extend(monitor.all_events)
        
        # 过滤事件（如果设置了服务器过滤）
        if self.filter_server:
            filtered_events = [e for e in all_events if e.server_name == self.filter_server]
        else:
            filtered_events = all_events
        
        # 排序事件
        sorted_events = self._get_sorted_events(filtered_events)
        event_count = len(sorted_events)
        
        # 检查是否有新事件
        new_events = False
        if event_count > self.last_event_count:
            new_events = True
            # 如果启用自动滚动，跳到最新
            if self.auto_scroll:
                self.current_line = max(0, event_count - self.page_size)
        
        # 显示标题和控制信息
        print(f"{Colors.BOLD}{Colors.CYAN}{self.title}{Colors.RESET}")
        print(f"{Colors.CYAN}服务器列表: {', '.join(self.server_names)}{Colors.RESET}")
        
        # 显示当前过滤和查看模式
        filter_display = f" | 过滤: {Colors.MAGENTA}{self.filter_server}{Colors.CYAN}" if self.filter_server else ""
        print(f"{Colors.CYAN}事件总数: {event_count} | 查看模式: {self.view_mode}{filter_display} | 排序: {'时间' if self.sort_by_time else '类型'} | 当前位置: {self.current_line+1}/{event_count}{Colors.RESET}")
        
        if new_events and not self.auto_scroll:
            print(f"{Colors.GREEN}有新事件到达! 按 'a' 切换自动滚动{Colors.RESET}")
        
        print(f"{Colors.YELLOW}控制: ↑/↓ 滚动 | t 切换排序 | a 切换自动滚动({'开' if self.auto_scroll else '关'}) | s 保存到文件{Colors.RESET}")
        print(f"{Colors.YELLOW}过滤: f 选择服务器 | v 切换查看模式 | c 清除过滤 | q 返回监控{Colors.RESET}")
        print("=" * 80)
        
        # 按查看模式显示
        if self.view_mode == 'combined' or self.filter_server:
            # 显示当前页的事件
            start_idx = self.current_line
            end_idx = min(start_idx + self.page_size, len(sorted_events))
            
            for i in range(start_idx, end_idx):
                event = sorted_events[i]
                
                # 显示行号 - 修复多余空格问题
                line_no = i + 1
                line_no_color = Colors.CYAN if line_no % 2 == 0 else Colors.BLUE
                # 使用固定宽度4，但左对齐，确保没有多余空格
                print(f"{line_no_color}{line_no:<4}{Colors.RESET} ", end="")
                
                # 显示事件
                print(f"{event}")
            
            # 如果还有更多事件，显示提示
            if end_idx < len(sorted_events):
                print(f"{Colors.CYAN}... 还有 {len(sorted_events) - end_idx} 个事件 ...{Colors.RESET}")
        else:
            # 按服务器分类显示
            server_events = defaultdict(list)
            for event in sorted_events:
                server_events[event.server_name].append(event)
            
            # 计算每个服务器显示的事件数量
            servers_per_page = max(1, self.page_size // 20)
            events_per_server = max(1, self.page_size // len(server_events))
            
            displayed_count = 0
            for server_name in self.server_names:
                if server_name in server_events:
                    events = server_events[server_name]
                    display_count = min(events_per_server, len(events))
                    
                    # 显示服务器标题
                    print(f"\n{Colors.BOLD}{Colors.MAGENTA}=== {server_name} (显示最近 {display_count} 条) ==={Colors.RESET}")
                    
                    # 显示该服务器的事件
                    for i in range(max(0, len(events) - display_count), len(events)):
                        print(f"  {events[i]}")
                        displayed_count += 1
                        
                        if displayed_count >= self.page_size - 5:  # 留出一些空间
                            break
                    
                    if displayed_count >= self.page_size - 5:
                        break
        
        print("=" * 80)
        print(f"{Colors.YELLOW}控制: ↑/↓ 滚动 | t 切换排序 | a 切换自动滚动({'开' if self.auto_scroll else '关'}) | s 保存到文件{Colors.RESET}")
        print(f"{Colors.YELLOW}过滤: f 选择服务器 | v 切换查看模式 | c 清除过滤 | q 返回监控{Colors.RESET}")
        
        # 更新最后显示的事件数量
        self.last_event_count = event_count
        self.last_update_time = time.time()
    
    def _get_sorted_events(self, events):
        """获取排序后的事件列表"""
        if self.sort_by_time:
            # 按时间排序（升序）
            return sorted(events, key=lambda e: e.timestamp)
        else:
            # 按类型分组，组内按时间排序
            events_by_type = {}
            for event in events:
                if event.event_type not in events_by_type:
                    events_by_type[event.event_type] = []
                events_by_type[event.event_type].append(event)
            
            # 对每个类型的事件按时间排序
            for event_type in events_by_type:
                events_by_type[event_type].sort(key=lambda e: e.timestamp)
            
            # 按类型顺序组合
            sorted_events = []
            type_order = ['status_change', 'player_join', 'player_leave', 'player_count', 'info']
            for event_type in type_order:
                if event_type in events_by_type:
                    sorted_events.extend(events_by_type[event_type])
            
            # 添加其他类型的事件
            for event_type in events_by_type:
                if event_type not in type_order:
                    sorted_events.extend(events_by_type[event_type])
            
            return sorted_events
    
    def handle_input(self):
        """处理用户输入"""
        # 非阻塞输入检测
        if os.name == 'nt':
            # Windows平台
            try:
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                    return self._process_key(key)
                else:
                    # 检查是否有新事件（每0.2秒检查一次）
                    current_time = time.time()
                    if current_time - self.last_update_time > 0.2:
                        # 触发一次显示更新
                        return True
                    time.sleep(0.05)  # 减少CPU占用
            except ImportError:
                time.sleep(0.1)
        else:
            # Unix-like平台
            try:
                if sys.stdin in select.select([sys.stdin], [], [], 0.05)[0]:
                    key = sys.stdin.read(1).lower()
                    return self._process_key(key)
                else:
                    # 检查是否有新事件（每0.2秒检查一次）
                    current_time = time.time()
                    if current_time - self.last_update_time > 0.2:
                        # 触发一次显示更新
                        return True
            except:
                time.sleep(0.1)
        
        return True
    
    def _process_key(self, key):
        """处理按键"""
        # 获取事件数量
        all_events = []
        for monitor in self.monitors:
            with monitor.event_lock:
                all_events.extend(monitor.all_events)
        
        event_count = len(all_events)
        
        if key == 'q':
            self.is_running = False
            return False
        elif key == 't':
            self.sort_by_time = not self.sort_by_time
            self.current_line = 0
        elif key == 's':
            self.save_to_file()
        elif key == 'a':
            self.auto_scroll = not self.auto_scroll
        elif key == 'v':
            # 切换查看模式
            modes = ['combined', 'server']
            current_index = modes.index(self.view_mode)
            self.view_mode = modes[(current_index + 1) % len(modes)]
            self.current_line = 0
        elif key == 'f':
            self.select_server_filter()
        elif key == 'c':
            self.filter_server = None
            self.current_line = 0
        elif key in ('\x1b',):  # ESC键开始
            # 处理方向键
            if os.name == 'nt':
                try:
                    import msvcrt
                    if msvcrt.kbhit():
                        next_char = msvcrt.getch()
                        if next_char == b'H':  # 上箭头
                            self.current_line = max(0, self.current_line - 1)
                        elif next_char == b'P':  # 下箭头
                            self.current_line = min(event_count - 1, self.current_line + 1)
                        elif next_char == b'I':  # Page Up
                            self.current_line = max(0, self.current_line - self.page_size)
                        elif next_char == b'Q':  # Page Down
                            self.current_line = min(event_count - 1, self.current_line + self.page_size)
                except:
                    pass
            else:
                if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                    next_chars = sys.stdin.read(2)
                    if next_chars == '[A':  # 上箭头
                        self.current_line = max(0, self.current_line - 1)
                    elif next_chars == '[B':  # 下箭头
                        self.current_line = min(event_count - 1, self.current_line + 1)
                    elif next_chars == '[5':  # Page Up
                        sys.stdin.read(1)  # 消耗'~'字符
                        self.current_line = max(0, self.current_line - self.page_size)
                    elif next_chars == '[6':  # Page Down
                        sys.stdin.read(1)  # 消耗'~'字符
                        self.current_line = min(event_count - 1, self.current_line + self.page_size)
        else:
            # 简单按键处理
            if key == 'k' or key == 'w':  # 上
                self.current_line = max(0, self.current_line - 1)
            elif key == 'j' or key == 's':  # 下
                self.current_line = min(event_count - 1, self.current_line + 1)
            elif key == 'g':  # 跳到开头
                self.current_line = 0
            elif key == 'G':  # 跳到结尾
                self.current_line = max(0, event_count - self.page_size)
            elif key == ' ':  # 空格键 - 下一页
                self.current_line = min(event_count - 1, self.current_line + self.page_size)
            elif key == 'b':  # 上一页
                self.current_line = max(0, self.current_line - self.page_size)
        
        return True
    
    def select_server_filter(self):
        """选择服务器过滤"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{Colors.BOLD}{Colors.CYAN}选择要过滤的服务器:{Colors.RESET}\n")
        
        for i, server_name in enumerate(self.server_names, 1):
            print(f"  {Colors.CYAN}{i}.{Colors.RESET} {server_name}")
        
        print(f"\n{Colors.YELLOW}输入服务器编号 (1-{len(self.server_names)}), 或 0 取消: {Colors.RESET}", end="")
        
        try:
            choice = input().strip()
            if choice == '0':
                return
            index = int(choice) - 1
            if 0 <= index < len(self.server_names):
                self.filter_server = self.server_names[index]
                self.current_line = 0
                print(f"{Colors.GREEN}已选择服务器: {self.filter_server}{Colors.RESET}")
                time.sleep(0.5)
            else:
                print(f"{Colors.RED}无效的服务器编号{Colors.RESET}")
                time.sleep(0.5)
        except ValueError:
            print(f"{Colors.RED}请输入数字{Colors.RESET}")
            time.sleep(0.5)
    
    def save_to_file(self):
        """保存日志到文件"""
        try:
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"multi_monitor_log_{timestamp}.txt"
            
            # 获取所有事件（线程安全）
            all_events = []
            for monitor in self.monitors:
                with monitor.event_lock:
                    all_events.extend(monitor.all_events)
            
            # 过滤事件（如果设置了服务器过滤）
            if self.filter_server:
                events_to_save = [e for e in all_events if e.server_name == self.filter_server]
            else:
                events_to_save = all_events
            
            # 写入文件
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"=== 多服务器监控日志 ===\n")
                f.write(f"服务器列表: {', '.join(self.server_names)}\n")
                if self.filter_server:
                    f.write(f"过滤服务器: {self.filter_server}\n")
                f.write(f"查看模式: {self.view_mode}\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"事件总数: {len(events_to_save)}\n")
                f.write(f"排序方式: {'按时间' if self.sort_by_time else '按类型'}\n")
                f.write("=" * 60 + "\n\n")
                
                # 按服务器分组
                server_events = defaultdict(list)
                for event in events_to_save:
                    server_events[event.server_name].append(event)
                
                # 按服务器名称排序
                for server_name in sorted(server_events.keys()):
                    events = server_events[server_name]
                    f.write(f"\n{'='*40}\n")
                    f.write(f"服务器: {server_name} (共{len(events)}条事件)\n")
                    f.write(f"{'='*40}\n\n")
                    
                    # 排序事件
                    sorted_events = self._get_sorted_events(events)
                    
                    for event in sorted_events:
                        f.write(event.to_plain_text(include_color=False) + "\n")
            
            print(f"\n{Colors.GREEN}日志已保存到: {filename}{Colors.RESET}")
            input(f"{Colors.CYAN}按回车键继续...{Colors.RESET}")
        except Exception as e:
            print(f"\n{Colors.RED}保存失败: {str(e)}{Colors.RESET}")
            input(f"{Colors.CYAN}按回车键继续...{Colors.RESET}")

# ========== 日志查看器 ==========
class LogViewer:
    """日志查看器，提供类似文本编辑器的界面"""
    
    def __init__(self, monitor_instance):
        """
        初始化日志查看器
        
        Args:
            monitor_instance: ServerMonitor实例，用于获取事件和同步状态
        """
        self.monitor = monitor_instance
        self.title = f"{monitor_instance.server['name']} - 监控日志"
        self.current_line = 0
        self.page_size = 0
        self.is_running = False
        self.sort_by_time = True  # 默认按时间排序
        self.last_event_count = 0  # 上次显示的事件数量
        self.auto_scroll = True    # 是否自动滚动到底部
        self.last_update_time = time.time()  # 最后更新时间
    
    def start(self):
        """启动日志查看器"""
        self.is_running = True
        self.current_line = 0
        
        # 获取终端尺寸
        try:
            terminal_size = os.get_terminal_size()
            self.page_size = terminal_size.lines - 10  # 留出空间显示控制信息
        except:
            self.page_size = 20
        
        # 记录开始时的日志数量
        with self.monitor.event_lock:
            self.last_event_count = len(self.monitor.all_events)
        
        while self.is_running:
            self.display()
            if not self.handle_input():
                break
        
        return True
    
    def display(self):
        """显示日志内容"""
        # 清屏
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # 获取当前事件（线程安全）
        with self.monitor.event_lock:
            current_events = list(self.monitor.all_events)
            event_count = len(current_events)
        
        # 检查是否有新事件
        new_events = False
        if event_count > self.last_event_count:
            new_events = True
            # 如果启用自动滚动，跳到最新
            if self.auto_scroll:
                self.current_line = max(0, event_count - self.page_size)
        
        # 显示标题和控制信息
        print(f"{Colors.BOLD}{Colors.CYAN}{self.title}{Colors.RESET}")
        print(f"{Colors.CYAN}事件总数: {event_count} | 排序方式: {'时间' if self.sort_by_time else '类型'} | 当前位置: {self.current_line+1}/{event_count}{Colors.RESET}")
        if new_events and not self.auto_scroll:
            print(f"{Colors.GREEN}有新事件到达! 按 'a' 切换自动滚动{Colors.RESET}")
        print(f"{Colors.YELLOW}控制: ↑/↓ 滚动 | t 切换排序 | a 切换自动滚动({'开' if self.auto_scroll else '关'}) | s 保存到文件 | q 返回监控{Colors.RESET}")
        print("=" * 80)
        
        # 排序事件
        sorted_events = self._get_sorted_events(current_events)
        
        # 显示当前页的事件
        start_idx = self.current_line
        end_idx = min(start_idx + self.page_size, len(sorted_events))
        
        for i in range(start_idx, end_idx):
            event = sorted_events[i]
            
            # 显示行号 - 修复多余空格问题
            line_no = i + 1
            line_no_color = Colors.CYAN if line_no % 2 == 0 else Colors.BLUE
            # 使用固定宽度4，但左对齐，确保没有多余空格
            print(f"{line_no_color}{line_no:<4}{Colors.RESET} ", end="")
            
            # 显示事件
            print(f"{event}")
        
        # 如果还有更多事件，显示提示
        if end_idx < len(sorted_events):
            print(f"{Colors.CYAN}... 还有 {len(sorted_events) - end_idx} 个事件 ...{Colors.RESET}")
        
        print("=" * 80)
        print(f"{Colors.YELLOW}控制: ↑/↓ 滚动 | t 切换排序 | a 切换自动滚动({'开' if self.auto_scroll else '关'}) | s 保存到文件 | q 返回监控{Colors.RESET}")
        
        # 更新最后显示的事件数量
        self.last_event_count = event_count
        self.last_update_time = time.time()
    
    def _get_sorted_events(self, events):
        """获取排序后的事件列表"""
        if self.sort_by_time:
            # 按时间排序（升序）
            return sorted(events, key=lambda e: e.timestamp)
        else:
            # 按类型分组，组内按时间排序
            events_by_type = {}
            for event in events:
                if event.event_type not in events_by_type:
                    events_by_type[event.event_type] = []
                events_by_type[event.event_type].append(event)
            
            # 对每个类型的事件按时间排序
            for event_type in events_by_type:
                events_by_type[event_type].sort(key=lambda e: e.timestamp)
            
            # 按类型顺序组合
            sorted_events = []
            type_order = ['status_change', 'player_join', 'player_leave', 'player_count', 'info']
            for event_type in type_order:
                if event_type in events_by_type:
                    sorted_events.extend(events_by_type[event_type])
            
            # 添加其他类型的事件
            for event_type in events_by_type:
                if event_type not in type_order:
                    sorted_events.extend(events_by_type[event_type])
            
            return sorted_events
    
    def handle_input(self):
        """处理用户输入"""
        # 非阻塞输入检测
        if os.name == 'nt':
            # Windows平台
            try:
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                    return self._process_key(key)
                else:
                    # 检查是否有新事件（每0.2秒检查一次）
                    current_time = time.time()
                    if current_time - self.last_update_time > 0.2:
                        # 触发一次显示更新
                        return True
                    time.sleep(0.05)  # 减少CPU占用
            except ImportError:
                time.sleep(0.1)
        else:
            # Unix-like平台
            try:
                if sys.stdin in select.select([sys.stdin], [], [], 0.05)[0]:
                    key = sys.stdin.read(1).lower()
                    return self._process_key(key)
                else:
                    # 检查是否有新事件（每0.2秒检查一次）
                    current_time = time.time()
                    if current_time - self.last_update_time > 0.2:
                        # 触发一次显示更新
                        return True
            except:
                time.sleep(0.1)
        
        return True
    
    def _process_key(self, key):
        """处理按键"""
        # 获取当前事件数量
        with self.monitor.event_lock:
            event_count = len(self.monitor.all_events)
        
        if key == 'q':
            self.is_running = False
            return False
        elif key == 't':
            self.sort_by_time = not self.sort_by_time
            self.current_line = 0  # 切换到新排序方式的开始
        elif key == 's':
            self.save_to_file()
        elif key == 'a':
            self.auto_scroll = not self.auto_scroll
            if self.auto_scroll:
                # 如果启用自动滚动，跳到最新
                self.current_line = max(0, event_count - self.page_size)
        elif key in ('\x1b',):  # ESC键开始
            # 处理方向键（对于Windows和Unix不同）
            if os.name == 'nt':
                # Windows处理 - 使用msvcrt获取更多字符
                try:
                    import msvcrt
                    if msvcrt.kbhit():
                        next_char = msvcrt.getch()
                        if next_char == b'H':  # 上箭头
                            self.current_line = max(0, self.current_line - 1)
                        elif next_char == b'P':  # 下箭头
                            self.current_line = min(event_count - 1, self.current_line + 1)
                        elif next_char == b'I':  # Page Up
                            self.current_line = max(0, self.current_line - self.page_size)
                        elif next_char == b'Q':  # Page Down
                            self.current_line = min(event_count - 1, self.current_line + self.page_size)
                except:
                    pass
            else:
                # Unix处理方向键
                if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                    next_chars = sys.stdin.read(2)
                    if next_chars == '[A':  # 上箭头
                        self.current_line = max(0, self.current_line - 1)
                    elif next_chars == '[B':  # 下箭头
                            self.current_line = min(event_count - 1, self.current_line + 1)
                    elif next_chars == '[5':  # Page Up
                        sys.stdin.read(1)  # 消耗'~'字符
                        self.current_line = max(0, self.current_line - self.page_size)
                    elif next_chars == '[6':  # Page Down
                        sys.stdin.read(1)  # 消耗'~'字符
                        self.current_line = min(event_count - 1, self.current_line + self.page_size)
        else:
            # 简单按键处理（Vi风格）
            if key == 'k' or key == 'w':  # 上
                self.current_line = max(0, self.current_line - 1)
            elif key == 'j' or key == 's':  # 下
                self.current_line = min(event_count - 1, self.current_line + 1)
            elif key == 'g':  # 跳到开头
                self.current_line = 0
            elif key == 'G':  # 跳到结尾
                self.current_line = max(0, event_count - self.page_size)
            elif key == ' ':  # 空格键 - 下一页
                self.current_line = min(event_count - 1, self.current_line + self.page_size)
            elif key == 'b':  # 上一页
                self.current_line = max(0, self.current_line - self.page_size)
        
        return True
    
    def save_to_file(self):
        """保存日志到文件"""
        try:
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"monitor_log_{timestamp}.txt"
            
            # 获取事件（线程安全）
            with self.monitor.event_lock:
                events_to_save = list(self.monitor.all_events)
            
            # 写入文件
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"=== 监控日志 ===\n")
                f.write(f"服务器: {self.monitor.server['name']}\n")
                f.write(f"地址: {self.monitor.server['ip']}:{self.monitor.server.get('port', 25565)}\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"事件总数: {len(events_to_save)}\n")
                f.write(f"排序方式: {'按时间' if self.sort_by_time else '按类型'}\n")
                f.write("=" * 60 + "\n\n")
                
                # 排序事件
                sorted_events = self._get_sorted_events(events_to_save)
                
                for event in sorted_events:
                    f.write(event.to_plain_text(include_color=False) + "\n")
            
            print(f"\n{Colors.GREEN}日志已保存到: {filename}{Colors.RESET}")
            input(f"{Colors.CYAN}按回车键继续...{Colors.RESET}")
        except Exception as e:
            print(f"\n{Colors.RED}保存失败: {str(e)}{Colors.RESET}")
            input(f"{Colors.CYAN}按回车键继续...{Colors.RESET}")

# ========== 服务器监控器 ==========
class ServerMonitor:
    """服务器监控器"""
    
    def __init__(self, server_manager, server_index, multi_monitor_mode=False, enable_logging=True):
        """
        初始化服务器监控器
        
        Args:
            server_manager: 服务器管理器实例
            server_index: 服务器索引
            multi_monitor_mode: 是否是多服务器监控模式
            enable_logging: 是否启用日志记录
        """
        self.manager = server_manager
        self.server_index = server_index
        self.server = server_manager.servers[server_index]
        self.all_events = []  # 存储所有事件（无上限）
        self.last_result = None
        self.last_players = set()
        self.last_player_count = -1
        self.is_running = False
        self.refresh_interval = 30
        self.display_max_events = 20  # 监视界面显示的事件数量上限
        self.sort_by_time = True  # 默认按时间排序
        self.enable_logging = enable_logging  # 是否启用日志记录
        
        # 事件队列，用于线程安全的事件添加
        self.event_queue = queue.Queue()
        self.event_lock = threading.Lock()
        
        # 监控线程
        self.monitor_thread = None
        self.monitor_active = False
        
        # 显示控制
        self.pause_display = False
        self.force_refresh = False
        self.last_display_time = 0  # 最后显示时间
        self.last_event_count = 0   # 上次显示时的事件数量
        
        # 多服务器监控模式
        self.multi_monitor_mode = multi_monitor_mode
        if self.multi_monitor_mode:
            self.display_max_events = 10  # 多服务器模式下显示更少的事件
        
        # 初始化开始监控事件
        self.add_event('info', f"开始监控服务器: {self.server['name']}")
        
        # 清理旧日志
        if self.enable_logging:
            MonitorLogger.cleanup_old_logs()
    
    def start(self):
        """开始监控"""
        self.is_running = True
        self.monitor_active = True
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        try:
            while self.is_running:
                # 如果显示没有暂停，显示状态
                if not self.pause_display:
                    self.display_status()
                
                # 处理输入
                if not self.wait_for_input():
                    break
                    
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}监控已中断{Colors.RESET}")
        finally:
            self.stop()
    
    def start_multi_monitor(self):
        """在多服务器监控模式下启动监控（只启动监控线程，不进入单服务器的监控循环）"""
        self.monitor_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _monitor_loop(self):
        """监控循环（在后台线程中运行）"""
        while self.monitor_active:
            # 处理事件队列
            self._process_event_queue()
            
            # 查询服务器状态
            self.check_server_status()
            
            # 等待刷新间隔
            time.sleep(self.refresh_interval)
    
    def check_server_status(self):
        """检查服务器状态变化"""
        server = self.server
        server_type = server.get('type', SERVER_TYPE_JAVA)
        port = server.get('port', 25565 if server_type == SERVER_TYPE_JAVA else 19132)
        
        # 获取MinecraftPing实例
        ping_class = get_minecraft_ping()
        
        # 查询服务器
        current_result = ping_class.ping(
            server['ip'], port, timeout=5, 
            use_cache=False, server_type=server_type
        )
        
        # 更新上次查询时间戳
        server['last_query'] = time.time()
        
        # 检查服务器状态变化
        if self.last_result is not None:
            last_online = 'error' not in self.last_result
            current_online = 'error' not in current_result
            
            if last_online != current_online:
                if current_online:
                    self.add_event('status_change', f"服务器状态: 离线 → 上线")
                else:
                    error_msg = current_result.get('error', '未知错误')
                    self.add_event('status_change', f"服务器状态: 上线 → 离线 ({error_msg})")
        
        # 检查玩家变化（仅当服务器在线时）
        if 'error' not in current_result:
            # 检查玩家数量变化
            current_player_count = 0
            if 'players' in current_result:
                current_player_count = current_result['players'].get('online', 0)
            
            # 只有在有上次记录时才检查变化
            if self.last_player_count >= 0 and current_player_count != self.last_player_count:
                diff = current_player_count - self.last_player_count
                self.add_event('player_count', f"玩家数量变化: {self.last_player_count} → {current_player_count}", diff=diff)
            
            # 更新玩家数量记录
            self.last_player_count = current_player_count
            
            # 检查玩家列表变化（仅Java版）
            if server_type == SERVER_TYPE_JAVA:
                current_players = set()
                if ('players' in current_result and 
                    'sample' in current_result['players']):
                    for player in current_result['players']['sample']:
                        player_name = player.get('name', '未知')
                        # 清理玩家名字中的颜色代码
                        clean_name = ping_class.clean_mc_formatting(player_name)
                        current_players.add(clean_name)
                
                if self.last_players is not None:
                    # 玩家加入
                    new_players = current_players - self.last_players
                    for player in new_players:
                        self.add_event('player_join', f"玩家加入: {player}", player_name=player)
                    
                    # 玩家退出
                    left_players = self.last_players - current_players
                    for player in left_players:
                        self.add_event('player_leave', f"玩家退出: {player}", player_name=player)
                
                self.last_players = current_players
        
        self.last_result = current_result
    
    def add_event(self, event_type, message, player_name=None, diff=None):
        """添加事件到事件列表"""
        event = MonitorEvent(event_type, message, player_name=player_name, diff=diff, server_name=self.server['name'])
        
        # 将事件添加到队列（线程安全）
        self.event_queue.put(event)
        
        # 写入日志文件
        if self.enable_logging:
            MonitorLogger.write_log(
                self.server['name'], 
                event_type, 
                message, 
                player_name=player_name, 
                diff=diff
            )
    
    def _process_event_queue(self):
        """处理事件队列，将事件添加到主列表"""
        try:
            while True:
                event = self.event_queue.get_nowait()
                with self.event_lock:
                    self.all_events.append(event)
        except queue.Empty:
            pass
    
    def display_status(self):
        """显示服务器状态和事件"""
        import os
        
        # 清屏（跨平台）
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # 显示标题和控制信息
        monitor_mode = "多服务器监控" if self.multi_monitor_mode else "单服务器监控"
        print(f"{Colors.BOLD}{Colors.CYAN}服务器监控: {self.server['name']} [{monitor_mode}]{Colors.RESET}")
        print(f"{Colors.CYAN}地址: {self.server['ip']}:{self.server.get('port', 25565 if self.server.get('type', SERVER_TYPE_JAVA) == SERVER_TYPE_JAVA else 19132)}{Colors.RESET}")
        print(f"{Colors.CYAN}刷新间隔: {self.refresh_interval}秒 | 事件总数: {len(self.all_events)} | 排序: {'时间' if self.sort_by_time else '类型'}{Colors.RESET}")
        
        # 显示日志状态
        if self.enable_logging:
            log_files = MonitorLogger.list_log_files(self.server['name'])
            if log_files:
                latest_log = log_files[0]
                print(f"{Colors.CYAN}日志文件: {latest_log['filename']} ({len(log_files)}个文件){Colors.RESET}")
        
        print(f"{Colors.YELLOW}控制: q 返回 | +/- 调整间隔 | r 手动刷新 | t 切换排序 | l 查看完整日志{Colors.RESET}")
        print("=" * 80)
        
        # 显示服务器详细信息
        self.display_server_details()
        
        print("=" * 80)
        
        # 显示最近的事件
        self.display_event_log()
        
        print("=" * 80)
        print(f"{Colors.YELLOW}按 q 返回主菜单{Colors.RESET}")
        
        # 更新最后显示时间
        self.last_display_time = time.time()
        self.last_event_count = len(self.all_events)
    
    def display_server_details(self):
        """显示服务器详细信息"""
        server = self.server
        server_type = server.get('type', SERVER_TYPE_JAVA)
        
        # 序号颜色
        index_color = Colors.CYAN
        if self.last_result and 'error' in self.last_result and ("离线" in self.last_result['error'] or "timed out" in self.last_result['error']):
            index_color = Colors.RED
        elif self.last_result and 'players' in self.last_result and self.last_result['players'].get('online', 0) > 0:
            index_color = Colors.GREEN

        # 服务器类型标识
        server_type = self.last_result.get('server_type', server.get('type', SERVER_TYPE_JAVA)) if self.last_result else server.get('type', SERVER_TYPE_JAVA)
        type_display = f" [{Colors.MAGENTA}基岩版{Colors.RESET}]" if server_type == SERVER_TYPE_BEDROCK else f" [{Colors.BLUE}Java版{Colors.RESET}]"

        print(f"\n{index_color}[监控中]{Colors.RESET} {Colors.BOLD}{server['name']}{type_display}{Colors.RESET}")
        print(f"{Colors.BLUE}地址:{Colors.RESET} {server['ip']}:{server.get('port', 25565 if server_type == SERVER_TYPE_JAVA else 19132)}")
        
        # 显示最后查询时间
        if server.get('last_query', 0) > 0:
            last_query_time = datetime.fromtimestamp(server['last_query']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{Colors.YELLOW}上次查询:{Colors.RESET} {last_query_time}")

        # 显示公告栏
        if self.last_result and 'motd' in self.last_result and self.last_result['motd']:
            # 计算终端宽度
            try:
                terminal_width = os.get_terminal_size().columns
            except:
                terminal_width = 80

            # 分隔线
            print(f"{Colors.CYAN}┌{'─' * (terminal_width - 2)}┐{Colors.RESET}")

            # 显示公告栏内容
            motd = self.last_result['motd']
            print(f"{Colors.CYAN}│{Colors.RESET} {motd}")

            # 分隔线
            print(f"{Colors.CYAN}└{'─' * (terminal_width - 2)}┘{Colors.RESET}")

        if not self.last_result:
            print(f"{Colors.YELLOW}状态: 等待第一次查询...{Colors.RESET}")
        elif 'error' in self.last_result:
            # 离线状态
            if "timed out" in self.last_result['error'] or "离线" in self.last_result['error']:
                error_color = Colors.RED
            else:
                error_color = Colors.YELLOW

            print(f"{error_color}状态: {self.last_result['error']}{Colors.RESET}")
            if self.last_result.get('connect_time', 0) > 0:
                print(f"{Colors.BLUE}连接时间:{Colors.RESET} {self.last_result['connect_time']}ms")
        else:
            # 服务器版本
            version = self.last_result.get('version', {}).get('name', '未知')
            if server_type == SERVER_TYPE_BEDROCK:
                version_color = Colors.MAGENTA
                version_display = f"{version}"
            else:
                if '1.21' in version or '1.20' in version:
                    version_color = Colors.GREEN
                elif '1.19' in version or '1.20' in version:
                    version_color = Colors.YELLOW
                else:
                    version_color = Colors.RED
                version_display = f"{version}"

            print(f"{Colors.BLUE}版本:{Colors.RESET} {version_color}{version_display}{Colors.RESET}")

            # 玩家数量
            players = self.last_result.get('players', {})
            online = players.get('online', 0)
            max_players = players.get('max', 0)

            # 根据在线人数选择颜色
            if online == 0:
                player_color = Colors.RED
            elif online < max_players * 0.5:
                player_color = Colors.YELLOW
            else:
                player_color = Colors.GREEN

            print(f"{Colors.BLUE}玩家:{Colors.RESET} {player_color}{online}{Colors.RESET}/{max_players}")

            # 延迟信息
            if self.last_result.get('query_time', 0) > 0:
                delay_color = Colors.GREEN
                if self.last_result['query_time'] > 500:
                    delay_color = Colors.YELLOW
                if self.last_result['query_time'] > 1000:
                    delay_color = Colors.RED

                delay_info = f"{Colors.BLUE}延迟:{Colors.RESET} {delay_color}{self.last_result['query_time']}ms{Colors.RESET}"
                if self.last_result.get('connect_time', 0) > 0:
                    delay_info += f" ({Colors.BLUE}连接:{Colors.RESET} {self.last_result['connect_time']}ms)"
                print(delay_info)

            # 基岩版特定信息
            if server_type == SERVER_TYPE_BEDROCK:
                if 'game_mode' in self.last_result and self.last_result['game_mode']:
                    print(f"{Colors.BLUE}游戏模式:{Colors.RESET} {self.last_result['game_mode']}")
                if 'edition' in self.last_result and self.last_result['edition']:
                    print(f"{Colors.BLUE}版本:{Colors.RESET} {self.last_result['edition']}")
    
    def display_event_log(self):
        """显示事件日志"""
        print(f"\n{Colors.BOLD}事件日志 (显示最近 {min(self.display_max_events, len(self.all_events))} 条):{Colors.RESET}")
        
        if not self.all_events:
            print(f"  {Colors.YELLOW}暂无事件{Colors.RESET}")
            return
        
        # 获取要显示的事件
        events_to_show = self._get_display_events()
        
        for event in events_to_show:
            print(f"  {event}")
    
    def _get_display_events(self):
        """获取要显示的事件列表（根据当前排序方式）"""
        with self.event_lock:
            if self.sort_by_time:
                # 按时间排序，显示最新的
                sorted_events = sorted(self.all_events, key=lambda e: e.timestamp)
                return sorted_events[-self.display_max_events:]
            else:
                # 按类型分组，组内按时间排序
                events_by_type = {}
                for event in self.all_events:
                    if event.event_type not in events_by_type:
                        events_by_type[event.event_type] = []
                    events_by_type[event.event_type].append(event)
                
                # 对每个类型的事件按时间排序
                for event_type in events_by_type:
                    events_by_type[event_type].sort(key=lambda e: e.timestamp)
                
                # 按类型顺序组合，每个类型显示最多5条
                display_events = []
                type_order = ['status_change', 'player_join', 'player_leave', 'player_count', 'info']
                
                for event_type in type_order:
                    if event_type in events_by_type:
                        type_events = events_by_type[event_type]
                        # 取该类型的最新5条
                        display_events.extend(type_events[-5:])
                
                # 添加其他类型的事件
                for event_type in events_by_type:
                    if event_type not in type_order:
                        type_events = events_by_type[event_type]
                        display_events.extend(type_events[-3:])  # 其他类型显示3条
                
                # 按时间排序，取最新的
                display_events.sort(key=lambda e: e.timestamp)
                return display_events[-self.display_max_events:]
    
    def show_full_log(self):
        """显示完整日志查看器"""
        print(f"{Colors.CYAN}加载完整日志...{Colors.RESET}")
        time.sleep(0.5)  # 给用户时间看到提示
        
        # 暂停显示，但不停止监控
        self.pause_display = True
        
        # 创建日志查看器并启动
        viewer = LogViewer(self)
        viewer.start()
        
        # 恢复显示
        self.pause_display = False
        print(f"{Colors.GREEN}已退出日志查看器，返回监控界面{Colors.RESET}")
        time.sleep(0.5)  # 短暂延迟后显示监控界面
    
    def wait_for_input(self):
        """等待用户输入（非阻塞）"""
        # 非阻塞输入检测
        if os.name == 'nt':
            # Windows平台
            try:
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                    return self._handle_key(key)
            except ImportError:
                pass
        else:
            # Unix-like平台
            try:
                if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                    try:
                        key = sys.stdin.read(1).lower()
                        return self._handle_key(key)
                    except (KeyboardInterrupt, EOFError):
                        return False
            except:
                pass
        
        # 检查是否应该刷新显示（只有当事件数量变化时才刷新）
        current_event_count = len(self.all_events)
        if current_event_count != self.last_event_count and not self.pause_display:
            # 触发一次显示更新
            self.last_event_count = current_event_count
            return True
        
        # 短暂延迟，减少CPU占用和闪烁
        time.sleep(0.1)
        return True  # 继续监控
    
    def _handle_key(self, key):
        """处理按键"""
        if key == 'q':
            return False
        elif key == '+':
            self.refresh_interval = min(300, self.refresh_interval + 5)
            self.add_event('info', f"刷新间隔增加至 {self.refresh_interval}秒")
            return True  # 立即刷新显示
        elif key == '-':
            self.refresh_interval = max(5, self.refresh_interval - 5)
            self.add_event('info', f"刷新间隔减少至 {self.refresh_interval}秒")
            return True  # 立即刷新显示
        elif key == 'r':
            # 手动刷新：直接执行一次检查
            self.add_event('info', "手动刷新")
            self.check_server_status()  # 直接执行检查
            return True  # 立即刷新显示
        elif key == 't':
            self.sort_by_time = not self.sort_by_time
            self.add_event('info', f"排序方式切换为: {'按时间' if self.sort_by_time else '按类型'}")
            return True  # 立即刷新显示
        elif key == 'l':
            # 显示完整日志
            self.show_full_log()
            return True  # 返回监控界面
        else:
            return True  # 继续监控
    
    def stop(self):
        """停止监控"""
        self.is_running = False
        self.monitor_active = False
        
        # 等待监控线程结束
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        
        self.add_event('info', f"停止监控服务器: {self.server['name']}")

# ========== 多服务器监控器 ==========
class MultiServerMonitor:
    """多服务器监控器，支持同时监控多个服务器"""
    
    def __init__(self, server_manager, server_indices, enable_logging=True):
        """
        初始化多服务器监控器
        
        Args:
            server_manager: 服务器管理器实例
            server_indices: 服务器索引列表
            enable_logging: 是否启用日志记录
        """
        self.manager = server_manager
        self.server_indices = server_indices
        self.servers = [server_manager.servers[i] for i in server_indices]
        self.monitors = []
        self.is_running = False
        self.refresh_interval = 30
        self.last_display_time = 0
        self.last_event_counts = {}  # 每个服务器上次显示时的事件数量
        self.enable_logging = enable_logging
        
        # 创建每个服务器的监控器
        for server_index in server_indices:
            monitor = ServerMonitor(server_manager, server_index, multi_monitor_mode=True, enable_logging=enable_logging)
            self.monitors.append(monitor)
            self.last_event_counts[server_index] = 0
        
        # 清理旧日志
        if self.enable_logging:
            MonitorLogger.cleanup_old_logs()
    
    def start(self):
        """开始多服务器监控"""
        self.is_running = True
        
        print(f"{Colors.GREEN}开始监控 {len(self.monitors)} 个服务器...{Colors.RESET}")
        time.sleep(1)
        
        # 启动所有监控器（后台模式）- 使用新添加的start_multi_monitor方法
        for monitor in self.monitors:
            monitor.start_multi_monitor()
        
        try:
            while self.is_running:
                # 显示多服务器状态
                self.display_multi_status()
                
                # 处理输入
                if not self.wait_for_input():
                    break
                    
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}多服务器监控已中断{Colors.RESET}")
        finally:
            self.stop()
    
    def display_multi_status(self):
        """显示多服务器状态"""
        import os
        
        # 清屏（跨平台）
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # 显示标题和控制信息
        print(f"{Colors.BOLD}{Colors.CYAN}多服务器监控 ({len(self.monitors)}个服务器){Colors.RESET}")
        print(f"{Colors.CYAN}刷新间隔: {self.refresh_interval}秒 | 总事件数: {sum(len(m.all_events) for m in self.monitors)}{Colors.RESET}")
        
        # 显示日志状态
        if self.enable_logging:
            total_log_files = 0
            for server in self.servers:
                log_files = MonitorLogger.list_log_files(server['name'])
                total_log_files += len(log_files)
            if total_log_files > 0:
                print(f"{Colors.CYAN}日志文件: 共 {total_log_files} 个日志文件{Colors.RESET}")
        
        print(f"{Colors.YELLOW}控制: q 返回 | +/- 调整间隔 | r 手动刷新 | l 查看完整日志 | f 按服务器查看日志{Colors.RESET}")
        print("=" * 80)
        
        # 显示所有服务器状态
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}服务器状态概览:{Colors.RESET}\n")
        
        for i, monitor in enumerate(self.monitors):
            server = monitor.server
            server_type = server.get('type', SERVER_TYPE_JAVA)
            server_index = self.server_indices[i]
            
            # 服务器状态颜色
            status_color = Colors.RED
            status_text = "离线"
            player_count = 0
            max_players = 0
            
            if monitor.last_result and 'error' not in monitor.last_result:
                status_color = Colors.GREEN
                status_text = "在线"
                player_count = monitor.last_result.get('players', {}).get('online', 0)
                max_players = monitor.last_result.get('players', {}).get('max', 0)
            elif monitor.last_result and 'error' in monitor.last_result:
                if "timed out" in monitor.last_result['error'] or "离线" in monitor.last_result['error']:
                    status_color = Colors.RED
                    status_text = "离线"
                else:
                    status_color = Colors.YELLOW
                    status_text = "错误"
            
            # 服务器类型标识
            type_display = f" [{Colors.MAGENTA}基岩{Colors.RESET}]" if server_type == SERVER_TYPE_BEDROCK else f" [{Colors.BLUE}Java{Colors.RESET}]"
            
            # 显示服务器信息 - 修复序号多余空格问题
            server_idx = server_index + 1
            # 使用左对齐的固定宽度2，确保没有多余空格
            print(f"{Colors.CYAN}[{server_idx:<2}]{Colors.RESET} {Colors.BOLD}{server['name']}{type_display}{Colors.RESET}")
            print(f"     地址: {server['ip']}:{server.get('port', 25565 if server_type == SERVER_TYPE_JAVA else 19132)}")
            print(f"     状态: {status_color}{status_text}{Colors.RESET}", end="")
            
            if status_text == "在线":
                # 玩家数量颜色
                player_color = Colors.GREEN
                if player_count == 0:
                    player_color = Colors.RED
                elif player_count < max_players * 0.5:
                    player_color = Colors.YELLOW
                
                print(f" | 玩家: {player_color}{player_count}{Colors.RESET}/{max_players}", end="")
                
                # 显示延迟（如果可用）
                if monitor.last_result and monitor.last_result.get('query_time', 0) > 0:
                    delay_color = Colors.GREEN
                    if monitor.last_result['query_time'] > 500:
                        delay_color = Colors.YELLOW
                    if monitor.last_result['query_time'] > 1000:
                        delay_color = Colors.RED
                    
                    print(f" | 延迟: {delay_color}{monitor.last_result['query_time']}ms{Colors.RESET}", end="")
            
            print()  # 换行
            
            # 显示最近事件
            with monitor.event_lock:
                recent_events = monitor.all_events[-3:]  # 显示最近3条事件
            
            if recent_events:
                for event in recent_events:
                    print(f"        {event}")
            else:
                print(f"        {Colors.YELLOW}暂无事件{Colors.RESET}")
            
            print()  # 空行分隔
        
        print("=" * 80)
        print(f"{Colors.YELLOW}按 q 返回主菜单{Colors.RESET}")
        
        # 更新最后显示时间
        self.last_display_time = time.time()
    
    def wait_for_input(self):
        """等待用户输入（非阻塞）"""
        # 非阻塞输入检测
        if os.name == 'nt':
            # Windows平台
            try:
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                    return self._handle_key(key)
            except ImportError:
                pass
        else:
            # Unix-like平台
            try:
                if sys.stdin in select.select([sys.stdin], [], [], 0.5)[0]:
                    try:
                        key = sys.stdin.read(1).lower()
                        return self._handle_key(key)
                    except (KeyboardInterrupt, EOFError):
                        return False
            except:
                pass
        
        # 检查是否有服务器事件数量发生变化，如果有则刷新
        need_refresh = False
        for i, monitor in enumerate(self.monitors):
            server_index = self.server_indices[i]
            current_count = len(monitor.all_events)
            if current_count != self.last_event_counts.get(server_index, 0):
                self.last_event_counts[server_index] = current_count
                need_refresh = True
        
        # 如果有变化，刷新显示
        if need_refresh:
            return True
        
        # 短暂延迟，减少CPU占用和闪烁
        time.sleep(0.1)
        return True
    
    def _handle_key(self, key):
        """处理按键"""
        if key == 'q':
            return False
        elif key == '+':
            self.refresh_interval = min(300, self.refresh_interval + 5)
            for monitor in self.monitors:
                monitor.refresh_interval = self.refresh_interval
                monitor.add_event('info', f"刷新间隔增加至 {self.refresh_interval}秒")
            return True
        elif key == '-':
            self.refresh_interval = max(5, self.refresh_interval - 5)
            for monitor in self.monitors:
                monitor.refresh_interval = self.refresh_interval
                monitor.add_event('info', f"刷新间隔减少至 {self.refresh_interval}秒")
            return True
        elif key == 'r':
            # 手动刷新所有服务器
            for monitor in self.monitors:
                monitor.add_event('info', "手动刷新")
                monitor.check_server_status()
            return True
        elif key == 'l':
            # 显示合并日志查看器
            self.show_merged_log()
            return True
        elif key == 'f':
            # 显示按服务器分类的日志查看器
            self.show_server_categorized_log()
            return True
        else:
            return True
    
    def show_merged_log(self):
        """显示合并日志查看器"""
        print(f"{Colors.CYAN}加载合并日志...{Colors.RESET}")
        time.sleep(0.5)
        
        # 创建多服务器日志查看器并启动
        viewer = MultiServerLogViewer(self.monitors)
        viewer.start()
        
        print(f"{Colors.GREEN}已退出日志查看器，返回监控界面{Colors.RESET}")
        time.sleep(0.5)
    
    def show_server_categorized_log(self):
        """显示按服务器分类的日志查看器"""
        print(f"{Colors.CYAN}加载按服务器分类的日志...{Colors.RESET}")
        time.sleep(0.5)
        
        # 创建多服务器日志查看器并设置为按服务器分类模式
        viewer = MultiServerLogViewer(self.monitors)
        viewer.view_mode = 'server'
        viewer.start()
        
        print(f"{Colors.GREEN}已退出日志查看器，返回监控界面{Colors.RESET}")
        time.sleep(0.5)
    
    def stop(self):
        """停止多服务器监控"""
        self.is_running = False
        
        # 停止所有监控器
        for monitor in self.monitors:
            monitor.stop()
        
        print(f"{Colors.GREEN}已停止多服务器监控{Colors.RESET}")

# ========== 日志查看和导出功能 ==========
def show_monitor_logs(server_manager, server_name=None, max_lines=50):
    """显示监控日志"""
    print(f"{Colors.BOLD}{Colors.CYAN}监控日志查看器{Colors.RESET}")
    
    if server_name:
        print(f"{Colors.CYAN}服务器: {server_name}{Colors.RESET}")
    else:
        print(f"{Colors.CYAN}显示所有服务器的监控日志{Colors.RESET}")
    
    # 列出日志文件
    log_files = MonitorLogger.list_log_files(server_name)
    
    if not log_files:
        print(f"{Colors.YELLOW}未找到日志文件{Colors.RESET}")
        return
    
    print(f"{Colors.CYAN}找到 {len(log_files)} 个日志文件:{Colors.RESET}")
    for i, log_file in enumerate(log_files[:10]):  # 只显示前10个
        size_kb = log_file['size'] / 1024
        print(f"  {Colors.CYAN}{i+1}.{Colors.RESET} {log_file['filename']} ({size_kb:.1f}KB, {log_file['modified']})")
    
    if len(log_files) > 10:
        print(f"  {Colors.CYAN}... 还有 {len(log_files) - 10} 个文件{Colors.RESET}")
    
    # 读取并显示日志
    logs = MonitorLogger.read_logs(server_name, max_lines=max_lines)
    
    if not logs:
        print(f"\n{Colors.YELLOW}未找到日志记录{Colors.RESET}")
        return
    
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}最近 {len(logs)} 条日志记录:{Colors.RESET}")
    print("-" * 80)
    
    for i, log in enumerate(logs):
        timestamp = log.get('timestamp', '未知时间')
        log_server_name = log.get('server_name', '未知服务器')
        event_type = log.get('event_type', '未知')
        message = log.get('message', '')
        player_name = log.get('player_name')
        diff = log.get('diff')
        
        # 确定颜色
        if event_type == 'status_change':
            color = Colors.YELLOW
        elif event_type == 'player_join':
            color = Colors.GREEN
        elif event_type == 'player_leave':
            color = Colors.RED
        elif event_type == 'player_count':
            color = Colors.CYAN
        elif event_type == 'info':
            color = Colors.BLUE
        else:
            color = Colors.WHITE
        
        # 显示日志
        server_prefix = f"[{log_server_name}] " if server_name is None else ""
        diff_text = f" ({'+' if diff > 0 else ''}{diff})" if diff is not None else ""
        
        print(f"{Colors.CYAN}{timestamp}{Colors.RESET} {server_prefix}{color}{message}{diff_text}{Colors.RESET}")
        
        # 每10条日志暂停一次
        if (i + 1) % 10 == 0 and i + 1 < len(logs):
            input(f"{Colors.CYAN}按回车键继续显示...{Colors.RESET}")
            print("-" * 80)
    
    print("-" * 80)
    print(f"{Colors.GREEN}共显示 {len(logs)} 条日志记录{Colors.RESET}")
    
    # 提供导出选项
    try:
        export_choice = input(f"{Colors.YELLOW}是否导出这些日志? (y/N): {Colors.RESET}").strip().lower()
        if export_choice == 'y':
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_file = f"exported_logs_{timestamp}.json"
            
            if MonitorLogger.export_logs_to_file(server_name, output_file=export_file):
                print(f"{Colors.GREEN}日志已导出到: {export_file}{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        pass
    
    input(f"{Colors.CYAN}按回车键返回主菜单...{Colors.RESET}")

def export_monitor_logs(server_manager, server_name=None, date=None):
    """导出监控日志"""
    print(f"{Colors.BOLD}{Colors.CYAN}导出监控日志{Colors.RESET}")
    
    if server_name:
        print(f"{Colors.CYAN}服务器: {server_name}{Colors.RESET}")
    if date:
        print(f"{Colors.CYAN}日期: {date}{Colors.RESET}")
    
    # 获取日志文件信息
    log_files = MonitorLogger.list_log_files(server_name)
    
    if not log_files:
        print(f"{Colors.YELLOW}未找到日志文件{Colors.RESET}")
        return False
    
    print(f"{Colors.CYAN}找到 {len(log_files)} 个日志文件，总大小: {sum(f['size'] for f in log_files) / 1024:.1f}KB{Colors.RESET}")
    
    # 导出日志
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if server_name and date:
        export_file = f"export_{server_name}_{date}_{timestamp}.json"
    elif server_name:
        export_file = f"export_{server_name}_{timestamp}.json"
    elif date:
        export_file = f"export_{date}_{timestamp}.json"
    else:
        export_file = f"export_all_{timestamp}.json"
    
    if MonitorLogger.export_logs_to_file(server_name, date, export_file):
        print(f"{Colors.GREEN}日志导出成功!{Colors.RESET}")
        return True
    else:
        print(f"{Colors.RED}日志导出失败{Colors.RESET}")
        return False

def cleanup_monitor_logs(server_manager, keep_files=50):
    """清理监控日志"""
    print(f"{Colors.BOLD}{Colors.CYAN}清理监控日志{Colors.RESET}")
    print(f"{Colors.CYAN}将保留最新的 {keep_files} 个日志文件{Colors.RESET}")
    
    confirm = input(f"{Colors.YELLOW}确定要清理旧的日志文件吗? (y/N): {Colors.RESET}").strip().lower()
    if confirm != 'y':
        print(f"{Colors.YELLOW}操作已取消{Colors.RESET}")
        return False
    
    deleted_count = MonitorLogger.cleanup_old_logs(keep_files)
    
    if deleted_count > 0:
        print(f"{Colors.GREEN}已删除 {deleted_count} 个旧的日志文件{Colors.RESET}")
    else:
        print(f"{Colors.CYAN}无需清理，日志文件数量未超过限制{Colors.RESET}")
    
    input(f"{Colors.CYAN}按回车键返回主菜单...{Colors.RESET}")
    return deleted_count > 0

# ========== 接口函数 ==========
def monitor_server(server_manager, server_index):
    """监控单个服务器（用于server.py调用）"""
    if server_index < 0 or server_index >= len(server_manager.servers):
        print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
        return False
    
    monitor = ServerMonitor(server_manager, server_index)
    monitor.start()
    return True

def monitor_multiple_servers(server_manager, server_indices):
    """监控多个服务器（用于server.py调用）"""
    if not server_indices:
        print(f"{Colors.RED}没有指定有效的服务器序号{Colors.RESET}")
        return False
    
    # 检查所有索引是否有效
    valid_indices = []
    for idx in server_indices:
        if 0 <= idx < len(server_manager.servers):
            valid_indices.append(idx)
        else:
            print(f"{Colors.YELLOW}警告: 服务器序号 {idx+1} 无效，跳过{Colors.RESET}")
    
    if not valid_indices:
        print(f"{Colors.RED}没有有效的服务器序号{Colors.RESET}")
        return False
    
    if len(valid_indices) == 1:
        # 单个服务器，使用单服务器监控
        return monitor_server(server_manager, valid_indices[0])
    else:
        # 多个服务器，使用多服务器监控
        monitor = MultiServerMonitor(server_manager, valid_indices)
        monitor.start()
        return True

def monitor_all_servers(server_manager):
    """监控所有服务器（用于server.py调用）"""
    if not server_manager.servers:
        print(f"{Colors.RED}没有可监控的服务器{Colors.RESET}")
        return False
    
    indices = list(range(len(server_manager.servers)))
    return monitor_multiple_servers(server_manager, indices)

# ========== 主入口点 ==========
if __name__ == "__main__":
    # 独立运行支持
    parser = argparse.ArgumentParser(description='Minecraft服务器监控工具')
    parser.add_argument('servers', nargs='*', help='服务器地址格式: 1) 服务器序号 2) IP:端口 3) IP:端口:类型')
    parser.add_argument('-i', '--interval', type=int, default=30, help='刷新间隔（秒）')
    parser.add_argument('-j', '--json', type=str, help='使用JSON配置文件')
    parser.add_argument('-t', '--type', choices=['java', 'bedrock'], default='java', help='服务器类型（当使用IP:端口时）')
    parser.add_argument('-l', '--log', action='store_true', help='查看日志')
    parser.add_argument('-e', '--export', action='store_true', help='导出日志')
    parser.add_argument('-c', '--cleanup', action='store_true', help='清理旧日志')
    
    args = parser.parse_args()
    
    print(f"{Colors.BOLD}{Colors.CYAN}Minecraft服务器监控工具{Colors.RESET}")
    
    # 处理日志相关命令
    if args.log:
        show_monitor_logs(None)
        sys.exit(0)
    elif args.export:
        export_monitor_logs(None)
        sys.exit(0)
    elif args.cleanup:
        cleanup_monitor_logs(None)
        sys.exit(0)
    
    # 检查是否有服务器参数
    if not args.servers:
        print(f"{Colors.YELLOW}使用说明:{Colors.RESET}")
        print(f"  1. 监控服务器: python server_monitor.py <服务器序号或地址>")
        print(f"  2. 查看日志: python server_monitor.py -l")
        print(f"  3. 导出日志: python server_monitor.py -e")
        print(f"  4. 清理日志: python server_monitor.py -c")
        print()
        print(f"{Colors.CYAN}示例:{Colors.RESET}")
        print(f"  python server_monitor.py 1 2 3")
        print(f"  python server_monitor.py mc.hypixel.net:25565")
        print(f"  python server_monitor.py -l")
        sys.exit(0)
    
    print(f"{Colors.CYAN}参数: {args}{Colors.RESET}")
    
    # 简单示例 - 创建模拟服务器列表
    servers = [
        {'name': '示例服务器1', 'ip': 'mc.hypixel.net', 'port': 25565, 'type': 'java'},
        {'name': '示例服务器2', 'ip': 'play.example.com', 'port': 19132, 'type': 'bedrock'}
    ]
    
    # 创建简单的ServerManager
    class SimpleServerManager:
        def __init__(self, servers):
            self.servers = servers
    
    manager = SimpleServerManager(servers)
    
    # 启动监控
    monitor = MultiServerMonitor(manager, [0, 1])
    monitor.start()