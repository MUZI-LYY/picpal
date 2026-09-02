# HTTP 契约

`openapi-v1.yaml` 是正式对话式 MVP 前后端边界的唯一权威契约。

## 文件

- `openapi-v1.yaml`：OpenAPI 3.1 规范；
- `fixtures/`：经过契约校验的请求与响应样例；
- `../tests/contract/test_openapi_contract.py`：本地引用、操作、幂等要求、Fixture 和关键语义校验。

旧 `/api/v1/trips` 暂不属于该契约，只作为现有验收页的兼容接口保留。

## 验证

从 `backend/` 执行：

```bash
.venv/bin/python -m pytest tests/contract/test_openapi_contract.py -q
```

## 修改顺序

1. 先说明前端或产品任务；
2. 修改 `openapi-v1.yaml`；
3. 更新或增加 Fixture；
4. 运行契约测试；
5. 更新后端 Pydantic 模型和实现；
6. 重新生成前端类型；
7. 验证真实响应与 Fixture 使用同一契约。

所有 `$ref` 只允许指向当前 OpenAPI 文件中的 `#/components/*`，不加载远程引用或仓库外文件。
