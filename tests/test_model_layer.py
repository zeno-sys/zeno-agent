from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from model_layer.client import ModelClient
from model_layer.config import ModelLayerConfig, ProviderConfig, TaskConfig
from model_layer.factory import reset_default_model_client
from model_layer.middleware.rate_limit import RateLimitMiddleware
from model_layer.router import ModelRouter
from model_layer.types import ModelRequest, ModelResponse, ResolvedRoute, TASK_AGENT, TASK_AUXILIARY


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_default_model_client(None)
    yield
    reset_default_model_client(None)


def test_router_normalizes_title_task_alias():
    '''测试路由器是否正确地规范化标题任务别名'''
    cfg = ModelLayerConfig(
        tasks={
            TASK_AGENT: TaskConfig(provider="default", model="main-model"),
            TASK_AUXILIARY: TaskConfig(provider="default", model="cheap-model"),
        },
        providers={
            "default": ProviderConfig(base_url="http://test", api_key="k"),
        },
    )
    router = ModelRouter(cfg)
    route = router.resolve(
        ModelRequest(task="title_generation", messages=[{"role": "user", "content": "hi"}])
    )
    print(route.__dict__)
    assert route.model == "cheap-model"


def test_router_injects_session_id_for_agent():
    '''测试路由器是否正确地注入会话 ID 用于代理任务'''
    cfg = ModelLayerConfig(
        tasks={TASK_AGENT: TaskConfig(provider="default", model="m")},
        providers={"default": ProviderConfig()},
    )
    router = ModelRouter(cfg)
    route = router.resolve(
        ModelRequest(
            task=TASK_AGENT,
            messages=[],
            metadata={"session_id": "sess-1"},
        )
    )
    print(route.__dict__)
    assert route.extra_body.get("session_id") == "sess-1"


def test_rate_limit_middleware_blocks_burst():
    '''测试速率限制中间件是否正确地阻止突发请求'''
    mw = RateLimitMiddleware()

    # 设置任务agent的速率限制为2次/分钟
    mw.set_task_rpm(TASK_AGENT, 2)
    route = ResolvedRoute(provider_id="default", model="m")
    req = ModelRequest(task=TASK_AGENT, messages=[])

    # 模拟一个成功的响应
    def ok() -> ModelResponse:
        return ModelResponse(raw=MagicMock(usage=None))
    # 第1次请求成功
    mw.wrap_complete(req, route, ok)
    # 第2次请求成功
    mw.wrap_complete(req, route, ok)
    # 第3次请求失败，因为超过速率限制
    with pytest.raises(RuntimeError, match="rate limit"):
        mw.wrap_complete(req, route, ok)


def test_rate_limit_sliding_window_allows_after_window(monkeypatch):
    '''测试滑动窗口速率限制是否在窗口结束后允许新的请求'''


    mw = RateLimitMiddleware()
    # 设置任务agent的速率限制为1次/分钟
    mw.set_task_rpm(TASK_AGENT, 1)
    route = ResolvedRoute(provider_id="default", model="m")
    req = ModelRequest(task=TASK_AGENT, messages=[])

    t = [1000.0]

    def fake_time():
        return t[0]

    monkeypatch.setattr(time, "time", fake_time)

    def ok() -> ModelResponse:
        return ModelResponse(raw=MagicMock(usage=None))

    mw.wrap_complete(req, route, ok)
    with pytest.raises(RuntimeError):
        mw.wrap_complete(req, route, ok)

    t[0] = 1061.0
    mw.wrap_complete(req, route, ok)


class _FakeProvider:
    def __init__(self) -> None:
        self.stream_calls = 0

    def complete(self, route: ResolvedRoute, req: ModelRequest) -> ModelResponse:
        raw = MagicMock()
        raw.choices = [MagicMock(message=MagicMock(content="ok"))]
        raw.usage = MagicMock(total_tokens=10)
        return ModelResponse(raw=raw, usage=raw.usage)

    def stream(self, route: ResolvedRoute, req: ModelRequest) -> Iterator[Any]:
        self.stream_calls += 1
        chunk = MagicMock()
        chunk.choices = []
        chunk.usage = None
        yield chunk

    def complete_structured(self, route: ResolvedRoute, req: ModelRequest) -> ModelResponse:
        return self.complete(route, req)


def test_model_client_stream_pipeline():
    '''测试模型客户端的流式管道是否正确'''
    cfg = ModelLayerConfig(
        tasks={TASK_AGENT: TaskConfig(provider="default", model="m", stream=True)},
        providers={"default": ProviderConfig()},
    )
    # 模拟一个提供商
    fake = _FakeProvider()
    # 创建模型客户端
    client = ModelClient(ModelRouter(cfg), {"default": fake}, middlewares=[])
    chunks = list(
        client.stream(
            ModelRequest(task=TASK_AGENT, messages=[], stream=True),
        )
    )
    assert len(chunks) == 1
    assert fake.stream_calls == 1


def test_router_merges_provider_default_extra_body():
    '''测试路由器是否正确地合并提供商的默认额外参数'''
    
    # 创建模型层配置
    cfg = ModelLayerConfig(
        tasks={TASK_AGENT: TaskConfig(provider="default", model="m")},
        providers={
            "default": ProviderConfig(
                default_extra_body={"enable_thinking": False},
            ),
        },
    )
    route = ModelRouter(cfg).resolve(
        ModelRequest(task=TASK_AGENT, messages=[], metadata={"session_id": "s1"}),
    )
    assert route.extra_body.get("enable_thinking") is False
    assert route.extra_body.get("session_id") == "s1"
