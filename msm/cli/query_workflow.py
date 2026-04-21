from msm.cli.index_parser import parse_single_server_index


def run_players_workflow(parts, manager, Colors):
    """Run players command workflow."""
    actual_index = parse_single_server_index(parts, manager, Colors)
    if actual_index is not None:
        manager.show_players(actual_index)


def run_info_workflow(parts, manager, Colors):
    """Run info command workflow."""
    actual_index = parse_single_server_index(parts, manager, Colors)
    if actual_index is not None:
        manager.show_server_info(actual_index)
