"""fuzzy_find_and_replace 用法示例（由示例脚本迁入，用断言做回归）。

核心 API：fuzzy_find_and_replace(全文, 要找的片段, 替换为, replace_all=False)
"""

from utils.fuzzy_match import fuzzy_find_and_replace


def test_exact_match() -> None:
    """精确匹配（exact）。"""
    out, n, strategy, err = fuzzy_find_and_replace(
        "def foo():\n    pass\n",
        "def foo():",
        "def bar():",
    )
    assert err is None
    assert n == 1
    assert strategy == "exact"
    assert out == "def bar():\n    pass\n"


def test_unicode_normalized_match() -> None:
    """正文为智能引号，old_string 为 ASCII，通常会走 unicode_normalized。"""
    smart = "\u201chello\u201d"
    out, n, strategy, err = fuzzy_find_and_replace(
        f"msg = {smart}\n",
        'msg = "hello"',
        "msg = 'hi'",
    )
    assert err is None
    assert n == 1
    assert strategy == "unicode_normalized"
    assert out == "msg = 'hi'\n"


def test_empty_old_string_rejected() -> None:
    """校验错误：old_string 为空时返回原文且不替换。"""
    out, n, strategy, err = fuzzy_find_and_replace("abc", "", "x")
    assert out == "abc"
    assert n == 0
    assert strategy is None
    assert err == "old_string cannot be empty"
