# 异常处理与降级兜底策略

本文档说明智能开源项目评估 Agent 系统中的异常处理设计。

系统涉及多个外部依赖：

- GitHub API
- OpenDigger
- LLM API
- Redis
- 本地知识库

因此异常处理的核心目标不是“所有错误都让流程失败”，而是根据错误严重程度进行分层处理。

---

## 1. 异常处理总体原则

本系统的异常处理遵循以下原则：

### 1.1 输入错误提前返回

如果用户输入的 GitHub URL 格式错误，系统不会进入 LangGraph 主流程，而是在 API 层直接返回错误。

原因：

```text
输入格式错误属于请求层问题
没有必要继续调用 GitHub / OpenDigger / LLM
提前返回可以节省资源
```

### 1.2 外部数据源错误明确返回

如果 GitHub 仓库不存在，系统会返回明确的错误类型：

```text
github_repo_not_found
```

原因：

```text
没有仓库基础信息，后续指标采集、项目分类、报告生成都无法进行
```

### 1.3 非核心依赖失败时降级

Redis 是增强组件，不是主流程强依赖。

Redis 失败时：

```text
主评估流程继续执行
缓存不可用
历史报告不可保存
任务状态不可持久化
但仍然返回评估报告
```

### 1.4 LLM 失败时使用规则报告兜底

系统不会直接依赖 LLM 生成最终结果。

流程中先生成规则版 baseline 报告，再调用 LLM 增强。

因此 LLM 失败时：

```text
保留规则版报告
记录错误信息
继续执行 Quality Guard
返回可用报告
```

### 1.5 错误信息写入统一状态

工作流中的错误或警告会写入：

```text
state.errors
```

最终通过 API 返回：

```json
{
  "errors": []
}
```

这样方便调试、排查问题和面试展示。

## 2. 异常分层

当前系统的异常处理分布在不同层级。

| 层级     | 负责内容                     | 示例                                          |
| -------- | ---------------------------- | --------------------------------------------- |
| API 层   | 请求校验、整体流程异常包装   | 非法 URL、整体 evaluation_failed              |
| 工具层   | 外部 API 和 Redis 错误处理   | GitHub 404、GitHub API Error、Redis 连接失败  |
| Agent 层 | 节点内部业务异常和 fallback  | LLM 失败、selected_metrics 为空               |
| Graph 层 | 流程级路由和重试             | state.errors 提前结束、Quality Guard 失败重试 |
| Redis 层 | 缓存、历史报告、任务状态降级 | Redis 不可用时快速失败                        |

---

## 3. 当前已实现的异常类型

当前已实现四类主要异常处理：

| 异常场景          | 处理位置                                                  | 是否中断主流程 | 处理策略                       |
| ----------------- | --------------------------------------------------------- | -------------- | ------------------------------ |
| 非法 GitHub URL   | `app/main.py`                                             | 是             | 直接返回 `invalid_github_url`  |
| GitHub 仓库不存在 | `app/tools/github_client.py`、`app/main.py`               | 是             | 返回 `github_repo_not_found`   |
| LLM 生成报告失败  | `app/agents/ai_agents/llm_report_generator.py`            | 否             | 使用规则版报告兜底             |
| Redis 不可用      | `app/tools/redis_store.py`、`app/main.py`、工具层缓存逻辑 | 否             | 主流程继续，缓存和历史记录降级 |

## 4. 非法 GitHub URL

### 4.1 场景

用户传入的不是合法 GitHub 仓库地址。

示例请求：

```json
{
  "url": "abc",
  "use_cached_report": false
}
```

### 4.2 处理位置

```text
app/main.py
```

### 4.3 处理流程

```text
/evaluate 接收请求
→ 调用 parse_github_url 检查 URL
→ URL 不合法
→ 保存失败任务状态
→ 直接返回 invalid_github_url
```

### 4.4 返回示例

```json
{
  "task_id": "xxx",
  "status": "failed",
  "error_type": "invalid_github_url",
  "message": "Invalid GitHub repository URL. Example: https://github.com/langchain-ai/langgraph"
}
```

### 4.5 为什么在 API 层处理

非法 URL 属于输入校验问题。

如果 URL 格式明显错误，就没有必要进入 LangGraph 主流程，也不需要调用 GitHub、OpenDigger 或 LLM。

这样可以：

- 节省外部 API 请求
- 降低无效流程开销
- 返回更清晰的错误信息

## 5. GitHub 仓库不存在

### 5.1 场景

用户传入的 GitHub URL 格式正确，但仓库不存在或不可访问。

示例请求：

```json
{
  "url": "https://github.com/this-repo-does-not-exist-xyz/abc",
  "use_cached_report": false
}
```

### 5.2 处理位置

