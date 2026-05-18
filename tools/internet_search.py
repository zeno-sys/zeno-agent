from tavily import TavilyClient
from pydantic import BaseModel
from typing import Literal, Any
import json
from dotenv import load_dotenv
import os
load_dotenv()



tavily_client: TavilyClient = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))  # 使用 tavily 的搜索引擎

class InternetSearchInput(BaseModel):
    query: str
    max_results: int = 5
    topic: Literal["general", "news", "finance"] = "general"
    include_raw_content: bool = False

# Create a search tool
def internet_search(args: dict,extra_args: dict):
    input = InternetSearchInput.model_validate(args)
    """Run a web search"""
    results = tavily_client.search(
        input.query,
        max_results=input.max_results,
        include_raw_content=input.include_raw_content,
        topic=input.topic,
    )
    return json.dumps(results, ensure_ascii=False, indent=2)


TAVILY_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "internet_search",
        "description": "Run a web search",
        "parameters": InternetSearchInput.model_json_schema(),
    },
}