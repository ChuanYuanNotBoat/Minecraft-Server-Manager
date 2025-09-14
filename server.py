import os
import json
import socket
import struct
import time
import select
import sys
import threading
import signal
import re
from datetime import datetime
import queue
from collections import deque
import random

# 配置文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "servers.json")

# 检测操作系统并设置颜色支持
IS_WINDOWS = os.name == 'nt'

# ANSI 颜色代码
class Colors:
    if IS_WINDOWS:
        # Windows下启用ANSI转义序列支持
        os.system('')  # 这行命令启用Windows 10+的ANSI转义序列支持

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

    # 背景色
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'

# 全局查询取消标志
global_cancel_query = False

# 尝试导入server_info模块
try:
    from server_info import ServerInfoInterface, MinecraftQuery, MinecraftChatClient
    SERVER_INFO_AVAILABLE = True
except ImportError:
    SERVER_INFO_AVAILABLE = False
    print(f"{Colors.YELLOW}警告: 未找到server_info模块，详细查询功能将受限{Colors.RESET}")

# 全局聊天客户端实例
global_chat_client = None

class MinecraftPing:
    """改进的MC服务器ping实现，支持Java版和基岩版"""

    # 缓存结果（服务器地址 -> (结果, 过期时间)）
    cache = {}
    CACHE_DURATION = 60  # 缓存时间（秒）

    @staticmethod
    def detect_server_type(host, port=25565, timeout=3):
        """尝试自动检测服务器类型"""
        try:
            # 先尝试Java版
            result = MinecraftPing.ping_java(host, port, timeout)
            if 'error' not in result:
                return "java"

            # 再尝试基岩版（使用默认基岩版端口）
            result = MinecraftPing.ping_bedrock(host, 19132, timeout)
            if 'error' not in result:
                return "bedrock"

            # 如果指定了非默认端口，也尝试基岩版
            if port != 19132:
                result = MinecraftPing.ping_bedrock(host, port, timeout)
                if 'error' not in result:
                    return "bedrock"

        except Exception:
            pass

        return "unknown"

    @staticmethod
    def ping(host, port=25565, timeout=3, use_cache=True, server_type="java"):
        global global_cancel_query

        # 检查取消标志
        if global_cancel_query:
            return {"error": "查询已取消", "connect_time": 0, "query_time": 0}

        # 检查缓存
        cache_key = f"{host}:{port}:{server_type}"
        if use_cache and cache_key in MinecraftPing.cache:
            cached_data, expiry = MinecraftPing.cache[cache_key]
            if time.time() < expiry:
                return cached_data

        try:
            # 根据服务器类型选择ping方法
            if server_type == "bedrock":
                result = MinecraftPing.ping_bedrock(host, port, timeout)
            else:  # 默认为Java版
                result = MinecraftPing.ping_java(host, port, timeout)

            # 添加查询时间戳
            result['query_timestamp'] = time.time()

            # 更新缓存
            MinecraftPing.cache[cache_key] = (result, time.time() + MinecraftPing.CACHE_DURATION)

            return result
        except Exception as e:
            return {"error": str(e), "connect_time": 0, "query_time": 0, "motd": "", "server_type": server_type}

    @staticmethod
    def ping_java(host, port=25565, timeout=3):
        """Java版服务器ping实现"""
        global global_cancel_query

        try:
            # 解析主机名
            try:
                ip = socket.getaddrinfo(host, port, socket.AF_INET)[0][4][0]
            except:
                ip = host

            # 创建TCP连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)

            # 设置超时连接
            start_time = time.time()
            sock.connect((ip, port))
            connect_time = int((time.time() - start_time) * 1000)

            # 构建握手包
            protocol_version = -1
            handshake = bytearray()
            handshake.append(0x00)  # 包ID (Handshake)
            handshake.extend(MinecraftPing._pack_varint(protocol_version))
            handshake.extend(MinecraftPing._pack_string(host))
            handshake.extend(struct.pack('>H', port))
            handshake.extend(MinecraftPing._pack_varint(1))  # Next state: status

            # 构建完整包
            packet = bytearray()
            packet.extend(MinecraftPing._pack_varint(len(handshake)))
            packet.extend(handshake)

            # 发送状态请求包
            request = b'\x01\x00'  # Packet ID (0x01) + length (0)

            # 发送数据
            sock.sendall(packet)
            sock.sendall(request)

            # 使用select处理超时
            ready = select.select([sock], [], [], timeout)
            if not ready[0]:
                raise Exception("服务器响应超时")

            # 读取响应长度
            resp_length = MinecraftPing._read_varint(sock)
            if resp_length < 1:
                raise Exception("无效的响应长度")

            # 读取响应ID
            resp_id = MinecraftPing._read_varint(sock)
            if resp_id != 0x00:
                raise Exception(f"无效的响应ID: {resp_id}")

            # 读取JSON长度
            json_length = MinecraftPing._read_varint(sock)
            if json_length < 1:
                raise Exception("无效的JSON长度")

            # 读取JSON数据
            json_data = b''
            while len(json_data) < json_length:
                # 检查取消标志
                if global_cancel_query:
                    sock.close()
                    return {"error": "查询已取消", "connect_time": 0, "query_time": 0}

                chunk = sock.recv(min(4096, json_length - len(json_data)))
                if not chunk:
                    raise Exception("连接中断")
                json_data += chunk

            # 关闭连接
            sock.close()

            # 解析JSON
            result = json.loads(json_data.decode('utf-8'))
            result['connect_time'] = connect_time
            result['query_time'] = int((time.time() - start_time) * 1000)

            # 解析公告栏
            result['motd'] = MinecraftPing.parse_motd(result.get('description', ''))
            result['server_type'] = 'java'

            return result
        except Exception as e:
            return {"error": str(e), "connect_time": 0, "query_time": 0, "motd": "", "server_type": "java"}

    @staticmethod
    def ping_bedrock(host, port=19132, timeout=3):
        """基岩版服务器ping实现"""
        global global_cancel_query

        try:
            # 解析主机名
            try:
                ip = socket.getaddrinfo(host, port, socket.AF_INET)[0][4][0]
            except:
                ip = host

            # 创建UDP连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)

            # 构建未连接ping包
            packet = bytearray()
            packet.extend(b'\x01')  # 包ID (Unconnected Ping)
            packet.extend(struct.pack('>Q', int(time.time() * 1000)))  # 时间戳
            packet.extend(b'\x00\x00\x00\x00\x00\x00\x00\x00')  # Magic
            packet.extend(struct.pack('>Q', 0))  # 客户端GUID

            # 设置超时连接
            start_time = time.time()

            # 发送数据
            sock.sendto(packet, (ip, port))

            # 接收响应
            data, addr = sock.recvfrom(4096)

            # 关闭连接
            sock.close()

            query_time = int((time.time() - start_time) * 1000)

            # 解析响应
            if data[0] != 0x1C:  # Unconnected Pong
                raise Exception("无效的响应包")

            # 跳过时间戳和服务器GUID
            offset = 1 + 8 + 8 + 16  # 包ID + 时间戳 + 服务器GUID + Magic

            # 读取服务器信息字符串 - 修复编码问题
            try:
                server_info_str = data[offset:].decode('utf-8')
            except UnicodeDecodeError:
                # 如果UTF-8解码失败，尝试使用latin-1编码
                server_info_str = data[offset:].decode('latin-1')

            server_info = server_info_str.split(';')

            # 解析服务器信息
            result = {
                'server_type': 'bedrock',
                'query_time': query_time,
                'connect_time': query_time,  # UDP没有单独的连接时间
                'edition': server_info[0] if len(server_info) > 0 else '',
                'motd_line1': server_info[1] if len(server_info) > 1 else '',
                'protocol_version': server_info[2] if len(server_info) > 2 else '',
                'version': server_info[3] if len(server_info) > 3 else '',
                'online_players': int(server_info[4]) if len(server_info) > 4 and server_info[4].isdigit() else 0,
                'max_players': int(server_info[5]) if len(server_info) > 5 and server_info[5].isdigit() else 0,
                'server_id': server_info[6] if len(server_info) > 6 else '',
                'submotd': server_info[7] if len(server_info) > 7 else '',
                'game_mode': server_info[8] if len(server_info) > 8 else '',
                'game_mode_numeric': int(server_info[9]) if len(server_info) > 9 and server_info[9].isdigit() else 0,
                'port_ipv4': int(server_info[10]) if len(server_info) > 10 and server_info[10].isdigit() else 0,
                'port_ipv6': int(server_info[11]) if len(server_info) > 11 and server_info[11].isdigit() else 0,
            }

            # 构建MOTD
            result['motd'] = MinecraftPing.parse_motd(f"{result.get('motd_line1', '')}\n{result.get('submotd', '')}")

            # 构建玩家信息（与Java版格式保持一致）
            result['players'] = {
                'online': result['online_players'],
                'max': result['max_players']
            }

            # 构建版本信息（与Java版格式保持一致）
            result['version'] = {
                'name': result.get('version', ''),
                'protocol': result.get('protocol_version', '')
            }

            return result
        except Exception as e:
            return {"error": str(e), "connect_time": 0, "query_time": 0, "motd": "", "server_type": "bedrock"}

    @staticmethod
    def parse_motd(motd_data):
        """解析公告栏数据，支持字符串和对象格式"""
        if isinstance(motd_data, str):
            # 处理字符串格式的MOTD
            return MinecraftPing.convert_mc_formatting(motd_data)
        elif isinstance(motd_data, dict):
            # 处理JSON对象格式的MOTD
            return MinecraftPing.parse_motd_object(motd_data)
        return ""

    @staticmethod
    def parse_motd_object(motd_obj):
        """解析JSON对象格式的公告栏"""
        text = ""

        # 提取基本文本
        if 'text' in motd_obj:
            text += motd_obj['text']

        # 处理额外文本部分
        if 'extra' in motd_obj and isinstance(motd_obj['extra'], list):
            for extra in motd_obj['extra']:
                if isinstance(extra, dict):
                    text += MinecraftPing.parse_motd_object(extra)
                elif isinstance(extra, str):
                    text += extra

        # 应用格式化和颜色
        return MinecraftPing.convert_mc_formatting(text)

    @staticmethod
    def convert_mc_formatting(text):
        """将Minecraft格式代码转换为ANSI颜色代码"""
        # 格式代码映射
        formatting_map = {
            '§0': Colors.BLACK,
            '§1': Colors.BLUE,
            '§2': Colors.GREEN,
            '§3': Colors.CYAN,
            '§4': Colors.RED,
            '§5': Colors.MAGENTA,
            '§6': Colors.YELLOW,
            '§7': Colors.WHITE,
            '§8': Colors.BLACK + Colors.BOLD,
            '§9': Colors.BLUE + Colors.BOLD,
            '§a': Colors.GREEN + Colors.BOLD,
            '§b': Colors.CYAN + Colors.BOLD,
            '§c': Colors.RED + Colors.BOLD,
            '§d': Colors.MAGENTA + Colors.BOLD,
            '§e': Colors.YELLOW + Colors.BOLD,
            '§f': Colors.WHITE + Colors.BOLD,
            '§k': Colors.MAGENTA,  # 混淆文本（随机字符）
            '§l': Colors.BOLD,
            '§m': Colors.STRIKETHROUGH,
            '§n': Colors.UNDERLINE,
            '§o': Colors.ITALIC,
            '§r': Colors.RESET
        }

        # 替换所有格式代码
        for code, ansi in formatting_map.items():
            text = text.replace(code, ansi)

        # 确保最后有重置代码
        if not text.endswith(Colors.RESET):
            text += Colors.RESET

        return text

    @staticmethod
    def _pack_varint(value):
        """将整数打包为VarInt格式"""
        # 处理负数
        if value < 0:
            value = (1 << 32) + value

        result = bytearray()
        while True:
            byte = value & 0x7F
            value >>= 7
            if value != 0:
                byte |= 0x80
            result.append(byte)
            if value == 0:
                break
        return bytes(result)

    @staticmethod
    def _read_varint(sock):
        """从socket读取VarInt，带超时处理"""
        result = 0
        shift = 0
        timeout_count = 0
        max_timeouts = 3  # 最多容忍3次超时

        while timeout_count < max_timeouts:
            # 使用select确保有数据可读
            ready = select.select([sock], [], [], 1)
            if ready[0]:
                data = sock.recv(1)
                if not data:
                    break

                byte = data[0]
                result |= (byte & 0x7F) << shift
                shift += 7
                if not (byte & 0x80):
                    if result > 0x7FFFFFFF:
                        result -= 0x100000000
                    return result
            else:
                timeout_count += 1

        raise Exception("读取VarInt超时")

    @staticmethod
    def _pack_string(s):
        """打包字符串"""
        data = s.encode('utf-8')
        return MinecraftPing._pack_varint(len(data)) + data

