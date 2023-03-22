"""DataUpdateCoordinator for Twitch."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from twitchAPI.helper import first
from twitchAPI.twitch import (
    FollowedChannel,
    Twitch,
    TwitchAPIException,
    TwitchAuthorizationException,
    TwitchBackendException,
    TwitchResourceNotFound,
    TwitchUser,
)

from .const import CONF_CHANNELS, DOMAIN
from .data import TwitchChannel, TwitchCoordinatorData


async def get_user(
    client: Twitch,
) -> TwitchUser | None:
    """Return the username of the user."""
    return await first(client.get_users())


async def get_followed_channels(
    client: Twitch,
    user: TwitchUser,
) -> list[FollowedChannel]:
    """Return a list of channels the user is following."""
    channels: list[FollowedChannel] = [
        channel
        async for channel in await client.get_followed_channels(
            user_id=user.id,
        )
    ]

    return sorted(
        channels,
        key=lambda channel: channel.broadcaster_name.lower(),
        reverse=False,
    )


def get_twitch_channel(
    data: TwitchCoordinatorData,
    channel_id: str,
) -> TwitchChannel | None:
    """Get twitch channel from coordinator."""
    if data.channels is None or len(data.channels) < 1:
        return None
    return next(
        (channel for channel in data.channels if channel.id == channel_id),
        None,
    )


def get_twitch_channel_available(
    data: TwitchCoordinatorData,
    channel_id: str,
) -> bool:
    """Return True if the channel is available."""
    return get_twitch_channel(data, channel_id) is not None


def get_twitch_channel_entity_picture(
    data: TwitchCoordinatorData,
    channel_id: str,
) -> str | None:
    """Return the entity picture of the channel."""
    channel = get_twitch_channel(data, channel_id)
    if channel is None:
        return None

    if channel.stream is not None:
        if channel.stream.thumbnail_url is not None:
            return channel.stream.thumbnail_url.format(width=1280, height=720)
    return channel.profile_image_url


class TwitchUpdateCoordinator(DataUpdateCoordinator[TwitchCoordinatorData]):
    """Twitch data update coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        LOGGER: logging.Logger,
        client: Twitch,
        options: Mapping[str, Any],
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            LOGGER,
            # Name of the data. For logging purposes.
            name=DOMAIN,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=30),
        )
        self._client = client
        self._options = options
        self.user: TwitchUser | None = None

    async def _async_get_channel_data(
        self,
        channel_user: TwitchUser,
    ) -> TwitchChannel:
        """Return channel data."""
        if self.user is None:
            self.user = await get_user(self._client)

        if self.user is None:
            raise UpdateFailed("Cannot get user from Twitch API")

        followers, following, stream = await asyncio.gather(
            self._client.get_users_follows(
                to_id=channel_user.id,
            ),
            self._client.get_users_follows(
                from_id=self.user.id,
                to_id=channel_user.id,
            ),
            first(
                self._client.get_streams(
                    user_id=[channel_user.id],
                )
            ),
        )
        game = None
        if stream is not None:
            game = await first(self._client.get_games(game_ids=[stream.game_id]))
        subscription = None
        try:
            subscription = await self._client.check_user_subscription(
                broadcaster_id=channel_user.id,
                user_id=self.user.id,
            )
        except TwitchResourceNotFound as ex:
            self.logger.debug("User is not subscribed to this channel: %s", ex)

        return TwitchChannel(
            id=channel_user.id,
            display_name=channel_user.display_name,
            profile_image_url=channel_user.profile_image_url,
            followers=followers.total if followers is not None else None,
            following=following.data[0]
            if following is not None and len(following.data) > 0
            else None,
            game=game,
            stream=stream,
            subscription=subscription,
        )

    async def _async_get_data(self) -> TwitchCoordinatorData:
        """Return data from the coordinator."""
        if self.user is None:
            self.user = await get_user(self._client)

        if self.user is None:
            raise UpdateFailed("Cannot get user from Twitch API")

        self.logger.debug("User: %s", self.user)

        channel_users = []
        async for channel_user in self._client.get_users(
            user_ids=[self.user.id, *self._options[CONF_CHANNELS]],
        ):
            channel_users.append(channel_user)

        channels = await asyncio.gather(
            *[
                self._async_get_channel_data(channel_user)
                for channel_user in channel_users
            ]
        )

        self.logger.debug("Channels: %s", channels)

        return TwitchCoordinatorData(
            channels=channels,
            user=self.user,
        )

    async def _async_update_data(self) -> TwitchCoordinatorData:
        """Fetch data from Twitch."""
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(30):
                return await self._async_get_data()
        except TwitchAuthorizationException as err:
            raise ConfigEntryAuthFailed from err
        except (TwitchAPIException, TwitchBackendException, KeyError) as err:
            raise UpdateFailed from err
