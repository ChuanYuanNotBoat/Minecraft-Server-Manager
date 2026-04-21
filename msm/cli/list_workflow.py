def save_servers(manager, Colors):
    """Save current server list."""
    if manager.save_servers():
        print(f"{Colors.GREEN}Saved successfully!{Colors.RESET}")


def refresh_current_page(MinecraftPing, Colors):
    """Clear in-memory caches and refresh view state."""
    print(f"{Colors.GREEN}Refreshing current page...{Colors.RESET}")
    MinecraftPing.cache.clear()
    MinecraftPing.srv_cache.clear()


def clear_all_cache(MinecraftPing, Colors):
    """Clear all query caches explicitly."""
    print(f"{Colors.GREEN}Clearing all caches...{Colors.RESET}")
    MinecraftPing.clear_all_caches()


def sort_servers(manager, Colors):
    """Prompt and sort servers."""
    try:
        print(f"{Colors.CYAN}Sortable fields: name, ip, port, type{Colors.RESET}")
        field = input("Sort field: ").strip().lower()
        if field in ["name", "ip", "port", "type"]:
            order = input("Sort order (asc/desc): ").strip().lower() or "asc"
            if order not in ["asc", "desc"]:
                order = "asc"
            manager.sort_servers(field, order)
            manager.current_page = 0
        else:
            print(f"{Colors.RED}Invalid sort field{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")


def filter_servers(manager, Colors):
    """Prompt and filter server type."""
    try:
        print(f"{Colors.CYAN}Filter options:{Colors.RESET}")
        print(f"  {Colors.GREEN}all{Colors.RESET}: show all servers")
        print(f"  {Colors.GREEN}java{Colors.RESET}: show Java servers only")
        print(f"  {Colors.GREEN}bedrock{Colors.RESET}: show Bedrock servers only")

        filter_type = input("Filter type: ").strip().lower()
        if filter_type in ["all", "java", "bedrock"]:
            manager.filter_type = filter_type
            manager.current_page = 0
            print(f"{Colors.GREEN}Filter applied: {filter_type}{Colors.RESET}")
        else:
            print(f"{Colors.RED}Invalid filter type{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")
