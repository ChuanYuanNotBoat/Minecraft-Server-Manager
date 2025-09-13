import socket
import struct
import time
import select
import json
import re
import zlib
from datetime import datetime
from collections import deque
import uuid
import sys

# 调试模式开关
DEBUG_MODE = True

# 导入提示
print("Minecraft服务器查询模块已导入")
if DEBUG_MODE:
    print("调试模式已启用")

class MinecraftQuery:
    """Minecraft服务器查询模块，支持Java版和基岩版"""
    
    # 颜色代码定义 (ANSI)
    class Colors:
        BLACK = '\033[30m'
        RED = '\033[31m'
        GREEN = '\033[32m'
        YELLOW = '\033[33m'
        BLUE = '\033[34m'
        PURPLE = '\033[35m'
        CYAN = '\033[36m'
        WHITE = '\033[37m'
        RESET = '\033[0m'
        BOLD = '\033[1m'
        
        # Minecraft颜色代码映射
        MC_COLORS = {
            '0': BLACK,     # 黑色
            '1': BLUE,      # 深蓝
            '2': GREEN,     # 绿色
            '3': CYAN,      # 青色
            '4': RED,       # 红色
            '5': PURPLE,    # 紫色
            '6': YELLOW,    # 金色
            '7': WHITE,     # 灰色
            '8': BLACK,     # 深灰
            '9': BLUE,      # 蓝色
            'a': GREEN,     # 亮绿
            'b': CYAN,      # 天蓝
            'c': RED,       # 亮红
            'd': PURPLE,    # 粉红
            'e': YELLOW,    # 黄色
            'f': WHITE,     # 白色
            'k': '',        # 随机字符
            'l': BOLD,      # 粗体
            'm': '',        # 删除线
            'n': '',        # 下划线
            'o': '',        # 斜体
            'r': RESET,     # 重置
        }
    
    # 缓存机制
    cache = {}
    CACHE_DURATION = 60  # 缓存时间(秒)
    
    # 协议版本映射表 (Minecraft版本 -> 协议版本)
    PROTOCOL_VERSIONS = {
        "1.20.1": 763,
        "1.20": 763,
        "1.19.4": 762,
        "1.19.3": 761,
        "1.19.2": 760,
        "1.19.1": 759,
        "1.19": 759,
        "1.18.2": 758,
        "1.18.1": 757,
        "1.18": 757,
        "1.17.1": 756,
        "1.17": 755,
        "1.16.5": 754,
        "1.16.4": 754,
        "1.16.3": 753,
        "1.16.2": 751,
        "1.16.1": 736,
        "1.16": 735,
        "1.15.2": 578,
        "1.15.1": 575,
        "1.15": 573,
        "1.14.4": 498,
        "1.14.3": 490,
        "1.14.2": 485,
        "1.14.1": 480,
        "1.14": 477,
        "1.13.2": 404,
        "1.13.1": 401,
        "1.13": 393,
        "1.12.2": 340,
        "1.12.1": 338,
        "1.12": 335,
        "1.11.2": 316,
        "1.11.1": 316,
        "1.11": 315,
        "1.10.2": 210,
        "1.10.1": 210,
        "1.10": 210,
        "1.9.4": 110,
        "1.9.3": 110,
        "1.9.2": 109,
        "1.9.1": 108,
        "1.9": 107,
        "1.8.9": 47,
        "1.8.8": 47,
        "1.8.7": 47,
        "1.8.6": 47,
        "1.8.5": 47,
        "1.8.4": 47,
        "1.8.3": 47,
        "1.8.2": 47,
        "1.8.1": 47,
        "1.8": 47,
        "1.7.10": 5,
        "1.7.9": 5,
        "1.7.8": 5,
        "1.7.7": 5,
        "1.7.6": 5,
        "1.7.5": 4,
        "1.7.4": 4,
        "1.7.3": 4,
        "1.7.2": 4,
    }
    
    @staticmethod
    def ping(host, port=25565, timeout=3, server_type="auto", use_cache=True):
        """
        主查询方法
        
        参数:
            host: 服务器地址
            port: 服务器端口
            timeout: 超时时间(秒)
            server_type: 服务器类型("java", "bedrock", "auto")
            use_cache: 是否使用缓存
            
        返回:
            服务器信息字典
        """
        if DEBUG_MODE:
            print(f"[DEBUG] 开始查询服务器 {host}:{port}, 类型: {server_type}")
        
        # 检查缓存
        cache_key = f"{host}:{port}"
        if use_cache and cache_key in MinecraftQuery.cache:
            cached_data, timestamp = MinecraftQuery.cache[cache_key]
            if time.time() - timestamp < MinecraftQuery.CACHE_DURATION:
                if DEBUG_MODE:
                    print(f"[DEBUG] 使用缓存数据")
                return cached_data
        
        # 自动检测服务器类型
        if server_type == "auto":
            if DEBUG_MODE:
                print(f"[DEBUG] 自动检测服务器类型")
            server_type = MinecraftQuery.detect_server_type(host, port, timeout)
            if not server_type:
                return {"error": "无法检测服务器类型"}
            if DEBUG_MODE:
                print(f"[DEBUG] 检测到服务器类型: {server_type}")
        
        # 根据服务器类型调用相应查询方法
        start_time = time.time()
        try:
            if server_type == "java":
                if DEBUG_MODE:
                    print(f"[DEBUG] 调用Java版查询")
                result = MinecraftQuery.ping_java(host, port, timeout)
            elif server_type == "bedrock":
                if DEBUG_MODE:
                    print(f"[DEBUG] 调用基岩版查询")
                result = MinecraftQuery.ping_bedrock(host, port, timeout)
            else:
                return {"error": f"不支持的服务器类型: {server_type}"}
            
            # 计算查询时间
            query_time = int((time.time() - start_time) * 1000)
            result["query_time"] = query_time
            
            # 更新缓存
            MinecraftQuery.cache[cache_key] = (result, time.time())
            
            if DEBUG_MODE:
                print(f"[DEBUG] 查询完成，耗时: {query_time}ms")
            
            return result
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 查询失败: {str(e)}")
            return {"error": f"查询失败: {str(e)}"}
    
    @staticmethod
    def ping_java(host, port=25565, timeout=3):
        """Java版服务器查询"""
        if DEBUG_MODE:
            print(f"[DEBUG] Java版查询开始: {host}:{port}")
        
        # 创建TCP连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        connect_start = time.time()
        try:
            if DEBUG_MODE:
                print(f"[DEBUG] 尝试连接到服务器")
            sock.connect((host, port))
            connect_time = int((time.time() - connect_start) * 1000)
            if DEBUG_MODE:
                print(f"[DEBUG] 连接成功，耗时: {connect_time}ms")
        except socket.timeout:
            if DEBUG_MODE:
                print(f"[DEBUG] 连接超时")
            return {"error": "连接超时", "connect_time": int((time.time() - connect_start) * 1000)}
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 连接失败: {str(e)}")
            return {"error": f"连接失败: {str(e)}"}
        
        try:
            # 发送握手包
            protocol_version = MinecraftQuery.PROTOCOL_VERSIONS.get("1.20.1", 763)  # 默认使用1.20.1协议版本
            handshake = MinecraftQuery._pack_varint(0)  # 包ID: 握手
            handshake += MinecraftQuery._pack_varint(protocol_version)  # 协议版本
            handshake += MinecraftQuery._pack_string(host)  # 服务器地址
            handshake += struct.pack('>H', port)  # 服务器端口
            handshake += MinecraftQuery._pack_varint(1)  # 下一状态: 状态
            
            packet = MinecraftQuery._pack_varint(len(handshake)) + handshake
            if DEBUG_MODE:
                print(f"[DEBUG] 发送握手包")
            sock.send(packet)
            
            # 发送状态请求包
            status_request = MinecraftQuery._pack_varint(0)  # 包ID: 状态请求
            packet = MinecraftQuery._pack_varint(len(status_request)) + status_request
            if DEBUG_MODE:
                print(f"[DEBUG] 发送状态请求包")
            sock.send(packet)
            
            # 接收响应
            if DEBUG_MODE:
                print(f"[DEBUG] 等待服务器响应")
            
            # 读取包长度
            length = MinecraftQuery._read_varint(sock)
            if length is None:
                if DEBUG_MODE:
                    print(f"[DEBUG] 无响应")
                return {"error": "无响应", "connect_time": connect_time}
            
            # 读取包数据
            data_bytes = b''
            while len(data_bytes) < length:
                chunk = sock.recv(length - len(data_bytes))
                if not chunk:
                    if DEBUG_MODE:
                        print(f"[DEBUG] 接收数据不完整")
                    return {"error": "接收数据不完整", "connect_time": connect_time}
                data_bytes += chunk

            if DEBUG_MODE:
                print(f"[DEBUG] 收到响应，数据长度: {len(data_bytes)}")
                print(f"[DEBUG] 响应数据前100字节: {data_bytes[:100]}")
            
            # 解析包ID
            packet_id, offset = MinecraftQuery._read_varint_from_bytes(data_bytes)
            if packet_id is None:
                if DEBUG_MODE:
                    print(f"[DEBUG] 解析包ID失败")
                return {"error": "解析包ID失败", "connect_time": connect_time}

            if packet_id != 0x00:  # 状态响应包的ID应该是0x00
                if DEBUG_MODE:
                    print(f"[DEBUG] 无效的响应包ID: {packet_id}")
                return {"error": f"无效的响应包ID: {packet_id}", "connect_time": connect_time}

            # 读取字符串长度
            str_length, varint_size = MinecraftQuery._read_varint_from_bytes(data_bytes[offset:])
            offset += varint_size
            
            # 读取JSON字符串
            json_bytes = data_bytes[offset:offset+str_length]
            json_str = json_bytes.decode('utf-8', errors='ignore')
            
            if DEBUG_MODE:
                print(f"[DEBUG] 收到响应JSON: {json_str}")

            # 解析响应
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                if DEBUG_MODE:
                    print(f"[DEBUG] JSON解析失败: {e}")
                # 尝试处理Forge服务器的响应格式
                try:
                    # Forge服务器可能在JSON后附加了额外的数据
                    json_end = json_str.find('}{') + 1
                    if json_end > 0:
                        json_str = json_str[:json_end]
                        data = json.loads(json_str)
                    else:
                        raise e
                except:
                    return {"error": f"JSON解析失败: {e}", "connect_time": connect_time}
            
            if DEBUG_MODE:
                print(f"[DEBUG] Java版查询完成")
            
            # 处理玩家列表
            players = data.get("players", {})
            sample_players = players.get("sample", [])
            player_list = [p.get("name", "Anonymous Player") for p in sample_players]
            
            # 处理MOTD
            motd = MinecraftQuery.parse_motd(data.get("description", {}))
            
            # 检查是否为Forge服务器
            mod_info = data.get("modinfo", {})
            is_forge = mod_info.get("type", "").lower() == "forge" or "fml" in data
            
            # 返回结果
            result = {
                "server_type": "java",
                "connect_time": connect_time,
                "motd": motd,
                "version": {
                    "name": data.get("version", {}).get("name", "未知"),
                    "protocol": str(data.get("version", {}).get("protocol", -1))
                },
                "players": {
                    "online": players.get("online", 0),
                    "max": players.get("max", 0),
                    "sample": player_list
                },
                "forge": is_forge
            }
            
            # 添加mod信息（如果有）
            if is_forge and "modList" in mod_info:
                result["mods"] = mod_info["modList"]
            
            return result
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] Java版查询异常: {str(e)}")
            return {"error": f"查询异常: {str(e)}", "connect_time": connect_time}
        finally:
            sock.close()
    
    @staticmethod
    def ping_bedrock(host, port=19132, timeout=3):
        """基岩版服务器查询"""
        if DEBUG_MODE:
            print(f"[DEBUG] 基岩版查询开始: {host}:{port}")
        
        # 创建UDP连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        
        connect_start = time.time()
        try:
            # 发送查询包
            query_packet = b"\x01"  # 包ID
            query_packet += b"\x00\x00\x00\x00"  # 会话ID
            query_packet += b"\x00\x00\x00\x00"  # 令牌
            query_packet += bytes([0x00, 0xFF, 0xFF, 0x00, 0xFE, 0xFE, 0xFE, 0xFE, 0xFD, 0xFD, 0xFD, 0xFD, 0x12, 0x34, 0x56, 0x78])  # 魔术数
            
            if DEBUG_MODE:
                print(f"[DEBUG] 发送查询包")
            sock.sendto(query_packet, (host, port))
            
            # 接收响应
            if DEBUG_MODE:
                print(f"[DEBUG] 等待服务器响应")
            response, addr = sock.recvfrom(4096)
            connect_time = int((time.time() - connect_start) * 1000)
            if DEBUG_MODE:
                print(f"[DEBUG] 收到响应，耗时: {connect_time}ms")
            
            # 解析响应
            if len(response) < 35:
                if DEBUG_MODE:
                    print(f"[DEBUG] 响应过短")
                return {"error": "响应过短", "connect_time": connect_time}
            
            # 跳过包头
            offset = 1  # 包ID
            offset += 8  # 会话ID和令牌
            
            # 检查魔术数
            magic = response[offset:offset+16]
            offset += 16
            
            # 解析服务器信息
            server_id = MinecraftQuery._read_string(response, offset)
            offset += len(server_id) + 2
            
            motd = MinecraftQuery._read_string(response, offset)
            offset += len(motd) + 2
            
            protocol = MinecraftQuery._read_string(response, offset)
            offset += len(protocol) + 2
            
            version = MinecraftQuery._read_string(response, offset)
            offset += len(version) + 2
            
            online_players = MinecraftQuery._read_string(response, offset)
            offset += len(online_players) + 2
            
            max_players = MinecraftQuery._read_string(response, offset)
            offset += len(max_players) + 2
            
            if DEBUG_MODE:
                print(f"[DEBUG] 基岩版查询完成")
            
            # 返回结果
            return {
                "server_type": "bedrock",
                "connect_time": connect_time,
                "motd": MinecraftQuery.parse_motd(motd),
                "version": {
                    "name": version,
                    "protocol": protocol
                },
                "players": {
                    "online": int(online_players),
                    "max": int(max_players),
                    "sample": []  # 基岩版不提供玩家列表
                }
            }
        except socket.timeout:
            if DEBUG_MODE:
                print(f"[DEBUG] 连接超时")
            return {"error": "连接超时", "connect_time": int((time.time() - connect_start) * 1000)}
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 查询失败: {str(e)}")
            return {"error": f"查询失败: {str(e)}"}
        finally:
            sock.close()
    
    @staticmethod
    def detect_server_type(host, port=25565, timeout=3):
        """自动检测服务器类型"""
        if DEBUG_MODE:
            print(f"[DEBUG] 开始检测服务器类型: {host}:{port}")
        
        # 先尝试Java版
        result = MinecraftQuery.ping_java(host, port, timeout)
        if "error" not in result:
            if DEBUG_MODE:
                print(f"[DEBUG] 检测到Java版服务器")
            return "java"
        
        # 再尝试基岩版
        result = MinecraftQuery.ping_bedrock(host, port, timeout)
        if "error" not in result:
            if DEBUG_MODE:
                print(f"[DEBUG] 检测到基岩版服务器")
            return "bedrock"
        
        if DEBUG_MODE:
            print(f"[DEBUG] 无法检测服务器类型")
        
        return None
    
    @staticmethod
    def parse_motd(motd_data):
        """解析MOTD公告栏"""
        if DEBUG_MODE:
            print(f"[DEBUG] 解析MOTD: {motd_data}")
        
        if isinstance(motd_data, dict):
            # 处理JSON格式的MOTD
            if "text" in motd_data:
                return MinecraftQuery.convert_mc_formatting(motd_data["text"])
            elif "extra" in motd_data:
                text = ""
                for extra in motd_data["extra"]:
                    if "text" in extra:
                        text += extra["text"]
                return MinecraftQuery.convert_mc_formatting(text)
        elif isinstance(motd_data, str):
            # 处理字符串格式的MOTD
            return MinecraftQuery.convert_mc_formatting(motd_data)
        
        return "未知公告栏"
    
    @staticmethod
    def convert_mc_formatting(text):
        """将Minecraft格式代码转换为ANSI颜色"""
        if not text:
            return ""
        
        if DEBUG_MODE:
            print(f"[DEBUG] 转换Minecraft格式: {text}")
        
        # 处理格式代码
        result = ""
        i = 0
        while i < len(text):
            if text[i] == '§' and i + 1 < len(text):
                color_code = text[i+1]
                if color_code in MinecraftQuery.Colors.MC_COLORS:
                    result += MinecraftQuery.Colors.MC_COLORS[color_code]
                i += 2
            else:
                result += text[i]
                i += 1
        
        return result + MinecraftQuery.Colors.RESET
    
    @staticmethod
    def _pack_varint(value):
        """打包VarInt"""
        if DEBUG_MODE:
            print(f"[DEBUG] 打包VarInt: {value}")
        
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
        if DEBUG_MODE:
            print(f"[DEBUG] 读取VarInt")
        
        result = 0
        shift = 0
        while True:
            byte = sock.recv(1)
            if not byte:
                return None
            byte = ord(byte)
            result |= (byte & 0x7F) << shift
            shift += 7
            if not (byte & 0x80):
                break
        return result
    
    @staticmethod
    def _read_varint_from_bytes(data):
        """从字节数据读取VarInt，返回(value, offset)"""
        if DEBUG_MODE:
            print(f"[DEBUG] 从字节数据读取VarInt")

        result = 0
        shift = 0
        index = 0

        while True:
            if index >= len(data):
                return None, index

            byte = data[index]
            result |= (byte & 0x7F) << shift
            shift += 7
            index += 1

            if not (byte & 0x80):
                break

        return result, index
    
    @staticmethod
    def _pack_string(text):
        """打包字符串"""
        if DEBUG_MODE:
            print(f"[DEBUG] 打包字符串: {text}")
        
        text_bytes = text.encode('utf-8')
        return MinecraftQuery._pack_varint(len(text_bytes)) + text_bytes
    
    @staticmethod
    def _read_string(data, offset):
        """从字节数据读取字符串"""
        if DEBUG_MODE:
            print(f"[DEBUG] 读取字符串，偏移: {offset}")
        
        try:
            length = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
            return data[offset:offset+length].decode('utf-8', errors='ignore')
        except:
            return "未知"
    
    @staticmethod
    def _read_packet(sock):
        """从socket读取数据包"""
        if DEBUG_MODE:
            print(f"[DEBUG] 读取数据包")
        
        # 读取包长度
        length = MinecraftQuery._read_varint(sock)
        if length is None:
            return None
        
        # 读取包数据
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        
        return data.decode('utf-8', errors='ignore')


