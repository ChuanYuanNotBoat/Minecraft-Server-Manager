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

from msm.constants import (
    CONFIG_FILE,
    JSON_FILE,
    SERVER_TYPE_BEDROCK,
    SERVER_TYPE_JAVA,
    SERVER_TYPE_UNKNOWN,
    Colors,
)
from msm.help_text import print_help as print_common_help
from msm.dns_utils import DNSUtils
from msm.json_store import load_json_file, save_json_file
from msm.cli.command_handler import handle_command
from msm.cli.main_loop import run_main_loop
from msm.cli.session_workflow import print_startup_banner

# 全局变量
global_cancel_query = False

# 导入监控模块
try:
    from server_monitor import ServerMonitor, MonitorEvent, MultiServerMonitor, monitor_multiple_servers, monitor_all_servers
    SERVER_MONITOR_AVAILABLE = True
except ImportError as e:
    print(f"{Colors.YELLOW}警告: 未找到server_monitor模块，监控功能将受限: {str(e)}{Colors.RESET}")
    ServerMonitor = None
    MonitorEvent = None
    MultiServerMonitor = None
    monitor_multiple_servers = None
    monitor_all_servers = None
    SERVER_MONITOR_AVAILABLE = False



# 尝试导入server_info模块
try:
    from server_info import ServerInfoInterface, MinecraftQuery
    SERVER_INFO_AVAILABLE = True
except ImportError:
    SERVER_INFO_AVAILABLE = False
    print(f"{Colors.YELLOW}警告: 未找到server_info模块，详细查询功能将受限{Colors.RESET}")

