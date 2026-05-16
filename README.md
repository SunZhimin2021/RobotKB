# RobotKB

这是一个用于机器人开发的知识库。机器人开发涉及很多软硬件，手册等，资料太多，有在多个平台均可使用的，有针对单一平台的，情况复杂。我们需要借助AI，找到准确的、可用的资料，本库包含代码及相关资料。
本库的开发过程中，尽可能使用AI，所以相关的代码和文档大部分由AI生成。
但库内资料以原厂资料为主，也会包含部分AI生成的资料，生成的资料都经过验证后才会入库。

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                   客户端接入层                        │
│   Claude Code (MCP)  │  Web UI (React)  │  REST API  │
└──────────┬───────────┴────────┬─────────┴─────┬──────┘
           │                   │               │
┌──────────▼───────────────────▼───────────────▼──────┐
│                    应用服务层                         │
│  mcp_server (stdio)  │  api_server (FastAPI/RBAC)    │
│  agent_workflows (故障诊断)                           │
└──────────┬───────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────┐
│                    核心检索层                          │
│  retrieval_core (4路检索 + RRF融合 + Rerank)          │
│  constraint_engine (Aho-Corasick + 约束推理)          │
│  etl_worker (PDF/DOCX解析 → 分块 → 向量化 → 入库)    │
└──────────┬───────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────┐
│                    存储层 (Docker)                     │
│  PostgreSQL+pgvector │ Meilisearch │ Neo4j │ MinIO    │
│  Redis (Celery broker)                                │
└──────────────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────┐
│               推理服务 (Jetson AGX Orin)               │
│  bge-m3 Embedding (:7997) │ bge-reranker-v2-m3 (:7998)│
└──────────────────────────────────────────────────────┘
```

**目标硬件**：NVIDIA Jetson AGX Orin 64GB（ARM64），兼容其他 Rockchip/NXP 平台。

---

## 环境要求

| 组件 | 要求 |
|------|------|
| Python | 3.10+ |
| Docker & Docker Compose | v2.20+ |
| 推理服务机器 | Jetson AGX Orin 64GB（或同等 ARM64 服务器） |
| 开发机 | macOS / Linux（x86_64 或 ARM64） |

---

## 安装与部署

### 1. 克隆仓库

```bash
git clone https://github.com/SunZhimin2021/RobotKB.git
cd RobotKB
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，将所有 `change-me-*` 替换为真实密码，并根据实际 IP 调整服务地址：

- **Jetson 本机运行**：保持 `localhost`
- **开发机远程访问**：将 `localhost` 改为 Jetson 的局域网 IP（如 `192.168.3.58`）

### 3. 启动基础设施（存储 + 推理服务）

```bash
docker compose up -d
```

首次启动会自动拉取镜像并初始化容器，包括：

| 服务 | 端口 | 说明 |
|------|------|------|
| PostgreSQL + pgvector | 5432 | 文档元数据 + 向量检索 |
| Meilisearch | 7700 | 全文关键词检索 |
| MinIO | 9000 / 9001 | 原始文件存储（9001 为 Web 控制台） |
| Neo4j | 7474 / 7687 | 芯片族谱 + 故障图谱 |
| Redis | 6379 | Celery 任务队列 |

### 4. 初始化存储 Schema

```bash
bash infra/scripts/init-storage.sh
```

脚本会等待各容器健康后，依次执行：
- PostgreSQL：创建 pgvector 扩展、建表、建索引
- Meilisearch：创建 chunks 索引并应用字段设置
- Neo4j：创建节点唯一约束和全文索引

### 5. 安装 Python 依赖

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 6. 运行测试

```bash
PYTHONPATH=src pytest tests/ -v
```

全部 236 个测试应通过（耗时约 1 秒，全部为单元测试，无需真实存储连接）。

### 7. 启动 API Server

```bash
PYTHONPATH=src uvicorn api_server.main:create_app --factory --host 0.0.0.0 --port 8080
```

