from tms.utils.whatsapp_bot.helpers.messaging import send_reply
from tms.utils.whatsapp_bot.flows.passenger_flow import write_passengers_and_finalize
from tms.utils.whatsapp_utils import send_trip_pdf_via_whatsapp

def ensure_route_or_ask(ctx):
    contact = ctx["contact"]
    trip = ctx["trip"]
    lang = ctx["lang"]

    route = contact.route
    if not route:
        send_reply(ctx["doc"], "ask_route_header", lang)
        return

    trip.trip_route = route
    trip.save(ignore_permissions=True)

    # now write passengers + finalize
    write_passengers_and_finalize(trip, contact, lang)
    send_trip_pdf_via_whatsapp(trip.name)

    trip.kashf_sent = 1
    trip.save(ignore_permissions=True)

    # reset contact
    contact.bot_state = "DONE"
    contact.expected_passengers = 0
    contact.received_images = 0
    contact.collected_file_urls_json = "[]"
    contact.save(ignore_permissions=True)
