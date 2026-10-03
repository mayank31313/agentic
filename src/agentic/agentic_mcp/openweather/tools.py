from fastmcp.tools import tool
import requests
import logging
import os


logger = logging.getLogger(__name__)

def get_weather_tools():
    api_key = os.environ.get("OPEN_WEATHER_API_KEY")
    if not api_key:
        logger.warning("OPEN_WEATHER_API_KEY is not set in environment variables. Weather tools will not work without it.")
        return []

    @tool
    def get_current_weather(location: str) -> dict:
        """Get the current weather for a given location."""
        try:
            if not api_key:
                raise ValueError("OPEN_WEATHER_API_KEY is not set in environment variables.")
            url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching current weather: {e}")
            return {"error": str(e)}

    @tool
    def get_weather_forecast(location: str, days: int = 5) -> dict:
        """Get the weather forecast for a given location for the next specified number of days."""
        try:
            if not api_key:
                raise ValueError("OPEN_WEATHER_API_KEY is not set in environment variables.")
            url = f"http://api.openweathermap.org/data/2.5/forecast/daily?q={location}&cnt={days}&appid={api_key}&units=metric"
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching weather forecast: {e}")
            return {"error": str(e)}

    return [get_current_weather, get_weather_forecast]