def go_next_page(manager, Colors):
    """Go to next page if available."""
    if manager.current_page < manager.max_page():
        manager.current_page += 1
    else:
        print(f"{Colors.YELLOW}Already at last page{Colors.RESET}")


def go_prev_page(manager, Colors):
    """Go to previous page if available."""
    if manager.current_page > 0:
        manager.current_page -= 1
    else:
        print(f"{Colors.YELLOW}Already at first page{Colors.RESET}")


def go_to_page(manager, Colors):
    """Prompt and jump to a target page."""
    try:
        page = int(input("Page number: ").strip()) - 1
        if 0 <= page <= manager.max_page():
            manager.current_page = page
        else:
            print(f"{Colors.RED}Page out of range (1-{manager.max_page() + 1}){Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}Please enter a valid number{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")


def change_page_size(manager, Colors):
    """Prompt and update page size."""
    try:
        new_size = int(input(f"Page size (1-50, current: {manager.page_size}): ").strip())
        if 1 <= new_size <= 50:
            old_page = manager.current_page
            manager.page_size = new_size
            manager.save_page_size()

            max_page = manager.max_page()
            if old_page > max_page:
                manager.current_page = max_page

            print(f"{Colors.GREEN}Page size changed to {new_size}{Colors.RESET}")
        else:
            print(f"{Colors.RED}Value must be between 1 and 50{Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}Please enter a valid number{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}Operation canceled{Colors.RESET}")
