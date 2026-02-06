"""SkillMiddleware: 动态加载 Skill 内容到 SYSTEM_PROMPT.

根据用户意图智能选择并加载对应的 Skill 文件，通过 Jinja2 模板
渲染最终的系统提示词。

核心机制：
- 通过 wrap_model_call hook 动态控制 tools 和 system_prompt
- 仅在 HumanMessage 且无活跃任务时显示 select_skill tool
- 使用 ToolRuntime 访问 Store 进行 Skill 内容缓存
- 使用 Jinja2 模板渲染 system_prompt
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Union, Awaitable

import yaml
from jinja2 import Environment, BaseLoader
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ModelCallResult, AgentState
from langchain.messages import ToolMessage
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

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


# ---------------------------------------------------------------------------
# 全局 SkillLoader 实例（模块级别，供 tool 访问）
# ---------------------------------------------------------------------------

_skill_loader: SkillLoader | None = None


def _get_skill_loader() -> SkillLoader:
    """获取全局 SkillLoader 实例."""
    global _skill_loader
    if _skill_loader is None:
        raise RuntimeError("SkillLoader 未初始化，请先创建 SkillMiddleware")
    return _skill_loader


# ---------------------------------------------------------------------------
# select_skill Tool（使用 ToolRuntime 访问 Store）
# ---------------------------------------------------------------------------

@tool
def select_skill(skill_name: str, runtime: ToolRuntime) -> Command:
    """根据用户意图选择要加载的 Skill.

    根据用户当前的问题和意图，选择最合适的 Skill 来指导后续分析。

    **决策规则**：
    1. 分析用户消息中的关键词和意图
    2. 如果用户意图明确对应某个 Skill → 选择该 Skill
    3. 如果用户意图不明确或只是简单问候/闲聊 → 传入空字符串表示无需加载
    4. 如果 todos 列表中有未完成的任务，且当前已有活跃 Skill → 通常应继续使用当前 Skill

    Args:
        skill_name: Skill 名称。如果判断无需特定 Skill，传入空字符串 ""

    Returns:
        Command 包含 ToolMessage 和状态更新
    """
    loader = _get_skill_loader()
    store = runtime.store

    # 处理"无需特定 Skill"的情况
    if not skill_name or skill_name.lower() in ("none", "null", ""):
        logger.info("SkillMiddleware: LLM 选择不加载特定 Skill")
        if store:
            store.put(
                ("skills",),
                "active_skill",
                {
                    "name": None,
                    "description": None
                }
            )

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="已确认不加载特定 Skill，使用默认模式。",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    # 加载 Skill
    loaded = loader.load_skill(skill_name)
    if not loaded:
        available = ", ".join(s.name for s in loader.get_all_skills())
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Skill '{skill_name}' 不存在。可用 Skill: {available}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    logger.info(
        f"SkillMiddleware: 加载 Skill '{skill_name}' ({loaded.meta.title})"
    )

    # 将 Skill 内容存入 Store（长期缓存）
    if store:
        store.put(
            ("skills", ),
            "active_skill",
            {
                "name": skill_name,
                "title": loaded.meta.title,
                "description": loaded.meta.description,
                "content": loaded.content,
            }
        )

    # 返回 Command 更新状态
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"已加载 Skill: {loaded.meta.title}\n\n{loaded.meta.description}",
                    tool_call_id=runtime.tool_call_id,
                )
            ]
        }
    )


# ---------------------------------------------------------------------------
# SkillMiddleware
# ---------------------------------------------------------------------------

class SkillMiddleware(AgentMiddleware):
    """Skill 动态加载 Middleware.

    功能：
    1. 通过 wrap_model_call 动态控制 tools 和 system_prompt
    2. 仅在 HumanMessage 且无活跃任务时显示 select_skill tool
    3. 使用 ToolRuntime 在 select_skill 中访问 Store
    4. 通过 Jinja2 模板渲染 system_prompt
    """

    name: str = "skill"

    # 注册 tools 为类变量（按照 Skill参考.md 推荐模式）
    tools = [select_skill]

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
        global _skill_loader
        self._loader = SkillLoader(skills_dir)
        _skill_loader = self._loader  # 设置全局引用供 tool 使用

        self._base_template = base_prompt_template
        self._jinja_env = Environment(loader=BaseLoader())
        self._skills_prompt = self._build_skills_prompt()

        # 更新 select_skill tool 的 description
        self._update_tool_description()

        logger.info(f"SkillMiddleware: 初始化完成, skills_dir={skills_dir}")

    def _build_skills_prompt(self) -> str:
        """构建可用 Skill 列表的提示文本."""
        skills = self._loader.get_all_skills()
        if not skills:
            return "（暂无可用 Skill）"

        skills_list = []
        for skill in skills:
            skills_list.append(
                f"- **{skill.name}**: {skill.title} — {skill.description}"
            )
        return "\n".join(skills_list)

    def _update_tool_description(self) -> None:
        """更新 select_skill tool 的动态描述."""
        # 动态更新 tool description 包含可用 Skill 列表
        select_skill.description = f"""\
