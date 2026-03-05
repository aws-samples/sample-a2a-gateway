"""Calculator Agent — deployed to AgentCore Runtime via A2A protocol."""

import logging
import os
from strands import Agent, tool
from strands.multiagent.a2a import A2AServer
import uvicorn
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
logger.info(f"Runtime URL: {runtime_url}")


@tool
def calculate(expression: str) -> dict:
    """
    Evaluate a mathematical expression safely.

    Args:
        expression: A math expression to evaluate (e.g. "2 + 3 * 4").

    Returns:
        A dictionary with the expression and its result.
    """
    allowed = set("0123456789+-*/.() ")
    if not all(c in allowed for c in expression):
        return {"expression": expression, "error": "Invalid characters in expression"}

    try:
        result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


strands_agent = Agent(
    tools=[calculate],
    system_prompt=(
        "You are a helpful calculator assistant. Use the calculate tool "
        "to evaluate mathematical expressions. Show your work and provide "
        "clear answers."
    ),
    name="CalculatorAgent",
    description="A calculator agent that evaluates mathematical expressions.",
    callback_handler=None,
)

host, port = "0.0.0.0", 9000

a2a_server = A2AServer(
    agent=strands_agent,
    http_url=runtime_url,
    serve_at_root=True,
)

app = FastAPI()


@app.get("/ping")
def ping():
    return {"status": "healthy"}


app.mount("/", a2a_server.to_fastapi_app())

if __name__ == "__main__":
    uvicorn.run(app, host=host, port=port)
