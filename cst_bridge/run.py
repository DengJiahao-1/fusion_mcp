"""
CST Bridge 启动脚本。

用法:
    python -m cst_bridge.run
    python -m cst_bridge.run --port 9001
"""

import argparse
import sys
from pathlib import Path

# 确保项目根目录在 path 中
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from cst_bridge.server import run_server


def main():
    parser = argparse.ArgumentParser(description="CST Studio Suite Bridge HTTP Server")
    parser.add_argument("--port", type=int, default=9001, help="HTTP 端口")
    args = parser.parse_args()
    run_server(port=args.port)


if __name__ == "__main__":
    main()
