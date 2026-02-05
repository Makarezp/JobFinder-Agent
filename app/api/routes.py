from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from langchain_core.messages import HumanMessage
from app.agent.graph import graph
from app.agent.state import AgentState
from pathlib import Path
import markdown

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.post("/chat")
async def chat_endpoint(request: Request, message: str = Form(...)):
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Run Agent
    try:
        inputs: AgentState = {
            "messages": [HumanMessage(content=message)],
            "url": None,
            "scraped_content": None,
            "loading": False,
        }
        # Invoke the graph (synchronous invoke for simplicity in this step, async invoke preferred if supported)
        # Note: langgraph compile() returns a Runnable, which has ainvoke
        result = await graph.ainvoke(inputs)

        last_message = result["messages"][-1]
        ai_content = last_message.content

        # Convert Markdown to HTML for rendering
        ai_content_html = markdown.markdown(ai_content)

        return templates.TemplateResponse(
            request,
            "components/chat_message.html",
            {
                "user_message": message,
                "ai_message": ai_content_html,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "components/chat_message.html",
            {
                "user_message": message,
                "ai_message": f"<p class='text-red-500'>Error: {str(e)}</p>",
            },
        )
