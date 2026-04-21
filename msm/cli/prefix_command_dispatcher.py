from msm.cli.monitor_workflow import run_monitor_workflow
from msm.cli.query_workflow import run_info_workflow, run_players_workflow


def dispatch_prefix_command(cmd, manager, Colors):
    """Dispatch prefix-based commands.

    Returns True if handled, otherwise False.
    """
    if cmd.startswith("players "):
        run_players_workflow(cmd.split(), manager, Colors)
        return True
    if cmd.startswith("info "):
        run_info_workflow(cmd.split(), manager, Colors)
        return True
    if cmd.startswith("monitor "):
        run_monitor_workflow(cmd.split(), manager, Colors)
        return True
    return False
