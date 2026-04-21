from msm.cli.crud_command_dispatcher import dispatch_crud_command
from msm.cli.exact_command_dispatcher import dispatch_exact_command
from msm.cli.prefix_command_dispatcher import dispatch_prefix_command


def handle_command(
    cmd,
    manager,
    Colors,
    MinecraftPing,
    print_help,
    SERVER_TYPE_JAVA,
    SERVER_TYPE_BEDROCK,
):
    """Handle one normalized command.

    Returns:
        True if caller should exit main loop, else False.
    """
    exact_result = dispatch_exact_command(cmd, manager, Colors, MinecraftPing, print_help)
    if exact_result == "exit":
        return True
    if exact_result:
        return False

    if dispatch_crud_command(
        cmd,
        manager,
        Colors,
        MinecraftPing,
        SERVER_TYPE_JAVA,
        SERVER_TYPE_BEDROCK,
    ):
        return False

    if dispatch_prefix_command(cmd, manager, Colors):
        return False

    print(f"{Colors.RED}Unknown command (type 'h' for help){Colors.RESET}")
    return False
