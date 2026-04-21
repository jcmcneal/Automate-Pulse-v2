"""Connect to a Pulse V2 hub and log battery / RSSI updates (local debugging)."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import sys

import aiopulse2

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

last_battery: dict[str, tuple[float | None, int | None]] = {}


def log_roller(roller: aiopulse2.Roller) -> None:
    if not roller.has_battery:
        return
    v = roller.battery
    pct = roller.battery_percent
    prev = last_battery.get(roller.id)
    changed = prev is not None and (prev[0] != v or prev[1] != pct)
    last_battery[roller.id] = (v, pct)
    tag = "CHANGED" if changed else ("init" if prev is None else "unchanged")
    logger.info(
        "  %s [%s] battery=%sV %s%%  RSSI=%s  online=%s (%s)",
        roller.name or "?",
        roller.id,
        v,
        pct,
        roller.signal,
        roller.online,
        tag,
    )


def hub_update(hub: aiopulse2.Hub) -> None:
    logger.info("=== hub update === %s rollers=%s", hub.name, list(hub.rollers))
    for roller in hub.rollers.values():
        log_roller(roller)


def make_roller_cb(roller: aiopulse2.Roller):
    def _cb(_r: aiopulse2.Roller) -> None:
        log_roller(_r)

    return _cb


def attach_roller_callbacks(hub: aiopulse2.Hub) -> None:
    for rid, roller in hub.rollers.items():
        roller.callback_subscribe(make_roller_cb(roller))
        logger.debug("subscribed roller callback %s", rid)


async def run(host: str, retries: int = 5, delay: float = 5.0) -> None:
    hub = aiopulse2.Hub(host, propagate_callbacks=True)
    hub.callback_subscribe(hub_update)

    attempt = 0
    run_task = None
    while True:
        attempt += 1
        run_task = asyncio.create_task(hub.run())
        try:
            logger.info("Connecting to %s (attempt %d/%d) ...", host, attempt, retries)
            await asyncio.wait_for(hub.rollers_known.wait(), timeout=30)
            attach_roller_callbacks(hub)
            hub_update(hub)
            await run_task
            break
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for roller names from hub")
            if attempt >= retries:
                break
        except OSError as e:
            if e.errno == 65:  # EHOSTUNREACH — transient LAN blip
                logger.warning(
                    "[Errno 65] No route to host (attempt %d/%d) — retrying in %.0fs",
                    attempt,
                    retries,
                    delay,
                )
                await hub.stop()
                run_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await run_task
                await asyncio.sleep(delay)
                continue
            raise
        except KeyboardInterrupt:
            logger.info("Stopping...")
            break

    if hub.running:
        await hub.stop()
    if run_task is not None and not run_task.done():
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run_task


def main() -> int:
    default_host = os.environ.get("AUTOMATE_PULSE_HOST", "")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "host",
        nargs="?",
        default=default_host or None,
        help="Hub IP or hostname (or set AUTOMATE_PULSE_HOST)",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="INFO on aiopulse2/websockets only",
    )
    p.add_argument(
        "-r",
        "--retries",
        type=int,
        default=5,
        metavar="N",
        help="Retry N times on EHOSTUNREACH (default: 5, 0 = no retries)",
    )
    p.add_argument(
        "-d",
        "--delay",
        type=float,
        default=5.0,
        metavar="SECS",
        help="Seconds between retries on EHOSTUNREACH (default: 5)",
    )
    args = p.parse_args()
    if not args.host:
        p.error("pass host as argument or set AUTOMATE_PULSE_HOST")

    if args.quiet:
        logging.getLogger("aiopulse2").setLevel(logging.INFO)
        logging.getLogger("websockets").setLevel(logging.INFO)

    asyncio.run(run(args.host, retries=args.retries, delay=args.delay))
    return 0


if __name__ == "__main__":
    sys.exit(main())
