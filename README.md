<p align="center">
  <img src="docs/logo.svg" width="72" height="72" alt="数语" />
</p>

<h1 align="center">数语 · 自然语言数据分析 Agent</h1>

<p align="center">
  连上数据库，用中文提问，自动生成 SQL、出表、出图、给结论
</p>

<p align="center">
  <img alt="python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" />
  <img alt="fastapi" src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" />
  <img alt="vue" src="https://img.shields.io/badge/Vue-3.5-42B883?logo=vue.js&logoColor=white" />
  <img alt="license" src="https://img.shields.io/badge/License-MIT-blue" />
</p>

---

## 这是什么

**数语**把"查数"变成"问数"：业务人员用中文提问，系统读表结构、生成 SQL、校验安全、执行查询，返回表格、图表和一句话结论。每一次查询都记入审计日志。

它面向的场景：小公司没有数据分析团队，业务同学想看一眼数据得排队找研发写 SQL。

## 功能

**数据源**
- 上传 SQLite 文件（`.db` / `.sqlite`），自动解析表结构、行数、示例数据
- 连接 MySQL（只读账号），支持连通性测试
- 表结构浏览：字段、类型、主键、示例行

**查询**
- 中文提问 → 生成 SQL（先展示，可手动修改后执行）
- 多轮追问：基于上一轮 SQL 继续改（"那 9 月呢？"）
- 执行失败自动把数据库报错回填给模型修正，最多重试 2 次
- 结果：表格（最多 500 行）+ 自动图表（柱状/折线）+ 一句话结论

**安全**
- SQLite 以 `mode=ro` 只读打开；MySQL 建议只读账号
- 只允许单条 `SELECT` / `WITH`，`sqlparse` 解析后按关键字黑名单拦截
- 强制 `LIMIT`（默认 500 行）、查询超时（20s）
- 全链路审计：谁、何时、问什么、执行了什么 SQL

**运维**
- `/healthz`、`/readyz`（探测模型连通性）
- 请求日志带 `x-request-id`
- 后台统计：今日查询、平均延迟、失败率、用户与数据源数
- 单机 SQLite 元数据库，零外部依赖；可换 PostgreSQL

## 架构

```text
┌──────────────┐   REST      ┌──────────────────────────────────────────┐
│  Vue3 + EP   │ ──────────▶ │               FastAPI                     │
│  ECharts     │ ◀────────── │ auth · datasources · query · admin        │
└──────────────┘             └───────┬──────────────────┬───────────────┘
                                     │                  │
                          ┌──────────▼─────────┐  ┌─────▼─────────────┐
                          │   Text2SQL 流水线    │  │  模型服务          │
                          │ 选表 → 生成 → 校验   │  │ Ollama / OpenAI   │
                          │ → 执行 → 报错重试    │  │ 兼容接口           │
                          └──────────┬─────────┘  └───────────────────┘
                                     │
                     ┌───────────────▼────────────────┐
                     │ 目标数据库（只读）：SQLite / MySQL │
                     │ 元数据库：用户/数据源/查询/审计    │
                     └────────────────────────────────┘
```

**关键设计**：LLM 只负责"写 SQL"，安全与执行由代码把关——SQL 先过白名单，再由只读连接执行，失败才回填错误让它改。这样模型再"幻觉"也不会删库。

## 快速开始

### 本机运行

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt

copy .env.example .env             # Windows
# cp .env.example .env            # macOS / Linux

