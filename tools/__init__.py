"""Built-in tools and registration."""
import sys; sys.path.insert(0, '.')
from agent.tool.registry import registry


def register_all_tools() -> None:

    # 互联网搜索工具
    from tools.internet_search import TAVILY_SEARCH_SCHEMA, internet_search
    registry.register(
        name="internet_search",
        toolset="search",
        schema=TAVILY_SEARCH_SCHEMA,
        handler=lambda args, extra_args: internet_search(args, extra_args),
        is_async=False,
        emoji="🌐",
    )

    # TODO工具
    from tools.todo_tool import TODO_SCHEMA, todo_tool, check_todo_requirements
    registry.register(
        name="todo",
        toolset="todo",
        schema=TODO_SCHEMA,
        handler=lambda args, extra_args: todo_tool(
            todos=args.get("todos"), merge=args.get("merge", False), store=extra_args.get("store")
        ),
        check_fn=check_todo_requirements,
        emoji="📋",
    )

    # 主动记忆工具
    from tools.memory_tool import MEMORY_SCHEMA,memory_tool,check_memory_requirements
    registry.register(
        name="memory",
        toolset="memory",
        schema=MEMORY_SCHEMA,
        handler=lambda args, extra_args: memory_tool(
            action=args.get("action", ""),
            target=args.get("target", "memory"),
            content=args.get("content"),
            old_text=args.get("old_text"),
            store=extra_args.get("store"),
        ),
        check_fn=check_memory_requirements,
        emoji="🧠",
    )

    # 交互式澄清工具
    from tools.clarify_tool import CLARIFY_SCHEMA, clarify_tool, check_clarify_requirements
    registry.register(
        name="clarify",
        toolset="clarify",
        schema=CLARIFY_SCHEMA,
        handler=lambda args, extra_args: clarify_tool(
            question=args.get("question", ""),
            choices=args.get("choices"),
            callback=extra_args.get("callback")),
        check_fn=check_clarify_requirements,
        emoji="❓",
    )

    # 技能列表与查看（SKILL.md / 附属文件）
    from tools.skills_tool import check_skills_requirements, skill_view, skills_list, SKILLS_LIST_SCHEMA, SKILL_VIEW_SCHEMA
    registry.register(
        name="skills_list",
        toolset="skills",
        schema=SKILLS_LIST_SCHEMA,
        handler=lambda args, extra_args: skills_list(category=args.get("category")),
        check_fn=check_skills_requirements,
        emoji="📚",
    )
    registry.register(
        name="skill_view",
        toolset="skills",
        schema=SKILL_VIEW_SCHEMA,
        handler=lambda args, extra_args: skill_view(
            args.get("name", ""), file_path=args.get("file_path")
        ),
        check_fn=check_skills_requirements,
        emoji="📚",
    )

    # 技能管理工具
    from tools.skill_manager_tool import SKILL_MANAGE_SCHEMA, skill_manage
    registry.register(
        name="skill_manage",
        toolset="skills",
        schema=SKILL_MANAGE_SCHEMA,
        handler=lambda args, extra_args: skill_manage(
            action=args.get("action", ""),
            name=args.get("name", ""),
            content=args.get("content"),
            category=args.get("category"),
            file_path=args.get("file_path"),
            file_content=args.get("file_content"),
            old_string=args.get("old_string"),
            new_string=args.get("new_string"),
            replace_all=args.get("replace_all", False),
            absorbed_into=args.get("absorbed_into"),
        ),
        emoji="📝",
    )

    # BackendProtocol 文件工具（默认 FilesystemBackend，虚拟绝对路径 /...）
    from tools.backend_file_tools import register_backend_file_tools
    register_backend_file_tools()
