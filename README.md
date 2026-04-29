# 面向开源项目评估的多智能体系统

### 框架图

![workflow](.\pictures\workflow.jpg)

一个基于 LangGraph 的 multi-Agent 工作流系统。用户输入 GitHub 仓库地址后，Supervisor Agent 负责调度各个任务节点。首先 Project Parser Agent 提取项目基础信息，然后 Project Type Classifier Agent 判断项目属于哪类开源项目。接着 Metric Collector Agent 调用 GitHub API 和 OpenDigger API 获取指标数据。Core Metric Selector Agent 根据项目类型筛选关键指标。随后 RAG Retrieval Agent 从知识库中检索这些指标的定义和适用场景。最后 Evaluation Judge Agent 结合指标结果和定义生成评估报告，并由 Quality Guard Agent 做一致性检查。整个过程中的状态、缓存和历史报告信息都统一保存在 Redis 中。

### 工具层

#### 1. app/tools/github_client.py

解析 GitHub 链接，获取真实的仓库信息

#### 2. app/tools/opendigger_client.py

获取 OpenDigger 的开源指标

### 规则型Agent层 —— 依赖代码进行逻辑处理

#### 1. app/agents/project_parser.py

输入 GitHub URL → 解析 owner/repo → 调用 GitHub Client 获取基础信息 → 把结果写入 state.owner、state.repo、state.basic_info

#### 2. app/agents/type_classifier.py

读取 state.basic_info → 根据 topics、description、README、language → 判断项目类型 → 写入 state.project_type

#### 3. app/agents/metric_collector.py

读取 state.owner 和 state.repo → 调用 OpenDigger → 整理 GitHub 基础指标 → 写入 state.raw_metrics

#### 4. app/agents/metric_selector.py

读取 state.project_type 和 state.raw_metrics → 根据项目类型选择核心评估指标 → 从 OpenDigger 时间序列中提取最新指标值 → 为每个指标添加来源和选择理由 → 写入 state.selected_metrics

#### 5. app/agents/report_generator.py

读取 selected_metrics → 根据规则计算各维度分数 → 生成结构化 EvaluationReport → 写入 state.report

#### 6. app/agents/quality_guard.py

读取 state.report 和 state.selected_metrics → 检查报告是否完整、分数是否合理、数据来源是否存在、是否缺少关键字段 → 把检查结果写入 state.quality_result

### 提示词

#### 1. app/prompts/llm_report_prompt.md

- 给 LLM Report Agent 使用
- 输入 GitHub/OpenDigger 指标、项目类型、规则版报告，要求 LLM 生成结构化 JSON 格式的开源项目评估报告

#### 2. 

### AI Agent层 —— 调用 LLM 进行复杂问题理解和处理

#### 1. app/agents/ai_agents/llm_report_generator.py

**利用 LLM 优化 report_generator 生成的报告**

读取 state.basic_info、state.project_type、state.selected_metrics 和规则版 state.report → 读取提示词模板 → 把项目基础信息、核心指标、规则版报告填入 Prompt → 调用 LLM 生成更自然、更完整的结构化评估报告 → 解析 LLM 返回的 JSON → 校验为 `EvaluationReport` → 覆盖写入 `state.report`

