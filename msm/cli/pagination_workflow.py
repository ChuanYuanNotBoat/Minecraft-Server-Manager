def go_next_page(manager, Colors):
    """Go to next page if available."""
    if manager.current_page < manager.max_page():
        manager.current_page += 1
    else:
        print(f"{Colors.YELLOW}已经是最后一页{Colors.RESET}")


def go_prev_page(manager, Colors):
    """Go to previous page if available."""
    if manager.current_page > 0:
        manager.current_page -= 1
    else:
        print(f"{Colors.YELLOW}已经是第一页{Colors.RESET}")


def go_to_page(manager, Colors):
    """Prompt and jump to a target page."""
    try:
        page = int(input("输入页码: ").strip()) - 1
        if 0 <= page <= manager.max_page():
            manager.current_page = page
        else:
            print(f"{Colors.RED}页码超出范围 (1-{manager.max_page() + 1}){Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}请输入有效数字!{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")


def change_page_size(manager, Colors):
    """Prompt and update page size."""
    try:
        new_size = int(input(f"每页显示数量 (1-50, 当前: {manager.page_size}): ").strip())
        if 1 <= new_size <= 50:
            old_page = manager.current_page
            manager.page_size = new_size
            manager.save_page_size()

            max_page = manager.max_page()
            if old_page > max_page:
                manager.current_page = max_page

            print(f"{Colors.GREEN}每页显示数量已改为 {new_size}{Colors.RESET}")
        else:
            print(f"{Colors.RED}数量必须在1-50之间{Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}请输入有效数字!{Colors.RESET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{Colors.YELLOW}操作取消{Colors.RESET}")
