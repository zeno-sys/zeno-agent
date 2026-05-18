from pathlib import Path
import os
import datetime
import platform

from constants import get_workspace_path



SYSTEM = f"""你是一个通用助手，当前工作目录为 {get_workspace_path()}.
可以使用 todo 工具进行多步骤工作。在任务有多个步骤时，始终保持恰好有一个步骤处于 in_progress 状态，随着工作进展及时刷新计划。优先使用工具而非文字描述。

遇到特殊任务时，可以使用 run_subagent_tool 工具来执行子 Agent，以获得更加专业的结果。

在执行某项操作前，如果需要专门的操作说明，可以使用 load_skill 工具获取该技能的详细说明。
"""

class SystemPromptBuilder:
    """
    # 将系统提示分为独立的多个部分拼接而成。
    # 系统提示词不是一整块大字符串，而是一条可维护的组装流水线。
    """
    def __init__(
        self,
        workdir: Path = None,
        tools: list = None,
        model: str = None,
        # skills_registry: SkillRegistry = None,
        # memory_manager: SQLiteMemoryManager = None,
    ):
        self.workdir = workdir
        self.tools = tools or []
        self.model = model
        # self.skills_registry = skills_registry
        # self.memory_manager = memory_manager
    # -- Section 1: Core instructions --
    def _build_core(self) -> str:
        return SYSTEM
    # -- Section 2: Tool listings --
    def _build_tool_listing(self) -> str:
        return self.tools
    # # -- Section 3: Skill metadata (layer 1 from s05 concept) --
    # def _build_skill_listing(self) -> str:
    #     if not self.skills_registry:
    #         return ""
    #     return self.skills_registry.format_skills_for_system()
    # # -- Section 4: Memory content --
    # def _build_memory_section(self) -> str:
    #     if not self.memory_manager:
    #         return ""
    #     self.memory_manager.load_all()
    #     memory_section = self.memory_manager.load_memory_prompt()
    #     if memory_section:
    #         return memory_section
        return ""
    # -- Section 5: agent.md chain --
    def _build_agent_md(self) -> str:
        """
        按优先级顺序加载 agent.md 配置文件:
        1. ~/.zeno_agent/agent.md (user-global instructions)
        2. <project-root>/agent.md (project instructions)
        3. <current-subdir>/agent.md (directory-specific instructions)
        """
        sources = []
        # User-global
        user_agent = Path.home() / ".zeno_agent" / "agent.md"
        if user_agent.exists():
            sources.append(("user global (~/.zeno_agent/agent.md)", user_agent.read_text(encoding="utf-8")))
        # Project root
        project_agent = self.workdir / "agent.md"
        if project_agent.exists():
            sources.append(("project root (agent.md)", project_agent.read_text(encoding="utf-8")))
        # Subdirectory -- in real CC, this walks from cwd up to project root
        # Teaching: check cwd if different from workdir
        cwd = Path.cwd()
        if cwd != self.workdir:
            subdir_agent = cwd / "agent.md"
            if subdir_agent.exists():
                sources.append((f"subdir ({cwd.name}/agent.md)", subdir_agent.read_text(encoding="utf-8")))
        if not sources:
            return ""
        parts = ["# agent.md instructions"]
        for label, content in sources:
            parts.append(f"## From {label}")
            parts.append(content.strip())
        return "\n\n".join(parts)
    # -- Section 6: Dynamic context --
    def _build_dynamic_context(self) -> str:
        system_name = platform.system() or os.name
        lines = [
            f"Current datetime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Working directory: {self.workdir}",
            f"Model: {self.model}",
            f"Platform: {system_name}",
        ]
        return "\n".join(lines)

    def _wrap_section(self, tag: str, content: str) -> str:
        tag_name = tag.upper()
        return f"<{tag_name}>\n{content.strip()}\n</{tag_name}>"
    # -- Assemble all sections --
    def build(self) -> str:
        sections = []
        core = self._build_core()
        if core:
            sections.append(self._wrap_section("core", core))

        # skills = self._build_skill_listing()
        # if skills:
        #     sections.append(self._wrap_section("skills", skills))

        # memory = self._build_memory_section()
        # if memory:
        #     sections.append(self._wrap_section("memory", memory))

        agent_md = self._build_agent_md()
        if agent_md:
            sections.append(self._wrap_section("instructions", agent_md))

        dynamic = self._build_dynamic_context()
        if dynamic:
            sections.append(self._wrap_section("dynamic_context", dynamic))
        return "\n\n".join(sections)
    


if __name__ == "__main__":
    builder = SystemPromptBuilder(
        workdir=Path.cwd(), 
        model="gpt-4o",
    )
    print(builder.build())