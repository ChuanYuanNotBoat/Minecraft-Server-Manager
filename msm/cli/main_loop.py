from msm.cli.session_workflow import read_normalized_command, render_current_page


def run_main_loop(manager, Colors, MinecraftPing, print_help, handle_command):
    """Run interactive CLI main loop until exit."""
    while True:
        render_current_page(manager)
        cmd = read_normalized_command(manager, Colors)
        if not cmd:
            continue

        should_exit = handle_command(
            cmd,
            manager,
            Colors,
            MinecraftPing,
            print_help,
        )
        if should_exit:
            break
