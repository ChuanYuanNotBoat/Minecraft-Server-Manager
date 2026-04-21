import os

IS_WINDOWS = os.name == 'nt'
if IS_WINDOWS:
    # Enable ANSI escape sequence support on modern Windows terminals.
    os.system('')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FILE = os.path.join(PROJECT_ROOT, 'servers.json')
CONFIG_FILE = os.path.join(PROJECT_ROOT, 'config.json')
LOGS_DIR = os.path.join(PROJECT_ROOT, 'logs')

SERVER_TYPE_JAVA = 'java'
SERVER_TYPE_BEDROCK = 'bedrock'
SERVER_TYPE_UNKNOWN = 'unknown'


class Colors:
    BLACK = '\033[30m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    ITALIC = '\033[3m'
    STRIKETHROUGH = '\033[9m'

    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
