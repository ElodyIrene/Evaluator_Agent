# API 接口说明

本文档说明智能开源项目评估 Agent 系统当前提供的后端 API。

系统基于 FastAPI 实现，启动后可以通过 Swagger 页面查看和调试接口。

接口文档地址：

```text
http://127.0.0.1:8000/docs
```

---

## 1. API 总览

当前提供的接口如下：

| 接口                      | 方法 | 作用                 |
| ------------------------- | ---- | -------------------- |
| `/health`                 | GET  | 健康检查             |
| `/evaluate`               | POST | 执行 GitHub 仓库评估 |
| `/tasks/{task_id}`        | GET  | 查询任务状态         |
| `/reports/recent`         | GET  | 查询最近历史报告     |
| `/reports/{owner}/{repo}` | GET  | 查询指定仓库历史报告 |

---

## 2. 通用返回说明

系统主要返回 JSON。

正常情况下，核心状态字段为：

```json
{
  "status": "completed",
  "errors": []
}
```

异常情况下，通常返回：

```json
{
  "status": "failed",
  "error_type": "xxx",
  "message": "错误说明"
}
```

其中：

| 字段         | 含义                                           |
| ------------ | ---------------------------------------------- |
| `status`     | 当前请求状态，常见值为 `completed` 或 `failed` |
| `errors`     | 流程中的错误或警告列表                         |
| `error_type` | 失败类型                                       |
| `message`    | 面向调用方的错误说明                           |

## 3. 健康检查接口

### 3.1 接口

```text
GET /health
```

### 3.2 作用

用于检查 FastAPI 服务是否正常启动。

### 3.3 请求参数

无。

### 3.4 返回示例

```json
{
  "status": "ok"
}
```

### 3.5 字段说明

| 字段     | 含义                            |
| -------- | ------------------------------- |
| `status` | 服务状态。`ok` 表示服务正常运行 |

## 4. 仓库评估接口

### 4.1 接口

```text
POST /evaluate
```

### 4.2 作用

对指定 GitHub 仓库执行完整评估流程。

完整流程包括：

```text
GitHub URL 解析
→ GitHub 基础信息采集
→ OpenDigger 指标采集
→ 项目类型判断
→ 核心指标筛选
→ RAG 指标解释
→ 规则版报告生成
→ LLM 报告生成
→ Quality Guard 检查
→ Redis 保存历史报告和任务状态
→ 返回结构化评估结果
```

### 4.3 请求体

```json
{
  "url": "https://github.com/langchain-ai/langgraph",
  "use_cached_report": false
}
```

### 4.4 请求字段说明

| 字段                | 类型    | 必填 | 含义                                          |
| ------------------- | ------- | ---- | --------------------------------------------- |
| `url`               | string  | 是   | GitHub 仓库链接                               |
| `use_cached_report` | boolean | 否   | 是否优先复用 Redis 中的历史报告，默认 `false` |

### 4.5 `use_cached_report` 说明

当 `use_cached_report=false` 时：

```text
系统会重新执行完整评估流程。
```

当 `use_cached_report=true` 时：

```text
系统会先查询 Redis 中是否已有该仓库的历史报告。
如果命中缓存，则直接返回历史报告。
如果没有缓存，则继续执行完整评估流程。
```

适用场景：

| 模式                      | 适用场景                       |
| ------------------------- | ------------------------------ |
| `use_cached_report=false` | 想重新评估，获取尽可能新的结果 |
| `use_cached_report=true`  | Demo、重复查询、低延迟返回     |

## 5. `/evaluate` 正常返回示例

### 5.1 完整评估模式返回示例

请求：

```json
{
  "url": "https://github.com/langchain-ai/langgraph",
  "use_cached_report": false
}
```

返回示例：

```json
{
  "task_id": "a6092da6-4970-434e-b784-1d9d3fda195b",
  "status": "completed",
  "cache_hit": false,
  "owner": "langchain-ai",
  "repo": "langgraph",
  "project_type": "AI Framework / Agent Framework",
  "overall_score": 85,
  "dimension_scores": {
    "Popularity / Adoption": 20,
    "Activity": 20,
    "Maintainability": 15,
    "Community Health": 10,
    "Documentation & Governance": 20
  },
  "summary": "langgraph is a highly popular and actively maintained AI agent framework...",
  "strengths": [
    "Exceptional popularity with high stars and forks."
  ],
  "risks": [
    "Low contributor count may indicate sustainability risk."
  ],
  "suggestions": [
    "Increase contributor engagement and improve issue triage."
  ],
  "data_sources": [
    "GitHub REST API",
    "OpenDigger",
    "Local Metric Knowledge Base"
  ],
  "selected_metrics": [
    {
      "name": "stars",
      "value": 30856,
      "source": "github",
      "reason": "Stars show basic popularity and community attention."
    }
  ],
  "retrieved_context_count": 9,
  "retry_count": 0,
  "quality_result": {
    "passed": true,
    "issues": [],
    "suggestions": [
      "Report passed basic quality checks."
    ]
  },
  "history_saved": true,
  "errors": []
}
```

