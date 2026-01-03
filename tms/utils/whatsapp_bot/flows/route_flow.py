# apps/tms/tms/utils/whatsapp_bot/flows/route_flow.py
import frappe
from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
from tms.utils.whatsapp_bot.helpers.messaging import send_reply
from tms.utils.whatsapp_bot.flows.passenger_flow import write_passengers_and_finalize
from tms.utils.whatsapp_utils import send_trip_pdf_via_whatsapp


def get_available_routes(limit: int = 15) -> list[dict]:
    return (
        frappe.db.get_all(
            "Route",
            fields=["name", "from_city", "to_city"],
            order_by="modified desc",
            limit=limit,
        )
        or []
    )


def _format_routes_only(routes: list[dict]) -> str:
    """Return ONLY numbered routes lines (header comes from template ask_route)."""
    lines = []
    for i, r in enumerate(routes, start=1):
        fc = (r.get("from_city") or "").strip()
        tc = (r.get("to_city") or "").strip()
        lines.append(f"{i}) {fc} → {tc}")
    return "\n".join(lines)


def send_route_list(doc, contact, lang):
    """
    This is used by the 'route' command too.
    Build minimal ctx so {name}/{greet} works:
    - driver from contact.staff if present
    - trip from contact.current_trip
    """
    trip = None
    if getattr(contact, "current_trip", None) and frappe.db.exists("Trip", contact.current_trip):
        trip = frappe.get_doc("Trip", contact.current_trip)

    ctx = {
        "doc": doc,
        "contact": contact,
        "lang": lang,
        "trip": trip,
        "driver": getattr(contact, "staff", None),   # helps resolve_display_name -> Staff.full_name
    }
    return ensure_route_or_ask(ctx)


def ensure_route_or_ask(ctx) -> bool:
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]
    trip = ctx.get("trip")

    # load trip if not in ctx
    if not trip:
        trip_name = getattr(contact, "current_trip", None)
        if trip_name and frappe.db.exists("Trip", trip_name):
            trip = frappe.get_doc("Trip", trip_name)
            ctx["trip"] = trip

    if not trip:
        send_reply(doc, "trip_missing", lang, ctx=ctx)
        return False

    # If route already selected and state is WAITING_ROUTE -> finalize
    if getattr(trip, "trip_route", None) and (getattr(contact, "bot_state", "") == "WAITING_ROUTE"):
        return finalize_trip(ctx)

    routes = get_available_routes()
    if not routes:
        # Use one consistent template key (recommended)
        # Add this key in templates if not present: "no_routes_defined"
        send_reply(doc, "no_routes_defined", lang, ctx=ctx)
        return False

    # store stable mapping: number -> route name
    route_names = [r["name"] for r in routes if r.get("name")]
    set_json(contact, "route", route_names)

    # set state
    contact.db_set("bot_state", "WAITING_ROUTE", update_modified=False)

    # templates-only: show list via template ask_route
    routes_text = _format_routes_only(routes)
    send_reply(doc, "ask_route", lang, ctx=ctx, routes=routes_text)
    return True


def handle_route_choice(ctx, n) -> bool:
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]
    trip = ctx.get("trip")

    # load trip if not in ctx
    if not trip:
        trip_name = getattr(contact, "current_trip", None)
        if trip_name and frappe.db.exists("Trip", trip_name):
            trip = frappe.get_doc("Trip", trip_name)
            ctx["trip"] = trip

    if not trip:
        send_reply(doc, "trip_missing", lang, ctx=ctx)
        return False

    try:
        n_int = int(str(n).strip())
    except Exception:
        return False

    route_names = get_json(contact, "route", []) or []
    if not route_names:
        # If mapping missing, resend route list instead of failing
        ensure_route_or_ask(ctx)
        return False

    idx = n_int - 1
    if idx < 0 or idx >= len(route_names):
        return False

    route_name = route_names[idx]
    if not frappe.db.exists("Route", route_name):
        return False

    updates = {"trip_route": route_name}

    # optional from/to
    try:
        r = frappe.get_doc("Route", route_name)
        if trip.meta.has_field("from_location") and getattr(r, "from_city", None):
            updates["from_location"] = r.from_city
        if trip.meta.has_field("to_location") and getattr(r, "to_city", None):
            updates["to_location"] = r.to_city
    except Exception:
        pass

    frappe.db.set_value("Trip", trip.name, updates, update_modified=False)
    for k, v in updates.items():
        setattr(trip, k, v)

    send_reply(doc, "route_selected", lang, ctx=ctx)
    return finalize_trip(ctx)


