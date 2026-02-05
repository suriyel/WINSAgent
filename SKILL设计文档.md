# WINS Agent Skill 模块系统设计文档

## 1. 概述

### 1.1 背景

当前 WINS Agent 的系统提示词 `SYSTEM_PROMPT` 硬编码在 `backend/app/agent/core.py` 中，包含约 90 行的提示词内容。随着业务场景增加，这种方式存在以下问题：

- **可维护性差**：所有业务流程逻辑混杂在一个大字符串中
- **扩展性受限**：新增业务场景需要修改核心代码
- **复用性低**：无法按需加载特定领域的指导内容

### 1.2 目标

将硬编码的 `SYSTEM_PROMPT` 拆解为可按需加载的 Skill 模块，实现：

1. **消除硬编码**：将业务流程内容迁移至独立的 Skill 文件
2. **动态加载**：根据用户意图按需加载对应 Skill
3. **Jinja2 模板化**：通过模板引擎控制 SYSTEM_PROMPT 的组装
4. **智能决策**：通过内置 tool 让 LLM 自行判断加载哪个 Skill

## 2. 整体架构

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              用户消息                                    │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SkillMiddleware                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  wrap_model_call hook（核心控制点）                                │  │
│  │  1. 通过 request.state 检测是否为 HumanMessage                     │  │
│  │  2. 检测 todos 是否有未完成任务、是否有活跃 Skill                   │  │
│  │  3. 动态过滤 tools（移除/保留 select_skill）                       │  │
│  │  4. 通过 Jinja2 渲染 system_prompt（注入 skill_content）           │  │
│  │  5. 使用 request.override(tools=..., system_prompt=...) 修改请求  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  wrap_tool_call hook                                              │  │
│  │  - 拦截 select_skill 调用                                          │  │
│  │  - 加载对应 Skill 内容                                             │  │
│  │  - 更新 state.active_skill 和 state.skill_content                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Skills 目录                                     │
│  /Skills/                                                               │
│    ├── network_optimization.md    # 网络优化仿真分析 Skill              │
│    ├── coverage_analysis.md       # 覆盖问题分析 Skill                  │
│    ├── interference_analysis.md   # 干扰问题分析 Skill                  │
│    └── capacity_analysis.md       # 容量问题分析 Skill                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
HumanMessage
    │
    ▼
SkillMiddleware.wrap_model_call()
    │
    ├─── 从 request.state 读取状态 ─────────────────────────────────────┐
    │    (messages, active_skill, skill_content, todos)                 │
    │                                                                   │
    ├─── 判断是否为 HumanMessage ───────────────────────────────────────┤
    │                                                                   │
    ├─── 是 HumanMessage 且无活跃 Skill/无未完成任务 ────┐              │
    │                                                    ▼              │
    │                                   保留 select_skill tool           │
    │                                                    │              │
    ├─── 非 HumanMessage / 有活跃 Skill+未完成任务 ──────┤              │
    │                                                    ▼              │
    │                                   移除 select_skill tool           │
    │                                                                   │
    ├─── 渲染 system_prompt（Jinja2 + skill_content）──────────────────┤
    │                                                                   │
    └─── request.override(tools=..., system_prompt=...) ────────────────┘
                                    │
                                    ▼
                          LLM 调用 select_skill（若可见）
                                    │
                                    ▼
                    wrap_tool_call 拦截并加载 Skill
                                    │
                                    ▼
                    更新 state.active_skill, state.skill_content
                                    │
                                    ▼
                    下次 wrap_model_call 使用新 skill_content 渲染
```

## 3. 核心组件设计

### 3.1 Skill 文件格式

Skill 文件采用 Markdown 格式，包含 YAML Front Matter 元数据：

```markdown
---
name: network_optimization
title: 网络优化仿真分析
description: 用于分析网络覆盖、干扰、容量等问题并进行优化仿真对比
triggers:
  - 弱覆盖
  - 干扰
  - 容量
  - 切换
  - 优化
  - 仿真
  - 分析
priority: 100
---

# 网络优化仿真分析指南

## 工具编排流程

