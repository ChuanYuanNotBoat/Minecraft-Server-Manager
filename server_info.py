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
import os
import threading
import base64
import hashlib
import random
import string
import tkinter as tk
from tkinter import filedialog
import zipfile

# 调试模式开关
DEBUG_MODE = True

# 导入提示
print("Minecraft服务器查询模块已导入")
if DEBUG_MODE:
    print("调试模式已启用")

# 协议版本文件路径
PROTOCOL_VERSIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "protocol_versions.json")

# 尝试从外部文件加载协议版本
PROTOCOL_VERSIONS = {}
try:
    with open(PROTOCOL_VERSIONS_FILE, 'r', encoding='utf-8') as f:
        loaded_data = json.load(f)

    # 检查是否是嵌套结构（包含"Java Edition"键）
    if "Java Edition" in loaded_data:
        loaded_versions = loaded_data["Java Edition"]
        if DEBUG_MODE:
            print(f"[DEBUG] 检测到嵌套协议版本结构，使用'Java Edition'键下的数据")
    else:
        loaded_versions = loaded_data

    # 确保所有值都是整数，跳过无法转换的值
    for k, v in loaded_versions.items():
        try:
            if v is not None:  # 跳过null值
                PROTOCOL_VERSIONS[k] = int(v)
        except (ValueError, TypeError):
            if DEBUG_MODE:
                print(f"[DEBUG] 跳过无效的协议版本: {k}: {v}")
            continue

    if DEBUG_MODE:
        print(f"[DEBUG] 从外部文件加载了 {len(PROTOCOL_VERSIONS)} 个协议版本")
