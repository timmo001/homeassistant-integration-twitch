"""DataUpdateCoordinator for Twitch."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any

import async_timeout
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

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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

    async def _async_get_data(self) -> TwitchCoordinatorData:
        """Return data from the coordinator."""
        user = await get_user(self._client)
        if user is None:
            raise UpdateFailed("Cannot get user from Twitch API")

        channels = []
        async for channel_user in self._client.get_users(
            user_ids=self._options[CONF_CHANNELS],
        ):
            followers = await self._client.get_users_follows(
                to_id=channel_user.id,
            )
            following = await self._client.get_users_follows(
                from_id=user.id,
                to_id=channel_user.id,
            )
            stream = await first(
                self._client.get_streams(
                    user_id=[channel_user.id],
                )
            )
            subscription = None
            try:
                subscription = await self._client.check_user_subscription(
                    broadcaster_id=channel_user.id,
                    user_id=user.id,
                )
            except TwitchResourceNotFound as ex:
                self.logger.debug("User is not subscribed to this channel: %s", ex)

            channels.append(
                TwitchChannel(
                    id=channel_user.id,
                    display_name=channel_user.display_name,
                    profile_image_url=channel_user.profile_image_url,
                    followers=followers.total,
                    following=following.data[0],
                    stream=stream,
                    subscription=subscription,
                )
            )

        self.logger.debug("Channels: %s", channels)
        self.logger.debug("User: %s", user)

        return TwitchCoordinatorData(
            channels=channels,
            user=user,
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
        except (TwitchAPIException, TwitchBackendException) as err:
            raise UpdateFailed from err
