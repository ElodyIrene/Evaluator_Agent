# 性能优化记录

本文档记录智能开源项目评估 Agent 系统中的性能问题、优化方案和实测结果。

本项目的性能优化重点主要集中在三个方面：

1. OpenDigger 多指标请求优化
2. Redis 不可用时快速失败
3. 历史报告缓存快速返回

---

## 1. 性能优化背景

系统执行一次完整 `/evaluate` 评估时，会经过以下流程：

```text
GitHub URL 解析
→ GitHub API 请求
→ OpenDigger 多指标请求
→ 项目类型判断
→ 核心指标筛选
→ RAG 检索
→ 规则版报告生成
→ LLM 报告生成
→ Quality Guard 检查
→ Redis 保存历史报告和任务状态
```

其中可能影响性能的部分包括：

- GitHub API 网络请求
- OpenDigger 多个指标请求
- Redis 缓存读取和写入
- LLM 报告生成
- Redis 不可用时的连接等待

## 2. 遇到的主要性能问题

### 2.1 问题现象

在 Redis 停止的情况下，调用 `/evaluate` 接口仍然可以返回结果，但响应时间非常长。

实测优化前，在 Redis 停止状态下，连续三次调用 `/evaluate`：

```text
第 1 次：210.92 秒
第 2 次：222.16 秒
第 3 次：223.38 秒
平均：218.82 秒
```

这说明系统虽然功能正确，但在异常场景下响应时间不可接受。

### 2.2 初步判断

Redis 停止后，系统无法读取缓存，因此会重新请求 GitHub 和 OpenDigger。

其中 OpenDigger 需要请求多个指标：

```text
openrank
activity
stars
contributors
new_contributors
inactive_contributors
bus_factor
issues_new
issues_closed
issue_response_time
issue_resolution_duration
change_requests
change_requests_accepted
change_request_response_time
change_request_resolution_duration
```

如果这些请求串行执行，每个请求都要等待网络响应，总耗时会被显著放大。

### 2.3 问题原因总结

主要原因有两个：

1. OpenDigger 指标请求是串行的。
2. Redis 不可用时，每次缓存读取和写入都会等待连接失败。

因此需要同时优化：

```text
OpenDigger 请求方式
+
Redis 失败等待时间
```

## 3. 优化一：OpenDigger 指标并发请求

### 3.1 优化前

优化前，OpenDigger 指标是逐个请求的。

伪流程：

```text
请求 openrank
→ 等待返回
→ 请求 activity
→ 等待返回
→ 请求 contributors
→ 等待返回
→ ...
```

这种方式的问题是：

```text
总耗时 ≈ 所有指标请求耗时之和
```

如果每个指标请求都需要几秒，15 个指标串行请求就会非常慢。

### 3.2 优化后

优化后，使用 `ThreadPoolExecutor` 并发请求多个 OpenDigger 指标。

优化后的流程：

```text
同时请求多个 OpenDigger 指标
→ 谁先返回就先处理谁
→ 最后汇总所有结果
```

这样总耗时更接近：

```text
最慢的几个请求耗时
```

而不是所有请求耗时相加。

### 3.3 涉及文件

```text
app/tools/opendigger_client.py
```

### 3.4 关键设计

```text
OPENDIGGER_MAX_WORKERS = 8
OPENDIGGER_REQUEST_TIMEOUT_SECONDS = 8
```

含义：

- 最多同时执行 8 个 OpenDigger 请求
- 单个请求最长等待 8 秒
- 单个指标失败不会影响其他指标
- 失败指标会进入 `missing_metrics`

### 3.5 优化效果

在 Redis 停止状态下，优化后单独测 OpenDigger：

```text
OpenDigger 单独耗时：28.17 秒
```

完整 `/evaluate` 接口耗时从平均 218.82 秒下降到：

```text
85.50 秒
```

说明 OpenDigger 并发请求显著降低了整体等待时间。

## 4. 优化二：Redis 不可用时快速失败

### 4.1 优化前

Redis 停止后，系统尝试读取或写入 Redis 时，会等待连接失败。

这些 Redis 操作包括：

- 读取 GitHub 缓存
- 写入 GitHub 缓存
- 读取 OpenDigger 缓存
- 写入 OpenDigger 缓存
- 保存任务状态
- 保存历史报告

如果每次 Redis 连接失败都等待较长时间，就会拖慢整个评估流程。