# === Minecraft Ping 类 ===
class MinecraftPing:
    """改进的MC服务器ping实现"""
    
    cache = {}
    srv_cache = {}
    CACHE_DURATION = 60
    SRV_CACHE_DURATION = 300

    @staticmethod
    def clear_all_caches():
        """清除所有缓存"""
        MinecraftPing.cache.clear()
        MinecraftPing.srv_cache.clear()
        print(f"{Colors.GREEN}已清除所有服务器查询缓存和SRV记录缓存{Colors.RESET}")

    @staticmethod
    def detect_server_type(host, port=25565, timeout=3):
        """尝试自动检测服务器类型"""
        try:
            result = MinecraftPing.ping_java(host, port, timeout)
            if 'error' not in result:
                return SERVER_TYPE_JAVA

            result = MinecraftPing.ping_bedrock(host, 19132, timeout)
            if 'error' not in result:
                return SERVER_TYPE_BEDROCK

            if port != 19132:
                result = MinecraftPing.ping_bedrock(host, port, timeout)
                if 'error' not in result:
                    return SERVER_TYPE_BEDROCK

        except Exception:
            pass

        return SERVER_TYPE_UNKNOWN

    @staticmethod
    def ping(host, port=25565, timeout=3, use_cache=True, server_type=SERVER_TYPE_JAVA):
        global global_cancel_query

        if global_cancel_query:
            return {"error": "查询已取消", "connect_time": 0, "query_time": 0}

        # SRV记录处理
        resolved_host, resolved_port, used_srv = MinecraftPing._resolve_with_srv(host, port)
        
        cache_key = f"{resolved_host}:{resolved_port}:{server_type}"
        if use_cache and cache_key in MinecraftPing.cache:
            cached_data, expiry = MinecraftPing.cache[cache_key]
            if time.time() < expiry:
                if used_srv:
                    cached_data['srv_info'] = MinecraftPing._create_srv_info(host, port, resolved_host, resolved_port)
                return cached_data

        try:
            # 根据服务器类型选择ping方法
            if server_type == SERVER_TYPE_BEDROCK:
                result = MinecraftPing.ping_bedrock(resolved_host, resolved_port, timeout)
            else:
                result = MinecraftPing.ping_java(resolved_host, resolved_port, timeout)

            result['query_timestamp'] = time.time()
            
            if used_srv:
                result['srv_info'] = MinecraftPing._create_srv_info(host, port, resolved_host, resolved_port)
                result['original_address'] = f"{host}:{port}"
                result['resolved_address'] = f"{resolved_host}:{resolved_port}"

            MinecraftPing.cache[cache_key] = (result, time.time() + MinecraftPing.CACHE_DURATION)
            return result
        except Exception as e:
            # SRV记录失败回退
            if used_srv:
                print(f"{Colors.YELLOW}[DNS] SRV记录查询失败，尝试回退到原始地址: {host}:{port}{Colors.RESET}")
                try:
                    if server_type == SERVER_TYPE_BEDROCK:
                        result = MinecraftPing.ping_bedrock(host, port, timeout)
                    else:
                        result = MinecraftPing.ping_java(host, port, timeout)
                    
                    if 'error' not in result:
                        result['query_timestamp'] = time.time()
                        result['srv_fallback'] = True
                        return result
                except Exception:
                    pass
                    
            return MinecraftPing._create_error_result(str(e), server_type)

    @staticmethod
    def _resolve_with_srv(host, port):
        """解析SRV记录"""
        srv_cache_key = f"srv:{host}"
        resolved_host = host
        resolved_port = port
        used_srv = False
        
        if srv_cache_key in MinecraftPing.srv_cache:
            cached_srv, srv_expiry = MinecraftPing.srv_cache[srv_cache_key]
            if time.time() < srv_expiry:
                resolved_host, resolved_port = cached_srv
                used_srv = True
                print(f"{Colors.CYAN}[DNS] 使用缓存的SRV记录: {resolved_host}:{resolved_port}{Colors.RESET}")
        
        if not used_srv:
            try:
                srv_result = DNSUtils.resolve_srv_record(host)
                if srv_result:
                    resolved_host, resolved_port = srv_result
                    used_srv = True
                    MinecraftPing.srv_cache[srv_cache_key] = (
                        (resolved_host, resolved_port), 
                        time.time() + MinecraftPing.SRV_CACHE_DURATION
                    )
            except Exception as e:
                print(f"{Colors.YELLOW}[DNS] SRV记录解析失败，使用原始地址: {str(e)}{Colors.RESET}")

        return resolved_host, resolved_port, used_srv

    @staticmethod
    def _create_srv_info(original_host, original_port, resolved_host, resolved_port):
        """创建SRV信息字典"""
        return {
            'original_host': original_host,
            'original_port': original_port,
            'resolved_host': resolved_host,
            'resolved_port': resolved_port
        }

    @staticmethod
    def _create_error_result(error_msg, server_type):
        """创建错误结果"""
        return {
            "error": error_msg,
            "connect_time": 0,
            "query_time": 0,
            "motd": "",
            "server_type": server_type
        }

    @staticmethod
    def ping_java(host, port=25565, timeout=3):
        """Java版服务器ping实现"""
        global global_cancel_query

        try:
            try:
                ip = socket.getaddrinfo(host, port, socket.AF_INET)[0][4][0]
            except socket.gaierror:
                ip = host
            except:
                ip = host

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)

            start_time = time.time()
            sock.connect((ip, port))
            connect_time = int((time.time() - start_time) * 1000)

            # 构建握手包
            protocol_version = -1
            handshake = bytearray()
            handshake.append(0x00)
            handshake.extend(MinecraftPing._pack_varint(protocol_version))
            handshake.extend(MinecraftPing._pack_string(host))
            handshake.extend(struct.pack('>H', port))
            handshake.extend(MinecraftPing._pack_varint(1))

            packet = bytearray()
            packet.extend(MinecraftPing._pack_varint(len(handshake)))
            packet.extend(handshake)

            request = b'\x01\x00'
            sock.sendall(packet)
            sock.sendall(request)

            ready = select.select([sock], [], [], timeout)
            if not ready[0]:
                raise Exception("服务器响应超时")

            resp_length = MinecraftPing._read_varint(sock)
            if resp_length < 1:
                raise Exception("无效的响应长度")

            resp_id = MinecraftPing._read_varint(sock)
            if resp_id != 0x00:
                raise Exception(f"无效的响应ID: {resp_id}")

            json_length = MinecraftPing._read_varint(sock)
            if json_length < 1:
                raise Exception("无效的JSON长度")

            json_data = b''
            while len(json_data) < json_length:
                if global_cancel_query:
                    sock.close()
                    return {"error": "查询已取消", "connect_time": 0, "query_time": 0}

                chunk = sock.recv(min(4096, json_length - len(json_data)))
                if not chunk:
                    raise Exception("连接中断")
                json_data += chunk

            sock.close()

            result = json.loads(json_data.decode('utf-8'))
            result['connect_time'] = connect_time
            result['query_time'] = int((time.time() - start_time) * 1000)
            result['motd'] = MinecraftPing.parse_motd(result.get('description', ''))
            result['server_type'] = SERVER_TYPE_JAVA

            return result
        except Exception as e:
            return MinecraftPing._create_error_result(str(e), SERVER_TYPE_JAVA)

    @staticmethod
    def ping_bedrock(host, port=19132, timeout=3):
        """基岩版服务器ping实现"""
        global global_cancel_query

        try:
            try:
                ip = socket.getaddrinfo(host, port, socket.AF_INET)[0][4][0]
            except:
                ip = host

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)

            packet = bytearray()
            packet.extend(b'\x01')
            packet.extend(struct.pack('>Q', int(time.time() * 1000)))
            packet.extend(b'\x00\x00\x00\x00\x00\x00\x00\x00')
            packet.extend(struct.pack('>Q', 0))

            start_time = time.time()
            sock.sendto(packet, (ip, port))
            data, addr = sock.recvfrom(4096)
            sock.close()

            query_time = int((time.time() - start_time) * 1000)

            if data[0] != 0x1C:
                raise Exception("无效的响应包")

            offset = 1 + 8 + 8 + 16
            try:
                server_info_str = data[offset:].decode('utf-8')
            except UnicodeDecodeError:
                server_info_str = data[offset:].decode('latin-1')

            server_info = server_info_str.split(';')

            result = {
                'server_type': SERVER_TYPE_BEDROCK,
                'query_time': query_time,
                'connect_time': query_time,
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

            result['motd'] = MinecraftPing.parse_motd(f"{result.get('motd_line1', '')}\n{result.get('submotd', '')}")
            result['players'] = {
                'online': result['online_players'],
                'max': result['max_players']
            }
            result['version'] = {
                'name': result.get('version', ''),
                'protocol': result.get('protocol_version', '')
            }

            return result
        except Exception as e:
            return MinecraftPing._create_error_result(str(e), SERVER_TYPE_BEDROCK)

    @staticmethod
    def parse_motd(motd_data):
        """解析公告栏数据"""
        if isinstance(motd_data, str):
            # 移除颜色代码，但保留原始文本
            return MinecraftPing.clean_mc_formatting(motd_data)
        elif isinstance(motd_data, dict):
            return MinecraftPing.parse_motd_object(motd_data)
        return ""

    @staticmethod
    def parse_motd_object(motd_obj):
        """解析JSON对象格式的公告栏"""
        text = ""

        if 'text' in motd_obj:
            text += motd_obj['text']

        if 'extra' in motd_obj and isinstance(motd_obj['extra'], list):
            for extra in motd_obj['extra']:
                if isinstance(extra, dict):
                    text += MinecraftPing.parse_motd_object(extra)
                elif isinstance(extra, str):
                    text += extra

        return MinecraftPing.clean_mc_formatting(text)

    @staticmethod
    def convert_mc_formatting(text):
        """将Minecraft格式代码转换为ANSI颜色代码"""
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
            '§k': Colors.MAGENTA,
            '§l': Colors.BOLD,
            '§m': Colors.STRIKETHROUGH,
            '§n': Colors.UNDERLINE,
            '§o': Colors.ITALIC,
            '§r': Colors.RESET
        }

        for code, ansi in formatting_map.items():
            text = text.replace(code, ansi)

        return text

    @staticmethod
    def clean_mc_formatting(text):
        """清理Minecraft格式代码，移除颜色代码但不转换"""
        # 简单的正则表达式来移除§加一个字符的格式代码
        import re
        return re.sub(r'§[0-9a-fklmnor]', '', text)

    @staticmethod
    def safe_convert_mc_formatting(text, context_color=Colors.RESET):
        """安全地转换Minecraft格式代码，确保不会溢出到程序输出"""
        # 首先转换颜色代码
        converted = MinecraftPing.convert_mc_formatting(text)
        # 确保在字符串末尾重置颜色
        if not converted.endswith(Colors.RESET):
            converted += Colors.RESET
        # 确保回到上下文颜色
        converted += context_color
        return converted

    @staticmethod
    def _pack_varint(value):
        """将整数打包为VarInt格式"""
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
        """从socket读取VarInt"""
        result = 0
        shift = 0
        timeout_count = 0
        max_timeouts = 3

        while timeout_count < max_timeouts:
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

