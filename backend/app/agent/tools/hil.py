from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.runtime import Runtime
from langgraph.typing import ContextT


class CustomHumanInTheLoopMiddleware(HumanInTheLoopMiddleware):
    def before_agent(self,state: AgentState[Any], runtime: Runtime[ContextT])-> dict[str, Any] | None:
        super().before_agent(state, runtime)