### 4.2 优化后

在 Redis Client 中设置较短的连接超时和读写超时。

涉及文件：

```text
app/tools/redis_store.py
```

核心策略：

```text
Redis 是增强组件，不是主流程强依赖。
Redis 不可用时应该快速失败，不应该阻塞主评估流程。
```

### 4.3 当前策略

Redis 客户端设置短超时：

```text
socket_connect_timeout = 0.5
socket_timeout = 0.5
retry_on_timeout = False
```

这样 Redis 不可用时，可以快速抛出错误，由上层逻辑进行降级处理。

### 4.4 降级逻辑

Redis 不可用时：

```text
GitHub / OpenDigger 缓存失效
历史报告不可保存
任务状态不可持久化
主评估流程继续执行
最终仍然返回报告
```

### 4.5 优化效果

在 Redis 停止状态下：

```text
OpenDigger 并发请求后：85.50 秒
Redis 快速失败后：41.42 秒
```

说明 Redis 快速失败机制进一步降低了异常场景下的接口耗时。

## 5. 优化三：Redis 指标缓存

### 5.1 缓存目标

系统对两类外部数据做缓存：

1. GitHub 基础信息
2. OpenDigger 指标数据

这样可以减少重复请求，提高重复评估速度，并降低外部 API 限流风险。

---

### 5.2 GitHub 缓存

涉及文件：

```text
app/tools/github_client.py
```

缓存内容：

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

缓存 Key 示例：

```text
cache:github:basic_info:langchain-ai:langgraph
```

缓存时间：

```text
1 小时
```

设计原因：

```text
GitHub stars、forks、issues 会更新，但不需要秒级实时。
1 小时缓存可以在数据新鲜度和请求效率之间取得平衡。
```

---

### 5.3 OpenDigger 缓存

涉及文件：

```text
app/tools/opendigger_client.py
```

缓存内容：

- openrank
- activity
- contributors
- bus_factor
- issue_response_time
- change_request_response_time
- 其他 OpenDigger 指标

缓存 Key 示例：

```text
cache:opendigger:langchain-ai:langgraph:openrank
```

缓存时间：

```text
6 小时
```

设计原因：

```text
OpenDigger 指标通常不是实时变化的。
相比 GitHub 基础信息，它更适合缓存更长时间。
```

---

### 5.4 缓存命中时的流程

```text
读取 Redis 缓存
→ 命中缓存
→ 直接返回缓存数据
→ 不请求外部 API
```

### 5.5 缓存未命中时的流程

```text
读取 Redis 缓存
→ 未命中
→ 请求 GitHub / OpenDigger
→ 保存结果到 Redis
→ 返回结果
```

### 5.6 Redis 不可用时的流程

```text
读取 Redis 失败
→ 跳过缓存
→ 直接请求外部 API
→ 写入 Redis 失败则忽略
→ 主流程继续
```

这样可以保证 Redis 不可用时系统仍然可用。

## 6. 优化四：历史报告缓存快速返回

### 6.1 背景

即使 GitHub 和 OpenDigger 指标已经缓存，系统每次完整评估仍然需要调用 LLM 生成报告。

实测：

```text
Redis 正常 + 指标缓存 + LLM 重新生成：
约 17.1 秒
```

进一步测量发现：

```text
LLM Report Agent：
约 17.8 秒
```

说明当前主要瓶颈已经转移到 LLM 报告生成。

### 6.2 解决方案

系统新增请求参数：

```json
{
  "use_cached_report": true
}
```

当 `use_cached_report=true` 时：

```text
系统先查询 Redis 中是否已有该仓库的历史报告
→ 如果命中，直接返回历史报告
→ 跳过 GitHub / OpenDigger / RAG / LLM
```

### 6.3 适用场景

历史报告缓存适用于：

- Demo 演示
- 重复查询同一个仓库
- 对实时性要求不高的场景
- 希望快速返回结果的场景

### 6.4 不适用场景

如果用户希望获取尽可能新的评估结果，应使用：

```json
{
  "use_cached_report": false
}
```

这样系统会重新执行完整评估流程。

### 6.5 优化效果

实测：

```text
Redis 正常 + use_cached_report=true：
约 0.03 秒
```

相比重新调用 LLM 的约 17.1 秒，历史报告缓存模式实现了毫秒级返回。

## 7. 完整性能对比

