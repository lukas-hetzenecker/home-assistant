"""Helper methods to help with platform discovery."""
import asyncio

from homeassistant import bootstrap, core
from homeassistant.const import (
    ATTR_DISCOVERED, ATTR_SERVICE, EVENT_PLATFORM_DISCOVERED)
from homeassistant.util.async import (
    run_callback_threadsafe, fire_coroutine_threadsafe)

EVENT_LOAD_PLATFORM = 'load_platform.{}'
ATTR_PLATFORM = 'platform'


def listen(hass, service, callback):
    """Setup listener for discovery of specific service.

    Service can be a string or a list/tuple.
    """
    if isinstance(service, str):
        service = (service,)
    else:
        service = tuple(service)

    def discovery_event_listener(event):
        """Listen for discovery events."""
        if ATTR_SERVICE in event.data and event.data[ATTR_SERVICE] in service:
            callback(event.data[ATTR_SERVICE], event.data.get(ATTR_DISCOVERED))

    hass.bus.listen(EVENT_PLATFORM_DISCOVERED, discovery_event_listener)


def discover(hass, service, discovered=None, component=None, hass_config=None):
    """Fire discovery event. Can ensure a component is loaded."""
    if component is not None:
        bootstrap.setup_component(hass, component, hass_config)

    data = {
        ATTR_SERVICE: service
    }

    if discovered is not None:
        data[ATTR_DISCOVERED] = discovered

    hass.bus.fire(EVENT_PLATFORM_DISCOVERED, data)


def listen_platform(hass, component, callback):
    """Register a platform loader listener."""
    run_callback_threadsafe(
        hass.loop, async_listen_platform, hass, component, callback
    ).result()


def async_listen_platform(hass, component, callback):
    """Register a platform loader listener.

    This method must be run in the event loop.
    """
    service = EVENT_LOAD_PLATFORM.format(component)

    @core.callback
    def discovery_platform_listener(event):
        """Listen for platform discovery events."""
        if event.data.get(ATTR_SERVICE) != service:
            return

        platform = event.data.get(ATTR_PLATFORM)

        if not platform:
            return

        hass.async_run_job(
            callback, platform, event.data.get(ATTR_DISCOVERED)
        )

    hass.bus.async_listen(
        EVENT_PLATFORM_DISCOVERED, discovery_platform_listener)


def load_platform(hass, component, platform, discovered=None,
                  hass_config=None):
    """Load a component and platform dynamically.

    Target components will be loaded and an EVENT_PLATFORM_DISCOVERED will be
    fired to load the platform. The event will contain:
        { ATTR_SERVICE = LOAD_PLATFORM + '.' + <<component>>
          ATTR_PLATFORM = <<platform>>
          ATTR_DISCOVERED = <<discovery info>> }

    Use `listen_platform` to register a callback for these events.
    """
    fire_coroutine_threadsafe(
        async_load_platform(hass, component, platform,
                            discovered, hass_config), hass.loop)


@asyncio.coroutine
def async_load_platform(hass, component, platform, discovered=None,
                        hass_config=None):
    """Load a component and platform dynamically.

    Target components will be loaded and an EVENT_PLATFORM_DISCOVERED will be
    fired to load the platform. The event will contain:
        { ATTR_SERVICE = LOAD_PLATFORM + '.' + <<component>>
          ATTR_PLATFORM = <<platform>>
          ATTR_DISCOVERED = <<discovery info>> }

    Use `listen_platform` to register a callback for these events.

    Warning: Do not yield from this inside a setup method to avoid a dead lock.
    Use `hass.loop.create_task(async_load_platform(..))` instead.

    This method is a coroutine.
    """
    did_lock = False
    setup_lock = hass.data.get('setup_lock')
    if setup_lock and setup_lock.locked():
        did_lock = True
        yield from setup_lock.acquire()

    try:
        # No need to fire event if we could not setup component
        res = yield from bootstrap.async_setup_component(
            hass, component, hass_config)
    finally:
        if did_lock:
            setup_lock.release()

    if not res:
        return

    data = {
        ATTR_SERVICE: EVENT_LOAD_PLATFORM.format(component),
        ATTR_PLATFORM: platform,
    }

    if discovered is not None:
        data[ATTR_DISCOVERED] = discovered

    hass.bus.async_fire(EVENT_PLATFORM_DISCOVERED, data)
