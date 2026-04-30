# 模块职责说明

本文档说明智能开源项目评估 Agent 系统中各个核心文件、工具模块、规则型 Agent、AI Agent、Prompt 和知识库的职责。

---

## 1. 模块分层总览

系统整体分为六层：

```text
API 层
→ app/main.py

决策层
→ app/graph.py

数据结构层
→ app/schemas.py

工具层
→ app/tools/

规则型 Agent 层
→ app/agents/

AI Agent 层
→ app/agents/ai_agents/

Prompt 与知识库
→ app/prompts/
→ knowledge_base/
```

这种分层的目的：

- API 层只负责接收请求和返回结果
- 工具层负责外部 API 和 Redis
- 规则型 Agent 负责稳定、确定性的处理逻辑
- AI Agent 负责调用 LLM 进行复杂语义生成
- LangGraph 负责统一调度整个工作流

## 2. API 层

### 2.1 `app/main.py`

`main.py` 是 FastAPI 后端入口。

主要职责：

```text
接收用户请求
→ 校验输入
→ 调用 LangGraph 工作流
→ 保存任务状态
→ 保存历史报告
→ 返回结构化 JSON 结果
```

当前提供的接口包括：

| 接口                      | 方法 | 作用                 |
| ------------------------- | ---- | -------------------- |
| `/health`                 | GET  | 健康检查             |
| `/evaluate`               | POST | 执行 GitHub 仓库评估 |
| `/tasks/{task_id}`        | GET  | 查询任务状态         |
| `/reports/recent`         | GET  | 查询最近历史报告     |
| `/reports/{owner}/{repo}` | GET  | 查询指定仓库历史报告 |

`main.py` 中处理的主要异常：

- 非法 GitHub URL
- GitHub 仓库不存在
- GitHub API 请求失败
- 整体评估流程失败
- Redis 保存历史报告失败

`main.py` 不负责具体业务分析逻辑，业务逻辑由 LangGraph 工作流和各个节点完成。

## 3. 决策层

### 3.1 `app/graph.py`

`graph.py` 是 LangGraph 工作流入口，也是当前系统的规则型 Supervisor 决策层。

主要职责：

```text
构建 LangGraph 工作流
→ 注册各个节点
→ 定义节点之间的执行顺序
→ 定义条件分支
→ 处理 Quality Guard 失败重试
→ 返回最终 EvaluationState
```

当前工作流：

```text
Project Parser
→ Type Classifier
→ Metric Collector
→ Metric Selector
→ RAG Retrieval
→ Rule Report Generator
→ LLM Report Generator
→ Quality Guard
→ END
```

当前 Supervisor 决策逻辑：

```text
每个关键节点执行后
→ 检查 state.errors
→ 如果有严重错误，提前结束
→ 如果没有错误，继续下一节点
```

Quality Guard 重试逻辑：

```text
Quality Guard 通过
→ END

Quality Guard 不通过 且 retry_count < 1
→ 回到 LLM Report Generator 重试

Quality Guard 不通过 且 retry_count >= 1
→ END
```

核心函数：

| 函数                              | 作用                                |
| --------------------------------- | ----------------------------------- |
| `build_graph()`                   | 构建 LangGraph 工作流               |
| `run_evaluation_graph(input_url)` | 执行完整评估流程                    |
| `_route_on_errors()`              | 根据 state.errors 判断是否继续      |
| `_route_after_llm_report()`       | 判断 LLM 报告生成后是否继续         |
| `_route_after_quality_guard()`    | 判断 Quality Guard 后是否重试或结束 |
| `prepare_quality_retry_node()`    | 重试前更新 retry_count              |

## 4. 数据结构层

### 4.1 `app/schemas.py`

`schemas.py` 定义系统中流转的核心数据结构，基于 Pydantic 实现。

主要职责：

```text
定义输入输出数据结构
→ 约束 Agent 节点输入输出
→ 约束 LLM 结构化报告格式
→ 约束 LangGraph 状态对象
```

核心数据结构：

| 类名               | 作用                                |
| ------------------ | ----------------------------------- |
| `RepoInput`        | GitHub URL 解析后的 owner/repo 结构 |
| `ProjectBasicInfo` | GitHub 仓库基础信息                 |
| `MetricBundle`     | GitHub + OpenDigger 原始指标集合    |
| `SelectedMetric`   | 筛选后的核心指标                    |
| `RetrievedDoc`     | RAG 检索到的知识片段                |
| `EvaluationReport` | 最终评估报告结构                    |
| `QualityResult`    | Quality Guard 检查结果              |
| `EvaluationState`  | LangGraph 全局状态对象              |

`EvaluationState` 是整个工作流最重要的状态对象。

核心字段：