```text
app/tools/github_client.py
app/main.py
```

### 5.3 处理流程

工具层：

```text
github_client.py 调用 GitHub API
→ GitHub 返回 404
→ 抛出 GitHubRepoNotFoundError
```

API 层：

```text
main.py 捕获 GitHubRepoNotFoundError
→ 保存失败任务状态
→ 返回 github_repo_not_found
```

### 5.4 返回示例

```json
{
  "task_id": "xxx",
  "status": "failed",
  "error_type": "github_repo_not_found",
  "message": "GitHub repository not found or not accessible: this-repo-does-not-exist-xyz/abc"
}
```

### 5.5 为什么要单独处理 404

GitHub 仓库不存在是一个明确的业务错误。

如果不单独处理，用户可能只看到底层 HTTP 报错，不利于理解问题。

单独处理后，调用方可以清楚知道：

```text
仓库不存在
或
仓库不可访问
```

### 5.6 和 GitHub API Error 的区别

| 错误类型                | 含义                                              |
| ----------------------- | ------------------------------------------------- |
| `github_repo_not_found` | 仓库不存在或不可访问                              |
| `github_api_error`      | GitHub API 请求失败，例如网络错误、限流、服务异常 |

## 6. GitHub API 请求失败

### 6.1 场景

GitHub API 请求失败，但不是仓库不存在。

可能原因：

- GitHub 网络不可达
- API 超时
- GitHub 限流
- Token 无效
- GitHub 服务异常

### 6.2 处理位置

```text
app/tools/github_client.py
app/main.py
```

### 6.3 处理流程

```text
GitHub API 请求失败
→ github_client.py 抛出 GitHubAPIError
→ main.py 捕获异常
→ 保存失败任务状态
→ 返回 github_api_error
```

### 6.4 返回示例

```json
{
  "task_id": "xxx",
  "status": "failed",
  "error_type": "github_api_error",
  "message": "GitHub API request failed..."
}
```

### 6.5 为什么 GitHub API 失败会中断主流程

GitHub 基础信息是后续流程的前置条件。

如果无法获取 GitHub 仓库基础信息，后续节点无法可靠执行：

```text
Type Classifier 需要 basic_info
Metric Collector 需要 owner/repo/basic_info
Metric Selector 需要 raw_metrics
Report Generator 需要 selected_metrics
```

因此 GitHub API 严重失败时，系统会终止评估流程。

## 7. LLM 生成报告失败

### 7.1 场景

LLM Report Agent 调用模型失败。

可能原因：

- API Key 错误
- 模型服务超时
- 模型不支持当前地区
- 中转 API 不稳定
- 模型返回格式不是合法 JSON
- LLM Provider 配置错误

### 7.2 处理位置

```text
app/agents/ai_agents/llm_report_generator.py
```

### 7.3 处理流程

```text
Rule Report Generator 先生成规则版报告
→ LLM Report Agent 尝试调用 LLM
→ 如果 LLM 成功，覆盖 state.report
→ 如果 LLM 失败，保留规则版 state.report
→ 记录错误到 state.errors
→ 继续进入 Quality Guard
```

### 7.4 错误示例

```text
LLM report generation failed: Unsupported LLM provider: unknown. Using rule-based report fallback.
```

API 返回中可能出现：

```json
{
  "status": "completed",
  "errors": [
    "LLM report generation failed: Unsupported LLM provider: unknown. Using rule-based report fallback."
  ]
}
```

### 7.5 为什么 LLM 失败不中断主流程

因为系统在 LLM 之前已经生成了规则版 baseline 报告。

规则版报告虽然表达没有 LLM 生成的自然，但仍然是基于真实指标生成的可用报告。

因此 LLM 失败时系统可以降级为：

```text
规则版报告模式
```

### 7.6 这种设计的优势

- 不会因为 LLM 失败导致整个系统不可用
- 方便面试展示 AI 应用的 fallback 设计
- 降低对单一模型服务的依赖
- 提升系统稳定性

## 8. Redis 不可用

### 8.1 场景

Redis 服务未启动或连接失败。

可能原因：

- Docker Redis 容器未启动
- Redis 端口不可用
- Redis URL 配置错误
- Redis 网络连接失败

### 8.2 处理位置

```text
app/tools/redis_store.py
app/main.py
app/tools/github_client.py
app/tools/opendigger_client.py
```

### 8.3 Redis 在系统中的作用

Redis 当前用于三类能力：

```text
1. GitHub / OpenDigger 指标缓存
2. 历史评估报告保存
3. task_id 对应任务状态保存
```

### 8.4 Redis 不可用时的处理策略

Redis 是增强组件，不是主流程强依赖。

Redis 不可用时：

