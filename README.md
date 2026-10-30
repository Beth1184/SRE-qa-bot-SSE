# SRE 运维问答机器人（SSE 流式版）

从零到一构建企业级飞书运维问答助手。

## 项目简介

在 SRE 运维场景中，研发/测试同学经常需要查询各种运维知识（如故障排查、监控配置、发布流程等）。传统方式是查阅文档或询问 SRE，效率较低。

本项目通过 AI + 飞书机器人，实现：

- 用户在飞书中 @机器人 提问
- 机器人基于知识库给出专业回答
- 支持多轮对话上下文
- SSE 流式输出，实时显示回答过程

## 核心特性

| 特性 | 说明 |
| --- | --- |
| SSE 流式输出 | 逐 token 实时更新飞书卡片，用户体验好 |
| 多轮对话 | 支持上下文记忆，追问更自然 |
| 限流保护 | 滑动窗口限流，防止 API 滥用 |
| 降级机制 | 流式失败自动降级为同步模式 |
| Token 统计 | 实时显示输入/输出 token 用量 |
| 可观测性 | 完整的日志和指标记录 |

## 技术栈

| 组件 | 技术选型 | 说明 |
| --- | --- | --- |
| 编程语言 | Python 3.12+ | 主流 AI 开发语言 |
| Web 框架 | FastAPI | 高性能异步框架 |
| LLM API | DeepSeek API | 支持 SSE 流式输出 |
| 飞书 SDK | lark-oapi | 官方 Python SDK |
| HTTP 客户端 | httpx | 支持流式请求 |
| 重试机制 | tenacity | 智能重试策略 |
| 配置管理 | python-dotenv | 环境变量管理 |

## 项目结构

```
project-01-sre-qa-bot-sse/
├── .env.example              # 环境变量模板
├── .env                      # 实际配置（不提交 Git）
├── requirements.txt          # Python 依赖
├── Dockerfile                # Docker 镜像构建
├── docker-compose.yml        # Docker 编排
├── start.sh                  # Linux/Mac 启动脚本
├── start.bat                 # Windows 启动脚本
├── README.md                 # 项目文档
└── src/
    ├── __init__.py
    ├── config.py             # 配置管理
    ├── deepseek_client.py    # DeepSeek API 客户端（核心）
    ├── lark_bot.py           # 飞书交互层（核心）
    ├── session_manager.py    # 会话管理
    ├── main.py               # FastAPI 入口（Webhook 模式）
    └── start_lark.py         # 长连接模式入口
```

## 快速开始

### 1. 获取 API Key

**DeepSeek API Key**

1. 访问 https://platform.deepseek.com
2. 注册账号并登录
3. 进入 API Keys 页面，创建新的 API Key
4. 保存 Key（只显示一次）

**飞书应用凭证**

1. 访问 https://open.feishu.cn
2. 创建企业自建应用，开启机器人能力
3. 配置权限：
   - `im:message:receive_v1` - 接收消息
   - `im:message:send_as_bot_v1` - 发送消息
4. 记录 App ID 和 App Secret
5. 配置事件订阅：
   - 订阅 `im.message.receive_v1` 事件
   - 设置请求地址：`http://your-server:8000/lark/event`

### 2. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入实际配置
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动服务

```bash
# 方式一：直接运行
python -m src.start_lark

# 方式二：使用启动脚本（Linux/Mac）
./start.sh

# 方式三：Windows 启动脚本
start.bat

# 方式四：Docker 部署
docker-compose up -d
```

## 环境变量说明

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| DEEPSEEK_API_KEY | - | DeepSeek API 密钥 |
| DEEPSEEK_MODEL | deepseek-chat | 使用的模型 |
| DEEPSEEK_MAX_TOKENS | 4096 | 最大输出 token 数 |
| DEEPSEEK_TEMPERATURE | 0.3 | 采样温度 |
| SSE_CARD_UPDATE_INTERVAL_MS | 800 | 卡片更新频率（毫秒） |
| LARK_APP_ID | - | 飞书应用 ID |
| LARK_APP_SECRET | - | 飞书应用密钥 |

## 扩展与优化方向

- 接入知识库（RAG），提升回答质量
- 多模型支持（DeepSeek / OpenAI / Qwen）
- 用户反馈机制（点赞 / 点踩）
- 监控与告警（Prometheus 指标）

## 参考资源

- [DeepSeek API 文档](https://platform.deepseek.com/api-docs)
- [飞书开放平台](https://open.feishu.cn)
- [飞书消息卡片](https://open.feishu.cn/document/common-capabilities/message-card)
- [httpx 文档](https://www.python-httpx.org)
- [lark-oapi](https://github.com/larksuite/oapi-sdk-python)
