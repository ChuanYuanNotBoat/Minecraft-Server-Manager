def run_scan_workflow(manager, Colors, scan_all=False):
    """Run scan or full-scan workflow and optionally add selected server."""
    try:
        host = input("Host/IP to scan: ").strip()
        if not host:
            print(f"{Colors.RED}Host/IP cannot be empty{Colors.RESET}")
            return

        if scan_all:
            print(f"{Colors.YELLOW}Warning: scanning all ports (1-65535) may take a long time{Colors.RESET}")
            confirm = input("Continue? (y/N): ").strip().lower()
            if confirm != "y":
                print(f"{Colors.YELLOW}Operation canceled{Colors.RESET}")
                return
            found_servers = manager.scan_all_ports(host)
        else:
            found_servers = manager.scan_ports(host)

        selected_server = manager.display_scan_results(host, found_servers)
        if not selected_server:
            return

        name = input("Server name: ").strip()
        if not name:
            name = f"{host}:{selected_server['port']}"

        note = input("Note (optional): ").strip()

        manager.add_server(
            {
                "name": name,
                "ip": host,
                "port": selected_server["port"],
                "type": selected_server["type"],
                "note": note if note else "",
            }
        )
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")
    except EOFError:
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")
