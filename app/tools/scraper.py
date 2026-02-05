import logging
from typing import Type
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from crawl4ai import AsyncWebCrawler

logger = logging.getLogger(__name__)


class ScrapeArgs(BaseModel):
    url: str = Field(..., description="The full URL of the website to scrape.")


@tool(args_schema=ScrapeArgs)
async def scrape_website(url: str) -> str:
    """
    Scrapes the content of a website and returns the markdown representation.
    Use this tool when you need to read the content of a URL to answer a question.
    """
    logger.info(f"Scraping URL: {url}")
    async with AsyncWebCrawler(verbose=True) as crawler:
        result = await crawler.arun(url=url)

        if result.success:
            # Limit content size to avoid context window issues (simple truncation for now)
            return result.markdown[:20000]
        else:
            return f"Failed to scrape {url}: {result.error_message}"
