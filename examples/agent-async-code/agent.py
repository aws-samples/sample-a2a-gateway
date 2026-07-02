"""Async A2A Agent — demonstrates task lifecycle with background execution."""

import asyncio
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

from strands import Agent
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_jsonrpc_routes, create_agent_card_routes
from a2a.types import AgentCard, AgentCapabilities, AgentSkill, Task, TaskStatus, TaskState
from google.protobuf.timestamp_pb2 import Timestamp
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

strands_agent = Agent(
    name="Async Test Agent",
    description="An async A2A agent that supports task lifecycle operations.",
    system_prompt="You are a helpful assistant. Answer questions clearly and concisely.",
    callback_handler=None,
)


class AsyncStrandsExecutor(AgentExecutor):
    """Runs the Strands agent in a background thread, enabling async task lifecycle."""

    def __init__(self, agent: Agent):
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        task_id = context.task_id
        context_id = context.context_id or str(uuid.uuid4())

        task = context.current_task
        if not task:
            ts = Timestamp()
            ts.FromDatetime(datetime.now(timezone.utc))
            task = Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED, timestamp=ts),
            )
            await event_queue.enqueue_event(task)

        task_updater = TaskUpdater(event_queue, task_id, context_id)
        await task_updater.start_work()

        loop = asyncio.get_event_loop()

        def _run():
            try:
                user_message = ""
                if context.message and context.message.parts:
                    for part in context.message.parts:
                        if part.text:
                            user_message += part.text

                result = self.agent(user_message)
                response_text = str(result)

                asyncio.run_coroutine_threadsafe(
                    task_updater.add_artifact([{"text": response_text}]),
                    loop,
                ).result()

                asyncio.run_coroutine_threadsafe(
                    task_updater.complete(),
                    loop,
                ).result()

            except Exception as e:
                logger.error(f"Agent execution failed: {e}")
                asyncio.run_coroutine_threadsafe(
                    task_updater.failed(str(e)),
                    loop,
                ).result()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        task_updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await task_updater.cancel()


task_store = InMemoryTaskStore()
executor = AsyncStrandsExecutor(strands_agent)

agent_card = AgentCard(
    name="Async Test Agent",
    description="An async A2A agent that supports task lifecycle operations.",
    version="0.0.1",
    capabilities=AgentCapabilities(streaming=True, push_notifications=False),
    skills=[
        AgentSkill(
            id="general",
            name="general",
            description="General conversation and Q&A",
        )
    ],
)

handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=task_store,
    agent_card=agent_card,
)


async def ping(request):
    return JSONResponse({"status": "Healthy"})


app = Starlette(
    routes=[Route("/ping", ping)]
    + create_agent_card_routes(agent_card)
    + create_jsonrpc_routes(handler, rpc_url="/", enable_v0_3_compat=True)
    + create_jsonrpc_routes(handler, rpc_url="/invocations", enable_v0_3_compat=True),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