按照正确的流程顺序调用工具：

1. **第一步**：调用 search_terminology 和 search_design_doc 获取领域知识
2. **第二步**：调用 match_scenario 匹配场景获取 digitaltwinsId
3. **第三步**：调用 query_root_cause_analysis 查询根因分析结果
4. **第四步**：**必须**输出固定提示语：**"根因分析完成。是否需要对该场景进行优化仿真？"**
5. **第五步**：如用户确认需要优化，调用 query_simulation_results 查询仿真结果
6. **第六步**（可选）：如用户需要直观对比，调用 compare_simulation_data 生成可视化对比图表

## 指标选择规则

根据用户意图和检索到的术语定义，**只查询相关指标**：
- 用户问"弱覆盖" → 查询 RSRP、MR覆盖率、覆盖电平等相关指标
- 用户问"干扰" → 查询 SINR、RSRQ、重叠覆盖度等相关指标
- 用户问"容量" → 查询 PRB利用率、下行流量、用户数等相关指标

## 分析粒度

每次分析需要考虑两种粒度：
- **小区级(cell)**：以基站小区为最小分析单元
- **栅格级(grid)**：以地理栅格为最小分析单元

## 图表类型选择

调用 compare_simulation_data 工具时，根据数据特征选择图表类型：
- grouped_bar_chart: 分组柱状图（默认推荐）
- line_chart: 折线图
- stacked_bar_chart: 堆叠柱状图
- scatter_plot: 散点图
- heatmap: 热力图
- table: 数据表格
```

### 3.2 SYSTEM_PROMPT 模板

基础 SYSTEM_PROMPT 模板（保留功能性部分）：

```python
# backend/app/agent/prompts/base_prompt.py

BASE_SYSTEM_PROMPT = """\
你是 WINS Agent 工作台的智能助手，专注于通信网络优化仿真场景。

## 核心职责

1. **理解用户意图**：准确识别用户关注的网络问题类型
2. **领域知识检索**：**必须**在执行任何分析前，先调用 search_terminology 和 search_design_doc 工具获取领域知识
3. **工具编排**：按照正确的流程顺序调用工具

## 缺省参数处理

当工具某些必填参数无法通过上下文或查询工具获得时：
- **务必**先尝试使用查询工具获取参数值
- 仍无法确定的参数，**必须**使用以下格式：
```params_request
{
  "tool_name": "工具名称",
  "known_params": {"已确定的参数名": "值"},
  "missing_params": ["缺失参数1", "缺失参数2"]
}
```
- **数组类型参数**的值必须使用 JSON 数组格式

## 注意事项

- 工具调用失败时，整个任务终止，不要重试
- 始终用中文回复用户
- 展示分析结果时，简要总结关键发现

## 建议回复选项

在每次回复结束时，提供 2-4 个建议的快捷回复选项：

```suggestions
{
  "suggestions": [
    {"text": "选项1文本"},
    {"text": "选项2文本"}
  ]
}
```

{% if skill_content %}
## 当前任务指南

{{ skill_content }}
{% endif %}
"""
```

### 3.3 SkillMiddleware 实现

```python
# backend/app/agent/middleware/skill.py

