"""TSCM-style scope-and-method section for the sweep report. Never says a place is "clear"."""
import time

from . import inspection

TITLE = "N0RMA TSCM-STYLE SWEEP REPORT (not a professional sweep)"
NOT_DONE = [
    "Non-linear junction detection (finds electronics even when switched off or dormant)",
    "Wideband RF spectrum analysis (this computer hears only its own Wi-Fi, Bluetooth and optional RTL-SDR 24 MHz-1.7 GHz)",
    "Thermal imaging",
    "Wired, telephone, power-line and cellular/GPS device checks",
    "Inspection by a trained examiner with specialist equipment",
]


def sections(rooms, events, mine_count=0):
    """rooms: {name: set(ticked item ids)}. events: dicts with level/domain."""
    flagged = [e for e in events if e["level"] in ("watch", "alert")]
    o = ["SCOPE"]
    o.append("- Areas covered: " + ", ".join(rooms) if rooms else "- No rooms or areas were set up, so no room-by-room inspection is recorded.")
    o += ["", "METHODS PERFORMED",
          "1. Continuous radio and network monitoring by this computer (Wi-Fi, Bluetooth, LAN, listening ports). Unlike the phone app it stays in one place, so there is no per-room radio sweep and it cannot show a tracker following you.",
          "2. Physical inspection checklist, per area (what the person doing the sweep ticked off by looking):"]
    if not rooms:
        o.append("   (none)")
    for name, done in rooms.items():
        items = inspection.items_for(name)
        n = sum(1 for i in items if i[0] in done)
        o.append(f"   - {name}: {n} of {len(items)} items checked")
        o += [f"       NOT CHECKED: {i[1]}" for i in items if i[0] not in done]
    counts = {}
    for e in flagged:
        counts[e["domain"]] = counts.get(e["domain"], 0) + 1
    o.append(f"3. Watch/alert findings in the log period: {len(flagged)}" + (" (" + ", ".join(f"{v} {k}" for k, v in counts.items()) + ")" if flagged else ""))
    if mine_count:
        o.append(f"   {mine_count} device(s) were marked by the user as their own and are not flagged.")
    o += ["", "METHODS NOT PERFORMED (a computer cannot do these)"] + [f"- {x}" for x in NOT_DONE]
    o += ["", "CONCLUSION"]
    o.append("- Nothing was flagged by the methods listed above. This does NOT show the area is free of surveillance devices." if not flagged else
             f"- {len(flagged)} item(s) were flagged and are listed in the event log below. Each is a signal worth checking in person, not proof of surveillance or of who placed anything.")
    o.append("- For a high-risk situation, hire a licensed TSCM professional. If you are in danger, call your local emergency number.")
    return "\n".join(o) + "\n"
