# 系统架构说明

本文档说明智能开源项目评估 Agent 系统的整体架构、LangGraph 工作流、Supervisor 条件分支和质量检查重试机制。

---

## 1. 架构目标

本系统的目标是构建一个后端 AI 应用，用于自动评估 GitHub 开源项目的健康度。

用户输入 GitHub 仓库链接后，系统会自动完成：

```text
仓库解析
→ 项目信息采集
→ 开源指标采集
→ 核心指标筛选
→ RAG 指标解释
→ 规则版报告生成
→ LLM 报告生成
→ Quality Guard 检查
→ 返回结构化评估报告
```

系统设计重点包括：

- 用 LangGraph 编排多节点工作流
- 用规则节点处理稳定、确定性的任务
- 用 LLM Agent 处理复杂语义生成任务
- 用 RAG 提供指标解释上下文
- 用 Redis 做缓存、历史报告和任务状态管理
- 用 Quality Guard 控制最终报告质量
- 用异常处理和 fallback 提升系统稳定性

## 2. 整体架构图

![workflow](../pictures/workflow.jpg)

整体架构可以分为六层：

```text
API 层
→ FastAPI

决策层
→ LangGraph + Supervisor 条件分支

工具层
→ GitHub API、OpenDigger API、Redis

规则型 Agent 层
→ 项目解析、类型判断、指标采集、指标筛选、RAG 检索、规则报告、质量检查

AI Agent 层
→ LLM Report Agent

知识库层
→ knowledge_base/metrics.md
```

当前系统实现的是一个 backend-only MVP，没有前端页面。所有能力通过 FastAPI 接口和 Swagger 文档进行演示。

## 3. 主工作流

当前 LangGraph 主工作流如下：

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

对应文件：

| 工作流节点            | 对应文件                                       | 作用                              |
| --------------------- | ---------------------------------------------- | --------------------------------- |
| Project Parser        | `app/agents/project_parser.py`                 | 解析 GitHub URL，获取仓库基础信息 |
| Type Classifier       | `app/agents/type_classifier.py`                | 判断项目类型                      |
| Metric Collector      | `app/agents/metric_collector.py`               | 采集 GitHub 和 OpenDigger 指标    |
| Metric Selector       | `app/agents/metric_selector.py`                | 根据项目类型筛选核心指标          |
| RAG Retrieval         | `app/agents/rag_retrieval.py`                  | 从知识库检索指标解释              |
| Rule Report Generator | `app/agents/report_generator.py`               | 生成规则版 baseline 报告          |
| LLM Report Generator  | `app/agents/ai_agents/llm_report_generator.py` | 调用 LLM 生成最终报告             |
| Quality Guard         | `app/agents/quality_guard.py`                  | 检查报告质量                      |

## 4. 为什么拆成多个节点

本项目没有把所有逻辑放进一个大 Agent，而是拆成多个职责清晰的节点。

原因是：

1. **可控性更强**

   GitHub URL 解析、API 请求、指标筛选、质量检查这些任务不需要 LLM，使用规则和工具更稳定。

2. **可调试性更好**

   每个节点输入输出明确，出问题时更容易定位。

3. **降低 LLM 幻觉风险**

   数据采集由工具完成，LLM 只基于已有数据生成报告，不负责编造指标。

4. **方便扩展**

   后续可以单独升级 RAG、Quality Guard、项目分类器或报告生成器，而不用重写整个系统。

5. **符合真实后端工程习惯**

   将 API 层、工具层、业务节点、AI Agent、存储层拆开，有利于维护和展示工程能力。

## 5. 规则型 Agent 与 AI Agent 的区分

本项目中，“Agent”分为两类。

### 5.1 规则型 Agent / 工作流节点

规则型 Agent 是广义 Agent，主要指在工作流中负责某个独立任务的节点。

它们通常不调用 LLM，而是依赖代码规则和外部工具。

例如：

- `project_parser.py`
- `type_classifier.py`
- `metric_collector.py`
- `metric_selector.py`
- `rag_retrieval.py`
- `report_generator.py`
- `quality_guard.py`

这些节点负责稳定、可控、确定性的工作。

### 5.2 AI Agent / LLM-driven Agent

AI Agent 指真正调用大模型进行复杂语义处理的节点。

当前实现：

- `app/agents/ai_agents/llm_report_generator.py`

它负责结合 GitHub 数据、OpenDigger 指标、RAG 检索内容和规则版报告，生成最终结构化评估报告。

### 5.3 为什么这样设计

系统没有把所有任务都交给 LLM，而是采用：

```text
确定性任务 → 规则和工具
语义生成任务 → LLM
```

这样可以在稳定性和智能化之间取得平衡。

## 6. Supervisor 条件分支

当前 `app/graph.py` 中实现了规则型 Supervisor 决策逻辑。

它不是完整的 Plan-and-Executor，而是：

```text
固定主流程
+
条件分支
+
失败兜底
+
质量重试
```

### 6.1 错误提前结束

每个关键节点执行后都会检查 `state.errors`。

```text
如果 state.errors 为空
→ 继续执行下一节点

如果 state.errors 不为空
→ 提前结束流程
```

这样可以避免前置步骤已经失败时，后续节点继续执行无意义操作。

### 6.2 LLM 失败兜底

LLM Report Agent 失败时，系统不会直接失败。

因为在调用 LLM 之前，系统已经生成了规则版报告。

流程是：

```text
Rule Report Generator
→ 生成规则版 baseline 报告
→ LLM Report Generator 尝试增强报告
→ 如果 LLM 失败，保留规则版报告
→ 继续进入 Quality Guard
```

这样可以保证 LLM 异常时系统仍然返回可用报告。

### 6.3 Quality Guard 失败重试

Quality Guard 检查失败时，Supervisor 会允许重试一次 LLM Report Agent。

```text
Quality Guard 通过
→ END

Quality Guard 不通过 且 retry_count < 1
→ 回到 LLM Report Generator 重试

Quality Guard 不通过 且 retry_count >= 1
→ END，返回带问题的报告
```

当前最大重试次数：

```text
1 次
```

对应状态字段：

```text
retry_count
```

## 7. 状态对象 EvaluationState

LangGraph 工作流中，各节点通过 `EvaluationState` 传递状态。

核心字段包括：

| 字段                | 含义                         |
| ------------------- | ---------------------------- |
| `input_url`         | 用户输入的 GitHub 仓库链接   |
| `owner`             | GitHub 仓库所属用户或组织    |
| `repo`              | GitHub 仓库名称              |
| `basic_info`        | GitHub 仓库基础信息          |
| `project_type`      | 项目类型                     |
| `raw_metrics`       | GitHub + OpenDigger 原始指标 |
| `selected_metrics`  | 筛选后的核心指标             |
| `retrieved_context` | RAG 检索到的指标解释内容     |
| `report`            | 当前评估报告                 |
| `quality_result`    | Quality Guard 检查结果       |
| `retry_count`       | Quality Guard 失败后重试次数 |
| `errors`            | 工作流中的错误或警告         |

这种统一状态设计的好处是：

- 各节点输入输出一致
- 方便 LangGraph 编排
- 方便 Redis 保存任务状态
- 方便 API 返回结构化结果
