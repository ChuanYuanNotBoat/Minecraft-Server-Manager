COMMAND_ALIASES = {
    'n': 'n', 'next': 'n',
    'p': 'p', 'prev': 'p', 'previous': 'p',
    'g': 'g', 'goto': 'g', 'page': 'g',
    'a': 'a', 'add': 'a',
    'd': 'd', 'delete': 'd', 'del': 'd', 'remove': 'd',
    'u': 'u', 'update': 'u', 'edit': 'u',
    's': 's', 'save': 's',
    'r': 'r', 'refresh': 'r', 'reload': 'r',
    'clear': 'clear', 'clearcache': 'clear',
    'o': 'o', 'sort': 'o', 'order': 'o',
    'c': 'c', 'pagesize': 'c', 'size': 'c',
    'f': 'f', 'filter': 'f',
    'players': 'players', 'player': 'players',
    'info': 'info', 'detail': 'info',
    'monitor': 'monitor', 'mon': 'monitor',
    'scan': 'scan', 'scancommon': 'scan',
    'scanall': 'scanall', 'scanfull': 'scanall',
    'h': 'h', 'help': 'h',
    'q': 'q', 'quit': 'q', 'exit': 'q',
}


def normalize_command(raw_command: str) -> str:
    cmd = (raw_command or '').strip().lower()
    if not cmd:
        return ''

    parts = cmd.split()
    parts[0] = COMMAND_ALIASES.get(parts[0], parts[0])
    return ' '.join(parts)
