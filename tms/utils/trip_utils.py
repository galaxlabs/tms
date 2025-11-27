from frappe.utils import nowdate, getdate, now_datetime, time_diff_in_hours

def is_trip_active(trip):
    # 1) Cancelled → not active
    if trip.trip_status == "Cancelled":
        return False

    # 2) Arrival set → completed
    if trip.arrival:
        return False

    # 3) Trip date older than today → not active
    if getdate(trip.date) < getdate(nowdate()):
        return False

    # 4) If trip is older than 12 hours → treat as finished
    hours_since_creation = time_diff_in_hours(now_datetime(), trip.creation)
    if hours_since_creation > 12:
        return False

    # Otherwise, treat as active
    return True

# def get_or_create_trip_for_driver(driver_name, mobile_no):
#     """
#     1) Try to find latest non-cancelled Trip for this driver.
#     2) If not found, create a new Trip and set driver + mobile_no.
#     """
#     trip_name = frappe.db.get_value(
#         "Trip",
#         {
#             "driver": driver_name,
#             "trip_status": ["!=", "Cancelled"],
#         },
#         "name",
#         order_by="creation desc",
#     )

#     if trip_name:
#         return frappe.get_doc("Trip", trip_name)

#     # No trip found → create a new Trip
#     trip = frappe.new_doc("Trip")
#     trip.driver = driver_name
#     trip.mobile_no = mobile_no
#     trip.date = nowdate()
#     trip.trip_status = "Scheduled"  # matches your options: Scheduled/Departed/Arrived/Cancelled
#     # other fields (trip_route, from_location, etc.) can use your defaults
#     trip.insert(ignore_permissions=True)
#     frappe.db.commit()

#     frappe.logger().info(
#         f"[TMS WA] Created new Trip {trip.name} for driver {driver_name}"
#     )
#     return trip
