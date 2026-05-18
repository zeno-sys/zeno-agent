"""工具实现共用的路径校验辅助函数。

将原先分散在 skill_manager_tool、skills_tool、skills_hub、cronjob_tools、credential_files
等处的 ``resolve()`` + ``relative_to()`` 以及 ``..`` 穿越检测模式集中到此模块。
"""
from pathlib import Path
from typing import Optional



def validate_within_dir(path: Path, root: Path) -> Optional[str]:
    """确认 *path* 解析后落在 *root* 目录树内。

    校验失败返回错误说明字符串，安全则返回 ``None``。使用 ``Path.resolve()`` 跟随符号链接并
    规范化 ``..`` 等分量。
    """
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (ValueError, OSError) as exc:
        return f"Path escapes allowed directory: {exc}"
    return None


def has_traversal_component(path_str: str) -> bool:
    """若 *path_str* 的路径分量中含 ``..`` 则返回 True。

    在完整 ``resolve()`` 之前对明显目录穿越的快速检查。
    """
    parts = Path(path_str).parts
    return ".." in parts