| 字段                | 含义                       |
| ------------------- | -------------------------- |
| `input_url`         | 用户输入的 GitHub 仓库链接 |
| `owner`             | GitHub 仓库所属用户或组织  |
| `repo`              | GitHub 仓库名称            |
| `basic_info`        | GitHub 仓库基础信息        |
| `project_type`      | 项目类型                   |
| `raw_metrics`       | 原始指标数据               |
| `selected_metrics`  | 核心评估指标               |
| `retrieved_context` | RAG 检索结果               |
| `report`            | 当前报告                   |
| `quality_result`    | 质量检查结果               |
| `retry_count`       | Quality Guard 失败重试次数 |
| `errors`            | 错误和警告信息             |

## 5. 配置层

### 5.1 `app/config.py`

`config.py` 负责读取环境变量。

主要职责：

```text
读取 .env
→ 提供 GitHub Token
→ 提供 LLM API Key
→ 提供 Redis URL
→ 提供 LLM Provider 和模型名称
```

当前支持的配置包括：

| 配置项              | 作用                         |
| ------------------- | ---------------------------- |
| `GITHUB_TOKEN`      | GitHub API Token             |
| `ANTHROPIC_API_KEY` | Claude API Key，当前预留     |
| `OPENAI_API_KEY`    | OpenAI API Key，当前可选     |
| `DEEPSEEK_API_KEY`  | DeepSeek 或中转平台 Key      |
| `DEEPSEEK_BASE_URL` | DeepSeek 或中转平台 Base URL |
| `REDIS_URL`         | Redis 连接地址               |
| `LLM_PROVIDER`      | 当前使用的 LLM Provider      |
| `MODEL_NAME`        | 当前使用的模型名称           |

示例 `.env`：

```env
GITHUB_TOKEN=your_github_token

LLM_PROVIDER=deepseek
MODEL_NAME=your_model_name
DEEPSEEK_API_KEY=your_deepseek_or_proxy_key
DEEPSEEK_BASE_URL=your_deepseek_or_proxy_base_url

REDIS_URL=redis://localhost:6379/0
```

## 6. 工具层

工具层位于：

```text
app/tools/
```

工具层负责和外部服务交互，包括 GitHub、OpenDigger 和 Redis。

工具层的设计原则：

```text
外部 API 调用集中封装
缓存逻辑集中封装
错误转换集中封装
业务节点不直接写复杂请求逻辑
```

### 6.1 `app/tools/github_client.py`

`github_client.py` 负责 GitHub 仓库信息获取。

主要职责：

```text
解析 GitHub URL
→ 获取 owner/repo
→ 查询 Redis 缓存
→ 如果缓存存在，直接返回缓存
→ 如果缓存不存在，调用 GitHub API
→ 获取仓库基础信息
→ 保存结果到 Redis
```

当前获取字段：

- owner
- repo
- name
- description
- stars
- forks
- open issues
- language
- topics
- license
- README

主要函数：

| 函数                                  | 作用             |
| ------------------------------------- | ---------------- |
| `parse_github_url(url)`               | 解析 GitHub URL  |
| `get_readme(owner, repo)`             | 获取 README      |
| `get_project_basic_info(owner, repo)` | 获取仓库基础信息 |

自定义异常：

| 异常                      | 含义                 |
| ------------------------- | -------------------- |
| `GitHubRepoNotFoundError` | 仓库不存在或不可访问 |
| `GitHubAPIError`          | GitHub API 请求失败  |

缓存策略：

```text
GitHub 基础信息缓存 1 小时
```

Redis 不可用时：

```text
跳过缓存
继续请求 GitHub API
不影响主评估流程
```

### 6.2 `app/tools/opendigger_client.py`

`opendigger_client.py` 负责 OpenDigger 指标采集。

主要职责：

```text
读取 owner/repo
→ 查询 Redis 缓存
→ 如果缓存存在，直接返回缓存
→ 如果缓存不存在，并发请求 OpenDigger 指标
→ 保存结果到 Redis
```

当前采集指标：

- `openrank`
- `activity`
- `stars`
- `contributors`
- `new_contributors`
- `inactive_contributors`
- `bus_factor`
- `issues_new`
- `issues_closed`
- `issue_response_time`
- `issue_resolution_duration`
- `change_requests`
- `change_requests_accepted`
- `change_request_response_time`
- `change_request_resolution_duration`

主要函数：

| 函数                                              | 作用                     |
| ------------------------------------------------- | ------------------------ |
| `get_opendigger_metric(owner, repo, metric_name)` | 获取单个 OpenDigger 指标 |
| `get_opendigger_metric_bundle(owner, repo)`       | 获取一组 OpenDigger 指标 |

性能优化：

```text
OpenDigger 多个指标使用 ThreadPoolExecutor 并发请求
```

缓存策略：

```text
OpenDigger 指标缓存 6 小时
```

Redis 不可用时：

```text
跳过缓存
直接请求 OpenDigger
不影响主评估流程
```

### 6.3 `app/tools/redis_store.py`

`redis_store.py` 负责 Redis 存储。

