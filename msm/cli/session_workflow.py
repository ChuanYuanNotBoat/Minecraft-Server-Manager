from msm.command_aliases import normalize_command


def print_startup_banner(manager, Colors):
    """Print startup banner and initial summary."""
    print(f"{Colors.BOLD}Minecraft Server Manager{Colors.RESET}")
    print(f"{Colors.CYAN}Loaded {len(manager.servers)} servers, page size {manager.page_size}{Colors.RESET}")


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
            f"\n{Colors.BOLD}Command (h=help, page {manager.current_page + 1}/{manager.max_page() + 1}):{Colors.RESET} "
        ).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}Back to main menu...{Colors.RESET}")
        return ""

    return normalize_command(cmd)
