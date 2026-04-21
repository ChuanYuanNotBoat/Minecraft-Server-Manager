from msm.command_aliases import normalize_command


def print_startup_banner(manager, Colors):
    """Print startup banner and initial summary."""
    print(f"{Colors.BOLD}Minecraft 服务器管理器{Colors.RESET}")
    print(f"{Colors.CYAN}已加载 {len(manager.servers)} 个服务器，每页显示 {manager.page_size} 个{Colors.RESET}")


def render_current_page(manager):
    """Render current page server list."""
    current_servers = manager.get_page()
    manager.display_servers(current_servers)


def read_normalized_command(manager, Colors):
    """Read one command from input and normalize aliases.

    Returns empty string when input is canceled or blank.
    """
    try:
        cmd = input(
            f"\n{Colors.BOLD}命令 (h=帮助, 当前第{manager.current_page + 1}/{manager.max_page() + 1}页):{Colors.RESET} "
        ).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}返回主菜单...{Colors.RESET}")
        return ""

    return normalize_command(cmd)
