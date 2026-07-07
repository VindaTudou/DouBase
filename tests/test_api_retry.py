"""测试 API 重试逻辑。"""

from doubase.api_retry import is_retryable, retry_call


class Fake429Error(Exception):
    def __init__(self, msg="Error code: 429 - rate limit"):
        super().__init__(msg)


class Fake401Error(Exception):
    def __init__(self, msg="Error code: 401 - unauthorized"):
        super().__init__(msg)


def test_is_retryable_429():
    assert is_retryable(Fake429Error()) is True


def test_is_retryable_401():
    assert is_retryable(Fake401Error()) is False


def test_is_retryable_timeout():
    err = Exception("connection timeout error")
    assert is_retryable(err) is True


def test_is_retryable_normal_error():
    err = Exception("some random error")
    assert is_retryable(err) is False


def test_retry_call_succeeds_first_try():
    call_count = [0]

    def fake_api():
        call_count[0] += 1
        return "ok"

    result = retry_call(fake_api, label="test")
    assert result == "ok"
    assert call_count[0] == 1  # 只调用一次


def test_retry_call_succeeds_on_retry():
    call_count = [0]

    def fake_api():
        call_count[0] += 1
        if call_count[0] < 3:
            raise Fake429Error()
        return "ok after retry"

    result = retry_call(fake_api, max_retries=3, label="test")
    assert result == "ok after retry"
    assert call_count[0] == 3  # 前两次失败+第三次成功


def test_retry_call_fails_after_max():
    call_count = [0]

    def fake_api():
        call_count[0] += 1
        raise Fake429Error()

    try:
        retry_call(fake_api, max_retries=2, label="test")
        assert False, "should have raised"
    except Fake429Error:
        assert call_count[0] == 3  # 首次 + 2 次重试


def test_retry_call_no_retry_on_401():
    """401 认证失败不重试，直接抛异常"""
    call_count = [0]

    def fake_api():
        call_count[0] += 1
        raise Fake401Error()

    try:
        retry_call(fake_api, max_retries=3, label="test")
        assert False, "should have raised"
    except Fake401Error:
        assert call_count[0] == 1  # 仅一次，不重试
