def add_server_interactive(manager, Colors, MinecraftPing, SERVER_TYPE_JAVA, SERVER_TYPE_BEDROCK):
    """Interactive add-server workflow."""
    try:
        name = input("服务器名称: ").strip()
        if not name:
            print(f"{Colors.RED}名称不能为空!{Colors.RESET}")
            return

        ip = input("IP地址: ").strip()
        if not ip:
            print(f"{Colors.RED}IP地址不能为空!{Colors.RESET}")
            return

        server_type = SERVER_TYPE_JAVA
        print(f"{Colors.CYAN}正在尝试自动检测服务器类型...{Colors.RESET}")
        port_str = input("端口 (留空自动检测): ").strip()
        port = 25565

        if port_str:
            try:
                port = int(port_str)
            except ValueError:
                print(f"{Colors.YELLOW}端口必须是数字，使用默认值25565{Colors.RESET}")
                port = 25565

            server_type_input = input("服务器类型 (java/bedrock, 默认java): ").strip().lower()
            if server_type_input in ["java", "bedrock"]:
                server_type = server_type_input
            else:
                server_type = SERVER_TYPE_JAVA
        else:
            detected_type = MinecraftPing.detect_server_type(ip, port)
            if detected_type == "java":
                print(f"{Colors.GREEN}检测到Java版服务器{Colors.RESET}")
                server_type = "java"
            elif detected_type == "bedrock":
                print(f"{Colors.MAGENTA}检测到基岩版服务器{Colors.RESET}")
                server_type = "bedrock"
                port = 19132
            else:
                print(f"{Colors.YELLOW}无法自动检测服务器类型，请手动选择{Colors.RESET}")
                server_type_input = input("服务器类型 (java/bedrock, 默认java): ").strip().lower()
                if server_type_input in ["java", "bedrock"]:
                    server_type = server_type_input
                else:
                    server_type = SERVER_TYPE_JAVA

        if not port_str and server_type == SERVER_TYPE_BEDROCK:
            port = 19132

        note = input("备注 (可选): ").strip()

        manager.add_server(
            {
                "name": name,
                "ip": ip,
                "port": port,
                "type": server_type,
                "note": note if note else "",
            }
        )
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
    except EOFError:
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")


def delete_server_interactive(manager, Colors):
    """Interactive delete-server workflow."""
    try:
        index = int(input("输入要删除的序号: ").strip()) - 1
        actual_index = manager.current_page * manager.page_size + index
        if 0 <= actual_index < len(manager.servers):
            manager.delete_server(actual_index)
        else:
            print(f"{Colors.RED}无效的序号{Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}请输入有效数字!{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")


def update_server_interactive(manager, Colors):
    """Interactive update-server workflow."""
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
            if field not in ["name", "ip", "port", "type", "note"]:
                print(f"{Colors.RED}无效字段!{Colors.RESET}")
                return

            value = input("新值: ").strip()
            if field == "type" and value not in ["java", "bedrock"]:
                print(f"{Colors.RED}服务器类型必须是 'java' 或 'bedrock'{Colors.RESET}")
                return

            manager.update_server(actual_index, field, value)
        else:
            print(f"{Colors.RED}无效的序号{Colors.RESET}")
    except (ValueError, KeyError):
        print(f"{Colors.RED}输入无效!{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
