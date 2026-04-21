import socket
import subprocess
import platform

from msm.constants import Colors


class DNSUtils:
    """DNS 解析工具，包含 Minecraft SRV 记录解析能力。"""

    @staticmethod
    def resolve_srv_record(hostname):
        """解析 Minecraft SRV 记录。"""
        try:
            try:
                import dns.resolver

                srv_hostname = f"_minecraft._tcp.{hostname}"
                try:
                    answers = dns.resolver.resolve(srv_hostname, 'SRV')
                    if answers:
                        srv_record = answers[0]
                        target_host = str(srv_record.target).rstrip('.')
                        port = srv_record.port
                        print(f"{Colors.CYAN}[DNS] 发现SRV记录: {target_host}:{port}{Colors.RESET}")
                        return target_host, port
                except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                    pass
            except ImportError:
                pass

            srv_hostname = f"_minecraft._tcp.{hostname}"

            if platform.system() == 'Windows':
                try:
                    result = subprocess.run(
                        ['nslookup', '-type=SRV', srv_hostname],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        lines = result.stdout.split('\n')
                        for line in lines:
                            if 'svr hostname' in line.lower() or '=' in line:
                                parts = line.split('=')
                                if len(parts) >= 2:
                                    target_info = parts[1].strip().split()
                                    if len(target_info) >= 4:
                                        port = int(target_info[2])
                                        target_host = target_info[3].rstrip('.')
                                        print(f"{Colors.CYAN}[DNS] 发现SRV记录: {target_host}:{port}{Colors.RESET}")
                                        return target_host, port
                except Exception:
                    pass
            else:
                try:
                    result = subprocess.run(
                        ['dig', '+short', 'SRV', srv_hostname],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        lines = result.stdout.strip().split('\n')
                        for line in lines:
                            parts = line.split()
                            if len(parts) >= 4:
                                port = int(parts[2])
                                target_host = parts[3].rstrip('.')
                                print(f"{Colors.CYAN}[DNS] 发现SRV记录: {target_host}:{port}{Colors.RESET}")
                                return target_host, port
                except Exception:
                    pass

        except Exception as e:
            print(f"{Colors.YELLOW}[DNS] SRV记录解析失败: {str(e)}{Colors.RESET}")

        return None

    @staticmethod
    def resolve_with_fallback(original_host, original_port=25565, timeout=3):
        """智能解析主机名，优先 SRV。"""
        try:
            srv_result = DNSUtils.resolve_srv_record(original_host)
            if srv_result:
                resolved_host, resolved_port = srv_result
                return resolved_host, resolved_port, True

            socket.getaddrinfo(original_host, original_port)
            return original_host, original_port, False

        except socket.gaierror as e:
            raise Exception(f"DNS解析失败: {original_host}: {str(e)}")
        except Exception as e:
            raise Exception(f"解析失败: {original_host}:{original_port}: {str(e)}")
