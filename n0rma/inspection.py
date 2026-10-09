"""Physical-inspection checklist (the part of a sweep a computer cannot do for you). A finished list means "I looked here", never "this room is clear".
Item ids match the Android app."""

GENERAL = [
    ("ceil", "Ceiling: smoke/CO detectors, light fittings, vents", "Look for a tiny hole or lens, a second device next to the detector, or loose/new wiring. Compare with a detector in another room."),
    ("outlets", "Outlets, USB chargers, power strips, adapters", "Anything plugged in that you didn't buy, a charger that is always in place with a tiny hole, or one that gets warm with nothing connected."),
    ("facing", "Objects facing the bed, sofa or desk (clocks, radios, picture frames, plants, books)", "Hold your eye level with each and look for a pinhole or glint. Ask: who put this here, and when?"),
    ("glint", "Lens-glint sweep", "Dim the room, slowly sweep a flashlight at eye level across shelves and walls. A small, bright, steady point reflected back can be a camera lens."),
    ("ir", "Infrared dots", "With the lights off, look at the room through a phone's front camera (it often shows infrared). Steady white or purple dots can be night-vision LEDs."),
    ("tv", "TVs, set-top boxes, soundbars, consoles, smart speakers", "Find built-in cameras and microphones. Cover or unplug the ones you don't use."),
    ("mirror", "Mirrors", "Touch a fingertip to the glass: on a normal mirror there's a gap between your finger and its reflection; on a two-way mirror they touch. Not reliable on its own."),
    ("furniture", "Furniture and soft items", "Look behind, under and inside shelves, drawers, cushions, tissue boxes, stuffed toys and decor. Look for anything new, moved or out of place."),
    ("router", "Wi-Fi and network", "Open your router's connected-devices list (or run `n0rma devices`) and look for anything you don't recognise."),
    ("moved", "Things that changed", "Note anything that wasn't there before or has moved. Photograph it where it is."),
]
BEDROOM = [("bed", "Around the bed", "Check the headboard, bedside lamps, chargers and anything on shelves pointing at the bed.")]
BATHROOM = [("bath", "Towel hooks, vents, shower rod, tissue holders, hair-dryer holders", "Look for tiny holes or lenses at head height and above. Bathrooms are a common place for hidden cameras.")]
RENTAL = [("rental", "Rental or hotel extras", "Check alarm clocks, USB hubs, smoke detectors, TV sets and any device you can't explain. Unplug the ones you can.")]
CAR = [
    ("obd", "OBD-II port under the dash", "Look for a plug-in device you don't recognise. Photograph it before touching it."),
    ("under", "Underneath and wheel wells", "With a flashlight, feel behind bumpers and inside wheel wells for small magnetic boxes."),
    ("seats", "Under and inside seats, door pockets, glove box, trunk", "Feel along seams and tuck points; check for taped-on or velcroed items."),
    ("dash", "Dashboard and mirror", "Look for a camera or box near the rear-view mirror and for extra wiring behind panels."),
    ("bags", "Bags and belongings kept in the car", "Check seams, lining and pockets for coin-sized or card-sized trackers."),
    ("ir", "Infrared dots", "With the lights off, look through a phone's front camera for steady white or purple dots."),
]


def items_for(room):
    r = room.lower()
    if any(k in r for k in ("car", "truck", "vehicle", "van", "suv")):
        return list(CAR)
    out = list(GENERAL)
    if "bed" in r:
        out += BEDROOM
    if any(k in r for k in ("bath", "restroom", "toilet")):
        out += BATHROOM
    if any(k in r for k in ("hotel", "rental", "airbnb")):
        out += RENTAL
    return out


def progress(room, done):
    items = items_for(room)
    return sum(1 for i in items if i[0] in done), len(items)
