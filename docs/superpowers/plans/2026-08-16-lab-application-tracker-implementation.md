# Lab Application Tracker 实施计划

- 日期：2026-08-16
- 状态：准备实施
- 依据：[Lab Application Tracker 设计规格](../specs/2026-08-15-lab-application-tracker-design.md)
- 实施方式：按任务顺序推进，每个任务先写测试，再写最小实现，验证通过后单独提交

## 1. 实施目标与固定边界

本计划把已经确认的规格实现成可在本机单进程运行的 React + FastAPI + SQLite 应用。实施期间保持以下边界：

- 后端使用 Python、FastAPI、Pydantic、LangChain/LangGraph 和参数化原始 SQL，不使用 ORM。
- 前端使用 JavaScript、React 和 Vite，不改成 TypeScript。
- 数据库只有 `professors`、`application_status`、`publications` 和 `update_proposals` 四张业务表。
- Tavily 与 OpenAlex 由 FastAPI 内部的 Python provider/LangChain Tool 直接调用，不搭建 MCP Server。
- job 状态只保存在单 worker 内存中，不增加 `update_jobs` 表。
- scope=new 严格串行处理教授，每位教授使用独立事务；现有教授只通过单人检查和确认更新。
- 常规自动化测试禁止访问真实 UIUC、Tavily、OpenAlex 或 LLM 服务。
- 用户已有的未跟踪文件 `docs/superpowers/specs/a.md` 和 `tmp/` 不属于实施计划，不修改也不提交。

## 2. 目标目录结构

```text
find_lab/
├─ .env.example
├─ .gitignore
├─ README.md
├─ backend/
│  ├─ pyproject.toml
│  ├─ lab_tracker/
│  │  ├─ __init__.py
│  │  ├─ __main__.py
│  │  ├─ main.py
│  │  ├─ config.py
│  │  ├─ errors.py
│  │  ├─ api/
│  │  ├─ db/
│  │  │  └─ migrations/001_initial.sql
│  │  ├─ models/
│  │  ├─ repositories/
│  │  └─ services/
│  └─ tests/
│     ├─ fixtures/
│     ├─ unit/
│     └─ integration/
├─ frontend/
│  ├─ package.json
│  ├─ vite.config.js
│  ├─ playwright.config.js
│  ├─ public/
│  ├─ src/
│  │  ├─ api/
│  │  ├─ assets/
│  │  ├─ components/
│  │  ├─ hooks/
│  │  ├─ pages/
│  │  └─ test/
│  └─ e2e/
└─ docs/
```

模块以业务边界拆分，路由只做 HTTP 解析，service 负责业务流程，repository 集中保存 SQL。单个文件出现多个不相关职责时，在当前任务内继续拆分，不创建通用的 `utils.py` 大杂烩。

## 3. 统一实施规则

每个任务执行以下循环：

1. 创建或修改指定测试，先运行并确认测试因缺少目标行为而失败。
2. 编写满足当前任务的最小实现，不提前实现后续任务。
3. 运行任务内的定向测试。
4. 运行全部既有后端或前端回归测试。
5. 检查 `git diff --check`，只暂存任务涉及的文件并提交。

默认验证命令：

```text
python -m pytest backend/tests
npm --prefix frontend test -- --run
npm --prefix frontend run test:e2e
npm --prefix frontend run build
```

外部服务测试统一使用 fixture、fake provider 或 fake `BaseChatModel`。只有最终手工验收阶段、用户提供真实 key 后，才运行显式标记的 live smoke test。

## 4. 实施任务

### 任务 1：建立项目脚手架与配置验证

创建：

- `.gitignore`
- `.env.example`
- `README.md`
- `backend/pyproject.toml`
- `backend/lab_tracker/__init__.py`
- `backend/lab_tracker/__main__.py`
- `backend/lab_tracker/config.py`
- `backend/tests/unit/test_config.py`
- `frontend/package.json`
- `frontend/vite.config.js`
- `frontend/src/main.jsx`
- `frontend/src/App.jsx`
- `frontend/src/test/setup.js`
- `frontend/src/App.test.jsx`

实现与验证：