"""SkillMiddleware: 动态加载 Skill 内容到 SYSTEM_PROMPT.

根据用户意图智能选择并加载对应的 Skill 文件，通过 Jinja2 模板
渲染最终的系统提示词。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from jinja2 import Environment, BaseLoader
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import BaseTool
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from typing_extensions import NotRequired

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill 数据结构
# ---------------------------------------------------------------------------

@dataclass
class SkillMeta:
    """Skill 元数据."""
    name: str
    title: str
    description: str
    triggers: list[str] = field(default_factory=list)
    priority: int = 0
    file_path: str = ""


@dataclass
class LoadedSkill:
    """已加载的 Skill."""
    meta: SkillMeta
    content: str


# ---------------------------------------------------------------------------
# Skill State 扩展
# ---------------------------------------------------------------------------

class SkillState(AgentState):
    """扩展的 Agent State，包含 Skill 相关字段."""

    active_skill: str | None  # 当前活跃的 Skill 名称
    skill_content: str | None  # 当前 Skill 的内容（用于 Jinja2 渲染）


# ---------------------------------------------------------------------------
# SkillLoader: Skill 文件加载器
# ---------------------------------------------------------------------------

class SkillLoader:
    """Skill 文件加载和管理."""

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._cache: dict[str, LoadedSkill] = {}
        self._index: dict[str, SkillMeta] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """确保 Skill 索引已加载."""
        if self._loaded:
            return
        self._load_index()
        self._loaded = True

    def _load_index(self) -> None:
        """扫描 Skills 目录，构建索引."""
        if not self.skills_dir.exists():
            logger.warning(f"Skills 目录不存在: {self.skills_dir}")
            return

        for file_path in self.skills_dir.glob("*.md"):
            try:
                meta = self._parse_frontmatter(file_path)
                if meta:
                    self._index[meta.name] = meta
                    logger.info(f"已索引 Skill: {meta.name} ({meta.title})")
            except Exception as e:
                logger.warning(f"解析 Skill 文件失败 {file_path}: {e}")

    def _parse_frontmatter(self, file_path: Path) -> SkillMeta | None:
        """解析 Markdown 文件的 YAML Front Matter."""
        content = file_path.read_text(encoding="utf-8")

        # 匹配 YAML Front Matter
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return None

        try:
            meta_dict = yaml.safe_load(match.group(1))
            return SkillMeta(
                name=meta_dict.get("name", file_path.stem),
                title=meta_dict.get("title", file_path.stem),
                description=meta_dict.get("description", ""),
                triggers=meta_dict.get("triggers", []),
                priority=meta_dict.get("priority", 0),
                file_path=str(file_path),
            )
        except yaml.YAMLError as e:
            logger.warning(f"YAML 解析失败 {file_path}: {e}")
            return None

    def get_all_skills(self) -> list[SkillMeta]:
        """获取所有可用 Skill 的元数据."""
        self._ensure_loaded()
        return sorted(
            self._index.values(),
            key=lambda s: -s.priority  # 按优先级降序
        )

    def load_skill(self, name: str) -> LoadedSkill | None:
        """加载指定名称的 Skill."""
        self._ensure_loaded()

        # 检查缓存
        if name in self._cache:
            return self._cache[name]

        # 查找元数据
        meta = self._index.get(name)
        if not meta:
            logger.warning(f"Skill 不存在: {name}")
            return None

        # 读取文件内容
        try:
            file_path = Path(meta.file_path)
            raw_content = file_path.read_text(encoding="utf-8")

            # 去除 Front Matter，只保留正文
            content = re.sub(
                r"^---\s*\n.*?\n---\s*\n",
                "",
                raw_content,
                flags=re.DOTALL
            ).strip()

            loaded = LoadedSkill(meta=meta, content=content)
            self._cache[name] = loaded
            return loaded
        except Exception as e:
            logger.error(f"加载 Skill 失败 {name}: {e}")
            return None

    def get_skill_for_prompt(self, skill_name: str | None) -> str:
        """获取用于 Jinja2 渲染的 Skill 内容."""
        if not skill_name:
            return ""

        loaded = self.load_skill(skill_name)
        return loaded.content if loaded else ""


# ---------------------------------------------------------------------------
# SkillMiddleware
# ---------------------------------------------------------------------------

class SkillMiddleware(AgentMiddleware[SkillState, ContextT]):
    """Skill 动态加载 Middleware.

    功能：
    1. 检测 HumanMessage 时判断是否需要选择 Skill
    2. 通过内置 select_skill tool 让 LLM 决定加载哪个 Skill
    3. 若 todos 有未完成任务，复用当前 Skill
    4. 非 HumanMessage 时移除 select_skill tool
    5. 通过 Jinja2 渲染包含 Skill 内容的 SYSTEM_PROMPT
    """

    name: str = "skill"
    state_schema = SkillState

    def __init__(
        self,
        skills_dir: str,
        base_prompt_template: str,
    ) -> None:
        """初始化 SkillMiddleware.

        Args:
            skills_dir: Skills 目录路径
            base_prompt_template: 基础 SYSTEM_PROMPT Jinja2 模板
        """
        self._loader = SkillLoader(skills_dir)
        self._base_template = base_prompt_template
        self._jinja_env = Environment(loader=BaseLoader())

        # 构建 select_skill tool
        self._select_skill_tool = self._build_select_skill_tool()

        logger.info(f"SkillMiddleware: 初始化完成, skills_dir={skills_dir}")

    # ------------------------------------------------------------------
    # 公共属性: select_skill tool
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[BaseTool]:
        """返回需要注入主 Agent tools 列表的工具."""
        return [self._select_skill_tool]

    # ------------------------------------------------------------------
    # Middleware Hook: before_model
    # ------------------------------------------------------------------

    def before_model(
        self,
        state: SkillState,
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """在 LLM 调用前处理 Skill 选择逻辑.

        判断逻辑：
        1. 检测最后一条消息是否为 HumanMessage
        2. 检测 todos 是否有未完成任务
        3. 决定是否需要 LLM 选择 Skill
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        last_message = messages[-1]
        is_human_message = isinstance(last_message, HumanMessage) or (
            hasattr(last_message, "type") and
            getattr(last_message, "type", None) == "human"
        )

        # 获取当前状态
        active_skill = state.get("active_skill")
        todos = state.get("todos", [])
        has_pending_todos = any(
            t.get("status") in ("pending", "in_progress")
            for t in todos
        )

        # 决策：是否需要选择 Skill
        need_skill_selection = False

        if is_human_message:
            if has_pending_todos and active_skill:
                # 有未完成任务且有活跃 Skill → 复用当前 Skill，无需重新选择
                logger.debug(
                    f"SkillMiddleware: 复用当前 Skill '{active_skill}' "
                    f"(有 {sum(1 for t in todos if t.get('status') != 'completed')} 个未完成任务)"
                )
                need_skill_selection = False
            else:
                # 新对话或无活跃 Skill → 需要选择
                need_skill_selection = True
        else:
            # 非 HumanMessage（如 ToolMessage、AIMessage）→ 不选择
            need_skill_selection = False

        # 动态控制 select_skill tool 的可见性
        # 通过 state 传递标记，在 tools 过滤时使用
        return {
            "_skill_selection_enabled": need_skill_selection,
        }

    # ------------------------------------------------------------------
    # Middleware Hook: wrap_tool_call
    # ------------------------------------------------------------------

    def wrap_tool_call(
        self,
        state: SkillState,
        tool_call: dict[str, Any],
        call_next: Callable,
    ) -> dict[str, Any]:
        """拦截 select_skill tool 调用，加载 Skill 内容.

        当 LLM 调用 select_skill 时：
        1. 解析 skill_name 参数
        2. 加载对应 Skill 内容
        3. 更新 state.active_skill 和 state.skill_content
        4. 返回 Skill 加载结果
        """
        tool_name = tool_call.get("name", "")

        if tool_name != "select_skill":
            # 非 select_skill，正常执行
            return call_next(state, tool_call)

        # 解析参数
        args = tool_call.get("args", {})
        skill_name = args.get("skill_name", "").strip()

        # 处理"无需特定 Skill"的情况
        if not skill_name or skill_name.lower() in ("none", "null", ""):
            logger.info("SkillMiddleware: LLM 选择不加载特定 Skill")
            return {
                "result": "已确认不加载特定 Skill，使用默认模式。",
                "state_update": {
                    "active_skill": None,
                    "skill_content": None,
                },
            }

        # 加载 Skill
        loaded = self._loader.load_skill(skill_name)
        if not loaded:
            available = ", ".join(s.name for s in self._loader.get_all_skills())
            return {
                "result": f"Skill '{skill_name}' 不存在。可用 Skill: {available}",
                "state_update": {},
            }

        logger.info(
            f"SkillMiddleware: 加载 Skill '{skill_name}' ({loaded.meta.title})"
        )

        return {
            "result": f"已加载 Skill: {loaded.meta.title}\n\n{loaded.meta.description}",
            "state_update": {
                "active_skill": skill_name,
                "skill_content": loaded.content,
            },
        }

    # ------------------------------------------------------------------
    # 渲染 SYSTEM_PROMPT
    # ------------------------------------------------------------------

    def render_system_prompt(self, state: SkillState) -> str:
        """使用 Jinja2 渲染最终的 SYSTEM_PROMPT.

        Args:
            state: 当前 Agent State

        Returns:
            渲染后的 SYSTEM_PROMPT
        """
        skill_content = state.get("skill_content", "")

        try:
            template = self._jinja_env.from_string(self._base_template)
            return template.render(skill_content=skill_content)
        except Exception as e:
            logger.error(f"SkillMiddleware: 渲染 SYSTEM_PROMPT 失败: {e}")
            # 降级：返回不含 Skill 的基础模板
            return self._base_template.replace(
                "{% if skill_content %}",
                "{% if False %}"
            )

    # ------------------------------------------------------------------
    # 内部: 构建 select_skill tool
    # ------------------------------------------------------------------

    def _build_select_skill_tool(self) -> BaseTool:
        """构建 select_skill 工具."""

        # 获取所有可用 Skill 的描述
        skills = self._loader.get_all_skills()
        skill_list = "\n".join(
            f"  - **{s.name}**: {s.title} — {s.description}"
            for s in skills
        )

        # 闭包捕获
        loader = self._loader

        @tool
        def select_skill(skill_name: str) -> str:
            """根据用户意图选择要加载的 Skill.

            Args:
                skill_name: Skill 名称。如果判断无需特定 Skill，传入空字符串或 "none"

            Returns:
                Skill 加载结果
            """
            # 实际逻辑在 wrap_tool_call 中处理
            # 这里只是占位，返回值会被 wrap_tool_call 覆盖
            return f"Loading skill: {skill_name}"

        # 动态更新 description
        select_skill.description = f"""\
根据用户当前的问题和意图，选择最合适的 Skill 来指导后续分析。

**决策规则**：
1. 分析用户消息中的关键词和意图
2. 如果用户意图明确对应某个 Skill → 选择该 Skill
3. 如果用户意图不明确或只是简单问候 → 传入空字符串表示无需加载
4. 如果 todos 列表中有未完成的任务，且当前已有活跃 Skill → 通常应继续使用当前 Skill

**可用 Skill 列表**：
{skill_list}

**参数说明**：
- skill_name: Skill 名称（如 "network_optimization"）。如果判断无需特定 Skill，传入空字符串 ""
"""

        return select_skill


