"""skills_list / skill_view 流程测试（打印风格对齐原 skills_tool __main__ 演示）"""

from __future__ import annotations

import json
import sys

from tools.skills_tool import skill_view, skills_list


def test_skills_list_and_skill_view_demo_flow() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("🎯 Skills Tool Test")
    print("=" * 60)

    print("\n📋 Listing all skills:")
    result = json.loads(skills_list())
    if result["success"]:
        print(
            f"Found {result['count']} skills in {len(result.get('categories', []))} categories"
        )
        print(f"Categories: {result.get('categories', [])}")
        print("\nFirst 10 skills:")
        for skill in result["skills"][:10]:
            cat = f"[{skill['category']}] " if skill.get("category") else ""
            print(f"  • {cat}{skill['name']}: {skill['description'][:60]}...")
    else:
        print(f"Error: {result['error']}")
    assert result.get("success") is True, result
    assert result["count"] >= 1, result
    assert "himalaya" in {s["name"] for s in result["skills"]}, result

    print("\n📖 Viewing skill 'himalaya':")
    result = json.loads(skill_view("himalaya"))
    if result["success"]:
        print(f"Name: {result['name']}")
        print(f"Description: {result.get('description', 'N/A')[:100]}...")
        print(f"Content length: {len(result['content'])} chars")
        if result.get("linked_files"):
            print(f"Linked files: {result['linked_files']}")
    else:
        print(f"Error: {result['error']}")
    assert result.get("success") is True, result
    assert result["name"] == "himalaya", result
    lf = result.get("linked_files") or {}
    assert "references" in lf, result
    assert any("configuration.md" in p.replace("\\", "/") for p in lf["references"]), result

    print("\n📄 Viewing reference file 'himalaya/references/configuration.md':")
    result = json.loads(skill_view("himalaya", "references/configuration.md"))
    if result["success"]:
        print(f"File: {result['file']}")
        print(f"Content length: {len(result['content'])} chars")
        print(f"Preview: {result['content'][:150]}...")
    else:
        print(f"Error: {result['error']}")
    assert result.get("success") is True, result
    assert result.get("file") == "references/configuration.md", result
    assert "Himalaya Configuration" in result["content"], result
