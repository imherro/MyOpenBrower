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

## 使用真实 ChatGPT 网页版

默认 `openbrowser` Provider 使用 Playwright 打开隔离的、持久化的 Chrome Profile。先为需要的 Profile 登录一次：

```powershell
python -m gateway.browser_login --profile default
```

在打开的 Chrome 窗口完成 ChatGPT 登录后，回到终端按 Enter 保存 Cookie。随后启动网关：

```powershell
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 9900
```

创建 Session 可让长期对话、浏览器 Profile 和 Memory 相互隔离：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9900/api/sessions -ContentType application/json -Body '{"session_id":"investing","profile_name":"default","conversation_url":"https://chatgpt.com/c/<conversation-id>"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9900/api/sessions/investing/memory -ContentType application/json -Body '{"content":"风险偏好保守，优先关注长期价值。"}'
```

不填 `conversation_url` 时，Provider 会从 ChatGPT 首页开始一个新对话，并在任务完成后保存生成的对话地址到该 Session。

设置 `GATEWAY_API_KEY` 后，所有 `/api/*` 请求都必须带 `X-API-Key` 请求头。测试控制台运行在同一主机时可继续使用；如向局域网开放，请在反向代理层额外配置认证。

任务控制接口：`POST /api/tasks/{task_id}/cancel` 可取消尚未由浏览器领取的任务；`POST /api/tasks/{task_id}/retry` 可重新排队失败或已取消的任务。运行日志写入 `logs/gateway.log`，单文件最大 5 MB，最多保留 5 个备份。

浏览器页面或生成失败时，Provider 会将页面截图保存到 `data/failures/<task_id>.png`，对应路径会写入任务错误信息，便于排查页面变化或登录问题。

创建任务：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9900/api/chat -ContentType application/json -Body '{"session_id":"general","prompt":"你好"}'
```

查询任务：

```powershell
Invoke-RestMethod http://127.0.0.1:9900/api/tasks/<task_id>
```

## 自定义浏览器驱动协议

当 `GATEWAY_PROVIDER=command` 时，配置 `GATEWAY_OPENBROWSER_COMMAND`。网关将一行 JSON 通过标准输入传给该命令：

```json
{"task_id":"...","session_id":"general","prompt":"...","timeout_seconds":300}
```

命令须在标准输出写回：

```json
{"answer":"模型回答"}
```

驱动负责浏览器连接、登录校验、会话定位、提问、等待完成和答案提取；失败时退出非零并将诊断输出写入标准错误。
