# mypdf


### 基于uv管理依赖
只使用`uv add xxx`添加依赖，不使用`pip install xxx`
- 安装依赖：`uv sync`

### 启动HTTP服务（FastAPI）
- 添加Web依赖：`uv add fastapi uvicorn[standard]`，然后执行`uv sync`同步环境
- 运行服务：`uv run uvicorn src.service:app --host 0.0.0.0 --port 8000 --reload`
- 健康检查：`GET /health` 返回 `{"status": "ok"}`
- 转换接口：`POST /convert`，表单字段`pdf`(文件必填)、`voice`、`speed`、`max_length`、`start_page`、`end_page`
- 示例：`curl -X POST -F "pdf=@test.pdf" -F "voice=alloy" http://127.0.0.1:8000/convert -o out.mp3`
