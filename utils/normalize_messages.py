#!/usr/bin/env python3
"""
normalize_messages_openai.py - OpenAI版本的消息规范化工具
适配OpenAI的消息格式和工具调用结构
"""

from typing import Any

import json

from agent.core.multimodal import is_openai_multimodal_content, merge_openai_content


def normalize_messages_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    清理和规范化OpenAI格式的消息列表
    
    OpenAI消息格式：
    - 角色: "system", "user", "assistant", "tool"
    - 内容: 可以是字符串或包含工具调用的数组
    - 工具响应: {"role": "tool", "content": "...", "tool_call_id": "..."}
    
    主要工作：
    1. 清理内部元数据字段
    2. 补全缺失的工具调用响应
    3. 规范化消息格式
    4. 合并连续的同角色消息
    """
    
    if not messages:
        return []
    
    # 阶段1: 基础检查
    cleaned_messages = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
            
        # 检查必需字段
        role = msg.get("role")
        if role not in ["system", "user", "assistant", "tool"]:
            continue

        # 清理内部元数据字段（约定以下划线开头）
        for key in list(msg.keys()):
            if isinstance(key, str) and key.startswith("_"):
                msg.pop(key, None)

        # 规范化 content 字段
        if "content" in msg:
            content = msg["content"]
            if content is None:
                msg["content"] = ""
            elif isinstance(content, str):
                msg["content"] = content
            elif is_openai_multimodal_content(content):
                msg["content"] = list(content)
            else:
                msg["content"] = str(content)

        # 流式聚合或旧会话里 function.arguments 可能为 "" 或非 JSON；网关常按 JSON 解析会 400
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function")
                if not isinstance(fn, dict):
                    continue
                raw = fn.get("arguments")
                if raw is None or (isinstance(raw, str) and not raw.strip()):
                    fn["arguments"] = "{}"
                elif isinstance(raw, str):
                    try:
                        json.loads(raw)
                    except json.JSONDecodeError:
                        fn["arguments"] = "{}"

        cleaned_messages.append(msg)

    # 阶段2: 收集现有的工具调用ID
    existing_tool_call_ids = set()
    for msg in cleaned_messages:
        if msg["role"] == "tool" and "tool_call_id" in msg:
            existing_tool_call_ids.add(msg["tool_call_id"])
    
    # 阶段3: 补全缺失的工具调用响应(确保工具调用有对应的响应)
    messages_to_insert = []
    for i, msg in enumerate(cleaned_messages):
        if msg["role"] == "assistant" and "tool_calls" in msg:
            tool_calls = msg.get("tool_calls", [])
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    call_id = tool_call.get("id")
                    if call_id and call_id not in existing_tool_call_ids:
                        # 这个工具调用没有对应的响应，需要补全
                        placeholder_response = {
                            "role": "tool",
                            "content": "(cancelled)",   # 告诉AI这个调用被取消了
                            "tool_call_id": call_id
                        }
                        messages_to_insert.append((i + 1, placeholder_response))
    
    # 在适当位置插入占位响应
    for offset, (insert_index, placeholder) in enumerate(messages_to_insert):
        actual_index = insert_index + offset
        if actual_index <= len(cleaned_messages):
            cleaned_messages.insert(actual_index, placeholder)
    
    # 阶段4: 合并连续的同角色消息
    if not cleaned_messages:
        return []
    
    merged_messages = [cleaned_messages[0]] 
    
    for msg in cleaned_messages[1:]:
        prev_msg = merged_messages[-1]  # 上一个消息
        
        # 4.1 检查是否可以合并
        can_merge = (
            msg["role"] == prev_msg["role"] and
            "tool_calls" not in msg and        # 当前消息不能包含工具调用
            "tool_calls" not in prev_msg and   # 上一个消息不能包含工具调用
            "tool_call_id" not in msg and      # 当前消息不能包含工具调用ID
            "tool_call_id" not in prev_msg     # 上一个消息不能包含工具调用ID
        )
        
        if can_merge:
            prev_content = prev_msg.get("content", "")
            curr_content = msg.get("content", "")
            prev_msg["content"] = merge_openai_content(prev_content, curr_content)
        else:
            merged_messages.append(msg)
    
    return merged_messages
