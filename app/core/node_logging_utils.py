import structlog
from langchain_core.messages import AIMessage

logger = structlog.get_logger(__name__)


def log_node_completed(node_name: str, response: AIMessage) -> None:
    """Log node completion with LLM token usage extracted from the response."""
    usage = response.usage_metadata
    logger.info(
        f"Node Completed: {node_name}",
        response_preview=str(response.content)[:100],
        input_tokens=usage.get("input_tokens") if usage else None,
        output_tokens=usage.get("output_tokens") if usage else None,
        total_tokens=usage.get("total_tokens") if usage else None,
    )
