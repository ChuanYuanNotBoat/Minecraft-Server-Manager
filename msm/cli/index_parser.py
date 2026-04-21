from typing import List, Optional


def _to_actual_index(page: int, page_size: int, token: str) -> Optional[int]:
    try:
        index = int(token) - 1
        return page * page_size + index
    except ValueError:
        return None


def parse_single_server_index(parts: List[str], manager, Colors) -> Optional[int]:
    """Parse a single 1-based server index from command parts into actual list index."""
    if len(parts) < 2:
        print(f"{Colors.RED}Please specify server index{Colors.RESET}")
        return None

    actual_index = _to_actual_index(manager.current_page, manager.page_size, parts[1])
    if actual_index is None:
        print(f"{Colors.RED}Please enter a valid server index{Colors.RESET}")
        return None

    if not (0 <= actual_index < len(manager.servers)):
        print(f"{Colors.RED}Invalid server index{Colors.RESET}")
        return None

    return actual_index


def parse_multi_server_indices(parts: List[str], manager, Colors) -> List[int]:
    """Parse multiple 1-based server indices from command parts into actual list indices."""
    if len(parts) < 2:
        print(f"{Colors.RED}Please specify server index{Colors.RESET}")
        return []

    indices: List[int] = []
    for token in parts[1:]:
        actual_index = _to_actual_index(manager.current_page, manager.page_size, token)
        if actual_index is None:
            print(f"{Colors.RED}Invalid server index: {token}{Colors.RESET}")
            return []

        if not (0 <= actual_index < len(manager.servers)):
            print(f"{Colors.RED}Invalid server index: {token}{Colors.RESET}")
            return []

        indices.append(actual_index)

    return indices
