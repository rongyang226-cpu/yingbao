import logging

from app.activity.life_state import get_life_state, update_life_state
from app.activity.home_world import get_home_world, update_home_world
from app.activity.world_state import get_presence, set_presence
from app.activity.domestic import (
    audit_domestic_consistency,
    get_household_state,
    get_wardrobe_state,
    update_outfit,
)

log = logging.getLogger(__name__)


async def enforce_state_consistency():
    """Repair only clear contradictions between the persistent life layers."""
    repairs = []

    life = await get_life_state()
    world = await get_home_world()
    presence = await get_presence()

    activity = life.get("activity")
    sleep_state = life.get("sleep_state")
    ent_mode = world.get("current_entertainment_mode")

    # Sleep is authoritative: a sleeping Ying must be sleeping in the bedroom,
    # with no active entertainment left behind.
    if sleep_state == "sleeping":
        if activity != "sleeping":
            life = await update_life_state(
                activity="sleeping",
                activity_started_at=life.get("activity_started_at"),
            )
            activity = "sleeping"
            repairs.append("activity->sleeping")

        if (
            world.get("room_location") != "bedroom"
            or ent_mode is not None
            or world.get("current_game") is not None
            or world.get("light_state") != "off"
        ):
            world = await update_home_world(
                room_location="bedroom",
                light_state="off",
                clear_game=True,
            )
            ent_mode = None
            repairs.append("home->sleeping_bedroom")

        if presence.get("place_key") != "bedroom":
            presence = await set_presence(
                "bedroom",
                reason="consistency:sleeping",
            )
            repairs.append("presence->bedroom")

        try:
            wardrobe = await get_wardrobe_state()
            if wardrobe.get("outfit_key") != "sleep":
                await update_outfit(
                    activity="sleeping",
                    sleep_state="sleeping",
                )
                repairs.append("outfit->sleep")
        except Exception:
            log.exception("Sleep outfit consistency repair failed")

    else:
        # Legacy value from the earliest Home World version.
        if world.get("room_location") == "bed":
            world = await update_home_world(room_location="bedroom")
            repairs.append("room:bed->bedroom")

        # Media is phone activity, not gaming.
        if ent_mode == "media" and activity == "gaming":
            life = await update_life_state(
                activity="phone",
                activity_started_at=life.get("activity_started_at"),
            )
            activity = "phone"
            presence = await set_presence(
                "living_room",
                reason="consistency:media_phone",
            )
            world = await update_home_world(
                room_location="living_room",
            )
            repairs.append("gaming+media->phone@living_room")

        # Entertainment records are only valid while their matching activity
        # is still active. Otherwise they are stale state from an older tick.
        if ent_mode == "media" and activity != "phone":
            world = await update_home_world(clear_game=True)
            ent_mode = None
            repairs.append("clear_stale_media")
        elif ent_mode in {"real", "simulated", "failed"} and activity != "gaming":
            world = await update_home_world(clear_game=True)
            ent_mode = None
            repairs.append("clear_stale_game")

        # Strong-location activities must agree across Home World and presence.
        strong_places = {
            "gaming": "game_room",
            "sleeping": "bedroom",
            "preparing_sleep": "bedroom",
            "washing": "bathroom",
            "organizing": "study",
            "coffee": "nearby_cafe",
            "shopping": "nearby_store",
        }
        target = strong_places.get(activity)
        if target:
            if presence.get("place_key") != target:
                presence = await set_presence(
                    target,
                    reason=f"consistency:{activity}",
                )
                repairs.append(f"presence->{target}")
            if world.get("room_location") != target:
                world = await update_home_world(room_location=target)
                repairs.append(f"room->{target}")
        else:
            # For flexible activities, presence is the source of truth for the
            # actual location. Home World mirrors it instead of inventing one.
            place = presence.get("place_key")
            if place and world.get("room_location") != place:
                world = await update_home_world(room_location=place)
                repairs.append(f"room->{place}")

    try:
        domestic_audit = await audit_domestic_consistency(
            repair=True
        )
        if domestic_audit.get("repairs"):
            repairs.extend(
                f"domestic:{x}"
                for x in domestic_audit["repairs"]
            )

        household = await get_household_state()
        pressure = max(
            float(household.get("dishes") or 0),
            float(household.get("trash") or 0),
            float(household.get("clutter") or 0),
        )
        if pressure >= 0.78:
            expected_cleanliness = "有些凌乱，需要认真收拾"
        elif pressure >= 0.52:
            expected_cleanliness = "基本整洁，但有些地方开始乱了"
        else:
            expected_cleanliness = "整洁"

        world = await get_home_world()
        if world.get("room_cleanliness") != expected_cleanliness:
            world = await update_home_world(
                room_cleanliness=expected_cleanliness
            )
            repairs.append("home_cleanliness_synced")
    except Exception:
        log.exception("Domestic consistency audit failed")

    if repairs:
        log.warning("State consistency repaired: %s", ", ".join(repairs))

    return {
        "repaired": bool(repairs),
        "repairs": repairs,
        "life": life,
        "world": world,
        "presence": presence,
    }
