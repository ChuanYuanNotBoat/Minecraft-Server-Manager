"""
forge_login_client.py

用途：
- 提供 Forge/FML 服务器 mod 列表探测、握手模拟、可选 mod 列表声明。
- 既可独立命令行运行，也可被 server.py/server_info.py 调用。

说明：
- 该脚本旨在通过模拟 Minecraft 客户端与 Forge/FML 服务器的登录握手，探测并返回服务器期望的 mod 列表。
- 通过分析服务器在登录阶段发送的自定义插件消息，提取 mod 列表和握手步骤。
- 可选地，脚本可以发送一个虚假的 mod 列表，以满足某些期望特定 mod 的服务器。

注意事项：
- 该实现并不完美，主要用于查询、聊天和玩家检测。
- 不支持 Mojang 在线验证或完整的加密握手。
- Forge/FML 握手格式因版本而异，脚本内置了多种常见格式的检测和解析。
- 对于某些特定的协议对话，可能需要手动调整和分析。

用法：
    python forge_login_client.py <host> [port] [username] [--mods "mod1:version1,mod2:version2"]

示例：
    python forge_login_client.py play.example.com 25565 PlayerBot --mods "minecraft:1.20.1,forge:40.2.0"

"""

import socket
import struct
import time
import sys
import json
import re
import argparse
from typing import Optional, List, Dict, Any

# Minimal VarInt utilities

def pack_varint(value: int) -> bytes:
    if value < 0:
        value = (1 << 32) + value
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value != 0:
            byte |= 0x80
        out.append(byte)
        if value == 0:
            break
    return bytes(out)


def read_varint_from_socket(sock: socket.socket, timeout=3) -> Optional[int]:
    sock.settimeout(timeout)
    result = 0
    shift = 0
    while True:
        b = sock.recv(1)
        if not b:
            return None
        byte = b[0]
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            break
        if shift > 35:
            raise Exception("VarInt too big")
    if result > 0x7FFFFFFF:
        result -= 0x100000000
    return result


def pack_string(s: str) -> bytes:
    b = s.encode('utf-8')
    return pack_varint(len(b)) + b