# ---------------------------------------------------------------------------
# 工具函数: 获取动态过滤后的 tools
# ---------------------------------------------------------------------------

def filter_tools_for_state(
    tools: list[BaseTool],
    state: SkillState,
) -> list[BaseTool]:
    """根据 state 中的标记过滤 tools 列表.

    当 _skill_selection_enabled 为 False 时，移除 select_skill tool。
    """
    skill_selection_enabled = state.get("_skill_selection_enabled", False)

    if skill_selection_enabled:
        return tools  # 保留所有 tools
    else:
        # 移除 select_skill tool
        return [t for t in tools if t.name != "select_skill"]
```

### 3.4 集成到 core.py

```python
# backend/app/agent/core.py (修改后)

"""Agent core: builds the main Agent with middleware and tools."""

from __future__ import annotations

import logging
from pathlib import Path

from langchain.agents.middleware import ContextEditingMiddleware, ClearToolUsesEdit
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.middleware.chart_data import ChartDataMiddleware
from app.agent.middleware.data_table import DataTableMiddleware
from app.agent.middleware.missing_params import MissingParamsMiddleware
from app.agent.middleware.skill import SkillMiddleware
from app.agent.middleware.suggestions import SuggestionsMiddleware
from app.agent.prompts.base_prompt import BASE_SYSTEM_PROMPT
from app.agent.subagents import SubAgentMiddleware
from app.agent.subagents.agents.todo_tracker import TODO_TRACKER_CONFIG
from app.agent.tools.telecom_tools import register_telecom_tools
from app.agent.tools.hil import CustomHumanInTheLoopMiddleware
from app.agent.tools.knowledge import register_knowledge_tools
from app.agent.tools.registry import tool_registry
from app.config import settings

