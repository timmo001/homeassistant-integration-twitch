"""Data ckasses for Twitch."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from twitchAPI.twitch import Stream, TwitchUser, TwitchUserFollow, UserSubscription

from homeassistant.helpers.typing import StateType


@dataclass
class TwitchChannel:
    """Twitch Channel."""

    id: str
    display_name: str
    profile_image_url: str
    followers: int | None = None
    following: TwitchUserFollow | None = None
    subscription: UserSubscription | None = None
    stream: Stream | None = None


@dataclass
class TwitchCoordinatorData:
    """Twitch Coordianator Data."""

    channels: list[TwitchChannel]
    user: TwitchUser


@dataclass
class TwitchBaseEntityDescriptionMixin:
    """Mixin for required Twitch base description keys."""

    value_fn: Callable[[TwitchCoordinatorData, str], StateType]