class ForgeLoginClient:
    def __init__(self, host: str, port: int = 25565, username: str = 'PlayerBot', 
                 protocol_version: int = 763, predefined_mods: Optional[List[Dict[str, str]]] = None):
        self.host = host
        self.port = port
        self.username = username
        self.protocol_version = protocol_version
        self.predefined_mods = predefined_mods or []
        self.sock: Optional[socket.socket] = None
        self.recv_timeout = 5

    def connect(self, timeout=5):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        print(f"[+] Connecting to {self.host}:{self.port}...")
        self.sock.connect((self.host, self.port))
        print("[+] Connected")

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def send_packet(self, packet_id: int, payload: bytes):
        # packet = VarInt(length) + packet_bytes
        packet_body = pack_varint(packet_id) + payload
        packet = pack_varint(len(packet_body)) + packet_body
        self.sock.sendall(packet)

    def send_handshake(self, next_state=2):
        # Handshake packet (state 1 -> status, 2 -> login)
        payload = pack_varint(self.protocol_version)
        payload += pack_string(self.host)
        payload += struct.pack('>H', self.port)
        payload += pack_varint(next_state)
        # packet id 0x00 for Handshake in modern protocols
        self.send_packet(0x00, payload)
        print("[>] Sent Handshake")

    def send_login_start(self):
        # Login Start packet id 0x00 in login state
        payload = pack_string(self.username)
        self.send_packet(0x00, payload)
        print(f"[>] Sent Login Start (username={self.username})")

    def send_plugin_message_login_phase(self, channel: str, data: bytes):
        # During Login phase, custom payload / plugin message packet id varies by protocol.
        # For many modern protocol versions, Login plugin message id is 0x17 in login state.
        # We'll attempt to send with that id. If the server ignores, nothing harmful.
        ch = channel.encode('utf-8')
        payload = pack_varint(len(ch)) + ch + pack_varint(len(data)) + data
        try:
            self.send_packet(0x17, payload)
            print(f"[>] Sent Login-PluginMessage on channel '{channel}', {len(data)} bytes")
        except Exception as e:
            print(f"[!] Failed to send plugin message: {e}")

    def read_packet(self, timeout=5):
        # returns (packet_id, payload_bytes) or (None, None) on EOF
        try:
            length = read_varint_from_socket(self.sock, timeout=timeout)
            if length is None:
                return None, None
            data = b''
            to_read = length
            while to_read > 0:
                chunk = self.sock.recv(to_read)
                if not chunk:
                    return None, None
                data += chunk
                to_read -= len(chunk)
            # read packet id from data
            # parse varint from bytes
            packet_id, consumed = self._read_varint_from_bytes(data, 0)
            payload = data[consumed:]
            return packet_id, payload
        except socket.timeout:
            return None, None

    def _read_varint_from_bytes(self, data: bytes, offset: int = 0):
        result = 0
        shift = 0
        idx = offset
        while True:
            if idx >= len(data):
                return None, idx - offset
            byte = data[idx]
            result |= (byte & 0x7F) << shift
            shift += 7
            idx += 1
            if not (byte & 0x80):
                break
            if shift > 35:
                raise Exception('VarInt too big')
        if result > 0x7FFFFFFF:
            result -= 0x100000000
        return result, idx - offset

    def parse_plugin_message(self, payload: bytes):
        # Heuristic parser for Login plugin message: [channelLength VarInt][channelBytes][dataLength VarInt][dataBytes]
        try:
            idx = 0
            channel_len, csz = self._read_varint_from_bytes(payload, idx)
            idx += csz
            channel = payload[idx:idx+channel_len].decode('utf-8', errors='ignore')
            idx += channel_len
            data_len, dsz = self._read_varint_from_bytes(payload, idx)
            idx += dsz
            data = payload[idx:idx+data_len]
            return channel, data
        except Exception as e:
            # fallback: try to read as simple string
            try:
                s = payload.decode('utf-8', errors='ignore')
                return 'unknown', payload
            except:
                return 'unknown', payload

    def heuristic_extract_strings(self, data: bytes):
        # Extract printable ASCII-like substrings of length >=3; useful to find modids/versions embedded
        s = data.decode('latin-1', errors='ignore')
        candidates = re.findall(r'[A-Za-z0-9_\-\.]{3,}', s)
        # filter out long numeric sequences
        candidates = [c for c in candidates if not re.fullmatch(r'\d{4,}', c)]
        return candidates

    def attempt_forge_handshake(self, auto_respond=True):
        """
        Main loop after sending Login Start. It will:
          - read incoming packets
          - try to detect and parse plugin/custom payloads related to Forge/FML
          - optionally respond with a simple "mod list" plugin message to satisfy servers
        """
        print("[+] Waiting for server login packets (timeout per read: 5s)...")
        start = time.time()
        seen_mods = set()
        while True:
            packet_id, payload = self.read_packet(timeout=self.recv_timeout)
            if packet_id is None:
                # no packet within timeout
                if time.time() - start > 15:
                    print("[!] No further packets; giving up")
                    break
                continue

            print(f"[<] Got packet id: {packet_id}, len={len(payload)}")

            # Common login-phase packet IDs to consider
            # 0x00: Disconnect
            # 0x01: Encryption Request
            # 0x02: Login Success
            # 0x03: Set Compression
            # 0x17: Login Plugin Message (custom payload) -- packet id may differ by protocol, but observed previously in many servers

            if packet_id == 0x00:
                # Disconnect (reason)
                try:
                    # payload starts with length-prefixed json string
                    reason_len, off = self._read_varint_from_bytes(payload, 0)
                    reason = payload[off:off+reason_len].decode('utf-8', errors='ignore')
                except Exception:
                    reason = payload.decode('utf-8', errors='ignore') if payload else '<no reason>'
                print(f"[!] Disconnect during login: {reason}")
                break

            if packet_id == 0x01:
                print("[!] Server requested Encryption. Can't continue without performing Mojang auth / encryption. Aborting.")
                break

            if packet_id == 0x02:
                print("[+] Login Success - we are in! (server allowed login without encryption)")
                # After this, the connection shifts to Play state; you can start reading play packets
                break

            if packet_id == 0x03:
                # Set compression
                thresh, _ = self._read_varint_from_bytes(payload, 0)
                print(f"[i] Server set compression threshold: {thresh}")
                continue

            # Heuristic: plugin/custom payload during login
            # We'll try to parse it as [channel][data]
            channel, data = self.parse_plugin_message(payload)
            print(f"[i] Plugin message channel: {channel}, data_len={len(data)}")

            # Look for textual clues (modids / versions) inside data
            found = self.heuristic_extract_strings(data)
            if found:
                print(f"[i] Heuristic strings in payload: {found[:10]}")
                for token in found:
                    seen_mods.add(token)

            # If channel looks like Forge/FML, attempt auto-response
            c_low = channel.lower() if isinstance(channel, str) else ''
            if ('fml' in c_low or 'forge' in c_low or 'mod' in c_low) and auto_respond:
                # Build a simple ModList response. Servers usually accept a "mod list" with pairs of (modid, version).
                # Here we craft a minimal response: a VarInt count + repeated strings (modid + '\0' + version) or JSON-like bytes
                # Because different handshake formats exist, we try two strategies:
                # 1) send a small "no-mods" honest response
                # 2) if we parsed mod ids from server payload, echo them back with placeholder versions

                # Use predefined mods if available, otherwise use detected mods
                if self.predefined_mods:
                    mod_entries = [(mod.get('id', ''), mod.get('version', '1.0')) for mod in self.predefined_mods]
                elif seen_mods:
                    mod_entries = [(m, '1.0') for m in list(seen_mods)[:50]]
                else:
                    mod_entries = [('minecraft', '1.20.1'), ('forge', '40.2.0')]

                # Strategy A: forge:handshake / FML legacy expects a sequence. We'll build a naive byte blob: JSON-like mod list
                try:
                    payload_json = json.dumps([{'id': mid, 'version': ver} for mid, ver in mod_entries]).encode('utf-8')
                    # send on common handshake channels
                    for ch in ['fml:handshake', 'FML|HS', 'FORGE', 'fml:login']:
                        try:
                            self.send_plugin_message_login_phase(ch, payload_json)
                            time.sleep(0.05)
                        except Exception:
                            pass
                    print(f"[+] Sent heuristic modlist response with {len(mod_entries)} entries")
                except Exception as e:
                    print(f"[!] Failed to craft modlist response: {e}")

            # Keep reading until login success / disconnect
        return list(seen_mods)


