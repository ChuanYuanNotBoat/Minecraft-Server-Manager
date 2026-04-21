from msm.cli.index_parser import parse_multi_server_indices


def run_monitor_workflow(parts, manager, Colors):
    """Run monitor command workflow for one or many server indices."""
    try:
        if len(parts) < 2:
            print(f"{Colors.RED}Please specify server index{Colors.RESET}")
            return

        if parts[1].lower() == "all":
            from server_monitor import monitor_all_servers

            if monitor_all_servers(manager):
                print(f"{Colors.GREEN}Started monitoring all servers{Colors.RESET}")
            return

        indices = parse_multi_server_indices(parts, manager, Colors)
        if not indices:
            print(f"{Colors.RED}No valid server index provided{Colors.RESET}")
            return

        from server_monitor import monitor_multiple_servers

        if monitor_multiple_servers(manager, indices):
            print(f"{Colors.GREEN}Started monitoring {len(indices)} server(s){Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Failed to start monitor: {str(e)}{Colors.RESET}")
