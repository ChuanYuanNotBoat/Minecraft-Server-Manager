import signal

from msm.cli.main_loop import run_main_loop
from msm.cli.session_workflow import print_startup_banner


def install_sigint_handler(on_sigint_cancel, Colors):
    """Install Ctrl+C handler for interactive mode."""

    def _sigint_handler(signum, frame):
        on_sigint_cancel()
        print(f"\n{Colors.YELLOW}Canceling query...{Colors.RESET}")

    signal.signal(signal.SIGINT, _sigint_handler)


def run_cli_app(manager, Colors, MinecraftPing, print_help, handle_command, on_sigint_cancel):
    """Run full interactive CLI app lifecycle."""
    install_sigint_handler(on_sigint_cancel, Colors)
    print_startup_banner(manager, Colors)
    run_main_loop(manager, Colors, MinecraftPing, print_help, handle_command)