### 5.2 历史报告缓存模式返回示例

请求：

```json
{
  "url": "https://github.com/langchain-ai/langgraph",
  "use_cached_report": true
}
```

如果 Redis 中已经保存过该仓库报告，返回示例：

```json
{
  "task_id": "xxx",
  "status": "completed",
  "cache_hit": true,
  "owner": "langchain-ai",
  "repo": "langgraph",
  "project_type": "AI Framework / Agent Framework",
  "overall_score": 85,
  "dimension_scores": {
    "Popularity / Adoption": 20,
    "Activity": 20,
    "Maintainability": 15,
    "Community Health": 10,
    "Documentation & Governance": 20
  },
  "summary": "...",
  "strengths": [],
  "risks": [],
  "suggestions": [],
  "data_sources": [
    "GitHub REST API",
    "OpenDigger",
    "Local Metric Knowledge Base"
  ],
  "selected_metrics": [],
  "retrieved_context_count": 0,
  "retry_count": null,
  "quality_result": null,
  "history_saved": false,
  "cached_saved_at": "2026-04-30T00:00:00+00:00",
  "errors": []
}
```

### 5.3 缓存模式说明

当 `cache_hit=true` 时，系统没有重新执行完整 LangGraph 流程。

因此以下字段可能为空或为默认值：

| 字段                      | 原因                                            |
| ------------------------- | ----------------------------------------------- |
| `selected_metrics`        | 缓存模式直接返回历史报告，不重新筛选指标        |
| `retrieved_context_count` | 缓存模式不重新执行 RAG                          |
| `retry_count`             | 缓存模式不重新执行 Quality Guard 重试           |
| `quality_result`          | 当前缓存中只保存 report，不保存完整质量检查结果 |
| `history_saved`           | 缓存命中时不会再次保存历史报告                  |

## 6. `/evaluate` 输出字段说明

```json
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
  "cached_saved_at": "历史报告缓存的保存时间。仅 cache_hit=true 时通常会出现。",
  "errors": "本次评估流程中产生的错误或警告列表。正常情况下为空数组。"
}
```

## 7. 查询任务状态接口

### 7.1 接口

```text
GET /tasks/{task_id}
```

### 7.2 作用

根据 `task_id` 查询一次评估任务的执行状态。

### 7.3 请求示例

```text
GET /tasks/a6092da6-4970-434e-b784-1d9d3fda195b
```

### 7.4 返回示例

```json
{
  "found": true,
  "task_id": "a6092da6-4970-434e-b784-1d9d3fda195b",
  "task_state": {
    "task_id": "a6092da6-4970-434e-b784-1d9d3fda195b",
    "saved_at": "2026-04-30T00:00:00+00:00",
    "state": {
      "input_url": "https://github.com/langchain-ai/langgraph",
      "owner": "langchain-ai",
      "repo": "langgraph",
      "project_type": "AI Framework / Agent Framework",
      "step": "completed",
      "status": "completed",
      "cache_hit": false,
      "overall_score": 85,
      "quality_passed": true,
      "history_saved": true,
      "errors": []
    }
  }
}
```

### 7.5 字段说明

| 字段                              | 含义                   |
| --------------------------------- | ---------------------- |
| `found`                           | 是否找到该任务状态     |
| `task_id`                         | 任务 ID                |
| `task_state.saved_at`             | 状态保存时间           |
| `task_state.state.step`           | 当前任务步骤           |
| `task_state.state.status`         | 当前任务状态           |
| `task_state.state.quality_passed` | Quality Guard 是否通过 |
| `task_state.state.errors`         | 任务执行中的错误或警告 |

### 7.6 未找到任务示例

```json
{
  "found": false,
  "task_id": "not-exist",
  "task_state": null
}
```

## 8. 查询最近历史报告接口

### 8.1 接口

```text
GET /reports/recent
```

### 8.2 作用

查询 Redis 中最近保存的评估报告。

### 8.3 请求参数