def get_mods_from_server(host: str, port: int = 25565, username: str = "Bot", 
                        mods_hint: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    """
    连接目标服务器，尽量完成 Forge/FML 握手并返回检测/声明的 mod 列表。
    可直接被 server.py/server_info.py 调用。
    """
    client = ForgeLoginClient(host, port, username, predefined_mods=mods_hint)
    try:
        client.connect()
        client.send_handshake(next_state=2)
        client.send_login_start()
        mod_tokens = client.attempt_forge_handshake(auto_respond=True)
        # 转为 [{id, version}] 格式
        mods = []
        for token in mod_tokens:
            if ':' in token and token.count(':') == 1:
                mod_id, version = token.split(':', 1)
                mods.append({"id": mod_id, "version": version})
            else:
                mods.append({"id": token, "version": "1.0"})
        return mods
    finally:
        client.close()


def parse_mods_argument(mods_str: str) -> List[Dict[str, str]]:
    """Parse mods string from command line argument"""
    if not mods_str:
        return []
    
    mods = []
    for mod_entry in mods_str.split(','):
        if ':' in mod_entry:
            mod_id, version = mod_entry.split(':', 1)
            mods.append({"id": mod_id.strip(), "version": version.strip()})
        else:
            mods.append({"id": mod_entry.strip(), "version": "1.0"})
    
    return mods


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Minecraft Forge Login Client')
    parser.add_argument('host', help='Server hostname or IP')
    parser.add_argument('port', nargs='?', type=int, default=25565, help='Server port (default: 25565)')
    parser.add_argument('username', nargs='?', default='PlayerBot', help='Username (default: PlayerBot)')
    parser.add_argument('--mods', help='Predefined mods in format "mod1:version1,mod2:version2"')

    args = parser.parse_args()
    mods_hint = parse_mods_argument(args.mods) if args.mods else None

    mods = get_mods_from_server(args.host, args.port, args.username, mods_hint)
    print('\nDetected/heuristic mods list:\n', mods)