# mcp_client.py
from typing import Any, Dict, Optional
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
)
from loguru import logger
import time
import inspect

# 导入本地实现的 WorldQuant 平台工具集合
import worldquant_platform_functions as wq_funcs

# 重试策略统一定义
RETRY_ATTEMPTS = 5
RETRY_WAIT_MULTIPLIER = 1
RETRY_WAIT_MAX = 30

class MCPClient:
    """
    MCPClient: 通过调用本地 worldquant_platform_functions 中的工具实现平台交互。
    提供：
      - run_tool(name, **kwargs): 通用工具调用（动态分派）
      - wq_create_simulation(settings, regular, meta): 调用 create_simulation
      - wq_get_result(location): 调用 get_submission_check（默认，可替换）
      - 以及速率、存储包装：acquire_rate_limit/release_rate_limit/store_put/store_get
    """

    def __init__(self, default_timeout: int = 30, query_tool: str = "get_submission_check"):
        self.default_timeout = default_timeout
        # 平台用于轮询查询回测状态的工具名称；可设为 "get_submission_check" 或你偏好的其他工具
        self.query_tool = query_tool

    def _has_tool(self, name: str) -> bool:
        return hasattr(wq_funcs, name) and callable(getattr(wq_funcs, name))

    def _call_tool(self, name: str, **kwargs) -> Any:
        """
        反射调用 worldquant_platform_functions 中的函数。
        会记录调用耗时，并在找不到函数时报错。
        """
        if not self._has_tool(name):
            raise AttributeError(f"Platform tool '{name}' not found in worldquant_platform_functions")
        func = getattr(wq_funcs, name)
        # 若函数签名包含 timeout，且 kwargs 中未提供，则添加默认超时
        sig = inspect.signature(func)
        if "timeout" in sig.parameters and "timeout" not in kwargs:
            kwargs["timeout"] = self.default_timeout
        start = time.time()
        try:
            resp = func(**kwargs)
        finally:
            elapsed = time.time() - start
            logger.debug("Tool call {} completed in {:.2f}s", name, elapsed)
        return resp

    @retry(
        wait=wait_exponential(multiplier=RETRY_WAIT_MULTIPLIER, min=1, max=RETRY_WAIT_MAX),
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def run_tool(self, name: str, **kwargs) -> Any:
        """
        通用工具调用，外层带重试（针对可恢复错误）。
        若某些工具需要特殊错误分类（例如 4xx 不重试），请在 platform 层抛出特定异常并在此处扩展过滤。
        """
        logger.info("Running tool: {} with args keys: {}", name, list(kwargs.keys()))
        return self._call_tool(name, **kwargs)

    # 常用包装：提交与查询（与之前代码接口兼容）
    @retry(
        wait=wait_exponential(multiplier=RETRY_WAIT_MULTIPLIER, min=1, max=RETRY_WAIT_MAX),
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def wq_create_simulation(self, settings: Dict[str, Any], regular: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        调用 worldquant_platform_functions.create_simulation(settings=settings, regular=regular, meta=meta)
        返回应至少包含 'location' 字段（也可包含 task_id 等信息）。
        """
        meta = meta or {}
        if not self._has_tool("create_simulation"):
            raise AttributeError("Platform does not implement 'create_simulation'")
        logger.debug("wq_create_simulation meta keys: {}", list(meta.keys()))
        resp = self._call_tool("create_simulation", settings=settings, regular=regular, meta=meta)
        if not isinstance(resp, dict) or "location" not in resp:
            # 如果返回不包含 location，尝试查看是否存在 alternative 字段
            logger.warning("create_simulation returned unexpected response: {}", resp)
            raise RuntimeError("create_simulation must return dict containing 'location'")
        return resp

    @retry(
        wait=wait_exponential(multiplier=RETRY_WAIT_MULTIPLIER, min=1, max=RETRY_WAIT_MAX),
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def wq_get_result(self, location: str) -> Dict[str, Any]:
        """
        通过预配置的 query_tool（默认 get_submission_check）查询回测结果/状态。
        如果你的平台有更合适的查询工具（如 get_alpha_pnl 等），请在构造 MCPClient 时传入 query_tool 参数。
        """
        if not self._has_tool(self.query_tool):
            raise AttributeError(f"Platform does not implement query tool '{self.query_tool}'")
        logger.debug("wq_get_result using tool '{}' for location {}", self.query_tool, location)
        resp = self._call_tool(self.query_tool, location=location)
        if not isinstance(resp, dict):
            logger.warning("Query tool {} returned non-dict: {}", self.query_tool, resp)
            raise RuntimeError(f"Query tool {self.query_tool} returned invalid response")
        return resp

    # 速率控制与存储的包装（若平台以其他名称实现，请在 worldquant_platform_functions 中保持以下函数）
    def rate_limit_acquire(self, name: str, permits: int = 1) -> bool:
        # 支持函数名 acquire_rate_limit 或 acquire_rate_limit (两种常见实现)
        for fn in ("acquire_rate_limit", "acquire_rate_limit"):  # 占位，可扩展
            if self._has_tool(fn):
                try:
                    resp = self._call_tool(fn, name=name, permits=permits)
                    if isinstance(resp, dict):
                        return bool(resp.get("ok", True))
                    return bool(resp)
                except Exception as e:
                    logger.warning("rate_limit_acquire('{}') raised {}", name, e)
                    return False
        # 如果没有实现，默认为允许（或根据策略返回 False）
        logger.warning("No rate limit acquire tool found; defaulting to True")
        return True

    def rate_limit_release(self, name: str, permits: int = 1) -> None:
        for fn in ("release_rate_limit", "release_rate_limit"):
            if self._has_tool(fn):
                try:
                    self._call_tool(fn, name=name, permits=permits)
                    return
                except Exception as e:
                    logger.warning("rate_limit_release('{}') raised {}", name, e)
                    return
        logger.debug("No rate limit release tool found; skipping")

    def store_put(self, key: str, value: Dict[str, Any]) -> bool:
        if self._has_tool("store_put"):
            try:
                resp = self._call_tool("store_put", key=key, value=value)
                if isinstance(resp, dict):
                    return bool(resp.get("ok", True))
                return True
            except Exception as e:
                logger.error("store_put failed for {}: {}", key, e)
                return False
        # 若没有 store_put，尝试使用 save_simulation_data 或 manage_config 作为持久化后备
        for alt in ("save_simulation_data", "manage_config"):
            if self._has_tool(alt):
                try:
                    resp = self._call_tool(alt, key=key, value=value)
                    if isinstance(resp, dict):
                        return bool(resp.get("ok", True))
                    return True
                except Exception as e:
                    logger.error("Alternative store '{}' failed: {}", alt, e)
                    return False
        logger.warning("No storage tool found; store_put is a no-op")
        return False

    def store_get(self, key: str) -> Optional[Dict[str, Any]]:
        if self._has_tool("store_get"):
            try:
                return self._call_tool("store_get", key=key)
            except Exception as e:
                logger.error("store_get failed for {}: {}", key, e)
                return None
        # 后备：尝试 get_platform_setting_options 或 get_user_profile（仅示例，不推荐）
        for alt in ("get_platform_setting_options", "get_user_profile"):
            if self._has_tool(alt):
                try:
                    return self._call_tool(alt, key=key)
                except Exception as e:
                    logger.warning("Alternative store_get '{}' failed: {}", alt, e)
                    return None
        logger.warning("No store_get tool found")
        return None

    # 便捷 wrapper: 调用其它 platform 方法
    def call_platform(self, tool_name: str, **kwargs) -> Any:
        """
        直接调用任意列在 worldquant_platform_functions 中的工具。
        例如: client.call_platform('get_leaderboard', limit=10)
        """
        return self.run_tool(tool_name, **kwargs)
