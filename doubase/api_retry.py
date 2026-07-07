"""API 重试工具 — 指数退避重试，处理临时性错误。"""

import time
import sys

# 可重试的错误码/类型
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BASE_DELAY = 1.0  # 秒


def is_retryable(exception: Exception) -> bool:
    """判断异常是否可重试（临时性错误）。

    可重试: 429 限流、5xx 服务端错误、网络超时、连接错误
    不重试: 401 认证失败、400 参数错误、其他客户端错误
    """
    error_str = str(exception).lower()

    # OpenAI SDK 抛出的异常携带 HTTP 状态码
    if hasattr(exception, "status_code"):
        return exception.status_code in RETRYABLE_HTTP_CODES

    # HTTP 状态码在错误消息中
    for code in RETRYABLE_HTTP_CODES:
        if str(code) in error_str:
            # 确保不是 4xx（如 "429" 在 "Error code: 429" 中）
            if f"error code: {code}" in error_str or f"status {code}" in error_str:
                return True

    # 网络层错误
    retryable_markers = [
        "timeout", "timed out", "connection reset",
        "connection error", "rate limit", "too many requests",
        "service unavailable", "internal server error",
        "bad gateway", "gateway timeout",
    ]
    if any(m in error_str for m in retryable_markers):
        return True

    return False


def retry_call(func, *args, max_retries: int = MAX_RETRIES, label: str = "API", **kwargs):
    """对可调用对象执行指数退避重试。

    Args:
        func: 要调用的函数（如 llm.chat, embedder.embed）。
        *args, **kwargs: 传给 func 的参数。
        max_retries: 最大重试次数（不含首次调用）。
        label: 日志标签（如 "LLM chat"）。

    Returns:
        func 的返回值。

    Raises:
        最后一次重试的异常（如果全部失败）。
    """
    last_exception = None
    for attempt in range(max_retries + 1):  # 0 = 首次, 1-3 = 重试
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries and is_retryable(e):
                delay = BASE_DELAY * (2 ** attempt)  # 1s, 2s, 4s
                print(
                    f"  ⚠️  {label} 调用失败 ({type(e).__name__}): {str(e)[:100]}"
                    f" — {delay:.0f}s 后重试 ({attempt + 1}/{max_retries})...",
                    file=sys.stderr,
                )
                time.sleep(delay)
            else:
                # 不可重试或已达最大次数
                break

    raise last_exception
