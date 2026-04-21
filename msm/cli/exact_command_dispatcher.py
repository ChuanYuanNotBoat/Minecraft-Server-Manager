from msm.cli.list_workflow import clear_all_cache, filter_servers, refresh_current_page, save_servers, sort_servers
from msm.cli.pagination_workflow import change_page_size, go_next_page, go_prev_page, go_to_page
from msm.cli.scan_workflow import run_scan_workflow


def dispatch_exact_command(cmd, manager, Colors, MinecraftPing, print_help):
    """Dispatch exact-match commands.

    Returns:
        'exit' for quit command, True if handled, False if not handled.
    """
    if cmd == "n":
        go_next_page(manager, Colors)
        return True
    if cmd == "p":
        go_prev_page(manager, Colors)
        return True
    if cmd == "g":
        go_to_page(manager, Colors)
        return True
    if cmd == "s":
        save_servers(manager, Colors)
        return True
    if cmd == "r":
        refresh_current_page(MinecraftPing, Colors)
        return True
    if cmd == "clear":
        clear_all_cache(MinecraftPing, Colors)
        return True
    if cmd == "o":
        sort_servers(manager, Colors)
        return True
    if cmd == "c":
        change_page_size(manager, Colors)
        return True
    if cmd == "f":
        filter_servers(manager, Colors)
        return True
    if cmd == "scan":
        run_scan_workflow(manager, Colors, scan_all=False)
        return True
    if cmd == "scanall":
        run_scan_workflow(manager, Colors, scan_all=True)
        return True
    if cmd in ("h", "help"):
        print_help(manager)
        return True
    if cmd == "q":
        print(f"{Colors.GREEN}Bye!{Colors.RESET}")
        return "exit"
    return False