主要职责：

```text
保存 JSON
读取 JSON
删除 Key
保存历史报告
读取历史报告
列出最近报告
保存任务状态
读取任务状态
```

当前支持三类能力：

### 6.3.1 指标缓存

用于缓存：

- GitHub 基础信息
- OpenDigger 指标

目的：

```text
减少重复 API 请求
降低 GitHub / OpenDigger 请求压力
提升重复评估速度
```

### 6.3.2 历史报告

支持：

- 保存某个仓库的最新评估报告
- 查询某个仓库的历史报告
- 查询最近评估报告列表

相关接口：

```text
GET /reports/recent
GET /reports/{owner}/{repo}
```

### 6.3.3 任务状态

支持根据 `task_id` 保存任务状态。

任务状态包含：

- input_url
- owner
- repo
- step
- status
- overall_score
- quality_passed
- history_saved
- errors

相关接口：

```text
GET /tasks/{task_id}
```

Redis 连接设置了短超时。

目的：

```text
Redis 不可用时快速失败
避免 Redis 阻塞主评估流程
```

## 7. 规则型 Agent 层

规则型 Agent 位于：

```text
app/agents/
```

这里的 Agent 是广义 Agent，指在 LangGraph 工作流中负责独立任务的节点。

这些节点主要依赖代码规则和工具调用，负责稳定、可控、确定性的处理逻辑。

规则型 Agent 的特点：

- 不依赖 LLM
- 输出更稳定
- 更容易调试
- 更适合处理结构化任务
- 可以作为 LLM 失败时的兜底基础

当前规则型 Agent 包括：

| 文件                  | 作用                               |
| --------------------- | ---------------------------------- |
| `project_parser.py`   | 解析 GitHub URL 并获取仓库基础信息 |
| `type_classifier.py`  | 根据项目信息判断项目类型           |
| `metric_collector.py` | 采集 GitHub 和 OpenDigger 指标     |
| `metric_selector.py`  | 根据项目类型筛选核心指标           |
| `rag_retrieval.py`    | 从本地知识库检索指标解释           |
| `report_generator.py` | 生成规则版 baseline 报告           |
| `quality_guard.py`    | 检查报告质量                       |

## 8. `app/agents/project_parser.py`

`project_parser.py` 负责项目解析。

它是整个评估流程的第一个业务节点。

### 8.1 输入

```text
EvaluationState.input_url
```

示例：

```text
https://github.com/langchain-ai/langgraph
```

### 8.2 工作流程

```text
读取 input_url
→ 调用 parse_github_url
→ 解析 owner/repo
→ 调用 get_project_basic_info
→ 获取 GitHub 仓库基础信息
→ 写入 state.owner
→ 写入 state.repo
→ 写入 state.basic_info
```

### 8.3 输出

更新后的 `EvaluationState`：

```text
state.owner
state.repo
state.basic_info
```

### 8.4 作用

这个节点负责把用户输入的 GitHub URL 转换成后续节点可以使用的结构化项目信息。

后续节点不会再直接解析 URL，而是使用这里写入的 `owner`、`repo` 和 `basic_info`。

## 9. `app/agents/type_classifier.py`

`type_classifier.py` 负责项目类型分类。

当前版本是规则型分类器。

### 9.1 输入

```text
state.basic_info
```

其中包含：

- name
- description
- language
- topics
- README

### 9.2 工作流程

```text
读取 state.basic_info
→ 提取 topics、description、README、language
→ 根据关键词规则判断项目类型
→ 写入 state.project_type
```

### 9.3 当前支持的项目类型

当前支持：

- AI Framework / Agent Framework
- SDK / Client Library
- Infrastructure
- Web / Backend Framework
- General Open Source Project

### 9.4 输出

```text
state.project_type
```

示例：

```text
AI Framework / Agent Framework
```

### 9.5 设计原因

项目类型会影响后续核心指标筛选。

例如：

- AI Framework 更关注 OpenRank、Activity、Contributors、Bus Factor
- SDK 更关注文档、版本稳定性、issue 响应
- Infrastructure 更关注维护稳定性、社区健康度和长期活跃度

当前使用规则分类，是为了保证稳定和可解释。

后续可以升级为：

```text
规则分类
+
LLM 辅助判断
```

## 10. `app/agents/metric_collector.py`

`metric_collector.py` 负责采集项目指标。

它会整合 GitHub 基础指标和 OpenDigger 指标，形成原始指标集合。

### 10.1 输入

```text
state.owner
state.repo
state.basic_info
```

### 10.2 工作流程

```text
读取 state.owner 和 state.repo
→ 从 state.basic_info 中整理 GitHub 基础指标
→ 调用 get_opendigger_metric_bundle
→ 获取 OpenDigger 指标
→ 合并 GitHub + OpenDigger 原始指标
→ 写入 state.raw_metrics
```

### 10.3 GitHub 基础指标

