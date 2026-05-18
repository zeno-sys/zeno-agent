from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Callable

from typing import Any


# 用于移除BaseModel转Json Schema时添加的title字段
def strip_schema_title_fields(schema: Any, in_properties: bool = False) -> Any:
    """Remove descriptive `title` keys from JSON schema.

    Keep `title` when it is used as a field name under `properties`.
    """
    if isinstance(schema, dict):
        cleaned: dict[str, Any] = {}
        for key, value in schema.items():
            if key == "title" and not in_properties:
                continue
            cleaned[key] = strip_schema_title_fields(
                value,
                in_properties=(key == "properties"),
            )
        return cleaned

    if isinstance(schema, list):
        return [strip_schema_title_fields(item, in_properties=False) for item in schema]

    return schema


class OpenAIFunctionSchema(BaseModel):
    name: str
    description: str
    parameters: dict

    @model_validator(mode="before")
    def _strip_parameters_titles(cls, data: Any) -> Any:
        if isinstance(data, dict) and "parameters" in data:
            data["parameters"] = strip_schema_title_fields(data["parameters"])
        return data



class OpenAIToolSchema(BaseModel):
    type: str = "function"
    function: OpenAIFunctionSchema



class ToolEntry(BaseModel):
    """Metadata for a single registered tool."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str                            # 工具在注册表里的主键
    toolset: str                         # 工具所属的工具集（逻辑分组）
    tool_schema: OpenAIToolSchema
    handler: Callable
    check_fn: Callable | None = None     # 可选的可用性检查
    requires_env: list[str] = Field(default_factory=list)
    is_async: bool = False
    description: str = ""                # 人类可读说明
    emoji: str = ""                      # 展示用图标字符串
    max_result_size_chars: int | float | None = None


if __name__ == "__main__":
    import json
    from pydantic import BaseModel, Field
    from typing import Literal
    

    class Address(BaseModel):
        title: str = Field(description="The title of the address") # 测试title字段是否会被删除
        street: str = Field(description="The street address")
        city: str = Field(description="The city")
        state: str = Field(description="The state")
        zip: str = Field(description="The zip code")

    class InternetSearchInput(BaseModel):
        query: str = Field(description="The query to search for")
        max_results: int = Field(description="The maximum number of results to return", default=5, ge=1, le=10)
        topic: Literal["general", "news", "finance"] = "general"
        include_raw_content: bool = False

    tool_schema = OpenAIToolSchema(
        function=OpenAIFunctionSchema(
            name="internet_search",
            description="Search the internet for information",
            parameters=InternetSearchInput.model_json_schema(),
        )
    )
    print(json.dumps(tool_schema.model_dump(), ensure_ascii=False, indent=2))