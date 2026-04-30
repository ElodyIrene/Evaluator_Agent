# 智能开源项目评估 Agent 系统

### 项目介绍

智能开源项目评估 Agent 系统通过 AI Agent 解决开发者在技术选型、项目调研、开源项目质量判断中的真实痛点，整合 **项目解析、指标采集、RAG 知识检索、LLM-as-a-Judge 评估** 四大核心能力，实现对 GitHub 开源项目的自动化分析、核心指标推荐和结构化评估报告生成。系统能够降低人工调研成本，提升开源项目评估效率。

### 框架图

![workflow](.\pictures\workflow.jpg)

一个基于 LangGraph 的 multi-Agent 工作流系统。用户输入 GitHub 仓库地址后，Supervisor Agent 负责调度各个任务节点。首先 Project Parser Agent 提取项目基础信息，然后 Project Type Classifier Agent 判断项目属于哪类开源项目。接着 Metric Collector Agent 调用 GitHub API 和 OpenDigger API 获取指标数据。Core Metric Selector Agent 根据项目类型筛选关键指标。随后 RAG Retrieval Agent 从知识库中检索这些指标的定义和适用场景。最后 Evaluation Judge Agent 结合指标结果和定义生成评估报告，并由 Quality Guard Agent 做一致性检查。整个过程中的状态、缓存和历史报告信息都统一保存在 Redis 中。

### 决策层

#### 1. app/graph.py —— 规则型决策节点

根据 state.errors、state.report、quality_result 决定下一步行动

每一步执行后 → 检查 state.errors → 如果有严重错误，提前结束 → 如果没有错误，继续下一步

**重试机制**（retry_count：是否重试过）：Quality Guard 不通过时，自动重试一次 LLM Report

- Quality Guard 通过 → END
- Quality Guard 不通过 且 retry_count < 1 → 回到 LLM Report Generator 重试
- Quality Guard 不通过 且 retry_count >= 1 → END，返回带问题的报告



### 工具层

#### 1. app/tools/github_client.py

提供仓库信息获取能力

先查 Redis

- 如果有缓存 → 直接使用缓存

- 如果没有缓存 → 解析 GitHub 链接，获取真实的仓库信息


#### 2. app/tools/opendigger_client.py

提供开源指标结果获取能力

先查 Redis

- 如果有缓存 → 直接使用缓存

- 如果没有缓存 → 获取 OpenDigger 的开源指标


#### 3. app/tools/redis_store.py

提供 Redis 存储工具，用于保存和读取 JSON 数据。

支持：
- 缓存 GitHub / OpenDigger 指标结果，减少重复 API 请求。
- 保存和查询历史评估报告。
- 根据 task_id 保存和查询每次评估任务的执行状态，包括任务状态、当前步骤、评分结果、质量检查结果和错误信息。

### 规则型Agent层 —— 依赖代码进行稳定的逻辑处理

#### 1. app/agents/project_parser.py

输入 GitHub URL → 解析 owner/repo → 调用 GitHub Client 获取基础信息 → 把结果写入 state.owner、state.repo、state.basic_info

#### 2. app/agents/type_classifier.py

读取 state.basic_info → 根据 topics、description、README、language → 判断项目类型 → 写入 state.project_type

#### 3. app/agents/metric_collector.py

读取 state.owner 和 state.repo → 调用 OpenDigger → 整理 GitHub 基础指标 → 写入 state.raw_metrics

#### 4. app/agents/metric_selector.py

读取 state.project_type 和 state.raw_metrics → 根据项目类型选择核心评估指标 → 从 OpenDigger 时间序列中提取最新指标值 → 为每个指标添加来源和选择理由 → 写入 state.selected_metrics

#### 5. app/agents/rag_retrieval.py

读取 selected_metrics → 读取 knowledge_base/metrics.md → 根据指标名找到对应知识库章节 → 把指标解释写入 state.retrieved_context

#### 6. app/agents/report_generator.py

读取 selected_metrics → 根据规则计算各维度分数 → 生成结构化 EvaluationReport → 写入 state.report

#### 7. app/agents/quality_guard.py

读取 state.report 和 state.selected_metrics → 检查报告是否完整、分数是否合理、数据来源是否存在、是否缺少关键字段 → 把检查结果写入 state.quality_result

### 提示词

#### 1. app/prompts/llm_report_prompt.md

- 给 LLM Report Agent 使用
- 输入 项目基础信息、项目类型、GitHub/OpenDigger 核心指标、RAG 检索得到的指标解释、规则版报告，要求 LLM 生成结构化 JSON 格式的开源项目评估报告

### AI Agent层 —— 调用 LLM 进行复杂问题理解和处理

#### 1. app/agents/ai_agents/llm_report_generator.py

**利用 LLM 优化 report_generator 生成的报告**

读取 state.basic_info、state.project_type、state.selected_metrics 和规则版 state.report → 读取提示词模板 → 把

- 项目基础信息
- 核心指标及结果
- 本地指标知识库指标解释
- 规则版报告

填入 Prompt → 调用 LLM 生成更自然、更完整的结构化评估报告 → 解析 LLM 返回的 JSON → 校验为 `EvaluationReport` → 覆盖写入 `state.report`

### 知识库

#### 1. knowledge_base/metrics.md (RAG DEMO)

- 给 RAG Retrieval Agent 使用。
- 保存 openrank、activity、bus_factor、issue_response_time 等指标的定义、适用场景和局限性。
- LLM 生成报告时，可以引用这些解释，让报告更可解释。

