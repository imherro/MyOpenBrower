# ChatGPT Web API Gateway 设计与实现文档

## 1. 项目概述

### 1.1 项目目标

利用 OpenBrowser 作为浏览器桥接层，将 ChatGPT 网页版封装成本地 API
服务。

目标架构：

    业务程序
      |
    HTTP API
      |
    ChatGPT Web Gateway
      |
    OpenBrowser
      |
    Chrome
      |
    ChatGPT Plus
      |
    返回结果

实现：

-   程序通过标准 API 调用 ChatGPT 能力；
-   使用 ChatGPT Plus 订阅降低 API 成本；
-   支持多个项目共享 AI 能力；
-   为 Personal AI OS 架构提供基础。

------------------------------------------------------------------------

# 2. 系统定位

本项目不是普通浏览器自动化工具，而是：

> 一个 ChatGPT 网页版兼容 API 网关。

业务程序不关心：

-   浏览器；
-   页面操作；
-   ChatGPT 登录；
-   会话管理。

业务程序只调用：

    chatgpt.ask(session, prompt)

获得结果。

------------------------------------------------------------------------

# 3. 总体架构

                 用户项目

                    |

            ChatGPT Web API Gateway

                    |

               Gateway Server

                    |

            OpenBrowser Adapter

                    |

                 Chrome

                    |

              ChatGPT Web

                    |

                 GPT模型

------------------------------------------------------------------------

# 4. 核心模块

## 4.1 API Gateway

职责：

-   接收请求；
-   创建任务；
-   查询结果；
-   管理 Session。

推荐技术：

-   Python
-   FastAPI
-   SQLite

### 服务网络配置

Gateway 默认运行在：

    0.0.0.0:9900

即监听本机全部网络接口，便于局域网内的业务程序调用。启动命令：

``` powershell
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 9900
```

可通过环境变量覆盖，但默认值必须保持：

``` text
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=9900
```

由于服务会暴露 ChatGPT 账号能力，部署到局域网或公网时必须额外配置认证、访问控制和防火墙；不应直接裸露在公网。

------------------------------------------------------------------------

## 4.2 Task Queue

采用 SQLite。

数据库：

    chatgpt_gateway.db

任务表：

``` sql
CREATE TABLE tasks (
 id INTEGER PRIMARY KEY,
 task_id TEXT UNIQUE,
 session_id TEXT,
 prompt TEXT,
 status TEXT DEFAULT 'pending',
 created_at DATETIME,
 started_at DATETIME,
 completed_at DATETIME,
 result TEXT,
 error TEXT
);
```

状态：

    pending
       |
    running
       |
    completed

    failed
       |
    retry

------------------------------------------------------------------------

# 5. API设计

## 5.1 创建任务

POST:

    /api/chat

请求：

``` json
{
 "session_id":"investing",
 "prompt":"分析机器人行业趋势"
}
```

返回：

``` json
{
 "task_id":"202608250001",
 "status":"queued"
}
```

------------------------------------------------------------------------

## 5.2 查询结果

GET:

    /api/task/{id}

返回：

``` json
{
 "status":"completed",
 "answer":"分析结果..."
}
```

------------------------------------------------------------------------

## 5.3 测试控制台

Gateway 内置测试页面：

    GET /

默认地址：

    http://127.0.0.1:9900/

页面功能：

-   提交 `session_id` 和 `prompt` 创建测试任务；
-   自动刷新并显示全部任务；
-   显示任务 ID、会话、问题、状态、重试次数、答案或错误信息、创建/完成时间。

任务列表接口：

    GET /api/tasks

该控制台用于本地开发和个人环境验证。若向局域网开放 Gateway，应使用认证或反向代理保护该页面，因为它会展示聊天内容。

------------------------------------------------------------------------

# 6. Session设计

ChatGPT网页端最大的价值是：

-   历史上下文；
-   Memory；
-   专业角色。

设计多个长期会话：

    sessions

    ├── investing
    ├── car
    ├── ai
    ├── general

例如：

investing：

保存：

-   投资理念；
-   风险偏好；
-   历史讨论。

------------------------------------------------------------------------

# 7. Worker设计

Worker负责：

1.  获取任务；
2.  调用OpenBrowser；
3.  打开对应ChatGPT会话；
4.  输入问题；
5.  获取回答；
6.  保存结果。

流程：

    读取任务

    ↓

    锁定任务

    ↓

    调用OpenBrowser

    ↓

    发送问题

    ↓

    等待回答

    ↓

    保存结果

    ↓

    更新状态

------------------------------------------------------------------------

# 8. OpenBrowser Adapter

不要让业务直接依赖 OpenBrowser。

设计接口：

``` python
class ChatProvider:

    def send(self, session, prompt):
        pass
```

未来可以替换：

-   ChatGPT Web
-   Claude Web
-   Gemini Web
-   本地模型
-   官方 API

------------------------------------------------------------------------