def finalize_trip(ctx) -> bool:
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]
    trip = ctx.get("trip")

    if not trip:
        return False

    added = write_passengers_and_finalize(trip, contact, lang) or 0

    try:
        send_trip_pdf_via_whatsapp(trip.name)
    except Exception:
        frappe.log_error("WA PDF SEND FAIL", frappe.get_traceback())
        send_reply(doc, "pdf_send_failed", lang, ctx=ctx)
        return False

    contact.db_set("bot_state", "DONE", update_modified=False)

    send_reply(doc, "trip_done", lang, ctx=ctx, n=added)
    return True

# # apps/tms/tms/utils/whatsapp_bot/flows/route_flow.py
# import frappe
# from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
# from tms.utils.whatsapp_bot.helpers.messaging import send_reply
# from tms.utils.whatsapp_bot.flows.passenger_flow import write_passengers_and_finalize
# from tms.utils.whatsapp_utils import send_trip_pdf_via_whatsapp


# def get_available_routes(limit: int = 15) -> list[dict]:
#     return (
#         frappe.db.get_all(
#             "Route",
#             fields=["name", "from_city", "to_city"],
#             order_by="modified desc",
#             limit=limit,
#         )
#         or []
#     )


# def _format_route_list(routes: list[dict]) -> str:
#     lines = ["🛣️ Please reply with route number:"]
#     for i, r in enumerate(routes, start=1):
#         fc = (r.get("from_city") or "").strip()
#         tc = (r.get("to_city") or "").strip()
#         lines.append(f"{i}) {fc} → {tc}")
#     return "\n".join(lines)


# def send_route_list(doc, contact, lang):
#     trip = None
#     if getattr(contact, "current_trip", None) and frappe.db.exists("Trip", contact.current_trip):
#         trip = frappe.get_doc("Trip", contact.current_trip)
#     ctx = {"doc": doc, "contact": contact, "lang": lang, "trip": trip}
#     return ensure_route_or_ask(ctx)


# def ensure_route_or_ask(ctx) -> bool:
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")

#     # load trip if not in ctx
#     if not trip:
#         trip_name = getattr(contact, "current_trip", None)
#         if trip_name and frappe.db.exists("Trip", trip_name):
#             trip = frappe.get_doc("Trip", trip_name)
#             ctx["trip"] = trip

#     if not trip:
#         send_reply(doc, "trip_missing", lang, fallback="❗ Trip not found. Type 'reset' to start again.")
#         return False

#     # If route already selected and state is WAITING_ROUTE -> finalize
#     if getattr(trip, "trip_route", None) and (getattr(contact, "bot_state", "") == "WAITING_ROUTE"):
#         return finalize_trip(ctx)

#     routes = get_available_routes()
#     if not routes:
#         send_reply(doc, "route_empty", lang, fallback="⚠️ No routes configured in Route doctype.")
#         return False

#     # store stable mapping: number -> route name
#     route_names = [r["name"] for r in routes if r.get("name")]
#     set_json(contact, "route", route_names)

#     # set state
#     contact.db_set("bot_state", "WAITING_ROUTE", update_modified=False)

#     # IMPORTANT FIX:
#     # Use a key that is NOT in templates, so fallback is ALWAYS sent (route list will show).
#     msg = _format_route_list(routes)
#     send_reply(doc, "__route_list__", lang, fallback=msg)
#     return True


# def handle_route_choice(ctx, n) -> bool:
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")

#     # load trip if not in ctx
#     if not trip:
#         trip_name = getattr(contact, "current_trip", None)
#         if trip_name and frappe.db.exists("Trip", trip_name):
#             trip = frappe.get_doc("Trip", trip_name)
#             ctx["trip"] = trip