logger = logging.getLogger(__name__)

# Skills 目录路径
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "Skills"

# In-memory checkpointer for dev/validation stage
_checkpointer = InMemorySaver()

# Track whether tools have been registered
_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    register_telecom_tools()
    register_knowledge_tools()
    _initialized = True


def build_agent():
    """Build and return the main Agent (CompiledStateGraph)."""
    _ensure_initialized()

    all_tools = tool_registry.get_all_tools()
    hitl_config = tool_registry.get_hitl_config()
    param_edit_config = tool_registry.get_param_edit_config()

    # Skill Middleware（放在最前面，以便控制 SYSTEM_PROMPT）
    skill_mw = SkillMiddleware(
        skills_dir=str(SKILLS_DIR),
        base_prompt_template=BASE_SYSTEM_PROMPT,
    )
    # 注入 select_skill tool
    all_tools.extend(skill_mw.tools)

    # SubAgent Middleware（替代 TodoListMiddleware）
    subagent_mw = SubAgentMiddleware(
        delegated=[],
        reactive=[TODO_TRACKER_CONFIG],
    )
    # 注入 task() tool（如有委派式子 Agent）
    all_tools.extend(subagent_mw.tools)

    middleware = [
        skill_mw,  # Skill 选择（最高优先级）
        subagent_mw,
        DataTableMiddleware(),
        ChartDataMiddleware(),
        SuggestionsMiddleware(),
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=3000,
                    keep=2,
                    clear_tool_inputs=True,
                    exclude_tools=[
                        'search_design_doc',
                        'search_terminology',
                        'select_skill',  # 不清理 Skill 选择记录
                    ],
                    placeholder="[cleared]"
                ),
            ]
        )
    ]

    # Add MissingParams middleware when there are tools with param edit schema
    if param_edit_config:
        middleware.append(
            MissingParamsMiddleware(
                tools_with_param_edit=param_edit_config,
                description_prefix="请填写以下参数",
            )
        )

    # Only add HITL middleware when there are tools requiring it
    if hitl_config:
        middleware.append(
            CustomHumanInTheLoopMiddleware(
                interrupt_on=hitl_config,
                description_prefix="该操作需要您确认",
            )
        )

    # 配置 LLM
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        streaming=True
    )

    # 使用动态 SYSTEM_PROMPT（通过 Skill Middleware 渲染）
    agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=BASE_SYSTEM_PROMPT,  # 初始模板，运行时由 middleware 动态渲染
        middleware=middleware,
        checkpointer=_checkpointer,
    )
    return agent