- 后端声明 FastAPI、Uvicorn、Pydantic Settings、httpx、Beautiful Soup、LangChain、LangGraph、`langchain-openai` 和 `langchain-tavily` 依赖；开发依赖包含 pytest、pytest-asyncio 和覆盖率工具。
- 前端声明 React、React Router、Vitest、Testing Library 和 Playwright。
- `Settings` 读取规格中的环境变量，拒绝小于 1.0 秒的三个请求间隔，不在异常中泄露 key。
- `python -m lab_tracker` 成为生产启动入口，并强制文档中的单 worker 部署方式。
- 前端先提供可渲染的空应用壳，测试只验证启动和基本无障碍结构。

定向测试：

```text
python -m pytest backend/tests/unit/test_config.py
npm --prefix frontend test -- --run src/App.test.jsx
```

提交信息：`chore: scaffold lab application tracker`

### 任务 2：实现原始 SQL 迁移与连接工厂

创建：

- `backend/lab_tracker/db/__init__.py`
- `backend/lab_tracker/db/connection.py`
- `backend/lab_tracker/db/migrations.py`
- `backend/lab_tracker/db/migrations/001_initial.sql`
- `backend/tests/integration/test_migrations.py`
- `backend/tests/integration/test_database_constraints.py`

实现与验证：

- 连接工厂配置 `sqlite3.Row`、foreign keys、WAL、busy timeout 和显式事务。
- 迁移器按文件编号执行 SQL，并用 `PRAGMA user_version` 记录版本；同一迁移重复运行必须幂等。
- 初始迁移创建四张表、外键、CHECK、普通索引、论文唯一约束和单教授 pending proposal 的部分唯一索引。
- proposal 状态只允许 pending、applied、rejected；申请状态只允许 interested、applied、accepted、rejected。
- 测试教授与论文同一事务发生异常时完整回滚。

定向测试：

```text
python -m pytest backend/tests/integration/test_migrations.py backend/tests/integration/test_database_constraints.py
```

提交信息：`feat: add raw sqlite schema and migrations`

### 任务 3：实现 Pydantic 模型与 repositories

创建：

- `backend/lab_tracker/models/common.py`
- `backend/lab_tracker/models/professor.py`
- `backend/lab_tracker/models/application.py`
- `backend/lab_tracker/models/publication.py`
- `backend/lab_tracker/models/update.py`
- `backend/lab_tracker/repositories/professors.py`
- `backend/lab_tracker/repositories/applications.py`
- `backend/lab_tracker/repositories/publications.py`
- `backend/lab_tracker/repositories/proposals.py`
- `backend/tests/unit/test_models.py`
- `backend/tests/integration/test_repositories.py`

实现与验证：

- repository 只使用 `?` 参数绑定；动态排序使用固定白名单映射。
- 教授列表查询支持搜索、自由标签、四种申请状态、分页和排序，并保留无申请记录教授。
- 教授详情一次返回教授、论文、申请记录和 pending proposal ID。
- 应用申请记录使用 upsert 语义；删除后教授仍存在且状态为空。
- proposal repository 实现 pending 唯一性、查询、apply 状态转换和 reject 状态转换。
- 测试恶意搜索、标签、状态和排序输入不能改变 SQL 结构。

定向测试：

```text
python -m pytest backend/tests/unit/test_models.py backend/tests/integration/test_repositories.py
```

提交信息：`feat: add models and raw sql repositories`

### 任务 4：实现健康检查、教授、标签和申请 API

创建：

- `backend/lab_tracker/errors.py`
- `backend/lab_tracker/api/dependencies.py`
- `backend/lab_tracker/api/health.py`
- `backend/lab_tracker/api/professors.py`
- `backend/lab_tracker/api/applications.py`
- `backend/lab_tracker/services/catalog.py`
- `backend/lab_tracker/services/applications.py`
- `backend/lab_tracker/main.py`
- `backend/tests/integration/test_catalog_api.py`
- `backend/tests/integration/test_application_api.py`

本任务交付六个 endpoint：

- `GET /api/health`
- `GET /api/professors`
- `GET /api/professors/{professor_id}`
- `GET /api/tags`
- `PUT /api/professors/{professor_id}/application`
- `DELETE /api/professors/{professor_id}/application`