#     if not trip:
#         send_reply(doc, "trip_missing", lang, fallback="❗ Trip not found. Type 'reset' to start again.")
#         return False

#     try:
#         n_int = int(str(n).strip())
#     except Exception:
#         return False

#     route_names = get_json(contact, "route", []) or []
#     if not route_names:
#         # If mapping missing, resend route list instead of failing
#         ensure_route_or_ask(ctx)
#         return False

#     idx = n_int - 1
#     if idx < 0 or idx >= len(route_names):
#         return False

#     route_name = route_names[idx]
#     if not frappe.db.exists("Route", route_name):
#         return False

#     updates = {"trip_route": route_name}

#     # optional from/to
#     try:
#         r = frappe.get_doc("Route", route_name)
#         if trip.meta.has_field("from_location") and getattr(r, "from_city", None):
#             updates["from_location"] = r.from_city
#         if trip.meta.has_field("to_location") and getattr(r, "to_city", None):
#             updates["to_location"] = r.to_city
#     except Exception:
#         pass

#     frappe.db.set_value("Trip", trip.name, updates, update_modified=False)

#     for k, v in updates.items():
#         setattr(trip, k, v)

#     send_reply(doc, "route_selected", lang, fallback="✅ Route selected.")
#     return finalize_trip(ctx)


# def finalize_trip(ctx) -> bool:
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")

#     if not trip:
#         return False

#     added = write_passengers_and_finalize(trip, contact, lang) or 0

#     try:
#         send_trip_pdf_via_whatsapp(trip.name)
#     except Exception:
#         frappe.log_error("WA PDF SEND FAIL", frappe.get_traceback())
#         send_reply(doc, "pdf_send_failed", lang, fallback="⚠️ Trip created but PDF sending failed.")
#         return False

#     contact.db_set("bot_state", "DONE", update_modified=False)

#     send_reply(
#         doc,
#         "trip_done",
#         lang,
#         fallback="✅ Trip ready. PDF sent. Passengers added: {n}.",
#         n=added,
#     )
#     return True

# apps/tms/tms/utils/whatsapp_bot/flows/route_flow.py
# import json
# import frappe
# from tms.utils.whatsapp_bot.helpers.messaging import send_reply
# from tms.utils.whatsapp_bot.flows.passenger_flow import write_passengers_and_finalize
# from tms.utils.whatsapp_utils import send_trip_pdf_via_whatsapp


# def _format_route_list(routes: list[dict]) -> str:
#     lines = ["🛣️ Please reply with route number:"]
#     for i, r in enumerate(routes, start=1):
#         fc = (r.get("from_city") or "").strip()
#         tc = (r.get("to_city") or "").strip()
#         lines.append(f"{i}) {fc} → {tc}")
#     return "\n".join(lines)


# def get_available_routes(limit: int = 15) -> list[dict]:
#     return frappe.db.get_all(
#         "Route",
#         fields=["name", "from_city", "to_city"],
#         order_by="modified desc",
#         limit=limit,
#     ) or []


# def ensure_route_or_ask(ctx) -> bool:
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")

#     if not trip:
#         trip_name = getattr(contact, "current_trip", None)
#         if trip_name and frappe.db.exists("Trip", trip_name):
#             trip = frappe.get_doc("Trip", trip_name)
#             ctx["trip"] = trip

#     if not trip:
#         send_reply(doc, "trip_missing", lang, fallback="❗ Trip not found. Type 'reset' to start again.")
#         return False

#     # If route already set, finalize
#     if getattr(trip, "trip_route", None) and contact.bot_state != "DONE":
#         return finalize_trip(ctx)

#     routes = get_available_routes()
#     if not routes:
#         send_reply(doc, "route_empty", lang, fallback="⚠️ No routes configured in Route doctype.")
#         return False

#     route_names = [r["name"] for r in routes if r.get("name")]

#     # ✅ store in correct json field
#     frappe.db.set_value(
#         contact.doctype,
#         contact.name,
#         {
#             "route_options_json": json.dumps(route_names),
#             "bot_state": "WAITING_ROUTE",
#         },
#         update_modified=False,
#     )