### 异常处理

#### 1. 传入非法地址

处理位置：app/main.py

```
{
  "status": "failed",
  "error_type": "invalid_github_url",
  "message": "Invalid GitHub repository URL. Example: XXX"
}
```

#### 2. GitHub 仓库不存在

处理位置：app/main.py、app/tools/github_client.py

```
{
  "status": "failed",
  "error_type": "github_repo_not_found",
  "message": "GitHub repository not found or not accessible"
}
```

#### 3. LLM 生成报告失败

**返回规则版报告**

处理位置：app/agents/ai_agents/llm_report_generator.py

```
errors: ['LLM report generation failed: Unsupported LLM provider: XXX. Using rule-based report fallback.']
```

#### 4. Redis 不可用

**主评估流程不崩溃，只有保存缓存、历史报告、任务状态的功能不可用**

Redis 不可用时，系统会降级为无缓存、无历史记录、无任务状态持久化，但仍然可以完成仓库评估并返回报告

处理位置：app/main.py、app/tools/redis_store.py、app/tools/github_client.py、app/tools/opendigger_client.py

```
errors: ['Failed to save report history: Error 10061 connecting to localhost:6379.']
```

### 遇到的问题

#### 1. 禁用Redis后评估流程响应时间较长

- **3 次平均响应时长 218.82 秒 → 并行优化后耗时 85.50 秒 → 短超时优化后耗时 41.42 秒，减少了约 81% 时间**
- Redis 正常 + 缓存可用：约 17.1 秒 (主要是 LLM 生成报告的耗时)
- **原因**：Redis 停止后缓存失效，OpenDigger 15 个指标变成串行网络请求；每次缓存读取/写入都要先等待失败
- **解决方案**：OpenDigger 指标从串行请求变为并发请求 + 通过短超时给 Redis 设置快速失败机制
- 增加多次评估同一仓库可选择复用之前的 LLM 报告机制，Redis 命中后耗时大约 0.03秒

#### 2. 

### 输出结构

```
{
  "task_id": "本次评估任务的唯一 ID，用于查询任务状态、Redis 保存任务执行状态和排查问题。",
  "status": "本次接口调用状态。completed 表示评估成功完成，failed 表示评估失败。",
  "cache_hit": "是否命中历史报告缓存。true 表示直接从 Redis 读取历史报告，false 表示重新执行完整评估流程。",

  "owner": "GitHub 仓库所属用户或组织名，例如 langchain-ai。",
  "repo": "GitHub 仓库名称，例如 langgraph。",
  "project_type": "系统判断出的项目类型，例如 AI Framework / Agent Framework。",

  "overall_score": "项目总评分，范围通常是 0 到 100，用于表示整体开源项目健康度。",
  "dimension_scores": {
    "description": "五个评估维度的分数，每个维度通常是 0 到 20 分，五项相加得到 overall_score。",
    "Popularity / Adoption": "项目受欢迎程度和采用度评分，主要参考 stars、forks、OpenRank 等指标。",
    "Activity": "项目活跃度评分，主要参考 OpenDigger activity、近期维护情况等指标。",
    "Maintainability": "项目可维护性评分，主要参考 open issues、issue response time、PR response time 等指标。",
    "Community Health": "社区健康度评分，主要参考 contributors、bus_factor、贡献者活跃情况等指标。",
    "Documentation & Governance": "文档与治理评分，主要参考 README、license、文档完整性和治理信号。"
  },

  "summary": "项目整体评估摘要，用简短文字总结项目的健康度、优势和主要风险。",
  "strengths": "项目优势列表，通常结合具体指标说明项目在哪些方面表现较好。",
  "risks": "项目风险列表，通常指出维护压力、贡献者集中、issue backlog 等潜在问题。",
  "suggestions": "改进建议列表，针对 risks 给出可执行的优化方向。",
  "data_sources": "报告使用的数据来源列表，例如 GitHub REST API、OpenDigger、Local Metric Knowledge Base。",

  "selected_metrics": {
    "description": "系统筛选出的核心评估指标列表，由 metric_selector.py 生成，供报告生成和 LLM 分析使用。",
    "name": "指标名称，例如 stars、forks、openrank、activity、bus_factor。",
    "value": "指标值，可以是数字、字符串、布尔值或包含 date/value 的对象。",
    "source": "指标来源，例如 github 或 opendigger。",
    "reason": "选择该指标的原因，用于解释它为什么对项目评估重要。"
  },

  "retrieved_context_count": "RAG 检索到的知识片段数量，用于表示本次报告生成参考了多少条本地知识库内容。",
  "retry_count": "Supervisor 触发质量重试的次数。0 表示一次通过，1 表示 Quality Guard 失败后重试过一次。",

  "quality_result": {
    "description": "Quality Guard 对最终报告的质量检查结果。",
    "passed": "报告是否通过质量检查。true 表示通过，false 表示未通过。",
    "issues": "质量检查发现的问题列表，例如缺少字段、分数越界、数据来源缺失等。",
    "suggestions": "Quality Guard 给出的修正建议。"
  },

  "history_saved": "本次评估报告是否成功保存到 Redis 历史报告中。true 表示保存成功，false 表示保存失败或未保存。",
  "errors": "本次评估流程中产生的错误或警告列表。正常情况下为空数组。"
}
```

