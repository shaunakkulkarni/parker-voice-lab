"""Adapters for Home Assistant and Hermes."""

from parker.adapters.base import HermesAdapter, HermesResponse, HomeAssistantAdapter
from parker.adapters.mock_anomaly import MockAnomalyStore
from parker.adapters.mock_devops import MockHermesCLI
from parker.adapters.mock_ha import MockHomeAssistant
from parker.adapters.mock_hermes import MockHermes
from parker.adapters.mock_media import MockMediaPlayer
from parker.adapters.mock_presence import MockPresence
from parker.adapters.mock_research import MockWebSearch
from parker.adapters.mock_routines import MockRoutineStore
from parker.adapters.mock_travel import MockTravel

__all__ = [
    "HermesAdapter",
    "HermesResponse",
    "HomeAssistantAdapter",
    "MockAnomalyStore",
    "MockHermes",
    "MockHermesCLI",
    "MockHomeAssistant",
    "MockMediaPlayer",
    "MockPresence",
    "MockRoutineStore",
    "MockTravel",
    "MockWebSearch",
]