class MinecraftLogin:
    """Minecraft模拟登录类"""
    
    def __init__(self, host, port=25565, username="MinecraftQueryBot", version="1.20.1"):
        self.host = host
        self.port = port
        self.username = username
        self.version = version
        self.protocol_version = MinecraftQuery.PROTOCOL_VERSIONS.get(version, 763)
        self.socket = None
        self.session_id = str(uuid.uuid4())
        self.compression_threshold = -1
        
        if DEBUG_MODE:
            print(f"[DEBUG] 初始化Minecraft登录: {host}:{port}, 用户: {username}")
    
    def connect(self):
        """连接到服务器"""
        if DEBUG_MODE:
            print(f"[DEBUG] 连接到服务器: {self.host}:{self.port}")
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(10)
        self.socket.connect((self.host, self.port))
        
        # 发送握手包
        self._send_handshake()
        
        # 发送登录开始包
        self._send_login_start()
    
    def _send_handshake(self):
        """发送握手包"""
        if DEBUG_MODE:
            print(f"[DEBUG] 发送握手包")
        
        packet = bytearray()
        
        # 包ID (握手)
        packet.extend(MinecraftQuery._pack_varint(0))
        
        # 协议版本
        packet.extend(MinecraftQuery._pack_varint(self.protocol_version))
        
        # 服务器地址
        packet.extend(MinecraftQuery._pack_string(self.host))
        
        # 服务器端口
        packet.extend(struct.pack('>H', self.port))
        
        # 下一状态 (2 for login)
        packet.extend(MinecraftQuery._pack_varint(2))
        
        # 发送包
        self._send_packet(packet)
    
    def _send_login_start(self):
        """发送登录开始包"""
        if DEBUG_MODE:
            print(f"[DEBUG] 发送登录开始包")
        
        packet = bytearray()
        
        # 包ID (登录开始)
        packet.extend(MinecraftQuery._pack_varint(0))
        
        # 用户名
        packet.extend(MinecraftQuery._pack_string(self.username))
        
        # 发送包
        self._send_packet(packet)
    
    def _send_packet(self, data):
        """发送数据包"""
        if DEBUG_MODE:
            print(f"[DEBUG] 发送数据包，长度: {len(data)}")
        
        # 添加包长度前缀
        length = MinecraftQuery._pack_varint(len(data))
        self.socket.send(length + data)
    
    def receive_packet(self):
        """接收数据包"""
        if DEBUG_MODE:
            print(f"[DEBUG] 接收数据包")
        
        # 读取包长度
        length = MinecraftQuery._read_varint(self.socket)
        if length is None:
            return None
        
        # 读取包数据
        data = b''
        while len(data) < length:
            chunk = self.socket.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        
        return data
    
    def login(self):
        """执行登录流程"""
        if DEBUG_MODE:
            print(f"[DEBUG] 开始登录流程")
        
        try:
            self.connect()
            
            # 处理登录响应
            while True:
                packet = self.receive_packet()
                if packet is None:
                    break
                
                # 解析包ID
                packet_id = MinecraftQuery._read_varint_from_bytes(packet)[0]
                offset = len(MinecraftQuery._pack_varint(packet_id))
                
                # 根据包ID处理
                if packet_id == 0x03:  # Set Compression
                    self.compression_threshold = MinecraftQuery._read_varint_from_bytes(packet[offset:])[0]
                    if DEBUG_MODE:
                        print(f"[DEBUG] 压缩阈值设置为: {self.compression_threshold}")
                
                elif packet_id == 0x02:  # Login Success
                    uuid = MinecraftQuery._read_string_from_bytes(packet[offset:])
                    offset += len(uuid) + 2
                    username = MinecraftQuery._read_string_from_bytes(packet[offset:])
                    if DEBUG_MODE:
                        print(f"[DEBUG] 登录成功: {username} ({uuid})")
                    return True
                
                elif packet_id == 0x01:  # Encryption Request
                    if DEBUG_MODE:
                        print(f"[DEBUG] 服务器要求加密，当前不支持")
                    return False
                
                elif packet_id == 0x00:  # Disconnect
                    reason = packet[offset:].decode('utf-8', errors='ignore')
                    if DEBUG_MODE:
                        print(f"[DEBUG] 服务器断开连接: {reason}")
                    return False
            
            return False
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 登录过程中发生错误: {e}")
            return False
        finally:
            if self.socket:
                self.socket.close()
    
    @staticmethod
    def _read_string_from_bytes(data):
        """从字节数据读取字符串"""
        if DEBUG_MODE:
            print(f"[DEBUG] 从字节数据读取字符串")
        
        length = MinecraftLogin._read_varint_from_bytes(data)[0]
        if length is None:
            return ""
        
        varint_len = len(MinecraftQuery._pack_varint(length))
        string_data = data[varint_len:varint_len+length]
        return string_data.decode('utf-8', errors='ignore')