```text
主评估流程继续执行
GitHub / OpenDigger 缓存不可用
历史报告无法保存
任务状态无法持久化
系统仍然返回评估报告
```

### 8.5 历史报告保存失败示例

```json
{
  "status": "completed",
  "history_saved": false,
  "errors": [
    "Failed to save report history: Error 10061 connecting to localhost:6379."
  ]
}
```

### 8.6 为什么 Redis 不可用不中断主流程

因为 Redis 并不是生成报告的必要条件。

完整评估的核心依赖是：

```text
GitHub API
OpenDigger
LangGraph 工作流
RAG
LLM
Quality Guard
```

Redis 只提升性能和可追踪性。

因此 Redis 不可用时，系统只降级，不失败。

### 8.7 Redis 快速失败机制

为了避免 Redis 不可用时拖慢接口，Redis 客户端设置了短超时。

目标是：

```text
Redis 连接失败时快速返回
避免阻塞主评估流程
```

优化后，Redis 不可用情况下 `/evaluate` 响应时间明显下降。

## 9. Quality Guard 失败

### 9.1 场景

最终报告没有通过质量检查。

可能原因：

- `overall_score` 超出 0-100
- 某个维度分数超出 0-20
- 缺少 summary
- 缺少 strengths
- 缺少 risks
- 缺少 suggestions
- 缺少 data_sources
- selected_metrics 为空

### 9.2 处理位置

```text
app/agents/quality_guard.py
app/graph.py
```

### 9.3 处理流程

```text
Quality Guard 检查报告
→ 如果通过，流程结束
→ 如果不通过，检查 retry_count
→ retry_count < 1，则回到 LLM Report Generator 重试
→ retry_count >= 1，则结束并返回带问题的报告
```

### 9.4 Supervisor 路由逻辑

```text
Quality Guard 通过
→ END

Quality Guard 不通过 且 retry_count < 1
→ 回到 LLM Report Generator 重试

Quality Guard 不通过 且 retry_count >= 1
→ END
```

### 9.5 当前最大重试次数

```text
1 次
```

### 9.6 为什么只重试一次

原因：

- 避免无限循环
- 控制 LLM 调用成本
- 保持接口响应时间可控
- MVP 阶段优先稳定性

后续可以增加更精细的策略，例如：

```text
只针对特定质量问题重试
重试时修改 Prompt
引入 LLM Quality Reviewer
```

## 10. OpenDigger 数据缺失

### 10.1 场景

OpenDigger 某些指标不存在或请求失败。

可能原因：

- OpenDigger 没有该项目的数据
- 某个指标文件不存在
- OpenDigger 网络请求失败
- 指标返回格式异常

### 10.2 处理位置

```text
app/tools/opendigger_client.py
app/agents/metric_collector.py
```

### 10.3 当前处理方式

当前 OpenDigger 指标采集采用尽力而为策略。

如果某个指标获取失败：

```text
该指标记入 missing_metrics
其他指标继续处理
主评估流程继续执行
```

### 10.4 为什么 OpenDigger 部分缺失不中断主流程

因为 GitHub 基础信息仍然可用，部分 OpenDigger 指标也可能可用。

即使缺失某些指标，系统仍然可以基于已有数据生成报告。

后续可以进一步优化：

- 在报告中明确提示缺失指标
- 降低相关维度评分置信度
- 在 Quality Guard 中检查关键指标缺失
- 在 API 返回中增加 `missing_metrics`

## 11. 异常处理总结

当前系统的异常处理策略可以总结为：

```text
输入错误
→ 提前失败返回

核心数据源失败
→ 明确失败返回

非核心增强组件失败
→ 降级继续

LLM 失败
→ 使用规则报告兜底

报告质量失败
→ 重试一次 LLM 报告生成

部分指标缺失
→ 尽力而为继续评估
```

这种设计的核心目标是：

```text
尽可能保证系统可用
尽可能返回结构化结果
尽可能记录错误原因
避免外部依赖失败导致整个系统崩溃
```

异常处理类型：

```text
第一类是输入错误，比如非法 GitHub URL，这种在 API 层直接返回，不进入 LangGraph。

第二类是核心依赖错误，比如 GitHub 仓库不存在，这会导致后续流程无法继续，所以返回明确的 github_repo_not_found。

第三类是非核心依赖错误，比如 Redis 不可用。Redis 只用于缓存、历史报告和任务状态，不影响主评估流程，所以系统会降级继续执行。

第四类是 LLM 错误。为了避免模型调用失败导致整个系统不可用，我先生成规则版 baseline 报告，再调用 LLM 增强。如果 LLM 失败，就保留规则报告并记录错误。

第五类是质量检查失败。Quality Guard 不通过时，Supervisor 会让 LLM Report Agent 重试一次，避免低质量报告直接返回。
```