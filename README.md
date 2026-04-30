# 智能开源项目评估 Agent 系统

### 项目介绍

智能开源项目评估 Agent 系统通过 AI Agent 解决开发者在技术选型、项目调研、开源项目质量判断中的真实痛点，整合 **项目解析、指标采集、RAG 知识检索、LLM-as-a-Judge 评估** 四大核心能力，实现对 GitHub 开源项目的自动化分析、核心指标推荐和结构化评估报告生成。系统能够降低人工调研成本，提升开源项目评估效率。

### 框架图

![workflow](.\pictures\workflow.jpg)

一个基于 LangGraph 的 multi-Agent 工作流系统。用户输入 GitHub 仓库地址后，Supervisor Agent 负责调度各个任务节点。首先 Project Parser Agent 提取项目基础信息，然后 Project Type Classifier Agent 判断项目属于哪类开源项目。接着 Metric Collector Agent 调用 GitHub API 和 OpenDigger API 获取指标数据。Core Metric Selector Agent 根据项目类型筛选关键指标。随后 RAG Retrieval Agent 从知识库中检索这些指标的定义和适用场景。最后 Evaluation Judge Agent 结合指标结果和定义生成评估报告，并由 Quality Guard Agent 做一致性检查。整个过程中的状态、缓存和历史报告信息都统一保存在 Redis 中。

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

