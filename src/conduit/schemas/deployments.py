from conduit.common.errors import ProviderError, NoHealthyDeploymentError
from conduit.common.streaming import SSE_DONE, StreamAccumulator, format_sse, stream_sse_response
from conduit.core.auth.api_key import check_budget, check_model_access
from conduit.core.auth.rate_limiter import RateLimitResult, get_rate_limiter
from conduit.core.cost.calculator import calculate_cost
from conduit.core.router.engine import RouterEngine
from conduit.models.api_key import APIKey
from conduit.models.deployment import ModelDeployment
from conduit.models.request_log import RequestLog
from conduit.providers.registry import get_adapter
from conduit.schemas.completion import ChatCompletionRequest, ChatCompletionResponse

logger = structlog.stdlib.get_logger()