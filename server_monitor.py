"""
server_monitor.py - Minecraft服务器监控模块
提供服务器状态监控、事件记录和日志查看功能
"""

import os
import time
import json
import threading
import queue
from collections import deque
from datetime import datetime
import select
import sys

# 导入主程序的颜色类
try:
    from server import Colors, MinecraftPing, SERVER_TYPE_JAVA, SERVER_TYPE_BEDROCK
except ImportError:
    # 如果单独运行模块，定义基本的颜色和类型
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

    class MinecraftPing:
        @staticmethod
        def clean_mc_formatting(text):
            import re
            return re.sub(r'§[0-9a-fklmnor]', '', text)
        
        @staticmethod
        def safe_convert_mc_formatting(text, context_color='\033[0m'):
            return text + context_color


# === 监控事件类 ===
class MonitorEvent:
    """监控事件类"""
    
    EVENT_TYPES = {
        'status_change': '状态变化',
        'player_join': '玩家加入',
        'player_leave': '玩家退出',
        'player_count': '玩家数量变化',
        'info': '信息'
    }
    
    def __init__(self, event_type, message, timestamp=None, player_name=None, diff=None):
        """
        初始化监控事件
        
        Args:
            event_type: 事件类型 ('status_change', 'player_join', 'player_leave', 'player_count', 'info')
            message: 事件消息
            timestamp: 时间戳（默认当前时间）
            player_name: 玩家名称（可选）
            diff: 变化量（用于玩家数量变化事件）
        """
        self.event_type = event_type
        self.message = message
        self.timestamp = timestamp or time.time()
        self.player_name = player_name
        self.diff = diff  # 变化量
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
            'type_display': self.get_type_display(),
            'time_display': self.format_time()
        }
    
    def to_plain_text(self, include_color=True):
        """转换为纯文本"""
        if include_color:
            return f"{Colors.CYAN}[{self.format_time()}]{self.color} {self.message}{Colors.RESET}"
        else:
            return f"[{self.format_time()}] {self.get_type_display()}: {self.message}"
    
    def __str__(self):
        # 如果有变化量，在消息后添加变化量显示
        if self.diff is not None:
            diff_color = Colors.GREEN if self.diff > 0 else Colors.RED
            diff_sign = "+" if self.diff > 0 else ""
            return f"{Colors.CYAN}[{self.format_time()}]{self.color} {self.message} {diff_color}({diff_sign}{self.diff}){Colors.RESET}"
        else:
            return f"{Colors.CYAN}[{self.format_time()}]{self.color} {self.message}{Colors.RESET}"
    
    def __lt__(self, other):
        """用于排序：按时间戳比较"""
        return self.timestamp < other.timestamp


# === 日志查看器 ===
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
            
            # 显示行号
            line_no = i + 1
            line_no_color = Colors.CYAN if line_no % 2 == 0 else Colors.BLUE
            print(f"{line_no_color}{line_no:4d}{Colors.RESET} ", end="")
            
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


# === 服务器监控器 ===
class ServerMonitor:
    """服务器监控器"""
    
    def __init__(self, server_manager, server_index):
        """
        初始化服务器监控器
        
        Args:
            server_manager: 服务器管理器实例
            server_index: 服务器索引
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
    
    def start(self):
        """开始监控"""
        self.is_running = True
        self.monitor_active = True
        self.all_events.clear()
        self.last_player_count = -1
        
        # 添加开始监控事件
        self.add_event('info', f"开始监控服务器: {self.server['name']}")
        
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
        
        # 查询服务器
        current_result = MinecraftPing.ping(
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
                        clean_name = MinecraftPing.clean_mc_formatting(player_name)
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
        event = MonitorEvent(event_type, message, player_name=player_name, diff=diff)
        
        # 将事件添加到队列（线程安全）
        self.event_queue.put(event)
    
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
        print(f"{Colors.BOLD}{Colors.CYAN}服务器监控: {self.server['name']}{Colors.RESET}")
        print(f"{Colors.CYAN}地址: {self.server['ip']}:{self.server.get('port', 25565 if self.server.get('type', SERVER_TYPE_JAVA) == SERVER_TYPE_JAVA else 19132)}{Colors.RESET}")
        print(f"{Colors.CYAN}刷新间隔: {self.refresh_interval}秒 | 事件总数: {len(self.all_events)} | 排序: {'时间' if self.sort_by_time else '类型'}{Colors.RESET}")
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
        
        # 检查是否应该刷新显示（每0.5秒检查一次）
        current_time = time.time()
        if current_time - self.last_display_time > 0.5 and not self.pause_display:
            # 触发一次显示更新
            return True
        
        # 短暂延迟，减少CPU占用
        time.sleep(0.05)
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