实现统一错误 envelope、参数校验、分页元数据和 404/409/422 行为。测试申请写入永远不能修改教授研究字段。

提交信息：`feat: add catalog and application APIs`

### 任务 5：实现目录抓取、身份规范化与限流器

创建：

- `backend/lab_tracker/services/rate_limit.py`
- `backend/lab_tracker/services/http.py`
- `backend/lab_tracker/services/discovery.py`
- `backend/lab_tracker/services/identity.py`
- `backend/tests/fixtures/uiuc_faculty_directory.html`
- `backend/tests/fixtures/uiuc_faculty_profile.html`
- `backend/tests/unit/test_rate_limit.py`
- `backend/tests/unit/test_identity.py`
- `backend/tests/unit/test_discovery.py`

实现与验证：

- 解析 UIUC 列表中的姓名、职称、邮箱和详情页 URL，并实现 research-active 职称规则。
- 规范化姓名、邮箱和 URL，按详情页 URL、邮箱、姓名加 affiliation 顺序识别现有教授。
- 歧义只使当前候选失败，不能阻止后续候选。
- provider limiter 使用 semaphore 1、至少 1.0 秒间隔、`Retry-After` 和有限指数退避。
- 测试 scope=new 在识别现有教授后不会调用研究 provider。

提交信息：`feat: add faculty discovery and rate limiting`

### 任务 6：实现受限 Tavily、网页提取和 OpenAlex Tools

创建：

- `backend/lab_tracker/models/research.py`
- `backend/lab_tracker/services/research_sources.py`
- `backend/lab_tracker/services/tavily_provider.py`
- `backend/lab_tracker/services/page_extractor.py`
- `backend/lab_tracker/services/openalex_provider.py`
- `backend/lab_tracker/services/research_tools.py`
- `backend/tests/fixtures/professor_homepage.html`
- `backend/tests/fixtures/lab_homepage.html`
- `backend/tests/unit/test_research_sources.py`
- `backend/tests/unit/test_research_tools.py`
- `backend/tests/unit/test_openalex_provider.py`

实现与验证：

- Tavily Tool 只暴露 `query`，固定 basic、最多五个结果且不返回 answer/raw content/images。
- 候选 registry 生成 job-local candidate/source ID；页面 Tool 只接受 registry 中的 ID，禁止任意 URL。
- 页面提取删除脚本、表单、导航和 prompt-like 指令，限制正文字符数并生成身份匹配信号。
- OpenAlex Tool 从 state 注入姓名和 UIUC affiliation，执行作者消歧、三年窗口、字段选择、缓存和论文去重。
- 工具从服务器环境读取 key；模型输入、日志和返回对象中都不能出现 key。
- 本任务不创建 MCP Server，LangGraph 后续直接调用这些 Python Tools。

提交信息：`feat: add bounded research tools`

### 任务 7：实现 LangGraph Research Agent

创建：

- `backend/lab_tracker/services/research_state.py`
- `backend/lab_tracker/services/research_prompts.py`
- `backend/lab_tracker/services/research_validation.py`
- `backend/lab_tracker/services/research_graph.py`
- `backend/tests/unit/test_research_graph.py`
- `backend/tests/unit/test_research_validation.py`
- `backend/tests/fixtures/prompt_injection_page.html`

实现与验证：

- 使用显式 StateGraph 节点和条件边实现规格流程，不使用无边界 `create_agent`。
- Research Agent 最多 8 turns、3 次 Tavily、5 个唯一页面、1 次 OpenAlex，一次模型响应只接受一个工具调用，recursion limit 为 24。
- `tool_budget_guard` 在 ToolNode 前拒绝未知工具、任意 URL、身份覆盖、并行 tool calls 和超预算调用。
- finalizer 使用 `with_structured_output(ProfessorResearchResult)`；校验失败最多只重试 finalizer 两次。
- summary、tags、链接、论文和 evidence 只能引用已验证 ID；证据不足的链接为 null，无法产生可靠摘要时当前教授失败。
- fake model 覆盖搜索改写、主动停止、预算耗尽、错误结构、未知 ID 和网页 prompt injection。