| 参数    | 类型    | 必填 | 默认值 | 含义               |
| ------- | ------- | ---- | ------ | ------------------ |
| `limit` | integer | 否   | 10     | 返回最近多少条报告 |

### 8.4 请求示例

```text
GET /reports/recent?limit=5
```

### 8.5 返回示例

```json
{
  "count": 2,
  "reports": [
    {
      "owner": "langchain-ai",
      "repo": "langgraph",
      "saved_at": "2026-04-30T00:00:00+00:00",
      "report": {
        "repo": "langchain-ai/langgraph",
        "project_type": "AI Framework / Agent Framework",
        "overall_score": 85,
        "summary": "..."
      }
    }
  ]
}
```

---

## 9. 查询指定仓库历史报告接口

### 9.1 接口

```text
GET /reports/{owner}/{repo}
```

### 9.2 作用

查询某个 GitHub 仓库最近一次保存的历史评估报告。

### 9.3 请求示例

```text
GET /reports/langchain-ai/langgraph
```

### 9.4 返回示例

```json
{
  "found": true,
  "owner": "langchain-ai",
  "repo": "langgraph",
  "report": {
    "owner": "langchain-ai",
    "repo": "langgraph",
    "saved_at": "2026-04-30T00:00:00+00:00",
    "report": {
      "repo": "langchain-ai/langgraph",
      "project_type": "AI Framework / Agent Framework",
      "overall_score": 85,
      "summary": "..."
    }
  }
}
```

### 9.5 未找到报告示例

```json
{
  "found": false,
  "owner": "langchain-ai",
  "repo": "not-exist",
  "report": null
}
```

## 10. 异常返回

### 10.1 非法 GitHub URL

请求示例：

```json
{
  "url": "abc",
  "use_cached_report": false
}
```

返回示例：

```json
{
  "task_id": "xxx",
  "status": "failed",
  "error_type": "invalid_github_url",
  "message": "Invalid GitHub repository URL. Example: https://github.com/langchain-ai/langgraph"
}
```

### 10.2 GitHub 仓库不存在

请求示例：

```json
{
  "url": "https://github.com/this-repo-does-not-exist-xyz/abc",
  "use_cached_report": false
}
```

返回示例：

```json
{
  "task_id": "xxx",
  "status": "failed",
  "error_type": "github_repo_not_found",
  "message": "GitHub repository not found or not accessible: this-repo-does-not-exist-xyz/abc"
}
```

### 10.3 GitHub API 请求失败

返回示例：

```json
{
  "task_id": "xxx",
  "status": "failed",
  "error_type": "github_api_error",
  "message": "GitHub API request failed..."
}
```

### 10.4 整体评估失败

返回示例：

```json
{
  "task_id": "xxx",
  "status": "failed",
  "error_type": "evaluation_failed",
  "message": "error message"
}
```

### 10.5 LLM 失败但规则报告兜底

LLM 失败时不一定返回 `failed`。

如果规则版报告已经生成，系统会继续返回报告，并在 `errors` 中记录：

```json
{
  "status": "completed",
  "errors": [
    "LLM report generation failed: Unsupported LLM provider: unknown. Using rule-based report fallback."
  ]
}
```

### 10.6 Redis 不可用但主流程继续

Redis 不可用时，主评估流程不失败。

可能返回：

```json
{
  "status": "completed",
  "history_saved": false,
  "errors": [
    "Failed to save report history: Error 10061 connecting to localhost:6379."
  ]
}
```

## 11. 调试建议

### 11.1 正常评估

使用：

```json
{
  "url": "https://github.com/langchain-ai/langgraph",
  "use_cached_report": false
}
```

检查：

```text
status = completed
cache_hit = false
quality_result.passed = true
errors = []
```

### 11.2 缓存报告模式

使用：

```json
{
  "url": "https://github.com/langchain-ai/langgraph",
  "use_cached_report": true
}
```

检查：

```text
cache_hit = true
```

### 11.3 非法 URL

使用：

```json
{
  "url": "abc",
  "use_cached_report": false
}
```

检查：

```text
status = failed
error_type = invalid_github_url
```

### 11.4 仓库不存在

使用：

```json
{
  "url": "https://github.com/this-repo-does-not-exist-xyz/abc",
  "use_cached_report": false
}
```

检查：

```text
status = failed
error_type = github_repo_not_found
```

### 11.5 任务状态

执行 `/evaluate` 后复制返回的 `task_id`，调用：

```text
GET /tasks/{task_id}
```

检查：

```text
found = true
task_state.state.status = completed
```