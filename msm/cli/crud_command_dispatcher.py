from msm.cli.server_crud_workflow import add_server_interactive, delete_server_interactive, update_server_interactive


def dispatch_crud_command(cmd, manager, Colors, MinecraftPing):
    """Dispatch CRUD commands.

    Returns True if handled, otherwise False.
    """
    if cmd == "a":
        add_server_interactive(manager, Colors, MinecraftPing)
        return True
    if cmd == "d":
        delete_server_interactive(manager, Colors)
        return True
    if cmd == "u":
        update_server_interactive(manager, Colors)
        return True
    return False
