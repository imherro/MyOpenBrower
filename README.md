# ChatGPT Web API Gateway

本地异步任务网关：FastAPI 接收请求，SQLite 保存队列，Worker 通过可替换 Provider 获取回答。

## 启动

PowerShell：

```powershell
Copy-Item .env.example .env
$env:GATEWAY_PROVIDER = "demo" # 仅用于本地验证；生产使用 openbrowser
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 9900
```

服务监听 `0.0.0.0:9900`。局域网暴露前请自行配置防火墙、反向代理和认证。

浏览器打开 `http://127.0.0.1:9900/` 可访问测试控制台：提交问题，并查看所有任务的问题、答案、状态、重试次数和时间。

创建任务：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9900/api/chat -ContentType application/json -Body '{"session_id":"general","prompt":"你好"}'
```

查询任务：

```powershell
Invoke-RestMethod http://127.0.0.1:9900/api/tasks/<task_id>
```

## OpenBrowser 驱动协议

当 `GATEWAY_PROVIDER=openbrowser` 时，配置 `GATEWAY_OPENBROWSER_COMMAND`。网关将一行 JSON 通过标准输入传给该命令：

```json
{"task_id":"...","session_id":"general","prompt":"...","timeout_seconds":300}
```

命令须在标准输出写回：

```json
{"answer":"模型回答"}
```

驱动负责浏览器连接、登录校验、会话定位、提问、等待完成和答案提取；失败时退出非零并将诊断输出写入标准错误。