```

## 4. Skill 文件示例

### 4.1 网络优化仿真分析 Skill

文件路径：`/Skills/network_optimization.md`

```markdown
---
name: network_optimization
title: 网络优化仿真分析
description: 完整的网络问题分析和优化仿真对比流程，适用于弱覆盖、干扰、容量等问题分析
triggers:
  - 弱覆盖
  - 干扰
  - 容量
  - 切换
  - 优化
  - 仿真
  - 根因分析
  - 网络问题
priority: 100
---

## 工具编排流程

按照以下顺序执行分析：

### 步骤 1：领域知识检索
- 调用 `search_terminology` 查询用户提及问题类型的术语和指标定义
- 调用 `search_design_doc` 获取对应的分析流程文档

### 步骤 2：场景匹配
- 调用 `match_scenario` 匹配数字孪生场景
- 获取 `digitaltwinsId` 用于后续查询

### 步骤 3：根因分析
- 调用 `query_root_cause_analysis` 查询根因分析结果
- 根据步骤 1 的术语检索结果，选择与用户问题相关的指标

### 步骤 4：固定提示（必须遵守）
展示根因分析结果后，**必须**输出以下固定提示语（一字不差）：

**"根因分析完成。是否需要对该场景进行优化仿真？"**

### 步骤 5：优化仿真（用户确认后）
- 调用 `query_simulation_results` 查询仿真结果