#     # keep memory in sync
#     contact.route_options_json = json.dumps(route_names)
#     contact.bot_state = "WAITING_ROUTE"

#     send_reply(doc, "ask_route", lang, fallback=_format_route_list(routes))
#     return True


# def handle_route_choice(ctx, n) -> bool:
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")

#     if not trip:
#         trip_name = getattr(contact, "current_trip", None)
#         if trip_name and frappe.db.exists("Trip", trip_name):
#             trip = frappe.get_doc("Trip", trip_name)
#             ctx["trip"] = trip

#     if not trip:
#         send_reply(doc, "trip_missing", lang, fallback="❗ Trip not found. Type 'reset' to start again.")
#         return False

#     try:
#         n_int = int(str(n).strip())
#     except Exception:
#         send_reply(doc, "route_invalid", lang, fallback="❗ Please reply with the route number (example: 2).")
#         return False

#     # ✅ read from correct json field
#     try:
#         route_names = json.loads(contact.route_options_json or "[]") or []
#     except Exception:
#         route_names = []

#     if not route_names:
#         send_reply(doc, "route_invalid", lang, fallback="❗ Route list missing. Type 'reset' and try again.")
#         return False

#     idx = n_int - 1
#     if idx < 0 or idx >= len(route_names):
#         send_reply(doc, "route_invalid", lang, fallback="❗ Please reply with the route number from the list (example: 2).")
#         return False

#     route_name = route_names[idx]
#     if not frappe.db.exists("Route", route_name):
#         send_reply(doc, "route_invalid", lang, fallback="❗ That route no longer exists. Type 'reset' and try again.")
#         return False

#     updates = {"trip_route": route_name}
#     frappe.db.set_value("Trip", trip.name, updates, update_modified=False)
#     trip.trip_route = route_name

#     send_reply(doc, "route_selected", lang, fallback="✅ Route selected.")
#     return finalize_trip(ctx)


# def finalize_trip(ctx) -> bool:
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")
#     if not trip:
#         return False

#     added = write_passengers_and_finalize(trip, contact, lang) or 0

#     try:
#         send_trip_pdf_via_whatsapp(trip.name)
#     except Exception:
#         frappe.log_error("WA PDF SEND FAIL", frappe.get_traceback())
#         send_reply(doc, "pdf_send_failed", lang, fallback="⚠️ Trip created but PDF sending failed.")
#         return False

#     contact.db_set("bot_state", "DONE", update_modified=False)

#     send_reply(
#         doc,
#         "trip_done",
#         lang,
#         fallback="✅ Trip ready. PDF sent. Passengers added: {n}.",
#         n=added,
#     )
#     return True

# # apps/tms/tms/utils/whatsapp_bot/flows/route_flow.py
# import frappe
# from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
# from tms.utils.whatsapp_bot.helpers.messaging import send_reply
# from tms.utils.whatsapp_bot.flows.passenger_flow import write_passengers_and_finalize
# from tms.utils.whatsapp_utils import send_trip_pdf_via_whatsapp


# def get_available_routes(limit: int = 15) -> list[dict]:
#     """Fetch routes from Route doctype."""
#     return frappe.db.get_all(
#         "Route",
#         fields=["name", "from_city", "to_city"],
#         order_by="modified desc",
#         limit=limit,
#     ) or []


# def _format_route_list(routes: list[dict]) -> str:
#     lines = ["🛣️ Please reply with route number:"]
#     for i, r in enumerate(routes, start=1):
#         fc = (r.get("from_city") or "").strip()
#         tc = (r.get("to_city") or "").strip()
#         lines.append(f"{i}) {fc} → {tc}")
#     return "\n".join(lines)


# def send_route_list(doc, contact, lang):
#     """Compatibility helper (some code calls this directly)."""
#     trip = None
#     if getattr(contact, "current_trip", None) and frappe.db.exists("Trip", contact.current_trip):
#         trip = frappe.get_doc("Trip", contact.current_trip)
#     ctx = {"doc": doc, "contact": contact, "lang": lang, "trip": trip}
#     return ensure_route_or_ask(ctx)