从 GitHub 获取并整理：

- stars
- forks
- open_issues
- language
- topics
- license
- readme_exists

### 10.4 OpenDigger 指标

从 OpenDigger 获取：

- openrank
- activity
- stars
- contributors
- new_contributors
- inactive_contributors
- bus_factor
- issues_new
- issues_closed
- issue_response_time
- issue_resolution_duration
- change_requests
- change_requests_accepted
- change_request_response_time
- change_request_resolution_duration

### 10.5 输出

```text
state.raw_metrics
```

其中包含：

```text
raw_metrics.github
raw_metrics.opendigger
raw_metrics.missing_metrics
```

### 10.6 设计原因

这个节点只负责采集和整理原始数据，不负责判断指标重要性，也不负责生成报告。

这样可以保证职责单一。

## 11. `app/agents/metric_selector.py`

`metric_selector.py` 负责核心指标筛选。

它不会重新采集数据，而是从 `state.raw_metrics` 中选择适合当前项目类型的关键指标。

### 11.1 输入

```text
state.project_type
state.raw_metrics
```

### 11.2 工作流程

```text
读取 state.project_type 和 state.raw_metrics
→ 根据项目类型选择核心评估指标
→ 从 OpenDigger 时间序列中提取最新指标值
→ 为每个指标添加来源和选择理由
→ 写入 state.selected_metrics
```

### 11.3 为什么需要指标筛选

原始指标很多，如果全部交给 LLM，会带来三个问题：

1. Prompt 变长，增加成本
2. 无关指标干扰报告生成
3. LLM 更容易抓不住重点

所以系统先做指标筛选，把原始数据转换成更适合报告生成的核心指标。

### 11.4 当前 AI Framework / Agent Framework 选择的指标

例如对于 AI Framework / Agent Framework，当前选择：

- stars
- forks
- open_issues
- license
- readme_exists
- openrank
- activity
- contributors
- bus_factor
- issue_response_time
- change_request_response_time

### 11.5 输出

```text
state.selected_metrics
```

每个指标结构包括：

```json
{
  "name": "openrank",
  "value": {
    "date": "2026Q1",
    "value": 73.58
  },
  "source": "opendigger",
  "reason": "OpenRank helps measure project influence in the open-source ecosystem."
}
```

### 11.6 设计原因

Metric Selector 是数据到报告之间的中间层。

它把大量原始指标转成一组可解释、可控、可展示的核心指标。

## 12. `app/agents/rag_retrieval.py`

`rag_retrieval.py` 负责当前版本的轻量 RAG 检索。

它根据核心指标，从本地知识库中查找对应的指标解释。

### 12.1 输入

```text
state.selected_metrics
```

### 12.2 工作流程

```text
读取 state.selected_metrics
→ 读取 knowledge_base/metrics.md
→ 根据指标名找到对应章节
→ 构造 RetrievedDoc
→ 写入 state.retrieved_context
```

### 12.3 当前检索方式

当前是轻量版 RAG，不使用向量数据库。

检索方式是：

```text
指标名
→ 指标标题映射
→ Markdown 章节匹配
→ 返回对应章节内容
```

例如：

```text
openrank → OpenRank
bus_factor → Bus Factor
issue_response_time → Issue Response Time
```

### 12.4 输出

```text
state.retrieved_context
```

每个检索结果结构：

```json
{
  "title": "OpenRank",
  "content": "OpenRank measures the influence of an open-source project...",
  "source": "knowledge_base/metrics.md"
}
```

### 12.5 设计原因

RAG Retrieval 的作用是让 LLM 报告不只依赖指标值，还能理解指标含义。

例如：

- OpenRank 为什么重要
- Bus Factor 有什么局限
- Issue Response Time 适合判断什么
- License 为什么影响采用安全性

### 12.6 后续升级方向

后续可以升级为完全版 RAG：

```text
多文档知识库
→ 文档切分
→ 本地索引
→ 相关 chunk 检索
→ 返回内容和来源
→ LLM 使用检索结果生成报告
```

## 13. `app/agents/report_generator.py`

`report_generator.py` 负责生成规则版 baseline 报告。

它不调用 LLM，而是根据固定规则计算分数并生成基础报告。

### 13.1 输入

```text
state.selected_metrics
state.project_type
state.owner
state.repo
```

### 13.2 工作流程

```text
读取 state.selected_metrics
→ 根据规则计算五个维度分数
→ 汇总 overall_score
→ 生成 summary
→ 生成 strengths
→ 生成 risks
→ 生成 suggestions
→ 写入 state.report
```

### 13.3 五个评分维度

当前评分维度：

- Popularity / Adoption
- Activity
- Maintainability
- Community Health
- Documentation & Governance

每个维度最高 20 分，总分最高 100 分。

### 13.4 输出

```text
state.report
```

结构为：

```text
EvaluationReport
```

包含：

