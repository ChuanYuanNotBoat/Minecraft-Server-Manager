def add_server_interactive(manager, Colors, MinecraftPing, SERVER_TYPE_JAVA, SERVER_TYPE_BEDROCK):
    """Interactive add-server workflow."""
    try:
        name = input("Server name: ").strip()
        if not name:
            print(f"{Colors.RED}Name cannot be empty{Colors.RESET}")
            return

        ip = input("IP address: ").strip()
        if not ip:
            print(f"{Colors.RED}IP address cannot be empty{Colors.RESET}")
            return

        server_type = SERVER_TYPE_JAVA
        print(f"{Colors.CYAN}Trying to detect server type automatically...{Colors.RESET}")
        port_str = input("Port (empty for auto-detect): ").strip()
        port = 25565

        if port_str:
            try:
                port = int(port_str)
            except ValueError:
                print(f"{Colors.YELLOW}Port must be a number, using default 25565{Colors.RESET}")
                port = 25565

            server_type_input = input("Server type (java/bedrock, default java): ").strip().lower()
            if server_type_input in ["java", "bedrock"]:
                server_type = server_type_input
            else:
                server_type = SERVER_TYPE_JAVA
        else:
            detected_type = MinecraftPing.detect_server_type(ip, port)
            if detected_type == "java":
                print(f"{Colors.GREEN}Detected Java server{Colors.RESET}")
                server_type = "java"
            elif detected_type == "bedrock":
                print(f"{Colors.MAGENTA}Detected Bedrock server{Colors.RESET}")
                server_type = "bedrock"
                port = 19132
            else:
                print(f"{Colors.YELLOW}Could not auto-detect server type, choose manually{Colors.RESET}")
                server_type_input = input("Server type (java/bedrock, default java): ").strip().lower()
                if server_type_input in ["java", "bedrock"]:
                    server_type = server_type_input
                else:
                    server_type = SERVER_TYPE_JAVA

        if not port_str and server_type == SERVER_TYPE_BEDROCK:
            port = 19132

        note = input("Note (optional): ").strip()

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
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")
    except EOFError:
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")


def delete_server_interactive(manager, Colors):
    """Interactive delete-server workflow."""
    try:
        index = int(input("Index to delete: ").strip()) - 1
        actual_index = manager.current_page * manager.page_size + index
        if 0 <= actual_index < len(manager.servers):
            manager.delete_server(actual_index)
        else:
            print(f"{Colors.RED}Invalid index{Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}Please enter a valid number{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")


def update_server_interactive(manager, Colors):
    """Interactive update-server workflow."""
    try:
        index = int(input("Index to update: ").strip()) - 1
        actual_index = manager.current_page * manager.page_size + index
        if 0 <= actual_index < len(manager.servers):
            server = manager.servers[actual_index]
            print(f"Current name: {Colors.CYAN}{server.get('name', '')}{Colors.RESET}")
            print(f"Current address: {Colors.CYAN}{server.get('ip', '')}:{server.get('port', 25565)}{Colors.RESET}")
            print(f"Current type: {Colors.CYAN}{server.get('type', 'java')}{Colors.RESET}")
            print(f"Current note: {Colors.CYAN}{server.get('note', '')}{Colors.RESET}")

            field = input("Field (name/ip/port/type/note): ").strip().lower()
            if field not in ["name", "ip", "port", "type", "note"]:
                print(f"{Colors.RED}Invalid field{Colors.RESET}")
                return

            value = input("New value: ").strip()
            if field == "type" and value not in ["java", "bedrock"]:
                print(f"{Colors.RED}Type must be 'java' or 'bedrock'{Colors.RESET}")
                return

            manager.update_server(actual_index, field, value)
        else:
            print(f"{Colors.RED}Invalid index{Colors.RESET}")
    except (ValueError, KeyError):
        print(f"{Colors.RED}Invalid input{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")