# def ensure_route_or_ask(ctx) -> bool:
#     """
#     Used by:
#       - handlers/media.py after OCR is OK
#       - handlers/resend.py after resend OCR is OK

#     If route is already set -> finalize.
#     Else show route list, store route names on contact.route, set state WAITING_ROUTE.
#     """
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")

#     # load trip if not in ctx
#     if not trip:
#         trip_name = getattr(contact, "current_trip", None)
#         if trip_name and frappe.db.exists("Trip", trip_name):
#             trip = frappe.get_doc("Trip", trip_name)
#             ctx["trip"] = trip

#     if not trip:
#         send_reply(doc, "trip_missing", lang, fallback="❗ Trip not found. Type 'reset' to start again.")
#         return False

#     # if already selected, finalize
# # If route exists but bot isn't DONE yet, still ask route (avoid auto-finalize)
#     if getattr(trip, "trip_route", None) and (contact.bot_state in ("WAITING_ROUTE",)):
#         return finalize_trip(ctx)

#     routes = get_available_routes()
#     if not routes:
#         send_reply(doc, "route_empty", lang, fallback="⚠️ No routes configured in Route doctype.")
#         return False

#     # store stable mapping: number -> route name
#     route_names = [r["name"] for r in routes if r.get("name")]
#     set_json(contact, "route", route_names)
#     contact.db_set("bot_state", "WAITING_ROUTE", update_modified=False)



#     msg = _format_route_list(routes)
#     send_reply(doc, "ask_route", lang, fallback=msg)
#     return True

# def handle_route_choice(ctx, n) -> bool:
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")

#     # load trip if not in ctx
#     if not trip:
#         trip_name = getattr(contact, "current_trip", None)
#         if trip_name and frappe.db.exists("Trip", trip_name):
#             trip = frappe.get_doc("Trip", trip_name)
#             ctx["trip"] = trip

#     if not trip:
#         send_reply(doc, "trip_missing", lang, fallback="❗ Trip not found. Type 'reset' to start again.")
#         return False

#     # ---- make it compatible: handlers might pass text, not int ----
#     try:
#         n_int = int(str(n).strip())
#     except Exception:
#         return False

#     route_names = get_json(contact, "route", []) or []
#     if not route_names:
#         send_reply(doc, "route_invalid", lang, fallback="❗ Route list missing. Type 'reset' and try again.")
#         return False

#     idx = n_int - 1
#     if idx < 0 or idx >= len(route_names):
#         return False

#     route_name = route_names[idx]
#     if not frappe.db.exists("Route", route_name):
#         return False

#     updates = {"trip_route": route_name}

#     # optional from/to
#     try:
#         r = frappe.get_doc("Route", route_name)
#         if trip.meta.has_field("from_location") and getattr(r, "from_city", None):
#             updates["from_location"] = r.from_city
#         if trip.meta.has_field("to_location") and getattr(r, "to_city", None):
#             updates["to_location"] = r.to_city
#     except Exception:
#         pass

#     # ✅ single UPDATE, avoids locks caused by trip.save()
#     frappe.db.set_value("Trip", trip.name, updates, update_modified=False)

#     # keep ctx trip in sync (optional)
#     for k, v in updates.items():
#         setattr(trip, k, v)

#     send_reply(doc, "route_selected", lang, fallback="✅ Route selected.")
#     return finalize_trip(ctx)



# def finalize_trip(ctx) -> bool:
#     """
#     Writes passengers into Trip and sends PDF, then marks DONE.
#     """
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     trip = ctx.get("trip")

#     if not trip:
#         return False

#     added = write_passengers_and_finalize(trip, contact, lang) or 0

#     try:
#         send_trip_pdf_via_whatsapp(trip.name)
#     except Exception:
#         frappe.log_error("WA PDF SEND FAIL", frappe.get_traceback())
#         send_reply(doc, "pdf_send_failed", lang, fallback="⚠️ Trip created but PDF sending failed.")
#         return False

#     contact.db_set("bot_state", "DONE", update_modified=False)

#     send_reply(
#         doc,
#         "trip_done",
#         lang,
#         fallback="✅ Trip ready. PDF sent. Passengers added: {n}.",
#         n=added,
#     )
#     return True
