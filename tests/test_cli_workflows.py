import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from msm.cli import index_parser
from msm.cli import list_workflow
from msm.cli import monitor_workflow
from msm.cli import pagination_workflow
from msm.cli import query_workflow
from msm.cli import scan_workflow
from msm.cli import server_crud_workflow


class FakeColors:
    RED = "<r>"
    GREEN = "<g>"
    YELLOW = "<y>"
    CYAN = "<c>"
    RESET = "</>"


class FakeManager:
    def __init__(self):
        self.current_page = 0
        self.page_size = 10
        self.servers = [{} for _ in range(25)]
        self.filter_type = "all"
        self.saved_page_size = False
        self.saved_servers = False
        self.sorted = None
        self.players_shown = None
        self.info_shown = None
        self.added_server = None
        self.scan_ports_called = []
        self.scan_all_ports_called = []
        self.deleted_index = None

    def max_page(self):
        if not self.servers:
            return 0
        return (len(self.servers) - 1) // self.page_size

    def save_page_size(self):
        self.saved_page_size = True
        return True

    def save_servers(self):
        self.saved_servers = True
        return True

    def sort_servers(self, field, order):
        self.sorted = (field, order)

    def show_players(self, idx):
        self.players_shown = idx

    def show_server_info(self, idx):
        self.info_shown = idx

    def scan_ports(self, host):
        self.scan_ports_called.append(host)
        return [{"port": 25565, "type": "java"}]

    def scan_all_ports(self, host):
        self.scan_all_ports_called.append(host)
        return [{"port": 19132, "type": "bedrock"}]

    def display_scan_results(self, host, found):
        return found[0] if found else None

    def add_server(self, server):
        self.added_server = server

    def delete_server(self, idx):
        self.deleted_index = idx


class FakePing:
    cache = {"x": 1}
    srv_cache = {"y": 2}

    @staticmethod
    def clear_all_caches():
        FakePing.cache.clear()
        FakePing.srv_cache.clear()


class TestIndexParser(unittest.TestCase):
    def test_parse_single_valid_with_page_offset(self):
        m = FakeManager()
        m.current_page = 1
        result = index_parser.parse_single_server_index(["players", "2"], m, FakeColors)
        self.assertEqual(result, 11)

    def test_parse_single_invalid_token_returns_none(self):
        m = FakeManager()
        result = index_parser.parse_single_server_index(["players", "abc"], m, FakeColors)
        self.assertIsNone(result)

    def test_parse_multi_invalid_token_returns_empty(self):
        m = FakeManager()
        result = index_parser.parse_multi_server_indices(["monitor", "1", "x"], m, FakeColors)
        self.assertEqual(result, [])


class TestPaginationWorkflow(unittest.TestCase):
    def test_next_prev_page(self):
        m = FakeManager()
        pagination_workflow.go_next_page(m, FakeColors)
        self.assertEqual(m.current_page, 1)
        pagination_workflow.go_prev_page(m, FakeColors)
        self.assertEqual(m.current_page, 0)

    def test_go_to_page_updates_current_page(self):
        m = FakeManager()
        with patch("builtins.input", return_value="2"):
            pagination_workflow.go_to_page(m, FakeColors)
        self.assertEqual(m.current_page, 1)

    def test_change_page_size_persists(self):
        m = FakeManager()
        m.current_page = 3
        with patch("builtins.input", return_value="5"):
            pagination_workflow.change_page_size(m, FakeColors)
        self.assertTrue(m.saved_page_size)
        self.assertEqual(m.page_size, 5)
        self.assertEqual(m.current_page, 3)


class TestListWorkflow(unittest.TestCase):
    def test_refresh_current_page_clears_cache_dicts(self):
        FakePing.cache = {"x": 1}
        FakePing.srv_cache = {"y": 2}
        list_workflow.refresh_current_page(FakePing, FakeColors)
        self.assertEqual(FakePing.cache, {})
        self.assertEqual(FakePing.srv_cache, {})

    def test_save_servers_calls_manager(self):
        m = FakeManager()
        list_workflow.save_servers(m, FakeColors)
        self.assertTrue(m.saved_servers)


class TestQueryWorkflow(unittest.TestCase):
    def test_players_workflow_calls_show_players(self):
        m = FakeManager()
        with patch("msm.cli.query_workflow.parse_single_server_index", return_value=7):
            query_workflow.run_players_workflow(["players", "1"], m, FakeColors)
        self.assertEqual(m.players_shown, 7)

    def test_info_workflow_calls_show_server_info(self):
        m = FakeManager()
        with patch("msm.cli.query_workflow.parse_single_server_index", return_value=3):
            query_workflow.run_info_workflow(["info", "1"], m, FakeColors)
        self.assertEqual(m.info_shown, 3)


class TestScanWorkflow(unittest.TestCase):
    def test_scan_workflow_adds_server(self):
        m = FakeManager()
        with patch("builtins.input", side_effect=["example.com", "", "note"]):
            scan_workflow.run_scan_workflow(m, FakeColors, scan_all=False)
        self.assertEqual(m.scan_ports_called, ["example.com"])
        self.assertIsNotNone(m.added_server)
        self.assertEqual(m.added_server["name"], "example.com:25565")

    def test_scan_all_cancel_does_not_scan(self):
        m = FakeManager()
        with patch("builtins.input", side_effect=["example.com", "n"]):
            scan_workflow.run_scan_workflow(m, FakeColors, scan_all=True)
        self.assertEqual(m.scan_all_ports_called, [])


class TestMonitorWorkflow(unittest.TestCase):
    def test_monitor_all_uses_server_monitor_module(self):
        m = FakeManager()
        fake_module = types.SimpleNamespace(monitor_all_servers=MagicMock(return_value=True))
        with patch.dict(sys.modules, {"server_monitor": fake_module}, clear=False):
            monitor_workflow.run_monitor_workflow(["monitor", "all"], m, FakeColors)
        fake_module.monitor_all_servers.assert_called_once_with(m)

    def test_monitor_multi_uses_parsed_indices(self):
        m = FakeManager()
        fake_module = types.SimpleNamespace(monitor_multiple_servers=MagicMock(return_value=True))
        with patch("msm.cli.monitor_workflow.parse_multi_server_indices", return_value=[1, 2]):
            with patch.dict(sys.modules, {"server_monitor": fake_module}, clear=False):
                monitor_workflow.run_monitor_workflow(["monitor", "1", "2"], m, FakeColors)
        fake_module.monitor_multiple_servers.assert_called_once_with(m, [1, 2])


class TestServerCrudWorkflow(unittest.TestCase):
    def test_add_server_with_manual_port_and_type(self):
        m = FakeManager()
        with patch("builtins.input", side_effect=["S1", "127.0.0.1", "25570", "java", "n1"]):
            server_crud_workflow.add_server_interactive(m, FakeColors, FakePing, "java", "bedrock")
        self.assertIsNotNone(m.added_server)
        self.assertEqual(m.added_server["name"], "S1")
        self.assertEqual(m.added_server["port"], 25570)
        self.assertEqual(m.added_server["type"], "java")

    def test_delete_server_valid_index(self):
        m = FakeManager()
        with patch("builtins.input", return_value="2"):
            server_crud_workflow.delete_server_interactive(m, FakeColors)
        self.assertEqual(m.deleted_index, 1)


if __name__ == "__main__":
    unittest.main()
