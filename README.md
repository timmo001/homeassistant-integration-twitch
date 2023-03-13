# Home Assistant Integration - Twitch

[Twitch](https://twitch.tv) integration for [Home Assistant](https://www.home-assistant.io/).

> This is a replacement for the core integration. If you experience any issues, please open an issue here and not in the core repository.

## How is this different from the Home Assistant Core integration

This integration is a replacement for the core integration. It implements the following:

- Config flow with OAuth2
- Coordinator for data updates
- More to come

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=timmo001&repository=homeassistant-integration-system-bridge&category=integration)

This integration is available in the [Home Assistant Community Store](https://hacs.xyz/).

## Setup and Configuration

- Create app
- Use redirect URI: `https://my.home-assistant.io/redirect/oauth`
- Copy client ID and secret
- Add to Home Assistant using the UI
