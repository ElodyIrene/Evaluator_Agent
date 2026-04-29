# 面向开源项目评估的多智能体系统

### 框架图

![image-20260428213337213](C:\Users\22503\AppData\Roaming\Typora\typora-user-images\image-20260428213337213.png)

一个基于 LangGraph 的 multi-Agent 工作流系统。用户输入 GitHub 仓库地址后，Supervisor Agent 负责调度各个任务节点。首先 Project Parser Agent 提取项目基础信息，然后 Project Type Classifier Agent 判断项目属于哪类开源项目。接着 Metric Collector Agent 调用 GitHub API 和 OpenDigger API 获取指标数据。Core Metric Selector Agent 根据项目类型筛选关键指标。随后 RAG Retrieval Agent 从知识库中检索这些指标的定义和适用场景。最后 Evaluation Judge Agent 结合指标结果和定义生成评估报告，并由 Quality Guard Agent 做一致性检查。整个过程中的状态、缓存和历史报告信息都统一保存在 Redis 中。

### 工具层

#### 1. app/tools/github_client.py

解析 GitHub 链接，获取真实的仓库信息

#### 2. app/tools/opendigger_client.py

获取 OpenDigger 的开源指标

### 规则型Agent层 —— 依赖代码进行逻辑处理

#### 1. app/agents/project_parser.py

输入 GitHub URL → 解析 owner/repo → 调用 GitHub Client 获取基础信息 → 把结果写入 EvaluationState

#### 2. app/agents/type_classifier.py

读取 basic_info → 根据 topics、description、README、language → 判断项目类型 → 写入 state.project_type

#### 3. app/agents/metric_collector.py

读取 owner/repo → 调用 OpenDigger → 整理 GitHub 基础指标 → 写入 state.raw_metrics

#### 4. app/agents/metric_selector.py

解析仓库 → 判断类型 → 采集 GitHub + OpenDigger 指标

#### 5. app/agents/report_generator.py

读取 selected_metrics → 计算初步评分 → 生成结构化 EvaluationReport → 写入 state.report

#### 6. app/agents/quality_guard.py

读取 state.report → 检查报告是否完整、分数是否合理、数据来源是否存在 → 把检查结果写入 state.quality_result