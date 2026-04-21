
def run_scan_workflow(manager, Colors, scan_all=False):
    """Run scan or full-scan workflow and optionally add selected server."""
    try:
        host = input("输入要扫描的IP地址或域名: ").strip()
        if not host:
            print(f"{Colors.RED}IP地址不能为空!{Colors.RESET}")
            return

        if scan_all:
            print(f"{Colors.YELLOW}警告: 扫描所有端口(1-65535) 可能需要很长时间{Colors.RESET}")
            confirm = input("是否继续? (y/N): ").strip().lower()
            if confirm != 'y':
                print(f"{Colors.YELLOW}操作取消{Colors.RESET}")
                return
            found_servers = manager.scan_all_ports(host)
        else:
            found_servers = manager.scan_ports(host)

        selected_server = manager.display_scan_results(host, found_servers)
        if not selected_server:
            return

        name = input("服务器名称: ").strip()
        if not name:
            name = f"{host}:{selected_server['port']}"

        note = input("备注 (可选): ").strip()

        manager.add_server({
            'name': name,
            'ip': host,
            'port': selected_server['port'],
            'type': selected_server['type'],
            'note': note if note else "",
        })
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
    except EOFError:
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