### 步骤 6：可视化对比（可选）
- 调用 `compare_simulation_data` 生成对比图表

## 指标选择规则

根据用户意图选择相关指标：

| 问题类型 | 相关指标 |
|---------|---------|
| 弱覆盖 | RSRP、MR覆盖率、覆盖电平 |
| 干扰 | SINR、RSRQ、重叠覆盖度 |
| 容量 | PRB利用率、下行流量、用户数 |

## 分析粒度

每次分析考虑两种粒度：
- **小区级(cell)**：以基站小区为最小分析单元
- **栅格级(grid)**：以地理栅格为最小分析单元

根据 `search_design_doc` 返回的流程文档，确定执行哪种粒度的分析。

## 图表类型选择

调用 `compare_simulation_data` 时选择合适的图表类型：
- `grouped_bar_chart`：分组柱状图（默认推荐）
- `line_chart`：折线图 — 展示趋势
- `stacked_bar_chart`：堆叠柱状图 — 总量对比
- `scatter_plot`：散点图 — 检测异常
- `heatmap`：热力图 — 大规模数据分布
- `table`：表格 — 查看精确数值
```

### 4.2 覆盖问题专项分析 Skill

文件路径：`/Skills/coverage_analysis.md`

```markdown
---
name: coverage_analysis
title: 覆盖问题专项分析
description: 专注于弱覆盖、信号盲区等覆盖类问题的深度分析
triggers:
  - 弱覆盖
  - 覆盖问题
  - 信号差
  - 盲区
  - RSRP
  - 覆盖率
priority: 90
---

## 覆盖问题分析流程

### 关键指标

覆盖分析主要关注以下指标：
- **RSRP(dBm)**：参考信号接收功率，主要覆盖质量指标
- **MR覆盖率(%)**：基于测量报告的覆盖率统计
- **覆盖电平(dBm)**：综合覆盖电平

### 问题定界

1. 弱覆盖判断标准：RSRP < -110 dBm
2. 覆盖率目标：MR覆盖率 ≥ 95%
3. 重点关注覆盖电平低于门限的区域

### 分析要点

- 识别弱覆盖热点区域
- 分析主服务小区配置
- 评估邻区关系是否合理
- 检查天馈参数（方位角、下倾角、功率）
```

## 5. 目录结构

```
WINSAgent/
├── Skills/                              # 新增: Skill 文件目录
│   ├── network_optimization.md          # 网络优化仿真分析
│   ├── coverage_analysis.md             # 覆盖问题分析
│   ├── interference_analysis.md         # 干扰问题分析
│   └── capacity_analysis.md             # 容量问题分析
├── backend/
│   └── app/
│       ├── agent/
│       │   ├── core.py                  # 修改: 集成 SkillMiddleware
│       │   ├── middleware/
│       │   │   ├── skill.py             # 新增: SkillMiddleware
│       │   │   └── ...
│       │   └── prompts/
│       │       └── base_prompt.py       # 新增: 基础 SYSTEM_PROMPT 模板
│       └── config.py                    # 修改: 添加 SKILLS_DIR 配置
└── ...
```

## 6. 配置项

在 `backend/app/config.py` 中添加：

```python
class Settings(BaseSettings):
    # ... 现有配置 ...

    # Skills
    skills_dir: str = str(Path(__file__).resolve().parent.parent.parent / "Skills")
```

在 `.env.example` 中添加：

```bash
# Skills 目录（可选，默认为项目根目录下的 Skills/）
# SKILLS_DIR=/path/to/skills
```

## 7. 执行流程详解

### 7.1 正常流程（用户新对话）

```
1. 用户发送: "帮我分析一下 A 区域的弱覆盖问题"
2. SkillMiddleware.before_model():
   - 检测到 HumanMessage
   - 无活跃 Skill，无未完成 todos
   - 设置 _skill_selection_enabled = True