- repo
- project_type
- overall_score
- dimension_scores
- summary
- strengths
- risks
- suggestions
- data_sources

### 13.5 设计原因

系统先生成规则版报告，再调用 LLM 增强报告。

这样做有三个好处：

1. LLM 失败时仍然有可用报告
2. LLM 不需要从零生成内容，减少幻觉
3. 规则版分数可以作为稳定参考

### 13.6 fallback 作用

如果 LLM Report Agent 失败，系统会保留这个规则版报告。

因此 `report_generator.py` 是整个系统稳定性的关键兜底节点。

## 14. `app/agents/quality_guard.py`

`quality_guard.py` 负责报告质量检查。

它是最终输出前的质量控制节点。

### 14.1 输入

```text
state.report
state.selected_metrics
```

### 14.2 工作流程

```text
读取 state.report 和 state.selected_metrics
→ 检查报告是否存在
→ 检查分数范围
→ 检查维度分数是否完整
→ 检查 summary / strengths / risks / suggestions
→ 检查 data_sources
→ 写入 state.quality_result
```

### 14.3 当前检查内容

当前 Quality Guard 检查：

- `overall_score` 是否在 0-100
- `dimension_scores` 是否包含所有必需维度
- 每个维度分数是否在 0-20
- `summary` 是否存在且长度合理
- `strengths` 是否为空
- `risks` 是否为空
- `suggestions` 是否为空
- `data_sources` 是否存在
- `selected_metrics` 是否存在

### 14.4 输出

```text
state.quality_result
```

结构：

```json
{
  "passed": true,
  "issues": [],
  "suggestions": [
    "Report passed basic quality checks."
  ]
}
```

### 14.5 和 Supervisor 的关系

Quality Guard 的结果会影响 Supervisor 路由。

```text
Quality Guard 通过
→ END

Quality Guard 不通过 且 retry_count < 1
→ 回到 LLM Report Generator 重试

Quality Guard 不通过 且 retry_count >= 1
→ END
```

### 14.6 当前局限

当前 Quality Guard 是规则检查，不能很好判断语义问题。

例如：

- 报告是否空泛
- 风险是否真的有指标支撑
- 是否误读了指标
- 是否存在自相矛盾

后续可以增加 `LLM Quality Reviewer` 来做语义级质量检查。

## 15. AI Agent 层

AI Agent 位于：

```text
app/agents/ai_agents/
```

当前项目中，AI Agent 指真正调用 LLM 的节点。

规则型 Agent 主要负责稳定、确定性的任务；AI Agent 主要负责复杂语义理解、自然语言生成和结构化报告增强。

当前已实现的 AI Agent：

| 文件                      | 作用                            |
| ------------------------- | ------------------------------- |
| `llm_report_generator.py` | 调用 LLM 生成最终结构化评估报告 |

后续可扩展的 AI Agent：

| 未来模块                  | 作用                                             |
| ------------------------- | ------------------------------------------------ |
| `llm_quality_reviewer.py` | 检查报告是否空泛、是否有无依据结论、是否误读指标 |
| `llm_type_classifier.py`  | 辅助项目类型判断                                 |
| `llm_metric_explainer.py` | 对指标进行更自然的解释和总结                     |

## 16. `app/agents/ai_agents/llm_report_generator.py`

`llm_report_generator.py` 是当前系统中的 LLM Report Agent。

它负责在规则版报告的基础上，结合 GitHub 数据、OpenDigger 指标、RAG 检索内容和 Prompt 模板，生成最终结构化评估报告。

### 16.1 输入

```text
state.basic_info
state.project_type
state.selected_metrics
state.retrieved_context
state.report
```

其中：

| 输入                      | 含义                 |
| ------------------------- | -------------------- |
| `state.basic_info`        | GitHub 仓库基础信息  |
| `state.project_type`      | 项目类型             |
| `state.selected_metrics`  | 筛选后的核心指标     |
| `state.retrieved_context` | RAG 检索到的指标解释 |
| `state.report`            | 规则版 baseline 报告 |

### 16.2 工作流程

```text
读取 state.basic_info
→ 读取 state.project_type
→ 读取 state.selected_metrics
→ 读取 state.retrieved_context
→ 读取规则版 state.report
→ 读取 app/prompts/llm_report_prompt.md
→ 填充 Prompt
→ 调用 LLM
→ 提取 LLM 返回中的 JSON
→ 校验为 EvaluationReport
→ 覆盖写入 state.report
```

### 16.3 输出

```text
state.report
```

输出结构为：

```text
EvaluationReport
```

包含：

- repo
- project_type
- overall_score
- dimension_scores
- summary
- strengths
- risks
- suggestions
- data_sources

### 16.4 支持的模型调用方式

当前通过 `langchain_openai.ChatOpenAI` 调用 OpenAI-compatible API。

当前支持：

- OpenAI
- DeepSeek
- DeepSeek 中转 API
- 其他兼容 OpenAI API 格式的平台

