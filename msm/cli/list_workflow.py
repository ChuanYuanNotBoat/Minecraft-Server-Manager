def save_servers(manager, Colors):
    """Save current server list."""
    if manager.save_servers():
        print(f"{Colors.GREEN}保存成功!{Colors.RESET}")


def refresh_current_page(MinecraftPing, Colors):
    """Clear in-memory caches and refresh view state."""
    print(f"{Colors.GREEN}刷新当前页...{Colors.RESET}")
    MinecraftPing.cache.clear()
    MinecraftPing.srv_cache.clear()


def clear_all_cache(MinecraftPing, Colors):
    """Clear all query caches explicitly."""
    print(f"{Colors.GREEN}清除所有缓存...{Colors.RESET}")
    MinecraftPing.clear_all_caches()


def sort_servers(manager, Colors):
    """Prompt and sort servers."""
    try:
        print(f"{Colors.CYAN}可用排序字段: name, ip, port, type{Colors.RESET}")
        field = input("排序字段: ").strip().lower()
        if field in ["name", "ip", "port", "type"]:
            order = input("排序顺序 (asc/desc): ").strip().lower() or "asc"
            if order not in ["asc", "desc"]:
                order = "asc"
            manager.sort_servers(field, order)
            manager.current_page = 0
        else:
            print(f"{Colors.RED}无效的排序字段{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")


def filter_servers(manager, Colors):
    """Prompt and filter server type."""
    try:
        print(f"{Colors.CYAN}可用筛选选项:{Colors.RESET}")
        print(f"  {Colors.GREEN}all{Colors.RESET}: 显示所有服务器")
        print(f"  {Colors.GREEN}java{Colors.RESET}: 仅显示Java版服务器")
        print(f"  {Colors.GREEN}bedrock{Colors.RESET}: 仅显示基岩版服务器")

        filter_type = input("选择筛选类型: ").strip().lower()
        if filter_type in ["all", "java", "bedrock"]:
            manager.filter_type = filter_type
            manager.current_page = 0
            print(f"{Colors.GREEN}已筛选: {filter_type}{Colors.RESET}")
        else:
            print(f"{Colors.RED}无效的筛选类型{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