3. LLM 收到带有 select_skill tool 的请求
4. LLM 决策调用: select_skill(skill_name="network_optimization")
5. SkillMiddleware.wrap_tool_call():
   - 加载 network_optimization.md
   - 更新 state.active_skill, state.skill_content
6. SYSTEM_PROMPT 通过 Jinja2 渲染，包含 Skill 内容
7. Agent 按照 Skill 中的流程执行分析
```

### 7.2 有未完成任务时

```
1. 用户发送: "继续分析"
2. SkillMiddleware.before_model():
   - 检测到 HumanMessage
   - 有活跃 Skill (network_optimization)
   - todos 中有 in_progress 任务
   - 设置 _skill_selection_enabled = False
3. select_skill tool 不可见
4. LLM 直接继续执行当前 Skill 的流程
```

### 7.3 非 HumanMessage

```
1. 工具返回结果 (ToolMessage)
2. SkillMiddleware.before_model():
   - 检测到非 HumanMessage
   - 设置 _skill_selection_enabled = False
3. select_skill tool 不可见
4. LLM 处理工具结果，继续执行
```

### 7.4 无需 Skill 的情况

```
1. 用户发送: "你好"
2. SkillMiddleware.before_model():
   - 检测到 HumanMessage
   - 无活跃 Skill
   - 设置 _skill_selection_enabled = True
3. LLM 分析意图，判断无需特定 Skill
4. LLM 调用: select_skill(skill_name="")
5. SkillMiddleware.wrap_tool_call():
   - 识别空字符串
   - 设置 state.active_skill = None
6. SYSTEM_PROMPT 渲染为默认模式（不含 Skill 内容）
7. LLM 以默认模式回复
```

## 8. 待确认事项

### 8.1 Skill 选择策略

**问题**：当用户意图可能匹配多个 Skill 时，如何选择？

采用选项 A，依赖 LLM 的判断能力。若后续需要更精细控制，可扩展为选项 B。

### 8.2 Skill 切换时机

**问题**：用户在对话中途明确要求切换分析类型时，如何处理？

采用选项 C，让 LLM 根据用户意图的强烈程度判断。若用户明确说"我想换一个..."则切换，若只是追问细节则继续当前 Skill。

### 8.3 Skill 内容的 Token 限制

**问题**：Skill 内容过长可能影响上下文窗口使用效率

初期采用选项 C，通过文档规范建议 Skill 内容控制在 1500 tokens 以内。

### 8.4 动态 SYSTEM_PROMPT 的实现方式

**问题**：LangChain create_agent 的 system_prompt 参数是否支持动态渲染？

**选项**：
- 使用 `wrap_model_call` hook 在每次 LLM 调用前替换 system prompt

### 8.5 Skill 热加载

**问题**：是否需要支持在运行时添加/修改 Skill 文件？

**选项**：
- A. 不支持，需要重启服务

## 9. 实现计划

### Phase 1: 基础架构
1. 创建 `/Skills` 目录
2. 实现 `SkillLoader` 类
3. 实现 `SkillMiddleware` 基础框架
4. 创建 `base_prompt.py` 模板

### Phase 2: 核心功能
1. 实现 `select_skill` tool
2. 实现 `before_model` hook 逻辑
3. 实现 `wrap_tool_call` hook 逻辑
4. 集成到 `core.py`

### Phase 3: Skill 迁移
1. 从现有 SYSTEM_PROMPT 提取业务流程内容
2. 创建 `network_optimization.md` Skill
3. 创建其他细分 Skill（可选）

### Phase 4: 测试与优化
1. 编写单元测试
2. 端到端测试
3. 性能优化（Skill 缓存、Token 控制）

## 10. 参考资料

- [LangChain AgentMiddleware 文档](https://docs.langchain.com/oss/python/langchain/middleware/custom)
- 现有实现参考：
  - `backend/app/agent/subagents/middleware.py` — SubAgentMiddleware
  - `backend/app/agent/middleware/missing_params.py` — MissingParamsMiddleware
  - `backend/app/agent/subagents/agents/todo_tracker.py` — TODO Tracker 配置