当前实测结果如下：

| 场景                                          |             耗时 |
| --------------------------------------------- | ---------------: |
| Redis 停止 + 串行 OpenDigger                  | 平均约 218.82 秒 |
| Redis 停止 + OpenDigger 并发请求              |      约 85.50 秒 |
| Redis 停止 + OpenDigger 并发 + Redis 快速失败 |      约 41.42 秒 |
| Redis 正常 + 指标缓存 + LLM 重新生成          |       约 17.1 秒 |
| Redis 正常 + `use_cached_report=true`         |       约 0.03 秒 |

---

## 8. 优化效果总结

### 8.1 从串行到并发

OpenDigger 从串行请求改为并发请求后，异常场景下耗时明显下降。

```text
约 218.82 秒
→ 约 85.50 秒
```

### 8.2 Redis 快速失败

Redis 不可用时快速失败后，耗时进一步下降。

```text
约 85.50 秒
→ 约 41.42 秒
```

### 8.3 历史报告缓存

历史报告缓存命中时，可以跳过完整评估流程。

```text
约 17.1 秒
→ 约 0.03 秒
```

---

## 9. 当前主要瓶颈

在 Redis 正常、指标缓存可用的情况下，当前主要耗时来自：

```text
LLM Report Agent
```

实测：

```text
LLM Report Agent：约 17.8 秒
/evaluate 正常模式：约 17.1 秒
```

说明 GitHub、OpenDigger、RAG 和 Redis 已经不是主要瓶颈。

后续如果继续优化，可以考虑：

- 缓存 LLM 报告
- 缩短 Prompt
- 减少传入 LLM 的上下文长度
- 使用更快的模型
- 异步任务化
- 流式返回

## 10. 缓存策略与取舍

### 10.1 为什么 GitHub 缓存 1 小时

GitHub 基础信息会变化，例如：

- stars
- forks
- open issues
- README
- topics

但这些变化通常不需要秒级实时。

因此使用 1 小时缓存可以减少重复请求，同时保持数据相对新鲜。

### 10.2 为什么 OpenDigger 缓存 6 小时

OpenDigger 指标通常变化频率较低。

例如：

- OpenRank
- Activity
- Bus Factor
- Issue Response Time

这些指标更适合使用较长缓存。

### 10.3 为什么历史报告缓存需要手动开启

历史报告缓存通过参数控制：

```json
{
  "use_cached_report": true
}
```

默认不使用历史报告缓存。

原因是：

```text
默认模式应该重新执行完整评估，尽量保证结果更新。
缓存模式适合 Demo 和重复查询。
```

### 10.4 缓存带来的风险

缓存可能带来数据不够新的问题。

例如：

- stars 已经增加，但缓存还没过期
- open issues 已经变化，但报告仍使用旧数据
- 历史报告可能不反映最新项目状态

### 10.5 当前取舍

当前系统的取舍是：

```text
默认重新评估
→ 保证结果相对新

可选使用历史缓存
→ 保证低延迟返回
```

这让用户可以根据场景选择：

| 模式                      | 特点           |
| ------------------------- | -------------- |
| `use_cached_report=false` | 更关注数据更新 |
| `use_cached_report=true`  | 更关注响应速度 |

## 11.总结

```text
在开发过程中，发现 Redis 停止后，系统虽然能返回结果，但响应时间非常长，平均超过 200 秒。

先通过 Measure-Command 测量接口耗时，确认这是一个性能问题，而不是功能问题。

进一步分析发现，Redis 停止后缓存失效，OpenDigger 的 15 个指标变成串行请求，同时 Redis 连接失败也会拖慢流程。

所以做了两步优化：

第一步，把 OpenDigger 指标从串行请求改成并发请求，让多个指标同时请求。

第二步，给 Redis 设置短超时，让 Redis 不可用时快速失败，不阻塞主流程。

优化后，Redis 停止场景下，接口耗时从平均 218.82 秒降低到 41.42 秒。

随我发现 Redis 正常时，主要瓶颈变成了 LLM 报告生成，大约 17 秒。因此我增加了 use_cached_report 参数，在重复查询或 Demo 场景下可以直接复用历史报告，响应时间降低到约 0.03 秒。
```

这体现了：

- 有实际性能问题发现过程
- 有数据化测量
- 有明确瓶颈分析
- 有针对性优化
- 有优化前后对比
- 有工程取舍意识