class ServerManager:
    """服务器管理核心类"""

    def __init__(self):
        self.servers = []
        self.current_page = 0
        self.page_size = 10
        self.sort_field = 'name'  # 默认排序字段
        self.sort_order = 'asc'   # 默认排序顺序
        self.filter_type = 'all'  # 默认筛选类型：all, java, bedrock
        self.load_servers()

    def load_servers(self):
        """从JSON文件加载服务器列表，保持向后兼容"""
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, 'r', encoding='utf-8') as f:
                    self.servers = json.load(f)

                # 确保每个服务器都有type字段（向后兼容）
                for server in self.servers:
                    if 'type' not in server:
                        server['type'] = 'java'  # 默认为Java版
                    # 添加最后查询时间字段（向后兼容）
                    if 'last_query' not in server:
                        server['last_query'] = 0
                    # 添加查询历史字段（向后兼容）
                    if 'query_history' not in server:
                        server['query_history'] = deque(maxlen=10)
                    # 添加玩家历史字段（向后兼容）
                    if 'player_history' not in server:
                        server['player_history'] = deque(maxlen=10)
                    # 添加mod列表字段（向后兼容）
                    if 'mod_list' not in server:
                        server['mod_list'] = []
                    # 添加聊天用户名字段（向后兼容）
                    if 'chat_username' not in server:
                        server['chat_username'] = f"Player{random.randint(1000, 9999)}"

                print(f"{Colors.CYAN}已加载 {len(self.servers)} 个服务器{Colors.RESET}")
            except Exception as e:
                print(f"{Colors.RED}加载服务器列表失败: {str(e)}{Colors.RESET}")
                self.servers = []
        else:
            print(f"{Colors.YELLOW}未找到服务器列表，将创建新文件{Colors.RESET}")
            self.servers = []

    def save_servers(self):
        """保存服务器列表到JSON文件"""
        try:
            # 将deque转换为list以便JSON序列化
            for server in self.servers:
                if 'query_history' in server and isinstance(server['query_history'], deque):
                    server['query_history'] = list(server['query_history'])
                if 'player_history' in server and isinstance(server['player_history'], deque):
                    server['player_history'] = list(server['player_history'])

            with open(JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.servers, f, indent=2, ensure_ascii=False)

            # 恢复deque结构
            for server in self.servers:
                if 'query_history' in server and isinstance(server['query_history'], list):
                    server['query_history'] = deque(server['query_history'], maxlen=10)
                if 'player_history' in server and isinstance(server['player_history'], list):
                    server['player_history'] = deque(server['player_history'], maxlen=10)

            return True
        except Exception as e:
            print(f"{Colors.RED}保存失败: {str(e)}{Colors.RESET}")
            return False

    def add_server(self, server):
        """添加新服务器"""
        # 添加必要的历史字段
        server['last_query'] = 0
        server['query_history'] = deque(maxlen=10)
        server['player_history'] = deque(maxlen=10)
        server['mod_list'] = []
        server['chat_username'] = f"Player{random.randint(1000, 9999)}"
        self.servers.append(server)
        self.save_servers()
        print(f"{Colors.GREEN}已添加: {server['name']}{Colors.RESET}")

    def delete_server(self, index):
        """删除服务器"""
        if 0 <= index < len(self.servers):
            name = self.servers[index]['name']
            del self.servers[index]
            self.save_servers()
            print(f"{Colors.GREEN}已删除: {name}{Colors.RESET}")
            return True
        else:
            print(f"{Colors.RED}无效的序号{Colors.RESET}")
            return False

    def update_server(self, index, field, value):
        """更新服务器信息"""
        if 0 <= index < len(self.servers):
            # 特殊处理端口更新
            if field == 'port':
                try:
                    value = int(value)
                except ValueError:
                    print(f"{Colors.RED}端口必须是数字{Colors.RESET}")
                    return False

            self.servers[index][field] = value
            self.save_servers()
            print(f"{Colors.GREEN}已更新: {self.servers[index]['name']}{Colors.RESET}")
            return True
        else:
            print(f"{Colors.RED}无效的序号{Colors.RESET}")
            return False

    def sort_servers(self, field, order='asc'):
        """排序服务器列表"""
        if field not in ['name', 'ip', 'port', 'type']:
            print(f"{Colors.RED}无效的排序字段{Colors.RESET}")
            return False

        self.sort_field = field
        self.sort_order = order

        reverse = (order == 'desc')

        try:
            self.servers.sort(key=lambda s: s.get(field, ''), reverse=reverse)
            print(f"{Colors.GREEN}已按 {field} {'降序' if reverse else '升序'} 排序{Colors.RESET}")
            return True
        except Exception as e:
            print(f"{Colors.RED}排序失败: {str(e)}{Colors.RESET}")
            return False

    def get_page(self, page=None):
        """获取分页数据"""
        if page is not None:
            self.current_page = max(0, min(page, self.max_page()))

        start = self.current_page * self.page_size
        end = start + self.page_size

        # 应用筛选
        filtered_servers = self.servers
        if self.filter_type != 'all':
            filtered_servers = [s for s in self.servers if s.get('type', 'java') == self.filter_type]

        return filtered_servers[start:end]

    def max_page(self):
        """计算最大页码"""
        # 应用筛选
        filtered_servers = self.servers
        if self.filter_type != 'all':
            filtered_servers = [s for s in self.servers if s.get('type', 'java') == self.filter_type]

        return max(0, (len(filtered_servers) - 1) // self.page_size)

    def scan_ports(self, host, timeout=1):
        """扫描常用Minecraft端口"""
        global global_cancel_query

        common_ports = [25565, 19132, 25566, 25567, 25568, 25569, 25570, 19133, 19134, 19135]

        print(f"{Colors.CYAN}开始扫描 {host} 上的常用Minecraft端口...{Colors.RESET}")
        print(f"{Colors.CYAN}扫描端口: {common_ports}{Colors.RESET}")
        print(f"{Colors.CYAN}按 ^C 中断扫描{Colors.RESET}")

        found_servers = []

        # 获取终端宽度
        try:
            terminal_width = os.get_terminal_size().columns
        except:
            terminal_width = 80

        for i, port in enumerate(common_ports):
            if global_cancel_query:
                print(f"\n{Colors.YELLOW}扫描已中断{Colors.RESET}")
                break

            # 显示进度
            progress = (i + 1) / len(common_ports) * 100
            bar_length = min(30, terminal_width - 40)  # 根据终端宽度调整进度条长度
            filled_length = int(bar_length * (i + 1) // len(common_ports))
            bar = '█' * filled_length + '░' * (bar_length - filled_length)

            # 使用单行显示，并清除之前的内容
            sys.stdout.write(f"\r{Colors.CYAN}扫描进度: {Colors.RESET}|{bar}| {progress:.1f}% {Colors.CYAN}({i+1}/{len(common_ports)}){Colors.RESET}")
            sys.stdout.flush()

            # 尝试Java版
            result = MinecraftPing.ping(host, port, timeout=timeout, use_cache=False, server_type="java")
            if 'error' not in result:
                found_servers.append({
                    'port': port,
                    'type': 'java',
                    'info': result
                })
                continue

            # 尝试基岩版
            result = MinecraftPing.ping(host, port, timeout=timeout, use_cache=False, server_type="bedrock")
            if 'error' not in result:
                found_servers.append({
                    'port': port,
                    'type': 'bedrock',
                    'info': result
                })

        # 完成进度显示，换行
        sys.stdout.write(f"\r{Colors.CYAN}扫描完成: {Colors.RESET}|{'█' * bar_length}| 100.0% {Colors.CYAN}({len(common_ports)}/{len(common_ports)}){Colors.RESET}\n")
        sys.stdout.flush()

        return found_servers

    def scan_all_ports(self, host, start_port=1, end_port=65535, batch_size=100, max_threads=50):
        """扫描指定主机上的所有Minecraft服务器端口"""
        global global_cancel_query

        print(f"{Colors.CYAN}开始扫描 {host} 上的所有Minecraft服务器端口...{Colors.RESET}")
        print(f"{Colors.CYAN}扫描范围: {start_port}-{end_port}{Colors.RESET}")
        print(f"{Colors.CYAN}按 ^C 中断扫描{Colors.RESET}")

        found_servers = []
        total_ports = end_port - start_port + 1
        scanned_ports = 0
        found_count = 0

        # 获取终端宽度
        try:
            terminal_width = os.get_terminal_size().columns
        except:
            terminal_width = 80

        # 创建端口队列
        port_queue = queue.Queue()
        for port in range(start_port, end_port + 1):
            port_queue.put(port)

        # 创建线程锁
        lock = threading.Lock()

        # 工作线程函数
        def worker():
            nonlocal scanned_ports, found_count
            while not global_cancel_query:
                try:
                    port = port_queue.get_nowait()
                except queue.Empty:
                    break

                # 检查取消标志
                if global_cancel_query:
                    break

                # 尝试Java版
                result = MinecraftPing.ping(host, port, timeout=1, use_cache=False, server_type="java")
                if 'error' not in result:
                    with lock:
                        found_servers.append({
                            'port': port,
                            'type': 'java',
                            'info': result
                        })
                        found_count += 1
                else:
                    # 尝试基岩版
                    result = MinecraftPing.ping(host, port, timeout=1, use_cache=False, server_type="bedrock")
                    if 'error' not in result:
                        with lock:
                            found_servers.append({
                                'port': port,
                                'type': 'bedrock',
                                'info': result
                            })
                            found_count += 1

                # 更新扫描计数
                with lock:
                    scanned_ports += 1

                port_queue.task_done()

        # 进度显示函数
        def progress_monitor():
            nonlocal scanned_ports, found_count
            last_update = 0
            animation = "|/-\\"
            anim_idx = 0

            # 计算进度条长度
            bar_length = min(30, terminal_width - 50)

            while not global_cancel_query and scanned_ports < total_ports:
                current_time = time.time()
                if current_time - last_update >= 0.1:  # 每0.1秒更新一次
                    with lock:
                        current_scanned = scanned_ports
                        current_found = found_count

                    # 计算进度百分比
                    progress = current_scanned / total_ports * 100

                    # 创建进度条
                    filled_length = int(bar_length * current_scanned // total_ports)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)

                    # 更新动画
                    anim_char = animation[anim_idx % len(animation)]
                    anim_idx += 1

                    # 显示进度 - 使用回车符覆盖上一行
                    sys.stdout.write(f"\r{Colors.CYAN}扫描进度: {Colors.RESET}|{bar}| {progress:.1f}% {Colors.CYAN}({current_scanned}/{total_ports}){Colors.RESET} {Colors.GREEN}找到: {current_found}{Colors.RESET} {anim_char}")
                    sys.stdout.flush()

                    last_update = current_time

                time.sleep(0.05)

            # 如果取消，显示取消信息
            if global_cancel_query:
                with lock:
                    current_scanned = scanned_ports
                    current_found = found_count

                progress = current_scanned / total_ports * 100
                filled_length = int(bar_length * current_scanned // total_ports)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)

                sys.stdout.write(f"\r{Colors.CYAN}扫描进度: {Colors.RESET}|{bar}| {progress:.1f}% {Colors.CYAN}({current_scanned}/{total_ports}){Colors.RESET} {Colors.GREEN}找到: {current_found}{Colors.RESET} ✗ \n")
                sys.stdout.flush()

        # 启动工作线程
        threads = []
        for _ in range(min(max_threads, total_ports)):
            t = threading.Thread(target=worker)
            t.daemon = True
            t.start()
            threads.append(t)

        # 启动进度监视器
        progress_thread = threading.Thread(target=progress_monitor)
        progress_thread.daemon = True
        progress_thread.start()

        # 等待所有端口扫描完成或取消
        try:
            # 设置超时，以便定期检查取消标志
            while not port_queue.empty() and not global_cancel_query:
                time.sleep(0.1)
        except KeyboardInterrupt:
            global_cancel_query = True
            print(f"\n{Colors.YELLOW}扫描已中断{Colors.RESET}")

        # 等待所有线程完成
        for t in threads:
            t.join(timeout=1)

        # 如果没有取消，显示最终进度
        if not global_cancel_query:
            with lock:
                current_scanned = scanned_ports
                current_found = found_count

            # 计算进度百分比
            progress = current_scanned / total_ports * 100

            # 创建进度条
            bar_length = min(30, terminal_width - 50)
            filled_length = int(bar_length * current_scanned // total_ports)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)

            # 显示最终进度
            sys.stdout.write(f"\r{Colors.CYAN}扫描完成: {Colors.RESET}|{bar}| {progress:.1f%} {Colors.CYAN}({current_scanned}/{total_ports}){Colors.RESET} {Colors.GREEN}找到: {current_found}{Colors.RESET} ✓ \n")
            sys.stdout.flush()

        # 重置取消标志
        global_cancel_query = False

        return found_servers

    def display_scan_results(self, host, found_servers):
        """显示端口扫描结果"""
        if not found_servers:
            print(f"{Colors.YELLOW}未在 {host} 上找到任何Minecraft服务器{Colors.RESET}")
            return None

        print(f"\n{Colors.GREEN}在 {host} 上找到 {len(found_servers)} 个Minecraft服务器:{Colors.RESET}")
        print("=" * 80)

        for i, server in enumerate(found_servers):
            result = server['info']
            server_type = server['type']

            # 序号颜色
            index_color = Colors.CYAN
            if 'error' in result and "离线" in result['error']:
                index_color = Colors.RED
            elif 'players' in result and result['players'].get('online', 0) > 0:
                index_color = Colors.GREEN

            # 显示服务器类型标识
            type_display = f" [{Colors.MAGENTA}基岩版{Colors.RESET}]" if server_type == 'bedrock' else f" [{Colors.BLUE}Java版{Colors.RESET}]"

            print(f"\n{index_color}[{i + 1}]{Colors.RESET} {Colors.BOLD}{host}:{server['port']}{type_display}{Colors.RESET}")

            if 'error' in result:
                # 离线状态
                if "timed out" in result['error'] or "离线" in result['error']:
                    error_color = Colors.RED
                else:
                    error_color = Colors.YELLOW

                print(f"{error_color}状态: {result['error']}{Colors.RESET}")
            else:
                # 服务器版本
                version = result.get('version', {}).get('name', '未知')
                if server_type == 'bedrock':
                    version_color = Colors.MAGENTA
                    version_display = f"{version}"
                else:
                    if '1.21' in version or '1.20' in version:
                        version_color = Colors.GREEN
                    elif '1.19' in version or '1.18' in version:
                        version_color = Colors.YELLOW
                    else:
                        version_color = Colors.RED
                    version_display = f"{version}"

                print(f"{Colors.BLUE}版本:{Colors.RESET} {version_color}{version_display}{Colors.RESET}")

                # 玩家数量
                players = result.get('players', {})
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
                if result.get('query_time', 0) > 0:
                    delay_color = Colors.GREEN
                    if result['query_time'] > 500:
                        delay_color = Colors.YELLOW
                    if result['query_time'] > 1000:
                        delay_color = Colors.RED

                    print(f"{Colors.BLUE}延迟:{Colors.RESET} {delay_color}{result['query_time']}ms{Colors.RESET}")

                # 显示公告栏
                if 'motd' in result and result['motd']:
                    # 计算终端宽度
                    try:
                        terminal_width = os.get_terminal_size().columns
                    except:
                        terminal_width = 80

                    # 分隔线
                    print(f"{Colors.CYAN}┌{'─' * (min(60, terminal_width - 2))}┐{Colors.RESET}")

                    # 显示公告栏内容
                    motd = result['motd']
                    print(f"{Colors.CYAN}│{Colors.RESET} {motd}")

                    # 分隔线
                    print(f"{Colors.CYAN}└{'─' * (min(60, terminal_width - 2))}┘{Colors.RESET}")

        print("=" * 80)

        # 让用户选择
        try:
            choice = input(f"{Colors.BOLD}选择要添加的服务器序号 (1-{len(found_servers)}), 输入 0 取消: {Colors.RESET}").strip().lower()

            if choice == '0':
                return None

            index = int(choice) - 1
            if 0 <= index < len(found_servers):
                return found_servers[index]
            else:
                print(f"{Colors.RED}无效的选择{Colors.RESET}")
                return None
        except (ValueError, KeyboardInterrupt):
            print(f"{Colors.RED}无效的选择{Colors.RESET}")
            return None

    def display_servers(self, servers):
        """显示服务器信息，带并发查询和颜色输出"""
        global global_cancel_query

        if not servers:
            print("\n" + "=" * 60)
            print(f"{Colors.YELLOW}没有可显示的服务器{Colors.RESET}")
            print("=" * 60)
            return

        print("\n" + "=" * 60)

        # 显示筛选信息
        filter_display = {
            'all': '全部服务器',
            'java': 'Java版服务器',
            'bedrock': '基岩版服务器'
        }
        print(f"{Colors.CYAN}筛选: {filter_display.get(self.filter_type, '全部服务器')}{Colors.RESET}")

        # 创建线程列表
        threads = []
        results = [None] * len(servers)

        # 查询函数
        def query_server(idx, server):
            try:
                server_type = server.get('type', 'java')
                port = server.get('port', 25565 if server_type == 'java' else 19132)
                results[idx] = MinecraftPing.ping(server['ip'], port, timeout=3, server_type=server_type)

                # 更新最后查询时间和历史记录
                server_index = self.servers.index(server)
                self.servers[server_index]['last_query'] = time.time()

                # 记录查询历史（延迟）
                if 'error' not in results[idx]:
                    query_time = results[idx].get('query_time', 0)
                    self.servers[server_index]['query_history'].append({
                        'timestamp': time.time(),
                        'query_time': query_time
                    })

                # 记录玩家历史
                if 'error' not in results[idx] and 'players' in results[idx]:
                    players = results[idx]['players']
                    online = players.get('online', 0)
                    max_players = players.get('max', 0)

                    self.servers[server_index]['player_history'].append({
                        'timestamp': time.time(),
                        'online': online,
                        'max': max_players
                    })

                # 检查并记录mod列表（仅Java版）
                if (server_type == 'java' and 'error' not in results[idx] and
                    'modinfo' in results[idx] and 'modList' in results[idx]['modinfo']):
                    mod_list = results[idx]['modinfo']['modList']
                    self.servers[server_index]['mod_list'] = mod_list

            except Exception as e:
                results[idx] = {"error": str(e), "connect_time": 0, "query_time": 0, "motd": "", "server_type": server.get('type', 'java')}

        # 启动查询线程
        for i, server in enumerate(servers):
            t = threading.Thread(target=query_server, args=(i, server))
            t.daemon = True
            t.start()
            threads.append(t)

        # 显示加载动画
        print(f"{Colors.CYAN}查询服务器状态中... (按 ^C 取消){Colors.RESET}", end='', flush=True)
        animation = "|/-\\"
        idx = 0

        # 等待所有线程完成或超时
        start_time = time.time()
        try:
            while any(t.is_alive() for t in threads) and (time.time() - start_time < 15):
                time.sleep(0.1)
                print(f"\r{Colors.CYAN}查询服务器状态中... (按 ^C 取消) {animation[idx % len(animation)]}{Colors.RESET}", end='', flush=True)
                idx += 1
        except KeyboardInterrupt:
            global_cancel_query = True
            print(f"\n{Colors.YELLOW}查询已取消，显示部分结果...{Colors.RESET}")
            # 等待一小段时间让线程有机会退出
            time.sleep(0.5)
        finally:
            # 重置取消标志
            global_cancel_query = False
            print("\r" + " " * 50 + "\r", end='', flush=True)  # 清除动画

        # 显示结果
        for i, server in enumerate(servers):
            result = results[i]
            if result is None:
                result = {"error": "查询未完成", "connect_time": 0, "query_time": 0, "motd": "", "server_type": server.get('type', 'java')}

            # 序号颜色
            index_color = Colors.CYAN
            if 'error' in result and "离线" in result['error']:
                index_color = Colors.RED
            elif 'players' in result and result['players'].get('online', 0) > 0:
                index_color = Colors.GREEN

            # 显示服务器类型标识
            server_type = result.get('server_type', server.get('type', 'java'))
            type_display = f" [{Colors.MAGENTA}基岩版{Colors.RESET}]" if server_type == 'bedrock' else f" [{Colors.BLUE}Java版{Colors.RESET}]"

            print(f"\n{index_color}[{self.current_page * self.page_size + i + 1}]{Colors.RESET} {Colors.BOLD}{server['name']}{type_display}{Colors.RESET}")
            print(f"{Colors.BLUE}地址:{Colors.RESET} {server['ip']}:{server.get('port', 25565 if server_type == 'java' else 19132)}")

            if 'note' in server and server['note']:
                print(f"{Colors.YELLOW}备注:{Colors.RESET} {server['note']}")

            # 显示最后查询时间
            if server.get('last_query', 0) > 0:
                last_query_time = datetime.fromtimestamp(server['last_query']).strftime('%Y-%m-%d %H:%M:%S')
                print(f"{Colors.YELLOW}上次查询:{Colors.RESET} {last_query_time}")

            # 显示公告栏
            if 'motd' in result and result['motd']:
                # 计算终端宽度
                try:
                    terminal_width = os.get_terminal_size().columns
                except:
                    terminal_width = 80

                # 分隔线
                print(f"{Colors.CYAN}┌{'─' * (terminal_width - 2)}┐{Colors.RESET}")

                # 显示公告栏内容
                motd = result['motd']
                print(f"{Colors.CYAN}│{Colors.RESET} {motd}")

                # 分隔线
                print(f"{Colors.CYAN}└{'─' * (terminal_width - 2)}┘{Colors.RESET}")

            if 'error' in result:
                # 离线状态
                if "timed out" in result['error'] or "离线" in result['error']:
                    error_color = Colors.RED
                else:
                    error_color = Colors.YELLOW

                print(f"{error_color}状态: {result['error']}{Colors.RESET}")
                if result['connect_time'] > 0:
                    print(f"{Colors.BLUE}连接时间:{Colors.RESET} {result['connect_time']}ms")
            else:
                # 服务器版本
                version = result.get('version', {}).get('name', '未知')
                if server_type == 'bedrock':
                    version_color = Colors.MAGENTA
                    version_display = f"{version}"
                else:
                    if '1.21' in version or '1.20' in version:
                        version_color = Colors.GREEN
                    elif '1.19' in version or '1.18' in version:
                        version_color = Colors.YELLOW
                    else:
                        version_color = Colors.RED
                    version_display = f"{version}"

                print(f"{Colors.BLUE}版本:{Colors.RESET} {version_color}{version_display}{Colors.RESET}")

                # 玩家数量
                players = result.get('players', {})
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

                # 显示玩家列表（如果可用）
                if server_type != 'bedrock' and 'players' in result and 'sample' in result['players']:
                    sample_players = result['players']['sample']
                    if sample_players and len(sample_players) > 0:
                        player_names = [player.get('name', '未知') for player in sample_players[:5]]  # 最多显示5个
                        print(f"{Colors.BLUE}在线玩家:{Colors.RESET}")
                        for name in player_names:
                            print(f"  {Colors.GREEN}•{Colors.RESET} {name}")

                        # 如果还有更多玩家，显示提示
                        if len(sample_players) > 5:
                            print(f"  {Colors.CYAN}... 还有 {len(sample_players) - 5} 个玩家{Colors.RESET}")

                # 延迟信息
                if result.get('query_time', 0) > 0:
                    delay_color = Colors.GREEN
                    if result['query_time'] > 500:
                        delay_color = Colors.YELLOW
                    if result['query_time'] > 1000:
                        delay_color = Colors.RED

                    delay_info = f"{Colors.BLUE}延迟:{Colors.RESET} {delay_color}{result['query_time']}ms{Colors.RESET}"
                    if result.get('connect_time', 0) > 0:
                        delay_info += f" ({Colors.BLUE}连接:{Colors.RESET} {result['connect_time']}ms)"
                    print(delay_info)

                # 基岩版特定信息
                if server_type == 'bedrock':
                    if 'game_mode' in result and result['game_mode']:
                        print(f"{Colors.BLUE}游戏模式:{Colors.RESET} {result['game_mode']}")
                    if 'edition' in result and result['edition']:
                        print(f"{Colors.BLUE}版本:{Colors.RESET} {result['edition']}")

        print("=" * 60)

        # 计算筛选后的服务器总数
        filtered_servers = self.servers
        if self.filter_type != 'all':
            filtered_servers = [s for s in self.servers if s.get('type', 'java') == self.filter_type]

        print(f"{Colors.CYAN}页码:{Colors.RESET} {self.current_page + 1}/{self.max_page() + 1} | {Colors.CYAN}总数:{Colors.RESET} {len(filtered_servers)}/{len(self.servers)}")
        print(f"{Colors.CYAN}排序:{Colors.RESET} {self.sort_field} ({self.sort_order}) | {Colors.CYAN}每页:{Colors.RESET} {self.page_size}")

    def show_players(self, index):
        """显示指定服务器的完整玩家列表"""
        if index < 0 or index >= len(self.servers):
            print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            return

        server = self.servers[index]
        server_type = server.get('type', 'java')
        port = server.get('port', 25565 if server_type == 'java' else 19132)

        if server_type == 'bedrock':
            print(f"{Colors.YELLOW}基岩版服务器不支持玩家列表查询{Colors.RESET}")
            return

        print(f"{Colors.CYAN}查询 {server['name']} 的玩家列表...{Colors.RESET}")

        # 使用server_info模块查询玩家列表（如果可用）
        if SERVER_INFO_AVAILABLE:
            try:
                players = ServerInfoInterface.get_player_list(server['ip'], port, server_type, timeout=5)
                if players:
                    print(f"\n{Colors.BOLD}{server['name']} 玩家列表:{Colors.RESET}")
                    print(f"{Colors.BLUE}在线玩家:{Colors.RESET} {len(players)}")
                    print("-" * 40)

                    # 显示所有玩家
                    for i, player in enumerate(players):
                        player_name = player.get('name', '未知') if isinstance(player, dict) else str(player)

                        # 每10个玩家分组显示
                        if i % 10 == 0 and i > 0:
                            input(f"{Colors.CYAN}按回车键继续显示...{Colors.RESET}")
                            print("-" * 40)

                        print(f"  {Colors.GREEN}{i+1:2d}.{Colors.RESET} {player_name}")

                    print("-" * 40)
                    return
            except Exception as e:
                print(f"{Colors.YELLOW}使用server_info查询失败: {str(e)}{Colors.RESET}")
                print(f"{Colors.CYAN}回退到基本查询...{Colors.RESET}")

        # 回退到基本查询
        result = MinecraftPing.ping(server['ip'], port, timeout=5, use_cache=False, server_type=server_type)

        if 'error' in result:
            print(f"{Colors.RED}查询失败: {result['error']}{Colors.RESET}")
            return

        if 'players' not in result or 'sample' not in result['players']:
            print(f"{Colors.YELLOW}服务器未返回玩家列表信息{Colors.RESET}")
            return

        players = result['players']
        sample_players = players.get('sample', [])
        online = players.get('online', 0)
        max_players = players.get('max', 0)

        print(f"\n{Colors.BOLD}{server['name']} 玩家列表:{Colors.RESET}")
        print(f"{Colors.BLUE}在线玩家:{Colors.RESET} {online}/{max_players}")
        print("-" * 40)

        if not sample_players:
            print(f"{Colors.YELLOW}没有玩家在线{Colors.RESET}")
            return

        # 显示所有玩家
        for i, player in enumerate(sample_players):
            player_name = player.get('name', '未知')
            player_id = player.get('id', '')

            # 每10个玩家分组显示
            if i % 10 == 0 and i > 0:
                input(f"{Colors.CYAN}按回车键继续显示...{Colors.RESET}")
                print("-" * 40)

            print(f"  {Colors.GREEN}{i+1:2d}.{Colors.RESET} {player_name}")

        print("-" * 40)

    def show_server_info(self, index, show_all_mods=False):
        """显示指定服务器的详细信息，包括历史统计和mod列表"""
        if index < 0 or index >= len(self.servers):
            print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            return

        server = self.servers[index]
        server_type = server.get('type', 'java')
        port = server.get('port', 25565 if server_type == 'java' else 19132)

        print(f"\n{Colors.BOLD}{Colors.CYAN}服务器详细信息: {server['name']}{Colors.RESET}")
        print(f"{Colors.CYAN}地址: {server['ip']}:{port}{Colors.RESET}")
        print(f"{Colors.CYAN}类型: {'Java版' if server_type == 'java' else '基岩版'}{Colors.RESET}")
        print("-" * 60)

        # 使用server_info模块查询详细信息（如果可用）
        if SERVER_INFO_AVAILABLE:
            try:
                print(f"{Colors.YELLOW}正在使用server_info模块查询服务器信息...{Colors.RESET}")
                result = ServerInfoInterface.get_detailed_info(server['ip'], port, server_type, timeout=10)

                if 'error' in result:
                    print(f"{Colors.RED}服务器离线: {result['error']}{Colors.RESET}")
                else:
                    # 显示基本信息
                    print(f"{Colors.BOLD}基本信息:{Colors.RESET}")
                    print(f"  {Colors.BLUE}版本:{Colors.RESET} {result.get('version', {}).get('name', '未知')}")

                    players = result.get('players', {})
                    online = players.get('online', 0)
                    max_players = players.get('max', 0)
                    print(f"  {Colors.BLUE}玩家:{Colors.RESET} {online}/{max_players}")

                    if result.get('query_time', 0) > 0:
                        print(f"  {Colors.BLUE}延迟:{Colors.RESET} {result['query_time']}ms")

                    # 显示公告栏
                    if 'motd' in result and result['motd']:
                        print(f"  {Colors.BLUE}公告栏:{Colors.RESET}")
                        print(f"    {result['motd']}")

                    # 获取mod列表（如果可用）
                    if server_type == 'java':
                        mod_list = ServerInfoInterface.get_mod_list(server['ip'], port, server_type, timeout=3)
                        if mod_list:
                            server['mod_list'] = mod_list
            except Exception as e:
                print(f"{Colors.YELLOW}使用server_info查询失败: {str(e)}{Colors.RESET}")
                print(f"{Colors.CYAN}回退到基本查询...{Colors.RESET}")

        # 回退到基本查询
        print(f"{Colors.YELLOW}正在查询服务器状态...{Colors.RESET}")
        result = MinecraftPing.ping(server['ip'], port, timeout=5, use_cache=False, server_type=server_type)

        if 'error' in result:
            print(f"{Colors.RED}服务器离线: {result['error']}{Colors.RESET}")
        else:
            # 显示基本信息
            print(f"{Colors.BOLD}基本信息:{Colors.RESET}")
            print(f"  {Colors.BLUE}版本:{Colors.RESET} {result.get('version', {}).get('name', '未知')}")

            players = result.get('players', {})
            online = players.get('online', 0)
            max_players = players.get('max', 0)
            print(f"  {Colors.BLUE}玩家:{Colors.RESET} {online}/{max_players}")

            if result.get('query_time', 0) > 0:
                print(f"  {Colors.BLUE}延迟:{Colors.RESET} {result['query_time']}ms")

            # 显示公告栏
            if 'motd' in result and result['motd']:
                print(f"  {Colors.BLUE}公告栏:{Colors.RESET}")
                print(f"    {result['motd']}")

        # 显示延迟统计
        print(f"\n{Colors.BOLD}延迟统计 (最近10次查询):{Colors.RESET}")
        if server['query_history']:
            query_times = [item['query_time'] for item in server['query_history']]
            avg_delay = sum(query_times) / len(query_times)
            min_delay = min(query_times)
            max_delay = max(query_times)

            print(f"  {Colors.BLUE}平均延迟:{Colors.RESET} {avg_delay:.1f}ms")
            print(f"  {Colors.BLUE}最低延迟:{Colors.RESET} {min_delay}ms")
            print(f"  {Colors.BLUE}最高延迟:{Colors.RESET} {max_delay}ms")
            print(f"  {Colors.BLUE}查询次数:{Colors.RESET} {len(query_times)}")

            # 显示延迟趋势
            if len(query_times) > 1:
                trend = "稳定"
                if query_times[-1] > avg_delay * 1.5:
                    trend = f"{Colors.RED}上升{Colors.RESET}"
                elif query_times[-1] < avg_delay * 0.5:
                    trend = f"{Colors.GREEN}下降{Colors.RESET}"
                print(f"  {Colors.BLUE}趋势:{Colors.RESET} {trend}")
        else:
            print(f"  {Colors.YELLOW}暂无历史数据{Colors.RESET}")

        # 显示玩家统计
        print(f"\n{Colors.BOLD}玩家统计 (最近10次查询):{Colors.RESET}")
        if server['player_history']:
            player_counts = [item['online'] for item in server['player_history']]
            avg_players = sum(player_counts) / len(player_counts)
            min_players = min(player_counts)
            max_players = max(player_counts)

            print(f"  {Colors.BLUE}平均在线:{Colors.RESET} {avg_players:.1f}")
            print(f"  {Colors.BLUE}最低在线:{Colors.RESET} {min_players}")
            print(f"  {Colors.BLUE}最高在线:{Colors.RESET} {max_players}")

            # 显示最近一次查询的玩家列表
            if 'error' not in result and 'players' in result and 'sample' in result['players']:
                sample_players = result['players']['sample']
                if sample_players and len(sample_players) > 0:
                    print(f"  {Colors.BLUE}当前在线玩家:{Colors.RESET}")
                    for i, player in enumerate(sample_players[:5]):  # 最多显示5个
                        print(f"    {Colors.GREEN}•{Colors.RESET} {player.get('name', '未知')}")

                    if len(sample_players) > 5:
                        print(f"    {Colors.CYAN}... 还有 {len(sample_players) - 5} 个玩家{Colors.RESET}")
        else:
            print(f"  {Colors.YELLOW}暂无历史数据{Colors.RESET}")

        # 显示mod列表（仅Java版）
        if server_type == 'java' and server.get('mod_list'):
            print(f"\n{Colors.BOLD}Mod列表 ({len(server['mod_list'])} 个):{Colors.RESET}")

            if not show_all_mods and len(server['mod_list']) > 10:
                # 显示前5个和后5个mod
                for i, mod in enumerate(server['mod_list'][:5]):
                    print(f"  {Colors.GREEN}•{Colors.RESET} {mod.get('modid', '未知')} - {mod.get('version', '未知')}")

                print(f"  {Colors.CYAN}... 省略 {len(server['mod_list']) - 10} 个mod ...{Colors.RESET}")

                for i, mod in enumerate(server['mod_list'][-5:]):
                    idx = len(server['mod_list']) - 5 + i
                    print(f"  {Colors.GREEN}•{Colors.RESET} {mod.get('modid', '未知')} - {mod.get('version', '未知')}")

                print(f"\n{Colors.CYAN}使用 'info {index+1} -allmod' 查看完整mod列表{Colors.RESET}")
            else:
                # 显示所有mod
                for i, mod in enumerate(server['mod_list']):
                    print(f"  {Colors.GREEN}•{Colors.RESET} {mod.get('modid', '未知')} - {mod.get('version', '未知')}")

        print("-" * 60)

        # 等待用户按回车返回
        input(f"{Colors.CYAN}按回车键返回主菜单...{Colors.RESET}")

    def chat_server(self, index):
      """连接到指定服务器的聊天"""
      if index < 0 or index >= len(self.servers):
        print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
        return False

      if not SERVER_INFO_AVAILABLE:
        print(f"{Colors.RED}聊天功能需要server_info模块，但未找到{Colors.RESET}")
        return False

      server = self.servers[index]
      server_type = server.get('type', 'java')
      port = server.get('port', 25565 if server_type == 'java' else 19132)

      if server_type != 'java':
        print(f"{Colors.RED}只有Java版服务器支持聊天功能{Colors.RESET}")
        return False

      print(f"{Colors.CYAN}正在连接到 {server['name']} 的聊天...{Colors.RESET}")

      # 获取聊天用户名
      username = server.get('chat_username', f"Player{random.randint(1000, 9999)}")
      print(f"{Colors.CYAN}使用用户名: {username}{Colors.RESET}")

      # 先尝试获取服务器版本信息
      print(f"{Colors.CYAN}正在检测服务器版本...{Colors.RESET}")
      try:
        result = MinecraftPing.ping(server['ip'], port, timeout=5, server_type="java")
        if 'error' in result:
          print(f"{Colors.YELLOW}无法检测服务器版本，使用默认版本{Colors.RESET}")
          server_version = None
        else:
          server_version = result.get('version', {}).get('name', None)
          if server_version:
            print(f"{Colors.GREEN}检测到服务器版本: {server_version}{Colors.RESET}")
          else:
            print(f"{Colors.YELLOW}无法获取服务器版本，使用默认版本{Colors.RESET}")
            server_version = None
      except Exception as e:
        print(f"{Colors.YELLOW}版本检测失败: {str(e)}{Colors.RESET}")
        server_version = None

      # 创建聊天客户端
      global global_chat_client
      try:
        # 获取服务器的mod列表
        forge_mods = server.get('mod_list', [])

        # 添加调试信息
        print(f"{Colors.CYAN}创建聊天客户端实例...{Colors.RESET}")
        chat_client = MinecraftChatClient(server['ip'], port, username, server_version)
        chat_client.set_server_name(server['name'])

        # 设置Forge mod列表
        if forge_mods:
          chat_client.set_forge_mods(forge_mods)
          print(f"{Colors.GREEN}检测到Forge服务器，已加载 {len(forge_mods)} 个Mod{Colors.RESET}")

        # 设置消息回调
        def chat_callback(sender, message):
          timestamp = datetime.now().strftime("%H:%M:%S")
          print(f"{Colors.CYAN}[{timestamp}] {Colors.GREEN}{sender}:{Colors.RESET} {message}")

        chat_client.set_chat_callback(chat_callback)

        # 连接到服务器
        if chat_client.start_listening():
          global_chat_client = chat_client
          print(f"{Colors.GREEN}已连接到聊天，输入消息发送，输入 '/quit' 退出聊天{Colors.RESET}")

          # 聊天循环
          while True:
            try:
              message = input().strip()
              if message.lower() == '/quit':
                break
              if message:
                chat_client.send_chat_message(message)
            except KeyboardInterrupt:
              print(f"\n{Colors.YELLOW}退出聊天{Colors.RESET}")
              break

          # 断开连接
          chat_client.stop()
          global_chat_client = None
          print(f"{Colors.GREEN}已断开聊天连接{Colors.RESET}")
        else:
          print(f"{Colors.RED}连接聊天失败{Colors.RESET}")
          return False

      except Exception as e:
        print(f"{Colors.RED}聊天连接错误: {str(e)}{Colors.RESET}")
        return False

      return True

def print_help():
    """打印帮助信息"""
    print(f"\n{Colors.BOLD}可用命令:{Colors.RESET}")
    print(f"  {Colors.GREEN}n{Colors.RESET}: 下一页")
    print(f"  {Colors.GREEN}p{Colors.RESET}: 上一页")
    print(f"  {Colors.GREEN}g{Colors.RESET}: 跳转到指定页")
    print(f"  {Colors.GREEN}a{Colors.RESET}: 添加服务器")
    print(f"  {Colors.GREEN}d{Colors.RESET}: 删除服务器")
    print(f"  {Colors.GREEN}u{Colors.RESET}: 更新服务器信息")
    print(f"  {Colors.GREEN}s{Colors.RESET}: 保存服务器列表")
    print(f"  {Colors.GREEN}r{Colors.RESET}: 刷新当前页")
    print(f"  {Colors.GREEN}o{Colors.RESET}: 排序服务器")
    print(f"  {Colors.GREEN}c{Colors.RESET}: 更改每页显示数量")
    print(f"  {Colors.GREEN}f{Colors.RESET}: 筛选服务器类型")
    print(f"  {Colors.GREEN}players <序号>{Colors.RESET}: 查看指定服务器的完整玩家列表")
    print(f"  {Colors.GREEN}info <序号>{Colors.RESET}: 查看指定服务器的详细信息")
    print(f"  {Colors.GREEN}info <序号> -allmod{Colors.RESET}: 查看指定服务器的完整mod列表")
    print(f"  {Colors.GREEN}chat <序号>{Colors.RESET}: 连接到指定服务器的聊天")
    print(f"  {Colors.GREEN}scan{Colors.RESET}: 扫描IP/域名下的Minecraft服务器端口")
    print(f"  {Colors.GREEN}scanall{Colors.RESET}: 扫描IP/域名下的所有端口 (1-65535)")
    print(f"  {Colors.GREEN}mods <序号>{Colors.RESET}: 配置指定服务器的Mod列表")
    print(f"  {Colors.GREEN}h{Colors.RESET}: 显示帮助")
    print(f"  {Colors.GREEN}q{Colors.RESET}: 退出")

    # 聊天功能说明
    print(f"\n{Colors.BOLD}聊天功能说明:{Colors.RESET}")
    print(f"  • 仅支持Java版服务器")
    print(f"  • 在聊天中输入 '/quit' 退出聊天模式")
    print(f"  • 按 Ctrl+C 也可以退出聊天模式")
    print(f"  • 聊天消息会自动记录到日志文件中")

    # 等待用户按回车继续
    input(f"\n{Colors.CYAN}按回车键继续...{Colors.RESET}")

def sigint_handler(signum, frame):
    """处理 Ctrl+C 信号"""
    global global_cancel_query
    global global_chat_client

    # 如果正在聊天，退出聊天
    if global_chat_client:
        global_chat_client.stop()
        global_chat_client = None
        print(f"\n{Colors.YELLOW}已退出聊天模式{Colors.RESET}")
        return

    global_cancel_query = True
    print(f"\n{Colors.YELLOW}正在取消查询...{Colors.RESET}")

def main():
    # 设置信号处理
    signal.signal(signal.SIGINT, sigint_handler)

    manager = ServerManager()

    print(f"{Colors.BOLD}Minecraft 服务器管理器{Colors.RESET}")
    print(f"{Colors.CYAN}已加载 {len(manager.servers)} 个服务器{Colors.RESET}")
    # 移除了启动时显示帮助信息的代码

    while True:
        # 显示当前页
        current_servers = manager.get_page()
        manager.display_servers(current_servers)

        # 用户命令
        try:
          cmd = input(f"\n{Colors.BOLD}命令 (h=帮助):{Colors.RESET} ").strip().lower()
        except (KeyboardInterrupt, EOFError):
          print(f"\n{Colors.YELLOW}返回主菜单...{Colors.RESET}")
          continue

        if cmd == 'n':  # 下一页
            if manager.current_page < manager.max_page():
                manager.current_page += 1
            else:
                print(f"{Colors.YELLOW}已经是最后一页{Colors.RESET}")
        elif cmd == 'p':  # 上一页
            if manager.current_page > 0:
                manager.current_page -= 1
            else:
                print(f"{Colors.YELLOW}已经是第一页{Colors.RESET}")
        elif cmd == 'g':  # 跳转到指定页
            try:
                page = int(input("输入页码: ").strip()) - 1
                if 0 <= page <= manager.max_page():
                    manager.current_page = page
                else:
                    print(f"{Colors.RED}页码超出范围 (1-{manager.max_page() + 1}){Colors.RESET}")
            except ValueError:
                print(f"{Colors.RED}请输入有效数字!{Colors.RESET}")
        elif cmd == 'a':  # 添加服务器
            try:
                name = input("服务器名称: ").strip()
                if not name:
                    print(f"{Colors.RED}名称不能为空!{Colors.RESET}")
                    continue

                ip = input("IP地址: ").strip()
                if not ip:
                    print(f"{Colors.RED}IP地址不能为空!{Colors.RESET}")
                    continue

                # 设置默认服务器类型
                server_type = 'java'

                # 自动检测服务器类型
                print(f"{Colors.CYAN}正在尝试自动检测服务器类型...{Colors.RESET}")
                port_str = input("端口 (留空自动检测): ").strip()
                port = 25565  # 默认Java版端口

                if port_str:
                    try:
                        port = int(port_str)
                    except ValueError:
                        print(f"{Colors.YELLOW}端口必须是数字，使用默认值25565{Colors.RESET}")
                        port = 25565

                    # 如果用户输入了端口，询问服务器类型
                    server_type_input = input("服务器类型 (java/bedrock, 默认java): ").strip().lower()
                    if server_type_input in ['java', 'bedrock']:
                        server_type = server_type_input
                    else:
                        server_type = 'java'
                else:
                    # 尝试自动检测
                    detected_type = MinecraftPing.detect_server_type(ip, port)
                    if detected_type == "java":
                        print(f"{Colors.GREEN}检测到Java版服务器{Colors.RESET}")
                        server_type = "java"
                    elif detected_type == "bedrock":
                        print(f"{Colors.MAGENTA}检测到基岩版服务器{Colors.RESET}")
                        server_type = "bedrock"
                        port = 19132  # 基岩版默认端口
                    else:
                        print(f"{Colors.YELLOW}无法自动检测服务器类型，请手动选择{Colors.RESET}")
                        server_type_input = input("服务器类型 (java/bedrock, 默认java): ").strip().lower()
                        if server_type_input in ['java', 'bedrock']:
                            server_type = server_type_input
                        else:
                            server_type = 'java'

                # 如果用户没有输入端口，但选择了基岩版，使用基岩版默认端口
                if not port_str and server_type == 'bedrock':
                    port = 19132

                note = input("备注 (可选): ").strip()

                manager.add_server({
                    'name': name,
                    'ip': ip,
                    'port': port,
                    'type': server_type,
                    'note': note if note else ""
                })
            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
        elif cmd == 'd':  # 删除服务器
            try:
                index = int(input("输入要删除的序号: ").strip()) - 1
                actual_index = manager.current_page * manager.page_size + index
                if 0 <= actual_index < len(manager.servers):
                    manager.delete_server(actual_index)
                else:
                    print(f"{Colors.RED}无效的序号{Colors.RESET}")
            except ValueError:
                print(f"{Colors.RED}请输入有效数字!{Colors.RESET}")
        elif cmd == 'u':  # 更新服务器
            try:
                index = int(input("输入要更新的序号: ").strip()) - 1
                actual_index = manager.current_page * manager.page_size + index
                if 0 <= actual_index < len(manager.servers):
                    server = manager.servers[actual_index]
                    print(f"当前名称: {Colors.CYAN}{server.get('name', '')}{Colors.RESET}")
                    print(f"当前地址: {Colors.CYAN}{server.get('ip', '')}:{server.get('port', 25565)}{Colors.RESET}")
                    print(f"当前类型: {Colors.CYAN}{server.get('type', 'java')}{Colors.RESET}")
                    print(f"当前备注: {Colors.CYAN}{server.get('note', '')}{Colors.RESET}")

                    field = input("更新字段 (name/ip/port/type/note): ").strip().lower()

                    if field not in ['name', 'ip', 'port', 'type', 'note']:
                        print(f"{Colors.RED}无效字段!{Colors.RESET}")
                        continue

                    value = input("新值: ").strip()

                    # 验证服务器类型
                    if field == 'type' and value not in ['java', 'bedrock']:
                        print(f"{Colors.RED}服务器类型必须是 'java' 或 'bedrock'{Colors.RESET}")
                        continue

                    manager.update_server(actual_index, field, value)
                else:
                    print(f"{Colors.RED}无效的序号{Colors.RESET}")
            except (ValueError, KeyError):
                print(f"{Colors.RED}输入无效!{Colors.RESET}")
        elif cmd == 's':  # 保存
            if manager.save_servers():
                print(f"{Colors.GREEN}保存成功!{Colors.RESET}")
        elif cmd == 'r':  # 刷新
            print(f"{Colors.GREEN}刷新当前页...{Colors.RESET}")
            # 清除缓存
            MinecraftPing.cache.clear()
        elif cmd == 'o':  # 排序
            print(f"{Colors.CYAN}可用排序字段: name, ip, port, type{Colors.RESET}")
            field = input("排序字段: ").strip().lower()
            if field in ['name', 'ip', 'port', 'type']:
                order = input("排序顺序 (asc/desc): ").strip().lower() or 'asc'
                if order not in ['asc', 'desc']:
                    order = 'asc'
                manager.sort_servers(field, order)
                manager.current_page = 0  # 排序后回到第一页
            else:
                print(f"{Colors.RED}无效的排序字段{Colors.RESET}")
        elif cmd == 'c':  # 更改每页数量
            try:
                new_size = int(input("每页显示数量 (1-50): ").strip())
                if 1 <= new_size <= 50:
                    manager.page_size = new_size
                    print(f"{Colors.GREEN}每页显示数量已改为 {new_size}{Colors.RESET}")
                    manager.current_page = 0  # 回到第一页
                else:
                    print(f"{Colors.RED}数量必须在1-50之间{Colors.RESET}")
            except ValueError:
                print(f"{Colors.RED}请输入有效数字!{Colors.RESET}")
        elif cmd == 'f':  # 筛选服务器类型
            print(f"{Colors.CYAN}可用筛选选项:{Colors.RESET}")
            print(f"  {Colors.GREEN}all{Colors.RESET}: 显示所有服务器")
            print(f"  {Colors.GREEN}java{Colors.RESET}: 仅显示Java版服务器")
            print(f"  {Colors.GREEN}bedrock{Colors.RESET}: 仅显示基岩版服务器")

            filter_type = input("选择筛选类型: ").strip().lower()
            if filter_type in ['all', 'java', 'bedrock']:
                manager.filter_type = filter_type
                manager.current_page = 0  # 回到第一页
                print(f"{Colors.GREEN}已筛选: {filter_type}{Colors.RESET}")
            else:
                print(f"{Colors.RED}无效的筛选类型{Colors.RESET}")
        elif cmd.startswith('players '):  # 查看玩家列表
            try:
                parts = cmd.split()
                if len(parts) < 2:
                    print(f"{Colors.RED}请指定服务器序号{Colors.RESET}")
                    continue

                index = int(parts[1]) - 1
                actual_index = manager.current_page * manager.page_size + index

                if 0 <= actual_index < len(manager.servers):
                    manager.show_players(actual_index)
                else:
                    print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            except ValueError:
                print(f"{Colors.RED}请输入有效的服务器序号{Colors.RESET}")
        elif cmd.startswith('info '):  # 查看服务器详细信息
            try:
                parts = cmd.split()
                if len(parts) < 2:
                    print(f"{Colors.RED}请指定服务器序号{Colors.RESET}")
                    continue

                index = int(parts[1]) - 1
                actual_index = manager.current_page * manager.page_size + index

                if 0 <= actual_index < len(manager.servers):
                    show_all_mods = '-allmod' in parts
                    manager.show_server_info(actual_index, show_all_mods)
                else:
                    print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            except ValueError:
                print(f"{Colors.RED}请输入有效的服务器序号{Colors.RESET}")
        elif cmd.startswith('chat '):  # 连接到服务器聊天
            try:
                parts = cmd.split()
                if len(parts) < 2:
                    print(f"{Colors.RED}请指定服务器序号{Colors.RESET}")
                    continue

                index = int(parts[1]) - 1
                actual_index = manager.current_page * manager.page_size + index

                if 0 <= actual_index < len(manager.servers):
                    manager.chat_server(actual_index)
                else:
                    print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            except ValueError:
                print(f"{Colors.RED}请输入有效的服务器序号{Colors.RESET}")
        elif cmd == 'scan':  # 扫描端口
            try:
                host = input("输入要扫描的IP地址或域名: ").strip()
                if not host:
                    print(f"{Colors.RED}IP地址不能为空!{Colors.RESET}")
                    continue

                # 扫描端口
                found_servers = manager.scan_ports(host)

                # 显示扫描结果并让用户选择
                selected_server = manager.display_scan_results(host, found_servers)

                if selected_server:
                    # 让用户输入服务器名称
                    name = input("服务器名称: ").strip()
                    if not name:
                        # 使用默认名称
                        name = f"{host}:{selected_server['port']}"

                    note = input("备注 (可选): ").strip()

                    # 添加服务器
                    manager.add_server({
                        'name': name,
                        'ip': host,
                        'port': selected_server['port'],
                        'type': selected_server['type'],
                        'note': note if note else ""
                    })
            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
        elif cmd == 'scanall':  # 扫描所有端口
            try:
                host = input("输入要扫描的IP地址或域名: ").strip()
                if not host:
                    print(f"{Colors.RED}IP地址不能为空!{Colors.RESET}")
                    continue

                # 确认扫描所有端口
                print(f"{Colors.YELLOW}警告: 扫描所有端口 (1-65535) 可能需要很长时间!{Colors.RESET}")
                confirm = input("是否继续? (y/N): ").strip().lower()
                if confirm != 'y':
                    print(f"{Colors.YELLOW}操作取消{Colors.RESET}")
                    continue

                # 扫描所有端口
                found_servers = manager.scan_all_ports(host)

                # 显示扫描结果并让用户选择
                selected_server = manager.display_scan_results(host, found_servers)

                if selected_server:
                    # 让用户输入服务器名称
                    name = input("服务器名称: ").strip()
                    if not name:
                        # 使用默认名称
                        name = f"{host}:{selected_server['port']}"

                    note = input("备注 (可选): ").strip()

                    # 添加服务器
                    manager.add_server({
                        'name': name,
                        'ip': host,
                        'port': selected_server['port'],
                        'type': selected_server['type'],
                        'note': note if note else ""
                    })
            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
        elif cmd in ['h', 'help']:  # 帮助
            print_help()
        elif cmd == 'q':  # 退出
            print(f"{Colors.GREEN}再见!{Colors.RESET}")
            break
        elif cmd.startswith('mods '):  # 配置Mod列表
            try:
              parts = cmd.split()
              if len(parts) < 2:
                print(f"{Colors.RED}请指定服务器序号{Colors.RESET}")
                continue

              index = int(parts[1]) - 1
              actual_index = manager.current_page * manager.page_size + index

              if 0 <= actual_index < len(manager.servers):
                server = manager.servers[actual_index]

                if server.get('type', 'java') != 'java':
                  print(f"{Colors.RED}只有Java版服务器需要配置Mod{Colors.RESET}")
                  continue

                print(f"{Colors.CYAN}正在为 {server['name']} 配置Mod...{Colors.RESET}")

                if not SERVER_INFO_AVAILABLE:
                  print(f"{Colors.RED}Mod配置需要server_info模块，但未找到{Colors.RESET}")
                  continue

                # 创建MinecraftLogin实例并选择mods文件夹
                from server_info import MinecraftLogin
                login = MinecraftLogin(server['ip'], server.get('port', 25565), server.get('chat_username', 'Player'))
                mods_list = login.select_mods_folder()

                if mods_list:
                  server['mod_list'] = mods_list
                  manager.save_servers()
                  print(f"{Colors.GREEN}已成功配置 {len(mods_list)} 个Mod{Colors.RESET}")
                else:
                  print(f"{Colors.YELLOW}未选择Mod或选择失败{Colors.RESET}")
              else:
                print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            except ValueError:
              print(f"{Colors.RED}请输入有效的服务器序号{Colors.RESET}")
            except Exception as e:
              print(f"{Colors.RED}配置Mod时出错: {str(e)}{Colors.RESET}")
        else:
            print(f"{Colors.RED}未知命令 (输入'h'查看帮助){Colors.RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}程序已退出{Colors.RESET}")
        sys.exit(0)