定向测试：

```text
python -m pytest backend/tests/unit/test_research_graph.py backend/tests/unit/test_research_validation.py
```

提交信息：`feat: add bounded professor research graph`

### 任务 8：实现内存 jobs 与“查找新教授”流程

创建：

- `backend/lab_tracker/services/jobs.py`
- `backend/lab_tracker/services/update_checks.py`
- `backend/lab_tracker/api/update_checks.py`
- `backend/tests/unit/test_jobs.py`
- `backend/tests/integration/test_new_professor_job.py`
- `backend/tests/integration/test_update_check_api.py`

实现与验证：

- 内存 registry 使用 UUID 字符串，状态仅为 queued/running/completed/failed，同时最多一个 job。
- scope=new 以普通串行循环逐位调用 Research Agent；禁止并发运行多位教授。
- 每位成功教授用独立事务写入教授和论文；单人失败回滚当前教授、递增 failed count 并继续。
- job 级配置、目录或额度错误停止剩余候选并保留此前提交。
- 计算 outcome 与四个计数，保证正常完成时计数不变量。
- `409 UPDATE_ALREADY_RUNNING` 返回活动 `job_id`；未知或服务重启前的 job 返回 404。

本任务交付：

- `POST /api/update-checks`
- `GET /api/update-checks/{job_id}`

关键验收测试模拟十位候选中第十位失败，确认前九位保留、第十位无残留、返回 9/1，并且下一次只重试失败候选。

提交信息：`feat: add resilient discovery jobs`

### 任务 9：实现单人检查与 proposal APIs

创建：

- `backend/lab_tracker/services/diff.py`
- `backend/lab_tracker/services/updates.py`
- `backend/lab_tracker/api/update_proposals.py`
- `backend/tests/unit/test_diff.py`
- `backend/tests/integration/test_update_proposal_api.py`

实现与验证：

- scope=professor 有 pending proposal 时返回 409；否则至少刷新一次 Tavily 和 OpenAlex。
- 没有真实字段或论文差异时返回 `changed=false`，不创建 proposal。
- 有差异时只创建 pending proposal，不修改教授或申请记录。
- Apply 在一个事务中更新教授、替换论文、标记 applied；失败时完整回滚并保持 pending。
- Reject 只标记 rejected；两种已解决状态都拒绝重复操作。

本任务交付四个 endpoint：

- `GET /api/update-proposals`
- `GET /api/update-proposals/{proposal_id}`
- `POST /api/update-proposals/{proposal_id}/apply`
- `POST /api/update-proposals/{proposal_id}/reject`

提交信息：`feat: add professor update proposals`

### 任务 10：实现前端应用壳与教授列表页

创建：

- `frontend/src/api/client.js`
- `frontend/src/App.jsx`
- `frontend/src/assets/block-i.svg`
- `frontend/src/components/AppHeader.jsx`
- `frontend/src/components/ProfessorTable.jsx`
- `frontend/src/components/TagFilter.jsx`
- `frontend/src/components/StatusFilter.jsx`
- `frontend/src/components/Pagination.jsx`
- `frontend/src/pages/ProfessorListPage.jsx`
- `frontend/src/pages/ProfessorListPage.test.jsx`
- `frontend/src/styles.css`

实现与验证：

- 使用官方 Illinois Block I 资产并在 README 记录来源；不自行重绘或变形。
- 桌面教授表格显示姓名、title、email、lab link、tags、state，窄屏重排为卡片。
- 搜索、标签、状态、分页和 URL query state 调用后端 API。
- 无申请记录显示 `—`；链接使用安全的外部打开属性。
- loading、empty、API error 和键盘焦点状态都有测试。

提交信息：`feat: add professor list interface`

### 任务 11：实现教授详情与申请编辑

创建：

- `frontend/src/components/ApplicationForm.jsx`
- `frontend/src/components/PublicationList.jsx`
- `frontend/src/components/ResearchSummary.jsx`
- `frontend/src/pages/ProfessorDetailPage.jsx`
- `frontend/src/pages/ProfessorDetailPage.test.jsx`