通过 `.env` 中的配置切换：

```env
LLM_PROVIDER=deepseek
MODEL_NAME=your_model_name
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=your_base_url
```

### 16.5 为什么使用 OpenAI-compatible Client

DeepSeek 支持 OpenAI-compatible API 格式，因此可以继续使用 `ChatOpenAI` 客户端。

这样做的好处是：

- 不需要为不同模型平台写多套调用逻辑
- 后续切换模型更简单
- LangChain 集成更方便
- Prompt 和输出解析逻辑可以复用

### 16.6 LLM 失败兜底

如果 LLM 调用失败，系统不会直接失败。

处理策略：

```text
保留规则版 report
→ 在 state.errors 中记录 LLM 失败原因
→ 继续进入 Quality Guard
→ 返回规则版报告
```

错误示例：

```text
LLM report generation failed: Unsupported LLM provider: unknown. Using rule-based report fallback.
```

### 16.7 设计原因

系统没有直接让 LLM 从零生成报告，而是采用：

```text
规则版 baseline 报告
→ LLM 增强报告
```

这样做的原因：

1. 规则版报告更稳定。
2. LLM 有明确参考，不容易跑偏。
3. LLM 失败时仍然可以返回可用结果。
4. Quality Guard 可以继续检查规则版报告。
5. 系统整体可用性更高。

## 17. `app/agents/ai_agents/llm_quality_reviewer.py`

`llm_quality_reviewer.py` 是语义质量审查 Agent。

它在规则版 `quality_guard.py` 之后执行，用于检查最终报告是否存在语义问题。

规则版 Quality Guard 主要检查：

```text
字段是否完整
分数是否越界
data_sources 是否存在
selected_metrics 是否为空
```

LLM Quality Reviewer 进一步检查：

```text
报告是否有指标依据
是否误读指标
是否存在过度推断
风险和建议是否匹配
结论是否前后矛盾
报告是否空泛
```

### 输入

```text
state.report
state.selected_metrics
state.retrieved_context
state.quality_result
```

### 工作流程

```text
读取最终报告
→ 读取 selected_metrics
→ 读取 retrieved_context
→ 读取规则版 quality_result
→ 填充 llm_quality_reviewer_prompt.md
→ 调用 LLM
→ 输出 QualityResult
→ 覆盖写入 state.quality_result
```

### 输出

```text
state.quality_result
```

示例：

```json
{
  "passed": false,
  "issues": [
    "The report overclaims that 15 days is fast response time without benchmark."
  ],
  "suggestions": [
    "Clarify the metric meaning and avoid calling it fast without comparison."
  ]
}
```

### 设计原因

规则版 Quality Guard 只能检查结构和字段，无法判断报告是否真正有依据。

LLM Quality Reviewer 用于补充语义级质量检查，帮助发现：

- 指标解释错误
- 结论缺少证据
- 风险描述空泛
- 建议和风险不匹配
- 报告前后矛盾

这让系统的质量控制从“格式检查”升级为“语义审查”。

## 18. Prompt 模板

Prompt 文件位于：

```text
app/prompts/
```

当前已实现两个 Prompt 文件：

```text
app/prompts/llm_report_prompt.md
app/prompts/llm_quality_reviewer_prompt.md
```

Prompt 没有直接写死在 Python 代码里，而是放到独立 Markdown 文件中。

这样做的好处：

- 代码更干净
- Prompt 更容易修改
- 不同 AI Agent 可以维护不同 Prompt
- 面试时更容易展示 Prompt 工程意识
- 后续可以做 Prompt 版本管理

---

### 18.1 `app/prompts/llm_report_prompt.md`

`llm_report_prompt.md` 给 LLM Report Agent 使用。

它的主要作用是要求 LLM 基于项目基础信息、项目类型、GitHub/OpenDigger 核心指标、RAG 检索内容和规则版报告，生成结构化 JSON 格式的开源项目评估报告。

#### 输入内容

Prompt 中会填入以下内容：

| 占位符                | 内容                 |
| --------------------- | -------------------- |
| `{basic_info}`        | GitHub 仓库基础信息  |
| `{project_type}`      | 项目类型             |
| `{selected_metrics}`  | 核心评估指标         |
| `{retrieved_context}` | RAG 检索到的指标解释 |
| `{rule_report}`       | 规则版 baseline 报告 |

#### 输出要求

Prompt 要求 LLM：

- 只返回 JSON
- 不返回 Markdown
- 不添加额外解释
- 不编造未提供的数据
- 不提及未提供的指标
- 分数必须在合法范围内
- `overall_score` 必须在 0-100
- 每个维度分数必须在 0-20
- `strengths`、`risks`、`suggestions` 必须具体且有指标依据

#### 目标输出结构