python scripts/seed_demo.py        # 生成演示库 data/sales.db
uvicorn app.main:app --port 8010
```

打开 http://127.0.0.1:8010 ，`admin / admin123` 登录（**登录后请改密码**）。
API 文档：http://127.0.0.1:8010/api/docs

进入后在「数据源」上传 `data/sales.db`，然后就能问：

- 每个品类的销售额是多少？
- 哪个城市客单价最高？
- 9 月销售额环比怎么样？
- 卖得最好的 5 个产品

### Docker

```bash
docker compose up -d --build
```

> 国内拉基础镜像慢时，配置 `registry-mirrors`（见另一项目 README 的说明），或先 `docker pull docker.m.daocloud.io/library/python:3.12-slim` 再打 tag。

### 模型

默认 **Ollama** 本地模型，断网可用：

```bash
ollama pull qwen2.5:7b
ollama serve
```

切云端（DeepSeek 等）：改 `.env` 的 `LLM_PROVIDER=openai` 与对应 KEY。

## 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` / `openai` |
| `OLLAMA_CHAT_MODEL` | `qwen2.5:7b` | 对话模型 |
| `MAX_ROWS` | `500` | 单次查询最多返回行数 |
| `QUERY_TIMEOUT_SECONDS` | `20` | 查询超时 |
| `MAX_RETRY` | `2` | 失败后自动修正次数 |
| `SCHEMA_SAMPLE_ROWS` | `3` | 给模型看的示例行数 |
| `SECRET_KEY` | - | 生产环境必须替换 |

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/login` | 登录 |
| POST | `/api/v1/datasources/upload` | 上传 SQLite |
| POST | `/api/v1/datasources` | 添加 MySQL |
| GET | `/api/v1/datasources/{id}/tables` | 表结构 |
| POST | `/api/v1/query` | 自然语言查询 |
| POST | `/api/v1/query/execute` | 手动执行 SQL |
| GET | `/api/v1/queries` | 历史（支持只看收藏） |
| GET | `/api/v1/admin/stats` | 统计 |

## 测试与评测

```bash
pytest                            # 8 个接口测试（含 SQL 安全拦截、权限隔离）
python scripts/e2e_smoke.py       # 端到端冒烟（需服务已启动）
python scripts/import_online_retail.py  # 下载并导入 UCI 真实数据集（53 万行）
python scripts/eval_nl2sql.py     # 20 题评测，自动出准确率
```

### 真实数据集评测结果

数据：UCI *Online Retail*（英国在线零售商 2010-12 ~ 2011-12 真实交易）
清洗后 **530,104 行**，派生 products/customers/countries 三张表，总销售额 10,666,684.54。

评测方法：每题配一条**参考 SQL** 直接查库得到标准答案，再与系统输出比对（标量误差 ≤0.5%；Top1 需标签与数值同时正确）。

| 指标 | 结果 |
|---|---|
| 一次通过 | **20/20 = 100%** |
| 平均延迟 | 1.2 s |
| P95 延迟 | 1.7 s |

基线阶段为 **66.7%（8/12）**，通过三类修复提升：业务口径说明注入（`COUNT(DISTINCT invoice_no)` 等）、
SQLite `temp_store=MEMORY` 解决受限环境临时文件报错、提示词区分"销量/销售额"口径。

### 分析能力

对结果集自动计算：峰谷与差额、最大单期下滑、整体趋势、星期效应、月初效应、头部集中度；
并用**问题对齐**机制优先回答用户真正比较的对象（如"1 号 vs 5 号"），而不是只给全局最大最小值。

## 目录

```text
app/
  main.py
  config.py / db.py / models.py / schemas.py / security.py / deps.py
  routers/        auth / datasources / query / admin / health
  services/
    connectors.py      SQLite（只读）与 MySQL 执行
    introspection.py   表结构、行数、示例、DDL 生成、表筛选
    sqlguard.py        单语句 / SELECT 白名单 / 关键字拦截 / 强制 LIMIT
    generator.py       选表 → 生成 → 校验 → 执行 → 重试
    narration.py       一句话结论 + 图表建议
  static/          预构建前端
frontend/          Vue3 + Element Plus + ECharts
tests/
scripts/seed_demo.py  scripts/e2e_smoke.py  scripts/start.ps1
```

## 已知边界

- 只支持 SQLite / MySQL，未做 PostgreSQL（接口已按 SQLAlchemy 预留）
- 复杂问题（同比环比、多步拆解）不做 Agent 化多轮规划，当前是单轮生成
- 表很多时用关键词粗筛，未做 embedding 级 schema 检索
- 只读保证依赖"只读连接 + SQL 白名单"，生产环境请再配只读账号兜底

## Roadmap

- [ ] PostgreSQL / ClickHouse
- [ ] 指标口径层（预定义 GMV、客单价，避免模型自由发挥）
- [ ] 查询模板与定时报表
- [ ] 多轮 Agent 规划（复杂问题拆解）
- [ ] Row-level 权限

## License

MIT