except Exception as e:
    if DEBUG_MODE:
        print(f"[DEBUG] 无法加载外部协议版本文件: {e}, 使用内置版本")

    # 使用内置的协议版本映射表 (作为回退)
    PROTOCOL_VERSIONS = {
        "1.21.1": 767,
        "1.21": 766,
        "1.20.6": 766,
        "1.20.5": 766,
        "1.20.4": 765,
        "1.20.3": 765,
        "1.20.2": 764,
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
            protocol_version = PROTOCOL_VERSIONS.get("1.20.1", 763)  # 默认使用1.20.1协议版本
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
        self.protocol_version = PROTOCOL_VERSIONS.get(version, 763)
        self.socket = None
        self.session_id = str(uuid.uuid4())
        self.compression_threshold = -1
        self.is_forge = False
        self.mods_list = []
        self.forge_mods = []
        self.channels = ["FML|HS", "FML", "FML|MP", "FORGE"]

        # 创建mods配置目录
        self.mods_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods_config")
        if not os.path.exists(self.mods_dir):
            os.makedirs(self.mods_dir)

        # 服务器标识符（用于文件名）
        self.server_id = f"{self.host}_{self.port}".replace(".", "_").replace(":", "_")
        self.mods_config_file = os.path.join(self.mods_dir, f"{self.server_id}.json")

        # 尝试加载现有的mod配置
        self.forge_mods = self._load_mods_config()

        if DEBUG_MODE:
            print(f"[DEBUG] 初始化Minecraft登录: {self.host}:{self.port}, 用户: {self.username}")

    def _load_mods_config(self):
        """加载现有的mod配置"""
        if os.path.exists(self.mods_config_file):
            try:
                with open(self.mods_config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                if DEBUG_MODE:
                    print(f"[DEBUG] 加载mod配置失败: {e}")

        # 如果没有配置或加载失败，返回默认的mod列表
        return [
            {"modid": "forge", "version": "40.2.0"},
            {"modid": "minecraft", "version": self.version}
        ]

    def _save_mods_config(self, mods_list):
        """保存mod配置到文件"""
        try:
            with open(self.mods_config_file, 'w', encoding='utf-8') as f:
                json.dump(mods_list, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 保存mod配置失败: {e}")
            return False

    def select_mods_folder(self):
        """选择mods文件夹并解析mod信息"""
        try:
            # 尝试使用GUI文件对话框
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            folder_path = filedialog.askdirectory(title="选择Minecraft mods文件夹")
            root.destroy()

            if not folder_path:
                # 如果GUI选择失败或用户取消，使用命令行输入
                print("GUI选择失败或取消，请输入mods文件夹路径:")
                folder_path = input("mods文件夹路径: ").strip()

            if not folder_path or not os.path.exists(folder_path):
                print("无效的路径，使用默认mod列表")
                return self.forge_mods

            # 解析mods文件夹
            mods_list = self._parse_mods_folder(folder_path)

            # 保存配置
            if mods_list:
                self._save_mods_config(mods_list)
                self.forge_mods = mods_list
                self.is_forge = len(mods_list) > 2  # 如果除了minecraft和forge外还有其他mod，则认为是Forge服务器

            return mods_list

        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 选择mods文件夹失败: {e}")
            print("选择mods文件夹失败，使用默认mod列表")
            return self.forge_mods

    def _parse_mods_folder(self, folder_path):
        """解析mods文件夹中的jar文件"""
        mods_list = []

        # 添加基础mod
        mods_list.append({"modid": "forge", "version": "40.2.0"})
        mods_list.append({"modid": "minecraft", "version": self.version})

        # 扫描mods文件夹
        for filename in os.listdir(folder_path):
            if filename.endswith('.jar'):
                mod_info = self._extract_mod_info(os.path.join(folder_path, filename))
                if mod_info:
                    mods_list.append(mod_info)

        return mods_list

    def _extract_mod_info(self, jar_path):
        """从jar文件中提取mod信息"""
        try:
            with zipfile.ZipFile(jar_path, 'r') as jar:
                # 首先尝试读取META-INF/mods.toml (Forge 1.13+)
                if 'META-INF/mods.toml' in jar.namelist():
                    with jar.open('META-INF/mods.toml') as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        mod_info = self._parse_mods_toml(content, os.path.basename(jar_path))
                        if mod_info and mod_info.get("version") != "unknown":
                            return mod_info

                # 尝试读取mcmod.info (Forge 1.12-)
                if 'mcmod.info' in jar.namelist():
                    with jar.open('mcmod.info') as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        mod_info = self._parse_mcmod_info(content, os.path.basename(jar_path))
                        if mod_info and mod_info.get("version") != "unknown":
                            return mod_info

                # 尝试读取fabric.mod.json (Fabric)
                if 'fabric.mod.json' in jar.namelist():
                    with jar.open('fabric.mod.json') as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        mod_info = self._parse_fabric_mod_json(content, os.path.basename(jar_path))
                        if mod_info and mod_info.get("version") != "unknown":
                            return mod_info

                # 如果以上方法都失败，尝试从文件名提取版本信息
                filename = os.path.basename(jar_path)
                return self._parse_mod_from_filename(filename)

        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 解析mod文件失败 {jar_path}: {e}")
            return None

    def _parse_mods_toml(self, content, filename):
        """解析mods.toml文件"""
        modid = None
        version = None
        display_name = None

        # 更全面的解析逻辑
        lines = content.split('\n')
        in_mod_section = False

        for line in lines:
            line = line.strip()

            # 检测mod部分开始
            if line == "[[mods]]":
                in_mod_section = True
                continue

            # 只在mod部分内解析
            if in_mod_section:
                if line.startswith('modId='):
                    modid = line.split('=', 1)[1].strip().strip('"\'')
                elif line.startswith('version='):
                    version = line.split('=', 1)[1].strip().strip('"\'')
                elif line.startswith('displayName='):
                    display_name = line.split('=', 1)[1].strip().strip('"\'')
                elif line.startswith('[') and not line.startswith('[[mods]]'):
                    # 新节开始，退出mod部分
                    break

        # 如果解析失败，使用文件名
        if not modid:
            modid = filename.replace('.jar', '')
        if not version or version == "${file.jarVersion}":
            version = self._extract_version_from_filename(filename)

        return {"modid": modid, "version": version, "display_name": display_name}

    def _parse_mcmod_info(self, content, filename):
        """解析mcmod.info文件"""
        try:
            # 尝试解析JSON
            data = json.loads(content)

            # 处理不同的JSON结构
            if isinstance(data, list) and len(data) > 0:
                # 旧格式: [{"modid": "...", "version": "...", ...}]
                mod_info = data[0]
                modid = mod_info.get("modid", filename.replace('.jar', ''))
                version = mod_info.get("version", "unknown")
            elif isinstance(data, dict):
                # 新格式: {"modList": [{"modid": "...", "version": "...", ...}]}
                if "modList" in data and isinstance(data["modList"], list) and len(data["modList"]) > 0:
                    mod_info = data["modList"][0]
                    modid = mod_info.get("modid", filename.replace('.jar', ''))
                    version = mod_info.get("version", "unknown")
                else:
                    modid = filename.replace('.jar', '')
                    version = "unknown"
            else:
                modid = filename.replace('.jar', '')
                version = "unknown"

            return {"modid": modid, "version": version}
        except:
            # 如果解析失败，尝试从文件名提取
            return self._parse_mod_from_filename(filename)

    def _parse_fabric_mod_json(self, content, filename):
        """解析Fabric mod的JSON文件"""
        try:
            data = json.loads(content)
            modid = data.get("id", filename.replace('.jar', ''))
            version = data.get("version", "unknown")
            return {"modid": modid, "version": version}
        except:
            return {"modid": filename.replace('.jar', ''), "version": "unknown"}

    def _parse_mod_from_filename(self, filename):
        """从文件名解析mod信息"""
        # 移除.jar扩展名
        name = filename.replace('.jar', '')

        # 常见mod文件名模式: modname-version 或 modname_version
        patterns = [
            r'(.+?)[-_](\d+\.\d+(?:\.\d+)?(?:-.+)?)$',  # modname-1.2.3 或 modname_1.2.3
            r'(.+?)[-_]v?(\d+(?:\.\d+)*(?:-.+)?)$',  # modname-v1.2.3 或 modname_v1.2.3
        ]

        for pattern in patterns:
            match = re.match(pattern, name)
            if match:
                modid = match.group(1)
                version = match.group(2)
                # 确保modid不包含版本号部分
                if version and not modid.endswith(version):
                    return {"modid": modid, "version": version}

        # 如果无法从文件名提取版本，返回基本mod信息
        return {"modid": name, "version": "unknown"}

    def _extract_version_from_filename(self, filename):
        """从文件名提取版本号"""
        # 常见版本号模式
        patterns = [
            r'(\d+\.\d+(?:\.\d+)?(?:-.+)?)$',  # 1.2.3 或 1.2.3-alpha
            r'[_-]v?(\d+(?:\.\d+)*(?:-.+)?)$',  # -v1.2.3 或 _1.2.3
        ]

        name = filename.replace('.jar', '')
        for pattern in patterns:
            match = re.search(pattern, name)
            if match:
                return match.group(1)

        return "unknown"

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

        # 如果是Forge服务器，添加Forge特定的数据
        if self.is_forge and self.forge_mods:
            # Forge握手数据
            forge_data = bytearray()

            # FML|HS标记
            forge_data.extend(MinecraftQuery._pack_string("FML|HS"))

            # Forge版本信息
            forge_data.extend(MinecraftQuery._pack_string("FML"))
            forge_data.extend(MinecraftQuery._pack_varint(3))  # 协议版本
            forge_data.extend(MinecraftQuery._pack_varint(len(self.forge_mods)))  # mod数量

            # 添加每个mod的信息
            for mod in self.forge_mods:
                forge_data.extend(MinecraftQuery._pack_string(mod["modid"]))
                forge_data.extend(MinecraftQuery._pack_string(mod["version"]))

            # 将Forge数据添加到握手包
            packet.extend(forge_data)

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

    def _handle_forge_handshake(self, data):
        """处理Forge握手响应"""
        if DEBUG_MODE:
            print(f"[DEBUG] 处理Forge握手响应")

        try:
            # 解析Forge响应
            offset = 0

            # 读取FML标记
            fml_marker, varint_len = MinecraftQuery._read_varint_from_bytes(data[offset:])
            offset += varint_len
            fml_marker_str = data[offset:offset + fml_marker].decode('utf-8', errors='ignore')
            offset += fml_marker

            if fml_marker_str == "FML":
                # 读取协议版本
                protocol_version, varint_len = MinecraftQuery._read_varint_from_bytes(data[offset:])
                offset += varint_len

                if DEBUG_MODE:
                    print(f"[DEBUG] Forge协议版本: {protocol_version}")

                # 这里可以添加更多的Forge响应处理逻辑
                return True
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 处理Forge握手响应失败: {e}")

        return False

    def _send_login_plugin_response(self, message_id, success=True, data=b''):
        """发送Login Plugin Response"""
        if DEBUG_MODE:
            print(f"[DEBUG] 发送Login Plugin Response")

        packet = bytearray()

        # 包ID (Login Plugin Response)
        packet.extend(MinecraftQuery._pack_varint(0x02))

        # 消息ID
        packet.extend(MinecraftQuery._pack_varint(message_id))

        # 成功标志
        packet.extend(b'\x01' if success else b'\x00')

        # 数据
        if success and data:
            packet.extend(MinecraftQuery._pack_varint(len(data)))
            packet.extend(data)
        else:
            packet.extend(MinecraftQuery._pack_varint(0))

        # 发送包
        self._send_packet(packet)

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
                packet_id, offset = MinecraftQuery._read_varint_from_bytes(packet)
                if packet_id is None:
                    continue

                # 根据包ID处理
                if packet_id == 0x03:  # Set Compression
                    self.compression_threshold = MinecraftQuery._read_varint_from_bytes(packet[offset:])[0]
                    if DEBUG_MODE:
                        print(f"[DEBUG] 压缩阈值设置为: {self.compression_threshold}")

                elif packet_id == 0x02:  # Login Success
                    uuid_str = MinecraftQuery._read_string_from_bytes(packet[offset:])
                    offset += len(uuid_str) + 2
                    username = MinecraftQuery._read_string_from_bytes(packet[offset:])
                    if DEBUG_MODE:
                        print(f"[DEBUG] 登录成功: {username} ({uuid_str})")
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

                elif packet_id == 0x04:  # Login Plugin Request (Forge相关)
                    if DEBUG_MODE:
                        print(f"[DEBUG] 收到Login Plugin Request，处理Forge握手")

                    # 读取消息ID
                    message_id, varint_len = MinecraftQuery._read_varint_from_bytes(packet[offset:])
                    offset += varint_len

                    # 读取通道名称
                    channel_len, varint_len = MinecraftQuery._read_varint_from_bytes(packet[offset:])
                    offset += varint_len
                    channel = packet[offset:offset + channel_len].decode('utf-8', errors='ignore')
                    offset += channel_len

                    # 读取数据
                    data_len, varint_len = MinecraftQuery._read_varint_from_bytes(packet[offset:])
                    offset += varint_len
                    data = packet[offset:offset + data_len] if data_len > 0 else b''

                    if DEBUG_MODE:
                        print(f"[DEBUG] Login Plugin Request - 消息ID: {message_id}, 通道: {channel}, 数据长度: {data_len}")

                    # 处理Forge握手
                    if channel == "FML|HS":
                        self._handle_forge_handshake(data)

                    # 发送响应
                    self._send_login_plugin_response(message_id, True)

                # 添加对其他可能包的处理
                else:
                    if DEBUG_MODE:
                        print(f"[DEBUG] 收到未知包ID: {packet_id}，长度: {len(packet)}")
                    # 对于未知包，继续处理，不立即断开

            return False
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 登录过程中发生错误: {e}")
            return False

    @staticmethod
    def _read_string_from_bytes(data):
        """从字节数据读取字符串"""
        if DEBUG_MODE:
            print(f"[DEBUG] 从字节数据读取字符串")

        str_length, varint_size = MinecraftQuery._read_varint_from_bytes(data)
        if str_length is None:
            return ""

        varint_len = len(MinecraftQuery._pack_varint(str_length))
        string_data = data[varint_len:varint_len+str_length]
        return string_data.decode('utf-8', errors='ignore')


class MinecraftChatClient:
    """Minecraft聊天客户端，支持监听和发送聊天消息"""

    # 聊天消息类型
    CHAT_MESSAGE = 0x0F
    SYSTEM_MESSAGE = 0x0A
    PLAYER_LIST = 0x36
    DISCONNECT = 0x1A

    def __init__(self, host, port=25565, username="ChatClient", version=None):
        self.host = host
        self.port = port
        self.username = username

        # 如果没有指定版本，尝试自动检测
        if version is None:
            self.version = self.detect_server_version()
        else:
            self.version = version

        # 获取协议版本
        if self.version in PROTOCOL_VERSIONS:
            self.protocol_version = PROTOCOL_VERSIONS[self.version]
        else:
            # 如果版本不在映射表中，尝试找到最接近的版本
            self.protocol_version = self.find_closest_protocol_version(self.version)
            if DEBUG_MODE:
                print(f"[DEBUG] 版本 {self.version} 不在映射表中，使用协议版本 {self.protocol_version}")

        self.socket = None
        self.session_id = str(uuid.uuid4())
        self.compression_threshold = -1
        self.running = False
        self.chat_callback = None
        self.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_logs")
        self.current_log_file = None
        self.server_name = f"{host}:{port}"
        self.is_forge = False
        self.forge_mods = []
        self.channels = ["FML|HS", "FML", "FML|MP", "FORGE"]

        # 确保日志目录存在
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # 创建mods配置目录
        self.mods_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods_config")
        if not os.path.exists(self.mods_dir):
            os.makedirs(self.mods_dir)

        # 服务器标识符（用于文件名）
        self.server_id = f"{self.host}_{self.port}".replace(".", "_").replace(":", "_")
        self.mods_config_file = os.path.join(self.mods_dir, f"{self.server_id}.json")

        # 尝试加载现有的mod配置
        self.forge_mods = self._load_mods_config()

    def _load_mods_config(self):
        """加载现有的mod配置"""
        if os.path.exists(self.mods_config_file):
            try:
                with open(self.mods_config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                if DEBUG_MODE:
                    print(f"[DEBUG] 加载mod配置失败: {e}")

        # 如果没有配置或加载失败，返回默认的mod列表
        return [
            {"modid": "forge", "version": "40.2.0"},
            {"modid": "minecraft", "version": self.version}
        ]

    def set_forge_mods(self, mods_list):
        """设置Forge mod列表"""
        self.forge_mods = mods_list
        self.is_forge = len(mods_list) > 2  # 如果除了minecraft和forge外还有其他mod，则认为是Forge服务器

    def detect_server_version(self):
        """自动检测服务器版本"""
        try:
            result = MinecraftQuery.ping(self.host, self.port, timeout=3, server_type="java")
            if "error" not in result and "version" in result:
                return result["version"].get("name", "1.20.1")
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 版本检测失败: {str(e)}")

        # 默认回退版本
        return "1.20.1"

    def find_closest_protocol_version(self, version):
        """查找最接近的协议版本"""
        # 尝试解析版本号
        try:
            version_parts = list(map(int, version.split('.')))

            # 查找所有可用的版本
            available_versions = []
            for v in PROTOCOL_VERSIONS.keys():
                try:
                    v_parts = list(map(int, v.split('.')))
                    available_versions.append((v, v_parts))
                except:
                    continue

            # 按版本号排序
            available_versions.sort(key=lambda x: x[1])

            # 找到最接近的版本
            closest_version = "1.21.1"  # 默认最新版本
            min_diff = float('inf')

            for v, v_parts in available_versions:
                # 计算版本差异
                diff = 0
                for i in range(min(len(version_parts), len(v_parts))):
                    diff += abs(version_parts[i] - v_parts[i]) * (10 ** (3 - i))

                if diff < min_diff:
                    min_diff = diff
                    closest_version = v

            return PROTOCOL_VERSIONS[closest_version]
        except:
            # 如果解析失败，返回最新版本的协议号
            return PROTOCOL_VERSIONS.get("1.21.1", 767)

    def set_server_name(self, name):
        """设置服务器名称（用于日志文件）"""
        self.server_name = name
        # 创建服务器特定的日志目录
        server_log_dir = os.path.join(self.log_dir, self.server_name)
        if not os.path.exists(server_log_dir):
            os.makedirs(server_log_dir)

    def set_chat_callback(self, callback):
        """设置聊天消息回调函数"""
        self.chat_callback = callback

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

        # 如果是Forge服务器，添加Forge特定的数据
        if self.is_forge and self.forge_mods:
            # Forge握手数据
            forge_data = bytearray()

            # FML|HS标记
            forge_data.extend(MinecraftQuery._pack_string("FML|HS"))

            # Forge版本信息
            forge_data.extend(MinecraftQuery._pack_string("FML"))
            forge_data.extend(MinecraftQuery._pack_varint(3))  # 协议版本
            forge_data.extend(MinecraftQuery._pack_varint(len(self.forge_mods)))  # mod数量

            # 添加每个mod的信息
            for mod in self.forge_mods:
                forge_data.extend(MinecraftQuery._pack_string(mod["modid"]))
                forge_data.extend(MinecraftQuery._pack_string(mod["version"]))

            # 将Forge数据添加到握手包
            packet.extend(forge_data)

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

        try:
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
        except socket.timeout:
            return None
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 接收数据包出错: {e}")
            return None

    def _handle_forge_handshake(self, data):
        """处理Forge握手响应"""
        if DEBUG_MODE:
            print(f"[DEBUG] 处理Forge握手响应")

        try:
            # 解析Forge响应
            offset = 0

            # 读取FML标记
            fml_marker, varint_len = MinecraftQuery._read_varint_from_bytes(data[offset:])
            offset += varint_len
            fml_marker_str = data[offset:offset + fml_marker].decode('utf-8', errors='ignore')
            offset += fml_marker

            if fml_marker_str == "FML":
                # 读取协议版本
                protocol_version, varint_len = MinecraftQuery._read_varint_from_bytes(data[offset:])
                offset += varint_len

                if DEBUG_MODE:
                    print(f"[DEBUG] Forge协议版本: {protocol_version}")

                # 这里可以添加更多的Forge响应处理逻辑
                return True
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 处理Forge握手响应失败: {e}")

        return False

    def _send_login_plugin_response(self, message_id, success=True, data=b''):
        """发送Login Plugin Response"""
        if DEBUG_MODE:
            print(f"[DEBUG] 发送Login Plugin Response")

        packet = bytearray()

        # 包ID (Login Plugin Response)
        packet.extend(MinecraftQuery._pack_varint(0x02))

        # 消息ID
        packet.extend(MinecraftQuery._pack_varint(message_id))

        # 成功标志
        packet.extend(b'\x01' if success else b'\x00')

        # 数据
        if success and data:
            packet.extend(MinecraftQuery._pack_varint(len(data)))
            packet.extend(data)
        else:
            packet.extend(MinecraftQuery._pack_varint(0))

        # 发送包
        self._send_packet(packet)

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
                packet_id, offset = MinecraftQuery._read_varint_from_bytes(packet)
                if packet_id is None:
                    continue

                # 根据包ID处理
                if packet_id == 0x03:  # Set Compression
                    self.compression_threshold = MinecraftQuery._read_varint_from_bytes(packet[offset:])[0]
                    if DEBUG_MODE:
                        print(f"[DEBUG] 压缩阈值设置为: {self.compression_threshold}")

                elif packet_id == 0x02:  # Login Success
                    uuid_str = MinecraftQuery._read_string_from_bytes(packet[offset:])
                    offset += len(uuid_str) + 2
                    username = MinecraftQuery._read_string_from_bytes(packet[offset:])
                    if DEBUG_MODE:
                        print(f"[DEBUG] 登录成功: {username} ({uuid_str})")
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

                elif packet_id == 0x04:  # Login Plugin Request (Forge相关)
                    if DEBUG_MODE:
                        print(f"[DEBUG] 收到Login Plugin Request，处理Forge握手")

                    # 读取消息ID
                    message_id, varint_len = MinecraftQuery._read_varint_from_bytes(packet[offset:])
                    offset += varint_len

                    # 读取通道名称
                    channel_len, varint_len = MinecraftQuery._read_varint_from_bytes(packet[offset:])
                    offset += varint_len
                    channel = packet[offset:offset + channel_len].decode('utf-8', errors='ignore')
                    offset += channel_len

                    # 读取数据
                    data_len, varint_len = MinecraftQuery._read_varint_from_bytes(packet[offset:])
                    offset += varint_len
                    data = packet[offset:offset + data_len] if data_len > 0 else b''

                    if DEBUG_MODE:
                        print(f"[DEBUG] Login Plugin Request - 消息ID: {message_id}, 通道: {channel}, 数据长度: {data_len}")

                    # 处理Forge握手
                    if channel == "FML|HS":
                        self._handle_forge_handshake(data)

                    # 发送响应
                    self._send_login_plugin_response(message_id, True)

                # 添加对其他可能包的处理
                else:
                    if DEBUG_MODE:
                        print(f"[DEBUG] 收到未知包ID: {packet_id}，长度: {len(packet)}")
                    # 对于未知包，继续处理，不立即断开

            return False
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 登录过程中发生错误: {e}")
            return False

    def send_chat_message(self, message):
        """发送聊天消息"""
        if not self.socket or not self.running:
            return False

        try:
            packet = bytearray()

            # 包ID (聊天消息)
            packet.extend(MinecraftQuery._pack_varint(0x03))

            # 消息内容
            packet.extend(MinecraftQuery._pack_string(message))

            # 发送包
            self._send_packet(packet)

            # 记录发送的消息
            self._log_message("SENT", self.username, message)

            return True
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 发送聊天消息失败: {e}")
            return False

    def _log_message(self, message_type, sender, message):
        """记录聊天消息到文件"""
        try:
            # 获取当前日期作为文件名
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = os.path.join(self.log_dir, self.server_name, f"{today}.txt")

            # 打开日志文件
            with open(log_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_entry = f"[{timestamp}] [{message_type}] {sender}: {message}\n"
                f.write(log_entry)
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 记录消息失败: {e}")

    def _process_chat_packet(self, packet):
        """处理聊天数据包"""
        try:
            # 解析JSON聊天数据
            offset = 0
            json_length, varint_size = MinecraftQuery._read_varint_from_bytes(packet[offset:])
            offset += varint_size

            json_data = packet[offset:offset+json_length]
            chat_data = json.loads(json_data.decode('utf-8'))

            # 提取聊天消息
            if isinstance(chat_data, dict):
                if "text" in chat_data:
                    message = chat_data["text"]
                    sender = "System"

                    # 检查是否有额外信息
                    if "extra" in chat_data and isinstance(chat_data["extra"], list):
                        for extra in chat_data["extra"]:
                            if isinstance(extra, dict) and "text" in extra:
                                message += extra["text"]

                    # 记录消息
                    self._log_message("CHAT", sender, message)

                    # 调用回调函数
                    if self.chat_callback:
                        self.chat_callback(sender, message)

                # 处理玩家聊天消息
                elif "translate" in chat_data and chat_data["translate"] == "chat.type.text":
                    if "with" in chat_data and isinstance(chat_data["with"], list) and len(chat_data["with"]) >= 2:
                        sender_data = chat_data["with"][0]
                        message_data = chat_data["with"][1]

                        if isinstance(sender_data, dict) and "text" in sender_data:
                            sender = sender_data["text"]
                        else:
                            sender = str(sender_data)

                        if isinstance(message_data, dict) and "text" in message_data:
                            message = message_data["text"]
                        else:
                            message = str(message_data)

                        # 记录消息
                        self._log_message("CHAT", sender, message)

                        # 调用回调函数
                        if self.chat_callback:
                            self.chat_callback(sender, message)

            return True
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 处理聊天数据包失败: {e}")
            return False

    def start_listening(self):
        """开始监听聊天消息"""
        if not self.login():
            return False

        self.running = True

        # 启动监听线程
        listener_thread = threading.Thread(target=self._listen_loop)
        listener_thread.daemon = True
        listener_thread.start()

        return True

    def _listen_loop(self):
        """监听循环"""
        while self.running:
            try:
                packet = self.receive_packet()
                if packet is None:
                    continue

                # 解析包ID
                packet_id = MinecraftQuery._read_varint_from_bytes(packet)[0]
                offset = len(MinecraftQuery._pack_varint(packet_id))

                # 处理不同类型的包
                if packet_id == self.CHAT_MESSAGE:
                    self._process_chat_packet(packet[offset:])
                elif packet_id == self.SYSTEM_MESSAGE:
                    self._process_chat_packet(packet[offset:])
                elif packet_id == self.DISCONNECT:
                    # 服务器断开连接
                    reason = packet[offset:].decode('utf-8', errors='ignore')
                    if DEBUG_MODE:
                        print(f"[DEBUG] 服务器断开连接: {reason}")
                    self.running = False
                    break

            except Exception as e:
                if DEBUG_MODE:
                    print(f"[DEBUG] 监听循环出错: {e}")
                self.running = False
                break

        # 关闭连接
        if self.socket:
            self.socket.close()

    def stop(self):
        """停止监听"""
        self.running = False
        if self.socket:
            self.socket.close()



# === Forge/FML mod 探测与缓存集成 ===
import os
import json
from forge_login_client import get_mods_from_server

MODS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods_config")

def load_cached_mods(host: str, port: int) -> list:
    os.makedirs(MODS_DIR, exist_ok=True)
    fname = f"{host.replace('.', '_')}_{port}.json"
    path = os.path.join(MODS_DIR, fname)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_mods(host: str, port: int, mods: list):
    os.makedirs(MODS_DIR, exist_ok=True)
    fname = f"{host.replace('.', '_')}_{port}.json"
    path = os.path.join(MODS_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mods, f, ensure_ascii=False, indent=2)

def query_and_cache_mods(host: str, port: int, username: str, mods_hint=None) -> list:
    cached = load_cached_mods(host, port)
    if cached:
        print(f"[i] Loaded {len(cached)} mods from cache.")
        return cached
    print("[i] No cache, querying server...")
    mods = get_mods_from_server(host, port, username, mods_hint)
    save_mods(host, port, mods)
    return mods

# 服务器信息查询接口类
class ServerInfoInterface:
    """服务器信息查询接口，用于与server.py协同工作"""

    @staticmethod
    def get_detailed_info(host, port, server_type="auto", timeout=5):
        """
        获取服务器的详细信息，集成 mod 探测与缓存
        """
        if DEBUG_MODE:
            print(f"[DEBUG] 获取服务器详细信息: {host}:{port}")

        # 使用MinecraftQuery获取基本信息
        result = MinecraftQuery.ping(host, port, timeout, server_type)

        # 集成 mod 探测与缓存（仅Java版）
        if "error" not in result and result.get("server_type") == "java":
            # 优先用缓存，否则主动探测
            mods = load_cached_mods(host, port)
            if not mods:
                # 尝试用 get_mods_from_server 主动探测
                mods = get_mods_from_server(host, port, "QueryBot")
                save_mods(host, port, mods)
            result["mods"] = mods

        return result

    @staticmethod
    def get_player_list(host, port, server_type="auto", timeout=5):
        """
        获取服务器的完整玩家列表
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
    def get_mod_list(host, port, server_type="auto", timeout=5, username="QueryBot"):
        """
        获取服务器的mod列表，优先缓存，必要时主动探测
        """
        if DEBUG_MODE:
            print(f"[DEBUG] 获取mod列表: {host}:{port}")

        # 只有Java版支持mod列表查询
        if server_type != "java":
            return []

        # 优先用缓存
        mods = load_cached_mods(host, port)
        if mods:
            return mods

        # 主动探测
        mods = get_mods_from_server(host, port, username)
        save_mods(host, port, mods)
        return mods

# 统一外部接口，便于 server.py 调用
def query_server_info(host, port, username="QueryBot", server_type="java"):
    """
    统一接口：返回详细信息和 mod 列表，优先缓存，必要时主动探测
    """
    info = ServerInfoInterface.get_detailed_info(host, port, server_type)
    mods = ServerInfoInterface.get_mod_list(host, port, server_type, username=username)
    info["mods"] = mods
    return info


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
