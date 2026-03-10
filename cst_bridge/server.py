"""
CST Bridge HTTP 服务器。

在本地运行 HTTP 服务，接收 MCP 服务器的请求，并调用 CST Studio Suite API。
"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

from . import cst_operations
from .logger import get_logger

logger = get_logger()


class CSTBridgeHandler(BaseHTTPRequestHandler):
    """处理 CST Bridge API 请求的 HTTP 处理器。"""

    def log_message(self, format, *args):
        message = format % args
        logger.info(f"HTTP: {message}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            if self.path == "/api/info":
                response = self._handle_info()
            else:
                response = {"error": f"未知端点: {self.path}"}
                self.send_response(404)
            self._send_json(response)
        except Exception as e:
            self._send_error(str(e))

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8")) if body else {}

            if self.path == "/api/import/step":
                response = self._handle_import_step(data)
            elif self.path == "/api/material/assign":
                response = self._handle_assign_material(data)
            elif self.path == "/api/solver/frequency":
                response = self._handle_set_frequency(data)
            elif self.path == "/api/solver/run":
                response = self._handle_run_simulation(data)
            elif self.path == "/api/results":
                response = self._handle_get_results(data)
            elif self.path == "/api/project/new":
                response = self._handle_new_project(data)
            else:
                response = {"error": f"未知端点: {self.path}"}
                self.send_response(404)

            self._send_json(response)
        except Exception as e:
            self._send_error(str(e))

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_error(self, msg: str, status: int = 500):
        self._send_json({"success": False, "error": msg, "traceback": traceback.format_exc()}, status)

    def _handle_info(self) -> Dict[str, Any]:
        return cst_operations.get_project_info()

    def _handle_import_step(self, data: Dict[str, Any]) -> Dict[str, Any]:
        file_path = data.get("file_path")
        if not file_path or not str(file_path).strip():
            return {"success": False, "error": "缺少 file_path 参数"}
        return cst_operations.import_step(
            file_path=str(file_path).strip(),
            component_name=str(data.get("component_name", "ImportedComponent")).strip() or "ImportedComponent",
        )

    def _handle_assign_material(self, data: Dict[str, Any]) -> Dict[str, Any]:
        component_name = data.get("component_name")
        if not component_name:
            return {"success": False, "error": "缺少 component_name 参数"}
        return cst_operations.assign_material(
            component_name=str(component_name).strip(),
            material_name=str(data.get("material_name", "Copper")).strip() or "Copper",
            solid_name=data.get("solid_name"),
        )

    def _handle_set_frequency(self, data: Dict[str, Any]) -> Dict[str, Any]:
        f_min = data.get("f_min_hz")
        f_max = data.get("f_max_hz")
        if f_min is None or f_max is None:
            return {"success": False, "error": "缺少 f_min_hz 或 f_max_hz 参数"}
        return cst_operations.set_frequency_range(float(f_min), float(f_max))

    def _handle_run_simulation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return cst_operations.run_simulation()

    def _handle_get_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return cst_operations.get_simulation_results()

    def _handle_new_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return cst_operations.new_project()


class CSTBridgeServer(threading.Thread):
    """在后台线程中运行 CST Bridge HTTP 服务器。"""

    def __init__(self, port: int = 9001, daemon: bool = True):
        super().__init__(daemon=daemon)
        self.port = port
        self.server = None
        self.running = False

    def run(self):
        try:
            self.server = HTTPServer(("localhost", self.port), CSTBridgeHandler)
            self.running = True
            logger.info(f"CST Bridge 服务已启动: http://localhost:{self.port}")
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"CST Bridge 启动失败: {e}")
            self.running = False

    def stop(self):
        self.running = False
        if self.server:
            self.server.shutdown()


def run_server(port: int = 9001):
    """启动 CST Bridge HTTP 服务器（前台运行）。"""
    server = HTTPServer(("localhost", port), CSTBridgeHandler)
    logger.info(f"CST Bridge 运行于 http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
