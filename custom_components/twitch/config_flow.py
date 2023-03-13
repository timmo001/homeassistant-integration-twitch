"""Config flow for Twitch."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_CLIENT_ID, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2FlowHandler,
    async_get_config_entry_implementation,
)
from twitchAPI.twitch import (
    Twitch,
    TwitchAPIException,
    TwitchAuthorizationException,
    TwitchBackendException,
    TwitchUser,
)

from .const import CONF_CHANNELS, CONF_REFRESH_TOKEN, DOMAIN, OAUTH_SCOPES
from .coordinator import get_followed_channels, get_user


class OAuth2FlowHandler(AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Config flow to handle Twitch OAuth2 authentication."""

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize."""
        super().__init__()
        self._client: Twitch | None = None
        self._oauth_data: dict[str, Any] = {}

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {"scope": " ".join([scope.value for scope in OAUTH_SCOPES])}

    async def async_oauth_create_entry(
        self,
        data: dict[str, Any],
    ) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        client_id = self.flow_impl.__dict__[CONF_CLIENT_ID]
        access_token = data[CONF_TOKEN][CONF_ACCESS_TOKEN]
        refresh_token = data[CONF_TOKEN][CONF_REFRESH_TOKEN]

        self._client = Twitch(
            app_id=client_id,
            authenticate_app=False,
        )
        self._client.auto_refresh_auth = False

        await self._client.set_user_authentication(
            access_token,
            OAUTH_SCOPES,
            refresh_token=refresh_token,
            validate=True,
        )

        self._oauth_data = data

        return await self.async_step_channels()

    async def async_step_channels(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle channels step."""
        self.logger.debug("Step channels: %s", user_input)
        if not self._client:
            return self.async_abort(reason="cannot_connect")

        try:
            user = await get_user(self._client)
        except TwitchAuthorizationException as err:
            self.logger.error("Authorization error: %s", err)
            return self.async_abort(reason="invalid_auth")
        except (TwitchAPIException, TwitchBackendException) as err:
            self.logger.error("Twitch API error: %s", err)
            return self.async_abort(reason="cannot_connect")

        if user is None:
            self.logger.error("No user found")
            return self.async_abort(reason="user_not_found")

        self.logger.debug("User: %s", user)

        if not user_input:
            try:
                channels = await get_followed_channels(
                    self._client,
                    user,
                )
            except (TwitchAPIException, TwitchBackendException) as err:
                self.logger.error("Twitch API error: %s", err)
                return self.async_abort(reason="cannot_connect")

            self.logger.debug("Channels: %s", channels)

            return self.async_show_form(
                step_id="channels",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_CHANNELS): cv.multi_select(
                            {
                                channel.broadcaster_id: channel.broadcaster_name
                                for channel in channels
                            }
                        ),
                    }
                ),
            )

        return self.async_create_entry(
            title=user.display_name,
            data={**self._oauth_data, "user": user.__dict__},
            options={CONF_CHANNELS: user_input[CONF_CHANNELS]},
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> FlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Confirm reauth dialog."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Handle a option flow for GitHub."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle init options flow."""
        return await self.async_step_channels(user_input)

    async def async_step_channels(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle channels options flow."""
        if not user_input:
            implementation = await async_get_config_entry_implementation(
                self.hass,
                self.config_entry,
            )

            configured_channels: list[str] = self.config_entry.options[CONF_CHANNELS]

            client_id = implementation.__dict__[CONF_CLIENT_ID]
            access_token = self.config_entry.data[CONF_TOKEN][CONF_ACCESS_TOKEN]
            refresh_token = self.config_entry.data[CONF_TOKEN][CONF_REFRESH_TOKEN]

            client = Twitch(
                app_id=client_id,
                authenticate_app=False,
            )
            client.auto_refresh_auth = False

            await client.set_user_authentication(
                access_token,
                OAUTH_SCOPES,
                refresh_token=refresh_token,
                validate=True,
            )

            try:
                channels = await get_followed_channels(
                    client,
                    TwitchUser(**self.config_entry.data["user"]),
                )
            except TwitchAuthorizationException as err:
                self.logger.error("Authorization error: %s", err)
                return self.async_abort(reason="invalid_auth")
            except (TwitchAPIException, TwitchBackendException) as err:
                self.logger.error("Twitch API error: %s", err)
                return self.async_abort(reason="cannot_connect")

            channel_ids = [channel.broadcaster_id for channel in channels]
            channels_dict = {
                channel.broadcaster_id: channel.broadcaster_name for channel in channels
            }

            self.logger.debug("Channels: %s", channels_dict)

            # In case the user has removed a channel that is already tracked
            for channel in configured_channels:
                if channel not in channel_ids:
                    channels_dict[channel] = channel

            return self.async_show_form(
                step_id="channels",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_CHANNELS,
                            default=configured_channels,
                        ): cv.multi_select(channels_dict),
                    }
                ),
            )

        return self.async_create_entry(title="", data=user_input)