```json
{
  "repo": "owner/repo",
  "project_type": "string",
  "overall_score": 0,
  "dimension_scores": {
    "Popularity / Adoption": 0,
    "Activity": 0,
    "Maintainability": 0,
    "Community Health": 0,
    "Documentation & Governance": 0
  },
  "summary": "string",
  "strengths": ["string"],
  "risks": ["string"],
  "suggestions": ["string"],
  "data_sources": [
    "GitHub REST API",
    "OpenDigger",
    "Local Metric Knowledge Base"
  ]
}
```

#### 设计原因

系统没有让 LLM 从零生成报告，而是先生成规则版 baseline 报告，再让 LLM 基于真实指标和 RAG 内容进行增强。

这样做可以：

- 降低 LLM 幻觉风险
- 保证报告有真实指标依据
- 让 LLM 输出更稳定
- 在 LLM 失败时保留规则版报告作为 fallback
- 方便后续使用 Pydantic 校验结构化输出

---

### 18.2 `app/prompts/llm_quality_reviewer_prompt.md`

`llm_quality_reviewer_prompt.md` 给 LLM Quality Reviewer 使用。

它的主要作用是要求 LLM 对最终评估报告进行语义质量审查，判断报告是否有指标依据、是否误读指标、是否存在过度推断、风险和建议是否匹配。

#### 输入内容

Prompt 中会填入以下内容：

| 占位符                  | 内容                            |
| ----------------------- | ------------------------------- |
| `{selected_metrics}`    | 系统筛选出的核心指标            |
| `{retrieved_context}`   | RAG 检索到的指标解释            |
| `{rule_quality_result}` | 规则版 Quality Guard 的检查结果 |
| `{report}`              | 当前最终评估报告                |

#### 检查重点

LLM Quality Reviewer 会重点检查：

- `strengths` 是否有指标支撑
- `risks` 是否有指标支撑
- `suggestions` 是否和 `risks` 对应
- 是否正确解释 GitHub / OpenDigger 指标
- 是否出现无依据结论
- 是否存在前后矛盾
- 是否把弱证据过度解释成强结论
- 报告是否足够具体
- 报告是否对开发者技术选型有实际参考价值

#### 输出要求

Prompt 要求 LLM：

- 只返回 JSON
- 不返回 Markdown
- 不重写报告
- 不调用外部工具
- 不编造新事实
- 只基于给定的 `report`、`selected_metrics`、`retrieved_context` 和 `rule_quality_result` 做判断

#### 目标输出结构

```json
{
  "passed": true,
  "issues": [],
  "suggestions": []
}
```

#### 可以发现的问题示例

LLM Quality Reviewer 可以发现规则版 Quality Guard 难以发现的语义问题。

例如：

```text
报告把 quantile_4 的 15 days response time 直接解释成 fast response，这是过度推断。
```

或者：

```text
报告把较高的 bus_factor 解释成高风险，但实际上较高 bus_factor 通常表示对单个维护者的依赖风险较低。
```

再例如：

```text
报告给出的建议没有和具体风险或指标证据对应，导致建议不够有依据。
```

#### 设计原因

规则版 `quality_guard.py` 主要检查结构完整性，例如：

```text
字段是否完整
分数是否越界
data_sources 是否存在
selected_metrics 是否为空
```

但它无法判断报告是否存在语义问题。

`llm_quality_reviewer_prompt.md` 用于让 LLM 做语义级质量审查，补充检查：

```text
报告是否真正有依据
指标是否被正确解释
风险和建议是否匹配
结论是否前后一致
是否存在过度推断
```

这让系统的质量控制从“格式检查”升级为“语义审查”。

---

### 18.3 Prompt 设计总结

当前系统中的两个 Prompt 分工如下：

| Prompt 文件                      | 使用节点             | 作用                                      |
| -------------------------------- | -------------------- | ----------------------------------------- |
| `llm_report_prompt.md`           | LLM Report Agent     | 基于真实指标和 RAG 内容生成结构化评估报告 |
| `llm_quality_reviewer_prompt.md` | LLM Quality Reviewer | 对最终报告进行语义质量审查                |

整体设计思路是：

```text
LLM Report Agent
→ 负责生成报告

LLM Quality Reviewer
→ 负责审查报告
```

这种设计把“生成”和“审查”拆开，有助于降低 LLM 输出风险，也更接近真实 AI 应用中的 LLM-as-a-Judge 设计。

## 19. 知识库

知识库位于：

```text
knowledge_base/
```

当前已实现：

```text
knowledge_base/metrics.md
```

### 19.1 `knowledge_base/metrics.md`

`metrics.md` 是当前轻量 RAG 使用的本地知识库。

它保存了开源项目评估指标的定义、适用场景和局限性。

当前包含：

- OpenRank
- Activity
- Contributors
- Bus Factor
- Issue Response Time
- Issue Resolution Duration
- Change Request Response Time
- Stars
- Forks
- License

### 19.2 知识库的作用

知识库用于帮助 LLM 理解指标含义。