# === 服务器管理器 ===
class ServerManager:
    """服务器管理核心类"""

    def __init__(self):
        self.servers = []
        self.current_page = 0
        self.page_size = self.load_page_size() or 10
        self.sort_field = 'name'
        self.sort_order = 'asc'
        self.filter_type = 'all'
        self.load_servers()

    def load_page_size(self):
        """从配置文件加载每页显示数量"""
        config = load_json_file(CONFIG_FILE, default=None)
        if isinstance(config, dict):
            return config.get('page_size', 10)
        return None

    def save_page_size(self):
        """保存每页显示数量到配置文件"""
        try:
            config = load_json_file(CONFIG_FILE, default={})
            if not isinstance(config, dict):
                config = {}
            
            config['page_size'] = self.page_size
            
            if not save_json_file(CONFIG_FILE, config, ensure_ascii=False, indent=2):
                raise Exception("写入配置文件失败")
            
            print(f"{Colors.GREEN}已保存页面设置: 每页 {self.page_size} 个服务器{Colors.RESET}")
            return True
        except Exception as e:
            print(f"{Colors.YELLOW}保存配置失败: {str(e)}{Colors.RESET}")
            return False

    def load_servers(self):
        """从JSON文件加载服务器列表"""
        loaded_servers = load_json_file(JSON_FILE, default=None)
        if loaded_servers is None:
            print(f"{Colors.YELLOW}未找到服务器列表，将创建新文件{Colors.RESET}")
            self.servers = []
            return

        if not isinstance(loaded_servers, list):
            print(f"{Colors.RED}加载服务器列表失败: 文件格式不正确（需要list）{Colors.RESET}")
            self.servers = []
            return

        self.servers = loaded_servers

        # 向后兼容性处理
        for server in self.servers:
            server.setdefault('type', SERVER_TYPE_JAVA)
            server.setdefault('last_query', 0)
            server.setdefault('query_history', deque(maxlen=10))
            server.setdefault('player_history', deque(maxlen=10))

        print(f"{Colors.CYAN}已加载 {len(self.servers)} 个服务器{Colors.RESET}")

    def save_servers(self):
        """保存服务器列表到JSON文件"""
        try:
            # 将deque转换为list以便JSON序列化
            for server in self.servers:
                for key in ['query_history', 'player_history']:
                    if key in server and isinstance(server[key], deque):
                        server[key] = list(server[key])

            if not save_json_file(JSON_FILE, self.servers, ensure_ascii=False, indent=2):
                raise Exception("写入服务器文件失败")

            # 恢复deque结构
            for server in self.servers:
                for key in ['query_history', 'player_history']:
                    if key in server and isinstance(server[key], list):
                        server[key] = deque(server[key], maxlen=10)

            return True
        except Exception as e:
            print(f"{Colors.RED}保存失败: {str(e)}{Colors.RESET}")
            return False

    def add_server(self, server):
        """添加新服务器"""
        server.update({
            'last_query': 0,
            'query_history': deque(maxlen=10),
            'player_history': deque(maxlen=10)
        })
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
            order_text = '降序' if reverse else '升序'
            print(f"{Colors.GREEN}已按 {field} {order_text} 排序{Colors.RESET}")
            return True
        except Exception as e:
            print(f"{Colors.RED}排序失败: {str(e)}{Colors.RESET}")
            return False

    def get_filtered_servers(self):
        """获取筛选后的服务器列表"""
        if self.filter_type == 'all':
            return self.servers
        return [s for s in self.servers if s.get('type', SERVER_TYPE_JAVA) == self.filter_type]

    def get_page(self, page=None):
        """获取分页数据"""
        if page is not None:
            self.current_page = max(0, min(page, self.max_page()))

        start = self.current_page * self.page_size
        end = start + self.page_size
        filtered_servers = self.get_filtered_servers()
        
        return filtered_servers[start:end]

    def max_page(self):
        """计算最大页码"""
        filtered_servers = self.get_filtered_servers()
        return max(0, (len(filtered_servers) - 1) // self.page_size)

    def query_servers_concurrently(self, servers, timeout=3):
        """并发查询多个服务器"""
        global global_cancel_query
        
        threads = []
        results = [None] * len(servers)
        
        def query_server(idx, server):
            try:
                server_type = server.get('type', SERVER_TYPE_JAVA)
                port = server.get('port', 25565 if server_type == SERVER_TYPE_JAVA else 19132)
                results[idx] = MinecraftPing.ping(server['ip'], port, timeout, server_type=server_type)
                
                # 更新服务器历史记录
                server_index = self.servers.index(server)
                self.servers[server_index]['last_query'] = time.time()
                
                if 'error' not in results[idx]:
                    query_time = results[idx].get('query_time', 0)
                    self.servers[server_index]['query_history'].append({
                        'timestamp': time.time(),
                        'query_time': query_time
                    })
                    
                    if 'players' in results[idx]:
                        players = results[idx]['players']
                        self.servers[server_index]['player_history'].append({
                            'timestamp': time.time(),
                            'online': players.get('online', 0),
                            'max': players.get('max', 0)
                        })
                        
            except Exception as e:
                server_type = server.get('type', SERVER_TYPE_JAVA)
                results[idx] = MinecraftPing._create_error_result(str(e), server_type)
        
        # 启动线程
        for i, server in enumerate(servers):
            t = threading.Thread(target=query_server, args=(i, server))
            t.daemon = True
            t.start()
            threads.append(t)
        
        # 显示加载动画（允许被SRV信息打断）
        self._show_loading_animation(threads, "查询服务器状态中...")
        
        # 确保所有线程完成
        for t in threads:
            t.join(timeout=1)
        
        return results

    def _show_loading_animation(self, threads, message="处理中..."):
        """显示加载动画（允许被其他输出打断）"""
        global global_cancel_query
        
        print(f"{Colors.CYAN}{message} (按 ^C 取消){Colors.RESET}", end='', flush=True)
        animation = "|/-\\"
        idx = 0
        start_time = time.time()
        
        try:
            while any(t.is_alive() for t in threads) and (time.time() - start_time < 15):
                time.sleep(0.1)
                if global_cancel_query:
                    break
                # 使用回车符覆盖上一行
                print(f"\r{Colors.CYAN}{message} (按 ^C 取消) {animation[idx % len(animation)]}{Colors.RESET}", end='', flush=True)
                idx += 1
        except KeyboardInterrupt:
            global_cancel_query = True
            print(f"\n{Colors.YELLOW}查询已取消，显示部分结果...{Colors.RESET}")
        finally:
            global_cancel_query = False
            print("\r" + " " * 50 + "\r", end='', flush=True)  # 清除动画

    def display_servers(self, servers):
        """显示服务器信息，带并发查询和颜色输出（保持原版格式）"""
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

        # 并发查询服务器
        results = self.query_servers_concurrently(servers)

        # 显示服务器信息
        for i, server in enumerate(servers):
            result = results[i] if results[i] is not None else MinecraftPing._create_error_result(
                "查询未完成", server.get('type', SERVER_TYPE_JAVA)
            )
            
            # 序号颜色
            index_color = Colors.CYAN
            if 'error' in result and ("离线" in result['error'] or "timed out" in result['error']):
                index_color = Colors.RED
            elif 'players' in result and result['players'].get('online', 0) > 0:
                index_color = Colors.GREEN

            # 服务器类型标识
            server_type = result.get('server_type', server.get('type', SERVER_TYPE_JAVA))
            type_display = f" [{Colors.MAGENTA}基岩版{Colors.RESET}]" if server_type == SERVER_TYPE_BEDROCK else f" [{Colors.BLUE}Java版{Colors.RESET}]"

            print(f"\n{index_color}[{self.current_page * self.page_size + i + 1}]{Colors.RESET} {Colors.BOLD}{server['name']}{type_display}{Colors.RESET}")
            print(f"{Colors.BLUE}地址:{Colors.RESET} {server['ip']}:{server.get('port', 25565 if server_type == SERVER_TYPE_JAVA else 19132)}")
            
            # 显示SRV解析信息
            if 'srv_info' in result:
                srv_info = result['srv_info']
                print(f"{Colors.CYAN}SRV解析:{Colors.RESET} {srv_info['original_host']}:{srv_info['original_port']} → {srv_info['resolved_host']}:{srv_info['resolved_port']}")

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
                if server_type != SERVER_TYPE_BEDROCK and 'players' in result and 'sample' in result['players']:
                    sample_players = result['players']['sample']
                    if sample_players and len(sample_players) > 0:
                        print(f"{Colors.BLUE}在线玩家:{Colors.RESET}")
                        for player in sample_players[:5]:  # 最多显示5个
                            player_name = player.get('name', '未知')
                            # 安全地转换玩家名字中的颜色代码
                            safe_name = MinecraftPing.safe_convert_mc_formatting(player_name, Colors.RESET)
                            print(f"  {Colors.GREEN}•{Colors.RESET} {safe_name}")

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
                if server_type == SERVER_TYPE_BEDROCK:
                    if 'game_mode' in result and result['game_mode']:
                        print(f"{Colors.BLUE}游戏模式:{Colors.RESET} {result['game_mode']}")
                    if 'edition' in result and result['edition']:
                        print(f"{Colors.BLUE}版本:{Colors.RESET} {result['edition']}")

        print("=" * 60)

        # 计算筛选后的服务器总数
        filtered_servers = self.get_filtered_servers()

        print(f"{Colors.CYAN}页码:{Colors.RESET} {self.current_page + 1}/{self.max_page() + 1} | {Colors.CYAN}总数:{Colors.RESET} {len(filtered_servers)}/{len(self.servers)}")
        print(f"{Colors.CYAN}排序:{Colors.RESET} {self.sort_field} ({self.sort_order}) | {Colors.CYAN}每页:{Colors.RESET} {self.page_size}")

    def show_players(self, index):
        """显示指定服务器的完整玩家列表"""
        if index < 0 or index >= len(self.servers):
            print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            return

        server = self.servers[index]
        server_type = server.get('type', SERVER_TYPE_JAVA)
        port = server.get('port', 25565 if server_type == SERVER_TYPE_JAVA else 19132)

        if server_type == SERVER_TYPE_BEDROCK:
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
                        # 安全地转换玩家名字中的颜色代码
                        safe_name = MinecraftPing.safe_convert_mc_formatting(player_name, Colors.RESET)

                        # 每10个玩家分组显示
                        if i % 10 == 0 and i > 0:
                            input(f"{Colors.CYAN}按回车键继续显示...{Colors.RESET}")
                            print("-" * 40)

                        print(f"  {Colors.GREEN}{i+1:2d}.{Colors.RESET} {safe_name}")

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
            # 安全地转换玩家名字中的颜色代码
            safe_name = MinecraftPing.safe_convert_mc_formatting(player_name, Colors.RESET)

            # 每10个玩家分组显示
            if i % 10 == 0 and i > 0:
                input(f"{Colors.CYAN}按回车键继续显示...{Colors.RESET}")
                print("-" * 40)

            print(f"  {Colors.GREEN}{i+1:2d}.{Colors.RESET} {safe_name}")

        print("-" * 40)

    def show_server_info(self, index):
        """显示指定服务器的详细信息，包括历史统计"""
        if index < 0 or index >= len(self.servers):
            print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            return

        server = self.servers[index]
        server_type = server.get('type', SERVER_TYPE_JAVA)
        port = server.get('port', 25565 if server_type == SERVER_TYPE_JAVA else 19132)

        print(f"\n{Colors.BOLD}{Colors.CYAN}服务器详细信息: {server['name']}{Colors.RESET}")
        print(f"{Colors.CYAN}地址: {server['ip']}:{port}{Colors.RESET}")
        print(f"{Colors.CYAN}类型: {'Java版' if server_type == SERVER_TYPE_JAVA else '基岩版'}{Colors.RESET}")
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
                        player_name = player.get('name', '未知')
                        # 安全地转换玩家名字中的颜色代码
                        safe_name = MinecraftPing.safe_convert_mc_formatting(player_name, Colors.RESET)
                        print(f"    {Colors.GREEN}•{Colors.RESET} {safe_name}")

                    if len(sample_players) > 5:
                        print(f"    {Colors.CYAN}... 还有 {len(sample_players) - 5} 个玩家{Colors.RESET}")
        else:
            print(f"  {Colors.YELLOW}暂无历史数据{Colors.RESET}")

        print("-" * 60)

        # 等待用户按回车返回
        input(f"{Colors.CYAN}按回车键返回主菜单...{Colors.RESET}")

    def monitor_server(self, index):
        """监控指定服务器的状态变化"""
        if index < 0 or index >= len(self.servers):
            print(f"{Colors.RED}无效的服务器序号{Colors.RESET}")
            return False
        
        # 检查监控模块是否可用
        if ServerMonitor is None:
            print(f"{Colors.RED}监控模块未加载，无法启动监控功能{Colors.RESET}")
            return False
        
        # 创建监控器
        monitor = ServerMonitor(self, index)
        
        # 开始监控
        monitor.start()
        
        print(f"\n{Colors.GREEN}已退出监控模式{Colors.RESET}")
        input(f"{Colors.CYAN}按回车键返回主菜单...{Colors.RESET}")
        return True

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
                    elif '1.19' in version or '1.20' in version:
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

def print_help(manager):
    return print_common_help(manager, Colors)

def sigint_handler(signum, frame):
    """处理 Ctrl+C 信号"""
    global global_cancel_query

    global_cancel_query = True
    print(f"\n{Colors.YELLOW}正在取消查询...{Colors.RESET}")

def main():
    # 设置信号处理
    signal.signal(signal.SIGINT, sigint_handler)

    manager = ServerManager()

    print_startup_banner(manager, Colors)
    run_main_loop(manager, Colors, MinecraftPing, print_help, handle_command)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}程序已退出{Colors.RESET}")
        sys.exit(0)