# 9. 浏览器Session管理

建议：

    profiles/

    ├── investing/

    ├── car/

    └── general/

每个 Profile 保存：

-   Cookie；
-   登录状态；
-   浏览器配置。

------------------------------------------------------------------------

# 10. 错误处理

需要处理：

## 页面失败

策略：

-   自动重试；
-   刷新页面；
-   重新连接。

## 登录失效

状态：

    AUTH_REQUIRED

提示人工登录。

## 超时

默认：

300秒。

------------------------------------------------------------------------

# 11. 目录结构

    ChatGPT-Web-Gateway/

    ├── api/
    │   └── server.py

    ├── worker/
    │   ├── worker.py
    │   └── openbrowser_adapter.py

    ├── database/
    │   └── chatgpt.db

    ├── sessions/

    ├── logs/

    ├── config/

    └── README.md

------------------------------------------------------------------------

# 12. MVP开发计划

## Phase 1

目标：

完成一次调用闭环。

实现：

-   FastAPI；
-   SQLite；
-   单Session；
-   OpenBrowser调用；
-   返回结果。

------------------------------------------------------------------------

## Phase 2

增加：

-   多Session；
-   任务队列；
-   重试；
-   日志。

------------------------------------------------------------------------

## Phase 3

增加：

-   Memory系统；
-   权限；
-   多项目支持。

------------------------------------------------------------------------

# 13. 长期架构

最终：

                 Personal AI OS

                        |

              ChatGPT Web Gateway

                        |

           ----------------------------

           |            |             |

       MyInvest      CarAI       Research

                        |

                    Memory

目标：

将 ChatGPT Plus 从：

    聊天工具

升级为：

    个人AI推理服务

------------------------------------------------------------------------

# 14. 注意事项

该方案适合：

-   个人自动化；
-   AI实验；
-   私人生产力系统。

不适合作为商业API服务。

网页自动化依赖：

-   浏览器环境；
-   页面结构；
-   登录状态。

因此需要：

-   重试机制；
-   日志；
-   异常恢复。

------------------------------------------------------------------------

# 15. 当前实现与运行说明

## 15.1 Provider 实现

当前默认 `openbrowser` Provider 由 Playwright 驱动独立的 Chrome 持久化 Profile 实现：

    Gateway Worker
       ↓
    OpenBrowserProvider（Provider 抽象层）
       ↓
    Playwright / Chrome Persistent Context
       ↓
    ChatGPT Web

每个 Gateway Session 保存 `profile_name` 和 `conversation_url`：

-   `profile_name` 决定 Cookie 和登录状态保存位置：`profiles/<profile_name>`；
-   `conversation_url` 指向长期 ChatGPT 对话；若为空，首次提问后自动保存浏览器当前对话地址；
-   多 Session 可复用同一 Profile，也可配置不同 Profile 实现账号隔离。

首次使用某个 Profile 需要人工登录：

``` powershell
python -m gateway.browser_login --profile default
```

该命令只使用 Gateway 自己的 Profile，不读取或修改日常 Chrome 用户资料。

## 15.2 API 与控制能力

除创建、查询任务外，当前实现提供：

``` text
GET    /api/tasks
POST   /api/tasks/{task_id}/cancel
POST   /api/tasks/{task_id}/retry
GET    /api/sessions
POST   /api/sessions
PATCH  /api/sessions/{session_id}
GET    /api/sessions/{session_id}/memory
POST   /api/sessions/{session_id}/memory
DELETE /api/sessions/{session_id}/memory/{memory_id}
```

Memory 条目按 Session 保存。Worker 执行任务时将它们组合为背景上下文并注入本次提问，使多个业务项目可保有独立偏好与长期信息。

任务取消仅适用于尚未被浏览器领取的 `pending` / `retry_wait` 任务；浏览器生成中的任务不会被强制中断，避免 ChatGPT 页面状态与数据库状态失去一致性。

## 15.3 安全与运维

-   设置 `GATEWAY_API_KEY` 后，所有 `/api/*` 接口要求 `X-API-Key`；测试页面会在浏览器本地存储该 Key 后调用接口。
-   运行日志写入 `logs/gateway.log`，单文件上限 5 MB，保留 5 个轮转备份。
-   数据库采用 SQLite WAL 与原子任务领取；Worker 启动时会恢复心跳超时的 `running` 任务。
-   Provider 将登录失效标记为 `AUTH_REQUIRED`；页面与生成超时会按照退避策略重试。
-   Provider 在页面或生成异常时保存 `data/failures/<task_id>.png` 页面截图，并将路径追加到任务错误信息，作为故障证据。

## 15.4 启动与验收

``` powershell
Copy-Item .env.example .env
python -m gateway.browser_login --profile default
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 9900
```

浏览器访问：

    http://127.0.0.1:9900/

测试控制台显示全部任务的问题、答案、状态、错误、重试次数与时间，并每两秒刷新一次。
