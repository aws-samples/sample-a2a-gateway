"""Weather Agent — deployed to AgentCore Runtime via A2A protocol."""

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
def get_weather(city: str) -> dict:
    """
    Get the current weather for a given city.

    Args:
        city: Name of the city to get weather for.

    Returns:
        A dictionary with weather information.
    """
    weather_data = {
        "seattle": {"temp_f": 58, "condition": "Cloudy", "humidity": 78, "wind_mph": 12},
        "new york": {"temp_f": 72, "condition": "Sunny", "humidity": 55, "wind_mph": 8},
        "miami": {"temp_f": 88, "condition": "Partly Cloudy", "humidity": 80, "wind_mph": 15},
        "chicago": {"temp_f": 65, "condition": "Windy", "humidity": 60, "wind_mph": 22},
        "san francisco": {"temp_f": 62, "condition": "Foggy", "humidity": 85, "wind_mph": 10},
        "london": {"temp_f": 55, "condition": "Rainy", "humidity": 90, "wind_mph": 14},
    }

    lookup = city.lower().strip()
    if lookup in weather_data:
        data = weather_data[lookup]
        return {
            "city": city,
            "temperature_f": data["temp_f"],
            "condition": data["condition"],
            "humidity_pct": data["humidity"],
            "wind_mph": data["wind_mph"],
        }

    return {
        "city": city,
        "temperature_f": 70,
        "condition": "Clear",
        "humidity_pct": 50,
        "wind_mph": 5,
        "note": "Default data — city not in sample dataset",
    }


strands_agent = Agent(
    tools=[get_weather],
    system_prompt=(
        "You are a helpful weather assistant. Use the get_weather tool "
        "to answer questions about weather conditions in various cities. "
        "Provide clear, concise weather summaries."
    ),
    name="WeatherAgent",
    description="A weather agent that provides weather information for cities.",
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