例如：

| 指标                         | 解释方向                        |
| ---------------------------- | ------------------------------- |
| OpenRank                     | 衡量项目在开源生态中的影响力    |
| Activity                     | 判断项目是否仍然活跃维护        |
| Contributors                 | 判断社区参与情况                |
| Bus Factor                   | 判断项目是否依赖少数维护者      |
| Issue Response Time          | 判断维护者响应用户问题的速度    |
| Change Request Response Time | 判断 PR review 效率和贡献者体验 |
| License                      | 判断项目是否适合安全采用        |

### 19.3 当前轻量 RAG 流程

```text
selected_metrics
→ 指标名映射为知识库标题
→ 从 metrics.md 中找到对应章节
→ 构造 RetrievedDoc
→ 写入 state.retrieved_context
→ LLM Report Agent 使用 retrieved_context
```

### 19.4 当前轻量 RAG 的优点

- 简单稳定
- 易于调试
- 不依赖向量数据库
- 适合 MVP 阶段
- 可以先跑通 RAG 到 LLM 的完整链路

### 19.5 当前轻量 RAG 的局限

- 只能按指标名匹配
- 不支持语义检索
- 不支持多文档排序
- 不支持复杂 query
- 不支持更细粒度 chunk 召回
- 知识库来源还不够丰富

### 19.6 后续完全版 RAG 计划

后续计划升级为：

```text
多文档知识库
→ Markdown 文档切分
→ 构建本地索引
→ 根据 project_type 和 selected_metrics 生成 query
→ 检索相关 chunk
→ 返回内容和来源
→ LLM 基于检索内容生成报告
```

完全版 RAG 可以进一步支持：

- 多个知识库文件
- 更细粒度文档切分
- 更灵活的检索 query
- 更清晰的来源追踪
- 更强的指标解释能力

## 20. 模块协作关系

一次完整评估中，各模块协作关系如下：

```text
app/main.py
接收 /evaluate 请求
↓
app/graph.py
启动 LangGraph 工作流
↓
project_parser.py
解析项目并获取 GitHub 基础信息
↓
type_classifier.py
判断项目类型
↓
metric_collector.py
采集 GitHub + OpenDigger 原始指标
↓
metric_selector.py
筛选核心指标
↓
rag_retrieval.py
检索指标知识
↓
report_generator.py
生成规则版 baseline 报告
↓
llm_report_generator.py
调用 LLM 生成最终报告
↓
quality_guard.py
检查报告质量
↓
app/main.py
保存历史报告和任务状态
↓
返回 JSON 结果
```

### 20.1 数据流转

核心数据通过 `EvaluationState` 传递。

```text
input_url
→ owner / repo
→ basic_info
→ project_type
→ raw_metrics
→ selected_metrics
→ retrieved_context
→ report
→ quality_result
→ API response
```

### 20.2 存储流转

Redis 主要参与三类存储：

```text
GitHub / OpenDigger 指标缓存
历史评估报告
任务状态
```

### 20.3 LLM 调用位置

当前系统只有一个节点真正调用 LLM：

```text
app/agents/ai_agents/llm_report_generator.py
```

其余节点主要依赖代码规则和外部工具，保证流程稳定。

## 21. 设计原则总结

### 21.1 规则优先，LLM 增强

系统尽量让确定性任务由规则和工具完成。

例如：

- URL 解析
- API 请求
- 指标采集
- 指标筛选
- 字段检查
- 分数范围检查

LLM 主要用于：

- 报告生成
- 指标含义综合解释
- 风险和建议生成

这样可以降低幻觉风险。

### 21.2 先 baseline，再 LLM

系统先生成规则版 baseline 报告，再让 LLM 进行增强。

好处：

- LLM 有明确参考
- 报告生成更稳定
- LLM 失败时有 fallback
- 方便 Quality Guard 检查

### 21.3 外部服务失败不影响主流程

Redis 是增强组件，不是主流程强依赖。

Redis 不可用时：

```text
缓存失效
历史报告不可保存
任务状态不可持久化
但主评估流程仍然可以返回报告
```

LLM 失败时：

```text
保留规则版报告
记录错误信息
继续返回可用结果
```

### 21.4 状态统一

所有节点通过 `EvaluationState` 传递状态。

好处：

- 输入输出统一
- 易于调试
- 易于接入 LangGraph
- 易于保存任务状态
- 易于 API 返回结构化结果

### 21.5 模块职责单一

每个模块只做一类事情：

- `github_client.py` 只处理 GitHub
- `opendigger_client.py` 只处理 OpenDigger
- `redis_store.py` 只处理 Redis
- `metric_collector.py` 只采集指标
- `metric_selector.py` 只筛选指标
- `report_generator.py` 只生成规则报告
- `llm_report_generator.py` 只调用 LLM 增强报告
- `quality_guard.py` 只做质量检查

这种设计便于维护、扩展和面试讲解。