实现与验证：

- 详情页显示完整教授资料、来源、最近检查时间、论文、申请状态、申请日期和笔记。
- 申请表单显式保存；删除申请记录后恢复空状态。
- 日期只包含 application date，不添加提醒或 follow-up date。
- pending proposal 时单人检查按钮替换为“查看待确认更新”。

提交信息：`feat: add professor details and applications`

### 任务 12：实现 job 反馈与 proposal 差异页

创建：

- `frontend/src/hooks/useUpdateJob.js`
- `frontend/src/components/JobNotice.jsx`
- `frontend/src/components/UpdateDiff.jsx`
- `frontend/src/pages/UpdateProposalPage.jsx`
- `frontend/src/hooks/useUpdateJob.test.js`
- `frontend/src/pages/UpdateProposalPage.test.jsx`

实现与验证：

- “Find new professors”运行时显示 Spinner 和文字、禁用按钮，不显示进度条或教授明细。
- `job_id` 保存到 sessionStorage；刷新恢复轮询，完成或 404 清理。
- 409 中存在活动 job ID 时恢复轮询，不重复创建任务。
- 成功、部分成功、无新增、全部单人失败和 job 级失败各显示一个简洁通知；added count 大于零时刷新列表。
- 差异页并排显示 current/proposed、论文差异、来源和 confidence，只能整体 Apply 或 Reject。

提交信息：`feat: add update job and proposal UI`

### 任务 13：完成端到端、生产构建与运行文档

创建或更新：

- `frontend/playwright.config.js`
- `frontend/e2e/catalog.spec.js`
- `frontend/e2e/discovery.spec.js`
- `frontend/e2e/update-proposal.spec.js`
- `backend/tests/integration/test_static_app.py`
- `backend/lab_tracker/main.py`
- `backend/lab_tracker/__main__.py`
- `README.md`

实现与验证：

- FastAPI 在生产模式托管 `frontend/dist`，API 路径优先，前端路由回退到 `index.html`。
- Playwright 使用 mock provider 或测试 fixture 覆盖列表、详情、申请、部分成功、proposal apply/reject。
- 验证 scope=new 不访问现有教授、串行处理、单教授事务和额度耗尽保留已提交数据。
- README 说明环境变量、免费额度风险、安装、开发运行、生产构建、单 worker 启动和数据库位置。
- 运行完整后端、前端、E2E 和 production smoke test。

最终验证：

```text
python -m pytest backend/tests
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
python -m lab_tracker
```

提交信息：`test: complete end-to-end tracker workflow`

## 5. REST API 实施映射

| Endpoint | 实施任务 |
|---|---:|
| `GET /api/health` | 4 |
| `GET /api/professors` | 4 |
| `GET /api/professors/{professor_id}` | 4 |
| `GET /api/tags` | 4 |
| `PUT /api/professors/{professor_id}/application` | 4 |
| `DELETE /api/professors/{professor_id}/application` | 4 |
| `POST /api/update-checks` | 8 |
| `GET /api/update-checks/{job_id}` | 8 |
| `GET /api/update-proposals` | 9 |
| `GET /api/update-proposals/{proposal_id}` | 9 |
| `POST /api/update-proposals/{proposal_id}/apply` | 9 |
| `POST /api/update-proposals/{proposal_id}/reject` | 9 |

## 6. 最终完成条件

实施只有在以下条件全部满足时完成：

- 四张表可由空数据库通过 migration 重建，所有 SQL 输入均参数绑定。
- 十二个 REST endpoint 的成功、校验错误、404 和 409 行为通过测试。
- UI 列表、详情、申请编辑、job 反馈和 proposal 差异流程全部可用。
- scope=new 不修改现有教授，严格串行，并以单教授事务支持部分成功。
- 单人检查只有经过用户 Apply 才修改教授与论文，永远不修改 application status。
- Research Agent 的调用预算、来源 ID、prompt-injection 防护和结构化输出约束通过测试。
- 默认测试套件完全离线；真实 provider 只在显式 live smoke test 中调用。
- 生产构建后可用一个单 worker Python 服务访问完整应用。
