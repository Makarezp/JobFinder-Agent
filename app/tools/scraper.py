import logging
from typing import Annotated

from crawl4ai import AsyncWebCrawler
from langchain_core.tools import tool
from pydantic import BaseModel, BeforeValidator, Field

logger = logging.getLogger(__name__)


def ensure_single_string(v: str | list[str]) -> str:
    if isinstance(v, list):
        if not v:
            return ""
        return v[0]
    return str(v)


class ScrapeArgs(BaseModel):
    url: Annotated[str, BeforeValidator(ensure_single_string)] = Field(
        ..., description="The full URL of the website to scrape."
    )


@tool(args_schema=ScrapeArgs)
async def scrape_website(url: str) -> str:
    """
    Scrapes the content of a website and returns the markdown representation.
    Use this tool when you need to read the content of a URL to answer a question.
    """
    logger.info(f"Scraping URL: {url}")

    # Handle potential list input for url
    if isinstance(url, list):
        if not url:
            return "Error: Empty URL list provided."
        url = url[0]

    async with AsyncWebCrawler(verbose=True) as crawler:
        result = await crawler.arun(url=url)

        if result.success:
            # Limit content size to avoid context window issues (simple truncation for now)
            return str(result.markdown)[:20000]
        else:
            return f"Failed to scrape {url}: {result.error_message}"
