"""Support for the Twitch stream status."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import TwitchDeviceEntity
from .const import DOMAIN
from .coordinator import (
    TwitchUpdateCoordinator,
    get_twitch_channel,
    get_twitch_channel_available,
    get_twitch_channel_entity_picture,
)
from .data import TwitchBaseEntityDescriptionMixin, TwitchCoordinatorData


@dataclass
class TwitchBaseBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Twitch binary sensor entity default overrides."""

    icon: str = "mdi:twitch"
    available_fn: Callable[[TwitchCoordinatorData, str], bool] = lambda data, k: True
    attributes_fn: Callable[
        [TwitchCoordinatorData, str], Mapping[str, Any] | None
    ] = lambda data, k: None
    entity_picture_fn: Callable[
        [TwitchCoordinatorData, str], str | None
    ] = lambda data, k: None


@dataclass
class TwitchBinarySensorEntityDescription(
    TwitchBaseBinarySensorEntityDescription,
    TwitchBaseEntityDescriptionMixin,
):
    """Describes Twitch issue sensor entity."""

    available_fn = get_twitch_channel_available
    entity_picture_fn = get_twitch_channel_entity_picture


def _twitch_live_value(
    data: TwitchCoordinatorData,
    channel_id: str,
) -> StateType:
    """Return the value of the sensor."""
    channel = get_twitch_channel(data, channel_id)
    if channel is None:
        return None

    if channel.stream is None:
        return False
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Config entry example."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data: TwitchCoordinatorData = coordinator.data

    entities: list[TwitchBinarySensorEntity] = []

    for channel in data.channels:
        entities.extend(
            [
                TwitchBinarySensorEntity(
                    coordinator,
                    TwitchBinarySensorEntityDescription(
                        key=f"{channel.id}_live",
                        name=f"{channel.display_name} live",
                        value_fn=_twitch_live_value,
                    ),
                    channel.id,
                    channel.display_name,
                ),
            ]
        )

    async_add_entities(entities)


class TwitchBinarySensorEntity(TwitchDeviceEntity, BinarySensorEntity):
    """Define a Twitch binary sensor."""

    _attr_has_entity_name = False

    entity_description: TwitchBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: TwitchUpdateCoordinator,
        description: TwitchBinarySensorEntityDescription,
        service_id: str,
        service_name: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(
            coordinator,
            service_id,
            service_name,
            description.key,
        )
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.available_fn(
                self.coordinator.data, self._service_id
            )
        )

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return cast(
            bool,
            self.entity_description.value_fn(self.coordinator.data, self._service_id),
        )

    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture."""
        return self.entity_description.entity_picture_fn(
            self.coordinator.data, self._service_id
        )
