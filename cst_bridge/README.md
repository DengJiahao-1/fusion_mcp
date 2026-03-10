# CST Studio Suite Bridge

CST Bridge 提供 HTTP API，供 MCP 服务器通过 LLM 控制 CST Studio Suite 进行电磁仿真。

## 架构

```
Fusion 360 (CAD)  →  export_to_step  →  xxx.step
                                        ↓
MCP Client (LLM)  ←  cst_import_step  ←  CST Bridge (HTTP :9001)  ←  CST Studio Suite
                     cst_run_simulation
                     cst_get_simulation_results
```

## 前置条件

1. **CST Studio Suite** 已安装（2020 及以上版本）
2. CST 自带 Python 库，路径类似：
   `C:\Program Files (x86)\CST Studio Suite 20xx\AMD64\python_cst_libraries`
3. 运行 Bridge 的 Python 需能导入 `cst.interface`

## 启动 CST Bridge

```bash
# 在项目根目录
python -m cst_bridge.run

# 指定端口
python -m cst_backend.run --port 9001
```

若未安装 CST，Bridge 仍可启动，但 API 调用会返回「CST 不可用」错误。

## 环境变量

| 变量 | 默认值 | 说明 |
|-----|--------|-----|
| CST_SERVER_URL | http://localhost:9001 | CST Bridge 地址 |
| CST_TIMEOUT | 60 | 请求超时（秒），仿真较长 |
| CST_ENABLED | true | MCP 是否启用 CST 工具 |

## API 端点

| 端点 | 方法 | 说明 |
|-----|------|-----|
| /api/info | GET | 项目/连接状态 |
| /api/import/step | POST | 导入 STEP |
| /api/material/assign | POST | 赋材料 |
| /api/solver/frequency | POST | 设置频率范围 |
| /api/solver/run | POST | 运行仿真 |
| /api/results | POST | 获取结果 |
| /api/project/new | POST | 新建项目 |

## 扩展实现

`cst_operations.py` 中的各函数当前为框架实现。实际调用 CST API 时需参考：

- CST 安装目录下的 `python_cst_libraries` 文档
- [CST Python API 文档](https://hermes.insa-rennes.fr/docs/cst-python-api/)
- CST 自带的 VBA 宏可转为等价 Python 调用

按实际 CST 版本调整 `import_step`、`assign_material`、`run_simulation`、`get_simulation_results` 等函数内的 API 调用即可。