# 服务器信息查询接口类
class ServerInfoInterface:
    """服务器信息查询接口，用于与server.py协同工作"""
    
    @staticmethod
    def get_detailed_info(host, port, server_type="auto", timeout=5):
        """
        获取服务器的详细信息
        
        参数:
            host: 服务器地址
            port: 服务器端口
            server_type: 服务器类型
            timeout: 超时时间
            
        返回:
            包含详细信息的字典
        """
        if DEBUG_MODE:
            print(f"[DEBUG] 获取服务器详细信息: {host}:{port}")
        
        # 使用MinecraftQuery获取基本信息
        result = MinecraftQuery.ping(host, port, timeout, server_type)
        
        # 添加额外的详细信息
        if "error" not in result:
            # 这里可以添加更多详细信息查询逻辑
            # 例如：获取完整玩家列表、mod信息等
            
            # 如果是Java版服务器，尝试获取更多信息
            if result.get("server_type") == "java":
                # 可以添加更多Java版特定信息查询
                pass
                
            # 如果是基岩版服务器，尝试获取更多信息
            elif result.get("server_type") == "bedrock":
                # 可以添加更多基岩版特定信息查询
                pass
        
        return result
    
    @staticmethod
    def get_player_list(host, port, server_type="auto", timeout=5):
        """
        获取服务器的完整玩家列表
        
        参数:
            host: 服务器地址
            port: 服务器端口
            server_type: 服务器类型
            timeout: 超时时间
            
        返回:
            玩家列表
        """
        if DEBUG_MODE:
            print(f"[DEBUG] 获取玩家列表: {host}:{port}")
        
        # 基岩版不支持玩家列表查询
        if server_type == "bedrock":
            return []
        
        # 使用MinecraftQuery获取玩家列表
        result = MinecraftQuery.ping(host, port, timeout, server_type)
        
        if "error" in result:
            return []
        
        # 返回玩家列表
        return result.get("players", {}).get("sample", [])
    
    @staticmethod
    def get_mod_list(host, port, server_type="auto", timeout=5):
        """
        获取服务器的mod列表
        
        参数:
            host: 服务器地址
            port: 服务器端口
            server_type: 服务器类型
            timeout: 超时时间
            
        返回:
            mod列表
        """
        if DEBUG_MODE:
            print(f"[DEBUG] 获取mod列表: {host}:{port}")
        
        # 只有Java版支持mod列表查询
        if server_type != "java":
            return []
        
        # 使用MinecraftQuery获取服务器信息
        result = MinecraftQuery.ping(host, port, timeout, server_type)
        
        if "error" in result:
            return []
        
        # 检查是否为Forge服务器并返回mod列表
        if result.get("forge", False) and "mods" in result:
            return result["mods"]
        
        return []  # 默认返回空列表


# 使用示例
if __name__ == "__main__":
    # 查询服务器信息
    print("开始查询服务器信息...")
    result = MinecraftQuery.ping("play.simpfun.cn", 23190)
    print("服务器查询结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 模拟登录 (需要服务器支持离线模式)
    # print("开始模拟登录...")
    # login = MinecraftLogin("play.simpfun.cn", 23190, "TestBot")
    # success = login.login()
    # print(f"登录结果: {success}")