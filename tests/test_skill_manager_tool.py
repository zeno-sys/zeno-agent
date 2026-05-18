"""skill_manage 各 action 流程测试（原 skill_manager_tool.py __main__ 演示）"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.skill import skill_utils
from tools import skill_manager_tool as smt
from tools.skill_manager_tool import skill_manage


@pytest.fixture
def isolated_skills_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """将技能根目录指向临时目录，避免污染仓库内 skills/。"""
    root = tmp_path / "skills"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(smt, "SKILLS_DIR", root)
    monkeypatch.setattr(skill_utils, "get_all_skills_dirs", lambda: [root])
    return root


def _ok(payload: str, *, banner: str | None = None) -> dict:
    if banner:
        print(f"--------------------------------{banner}--------------------------------")
        print(payload)
    data = json.loads(payload)
    assert data.get("success") is True, data
    return data


def test_skill_manage_demo_flow(isolated_skills_dir: Path) -> None:
    print(f"--------------------------------temp skills root--------------------------------\n{isolated_skills_dir}")

    _demo_skill_md = """---
name: test_skill
description: test_description
---

## Steps

- step1
- step2
- step3
"""

    _ok(skill_manage(action="create", name="test_skill", content=_demo_skill_md), banner="create skill")

    _ok(
        skill_manage(
            action="create",
            name="test_skill_categorized",
            category="examples",
            content="""---
name: test_skill_categorized
description: Same shape as test_skill, nested under a category folder.
---

## Steps

- step1
- step2
""",
        ),
        banner="create skill (with category)",
    )

    _ok(
        skill_manage(
            action="edit",
            name="test_skill",
            content="""---
name: test_skill
description: test_description (edited)
---

## Steps

- step1
- step2
- step3
- step4
""",
        ),
        banner="edit skill",
    )

    _ok(
        skill_manage(
            action="patch",
            name="test_skill",
            old_string="- step3",
            new_string="- step3 (patched)",
        ),
        banner="patch skill (SKILL.md)",
    )

    _ok(
        skill_manage(
            action="write_file",
            name="test_skill",
            file_path="references/notes.md",
            file_content="# Notes\n\nSupporting material for test_skill.\n",
        ),
        banner="write_file",
    )

    _ok(
        skill_manage(
            action="patch",
            name="test_skill",
            file_path="references/notes.md",
            old_string="Supporting material",
            new_string="Reference notes",
        ),
        banner="patch skill (supporting file)",
    )

    _ok(
        skill_manage(
            action="patch",
            name="test_skill",
            file_path="references/notes.md",
            old_string="test_skill",
            new_string="test_skill_demo",
            replace_all=True,
        ),
        banner="patch skill (replace_all)",
    )

    _ok(
        skill_manage(action="remove_file", name="test_skill", file_path="references/notes.md"),
        banner="remove_file",
    )

    _ok(
        skill_manage(
            action="create",
            name="skill_mgr_example_umbrella",
            content="""---
name: skill_mgr_example_umbrella
description: Umbrella skill for absorbed_into delete demo.
---

## Body

Placeholder.
""",
        ),
        banner="create skill (umbrella for absorbed_into demo)",
    )
    _ok(
        skill_manage(
            action="create",
            name="skill_mgr_example_leaf",
            content="""---
name: skill_mgr_example_leaf
description: Leaf skill merged into umbrella; delete names absorbed_into target.
---

## Body

To be removed after consolidation delete.
""",
        ),
        banner="create skill (leaf for absorbed_into demo)",
    )
    _ok(
        skill_manage(
            action="delete",
            name="skill_mgr_example_leaf",
            absorbed_into="skill_mgr_example_umbrella",
        ),
        banner="delete skill (consolidate, absorbed_into=<existing>)",
    )
    _ok(
        skill_manage(action="delete", name="skill_mgr_example_umbrella", absorbed_into=""),
        banner="delete skill (umbrella, prune absorbed_into=\"\")",
    )

    _ok(
        skill_manage(action="delete", name="test_skill_categorized", absorbed_into=""),
        banner="delete skill (prune, absorbed_into=\"\")",
    )

    _ok(
        skill_manage(action="delete", name="test_skill"),
        banner="delete skill (legacy, no absorbed_into)",
    )

    assert not (isolated_skills_dir / "test_skill").exists()
    assert not (isolated_skills_dir / "examples").exists() or not any(
        (isolated_skills_dir / "examples").iterdir()
    )
