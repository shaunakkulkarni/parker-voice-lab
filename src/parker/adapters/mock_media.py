"""Deterministic media player mock (no network)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from parker.contracts.domains import MediaPlayResult


class MockMediaPlayer:
    """Playlist playback with unavailable/fallback injection."""

    def __init__(self) -> None:
        self.players: dict[str, dict[str, Any]] = {
            "media_player.bathroom_homepod": {
                "state": "idle",
                "available": True,
                "media_title": None,
                "volume_level": 0.35,
            },
            "media_player.living_room_homepod": {
                "state": "idle",
                "available": True,
                "media_title": None,
                "volume_level": 0.4,
            },
        }
        self.playlists: dict[str, str] = {
            "shower_morning": "Shower Morning Mix",
            "focus": "Focus Playlist",
        }
        self.unavailable_playlists: set[str] = set()
        self.calls: list[dict[str, Any]] = []

    def reset(self) -> None:
        for player in self.players.values():
            player["state"] = "idle"
            player["available"] = True
            player["media_title"] = None
        self.unavailable_playlists.clear()
        self.calls.clear()

    def set_unavailable(self, entity_id: str) -> None:
        if entity_id in self.players:
            self.players[entity_id]["available"] = False

    def set_playlist_unavailable(self, playlist_id: str) -> None:
        self.unavailable_playlists.add(playlist_id)

    def start_playlist(self, entity_id: str, playlist_id: str) -> MediaPlayResult:
        self.calls.append(
            {"entity_id": entity_id, "playlist_id": playlist_id, "service": "play_media"}
        )
        player = self.players.get(entity_id)
        if player is None:
            return MediaPlayResult(
                entity_id=entity_id,
                playlist_id=playlist_id,
                success=False,
                state="unavailable",
                error_code="device_not_found",
            )
        if not player["available"]:
            return MediaPlayResult(
                entity_id=entity_id,
                playlist_id=playlist_id,
                success=False,
                state="unavailable",
                error_code="service_unavailable",
            )
        if playlist_id in self.unavailable_playlists or playlist_id not in self.playlists:
            return MediaPlayResult(
                entity_id=entity_id,
                playlist_id=playlist_id,
                success=False,
                state=player["state"],
                error_code="playlist_unavailable",
            )
        title = self.playlists[playlist_id]
        player["state"] = "playing"
        player["media_title"] = title
        return MediaPlayResult(
            entity_id=entity_id,
            playlist_id=playlist_id,
            success=True,
            state="playing",
            media_title=title,
        )

    def get_state(self, entity_id: str) -> dict[str, Any] | None:
        player = self.players.get(entity_id)
        return deepcopy(player) if player else None