### 8. 启动 MCP Server（供 Claude Code 使用）

```bash
PYTHONPATH=src python -m mcp_server.main
```

---

## 使用说明

### 通过 Claude Code 使用（MCP 接入）

在 Claude Code 的 MCP 配置文件中添加：

```json
{
  "mcpServers": {
    "robotkb": {
      "command": "python",
      "args": ["-m", "mcp_server.main"],
      "cwd": "/path/to/RobotKB",
      "env": {
        "PYTHONPATH": "src",
        "KB_MCP_TOKEN_SECRET": "your-token-secret"
      }
    }
  }
}
```

MCP Server 提供 6 个 Tools：

| Tool | 说明 |
|------|------|
| `search_kb` | 语义检索知识库，支持芯片/开发板/ROS版本过滤 |
| `diagnose_fault` | 结构化故障诊断，返回候选原因和诊断步骤 |
| `check_compatibility` | 查询芯片/开发板的软硬件兼容性矩阵 |
| `list_chips` | 列出已支持的芯片型号 |
| `list_boards` | 列出已支持的开发板型号 |
| `submit_feedback` | 提交文档反馈（标注错误/过时内容） |

### 通过 REST API 使用

首先获取 JWT Token（需管理员创建账号）：

```bash
# 上传文档（需 importer 角色）
curl -X POST http://localhost:8080/api/v1/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@datasheet.pdf" \
  -F 'meta={"title":"RK3588 Datasheet","category":"hardware","source_tier":"official","applicable_chips":["RK3588"],"applicable_boards":["Rock 5B"],"ros_versions":["Humble"]}'

# 语义检索
curl "http://localhost:8080/api/v1/search?q=I2C通信超时&chip=RK3588" \
  -H "Authorization: Bearer <token>"

# 故障诊断
curl -X POST http://localhost:8080/api/v1/diagnose \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"symptom":"RK3588 启动时 I2C 设备无响应"}'
```

### 通过 Web UI 使用

前端开发服务器（需先安装 Node.js 18+）：

```bash
cd web_ui
npm install
npm run dev        # 开发模式，访问 http://localhost:5173
npm run build      # 生产构建，输出到 web_ui/dist/
```

生产部署（Nginx 反向代理）：

```bash
# 构建后将 dist/ 内容部署到 Nginx，配置文件见 web_ui/nginx.conf
# Nginx 会将 /api/* 转发到 api_server:8080
```

---

## 权限说明

系统采用 RBAC 角色控制：

| 角色 | 权限 |
|------|------|
| `viewer` | 查看、搜索文档 |
| `importer` | 上传文档（只能修改自己上传的） |
| `reviewer` | 审核、发布文档，修改任意文档 |
| `admin` | 全部权限，包括删除文档 |

---

## 项目结构

```
RobotKB/
├── src/
│   ├── common/             # 公共 Schema、配置、异常
│   ├── storage/            # PostgreSQL/Meilisearch/Neo4j/MinIO DAO
│   ├── constraint_engine/  # Aho-Corasick 约束提取与推理
│   ├── graph_service/      # Neo4j 芯片族谱与故障图谱
│   ├── retrieval_core/     # 4路检索 + RRF融合 + Rerank
│   ├── etl_worker/         # 文档解析、分块、向量化 Pipeline
│   ├── agent_workflows/    # 故障诊断工作流
│   ├── mcp_server/         # MCP stdio 服务（Claude Code 接入）
│   └── api_server/         # FastAPI REST API
├── web_ui/                 # React 18 + TypeScript 前端
├── infra/
│   ├── postgres/init/      # SQL Schema 初始化脚本
│   ├── meilisearch/        # 索引字段配置
│   ├── neo4j/init/         # Cypher 约束初始化
│   └── scripts/            # 存储初始化脚本
├── tests/                  # 236 个单元测试
├── docker-compose.yml      # 全栈服务编排
└── .env.example            # 环境变量模板
```