根据用户当前的问题和意图，选择最合适的 Skill 来指导后续分析。

**决策规则**：
1. 分析用户消息中的关键词和意图
2. 如果用户意图明确对应某个 Skill → 选择该 Skill
3. 如果用户意图不明确或只是简单问候/闲聊 → 传入空字符串表示无需加载
4. 如果 todos 列表中有未完成的任务，且当前已有活跃 Skill → 通常应继续使用当前 Skill

**可用 Skill 列表**：
{self._skills_prompt}

**参数说明**：
- skill_name: Skill 名称（如 "network_optimization"）。如果判断无需特定 Skill，传入空字符串 ""
"""

    # ------------------------------------------------------------------
    # Middleware Hook: wrap_model_call
    # ------------------------------------------------------------------
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """在每次 LLM 调用前动态控制 tools 和 system_prompt.

        判断逻辑：
        1. 检测最后一条消息是否为 HumanMessage
        2. 检测是否有活跃 Skill 和未完成 todos
        3. 动态过滤 select_skill tool
        4. 通过 Jinja2 渲染包含 Skill 内容的 system_prompt
        """
        modified_request = self._wrap_model_call(request)
        return handler(modified_request)

    def _wrap_model_call(self, request):
        state = request.state
        messages = state.get("messages", [])
        # 判断是否为 HumanMessage
        is_human_message = False
        if messages:
            last_message = messages[-1]
            is_human_message = isinstance(last_message, HumanMessage) or (
                    hasattr(last_message, "type") and
                    getattr(last_message, "type", None) == "human"
            )
        # 获取当前状态
        todos = state.get("todos", [])
        has_pending_todos = any(
            t.get("status") in ("pending", "in_progress")
            for t in todos
        )
        # 获取 Skill 内容并渲染 system_prompt
        active_skill, skill_content = self._get_skill(request)
        # 决策：是否需要显示 select_skill tool
        need_skill_selection = False
        if is_human_message:
            if has_pending_todos and active_skill:
                # 有未完成任务且有活跃 Skill → 复用当前 Skill，不显示 select_skill
                logger.debug(
                    f"SkillMiddleware: 复用当前 Skill '{active_skill}' "
                    f"(有 {sum(1 for t in todos if t.get('status') != 'completed')} 个未完成任务)"
                )
                need_skill_selection = False
            else:
                # 新对话或无活跃 Skill → 需要选择
                need_skill_selection = True
        else:
            # 非 HumanMessage（如 ToolMessage、AIMessage）→ 不显示 select_skill
            need_skill_selection = False
        # 过滤 tools
        current_tools = list(request.tools) if request.tools else []
        if not need_skill_selection:
            # 移除 select_skill tool
            current_tools = [t for t in current_tools if t.name != "select_skill"]
        rendered_prompt = self._render_system_prompt(skill_content)
        # 使用 override 修改请求
        modified_request = request.override(
            tools=current_tools,
            system_message=SystemMessage(content=rendered_prompt)
        )
        return modified_request

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        modified_request = self._wrap_model_call(request)
        return await handler(modified_request)

    def _get_skill(
        self,
        request: ModelRequest,
    ) -> Union[(str, str), None]:
        """获取当前活跃 Skill 的内容.

        优先从 Store 读取缓存的 Skill 内容，否则从 Loader 加载。

        Args:
            request: 当前请求（用于访问 store）

        Returns:
            Skill 内容，或 None
        """
        skill_content = None
        active_skill = None

        # 尝试从 Store 读取缓存
        try:
            store = request.runtime.store
            if store:
                cached = store.get(("skills", ), "active_skill")
                if cached and cached.value:
                    active_skill = cached.value.get("name")
                    skill_content = cached.value.get("content")
        except Exception as e:
            logger.debug(f"从 Store 读取 Skill 缓存失败: {e}")

        # 如果 Store 没有缓存，从 Loader 加载
        if not skill_content:
            loaded = self._loader.load_skill(active_skill)
            if loaded:
                skill_content = loaded.content

        return active_skill,skill_content

    def _render_system_prompt(self, skill_content: str | None) -> str:
        """使用 Jinja2 渲染最终的 SYSTEM_PROMPT.

        Args:
            skill_content: Skill 内容，可为空

        Returns:
            渲染后的 SYSTEM_PROMPT
        """
        try:
            template = self._jinja_env.from_string(self._base_template)
            return template.render(skill_content=skill_content or "")
        except Exception as e:
            logger.error(f"SkillMiddleware: 渲染 SYSTEM_PROMPT 失败: {e}")
            # 降级：返回不含 Skill 的基础模板
            try:
                template = self._jinja_env.from_string(self._base_template)
                return template.render(skill_content="")
            except Exception:
                return self._base_template
