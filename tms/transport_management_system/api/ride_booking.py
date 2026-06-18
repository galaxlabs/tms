#!/usr/bin/env python3
import frappe
import json
from frappe.utils import now_datetime, get_datetime
from frappe import _

@frappe.whitelist(allow_guest=True)
def get_available_routes():
    routes = frappe.get_all(
        "Route",
        fields=["name", "from_city", "to_city", "from_place_full", "to_place_full", "distance", "route_value", "driver_commission_rate", "duration", "duration_minutes"],
        limit_page_length=100
    )
    return {"success": True, "data": routes}

@frappe.whitelist(allow_guest=True)
def create_ride_request(**kwargs):
    data = frappe._dict(kwargs)
    user = frappe.session.user
    
    doc = frappe.get_doc({
        "doctype": "Booking",
        "customer_name": data.get("customer_name") or frappe.db.get_value("User", user, "full_name") or user or "Guest",
        "phone": data.get("phone") or "",
        "email": frappe.db.get_value("User", user, "email") if user and user != 'Guest' else data.get("email", ""),
        "pickup_location": data.get("pickup_location"),
        "dropoff_location": data.get("dropoff_location"),
        "travel_date": data.get("travel_date"),
        "vehicle_type": data.get("vehicle_type", "Sedan"),
        "passengers": data.get("passengers", 1),
        "message": data.get("message", ""),
        "source": "Mobile App",
        "status": "New",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    
    return {
        "success": True,
        "name": doc.name,
        "status": doc.status,
    }

@frappe.whitelist(allow_guest=False)
def get_ride_requests():
    user = frappe.session.user
    bookings = frappe.get_all(
        "Booking",
        filters={"status": ["in", ["New", "In Progress"]]},
        fields=["name", "customer_name", "phone", "pickup_location", "dropoff_location", "travel_date", "vehicle_type", "passengers", "message", "status"],
        order_by="creation desc",
        limit_page_length=50
    )
    return {"success": True, "data": bookings}

@frappe.whitelist(allow_guest=False)
def get_my_rides():
    user = frappe.session.user
    bookings = frappe.get_all(
        "Booking",
        filters={"email": frappe.db.get_value("User", user, "email")},
        fields=["name", "customer_name", "phone", "pickup_location", "dropoff_location", "travel_date", "vehicle_type", "passengers", "message", "status"],
        order_by="creation desc",
        limit_page_length=50
    )
    return {"success": True, "data": bookings}

@frappe.whitelist(allow_guest=False)
def accept_ride(booking_name):
    user = frappe.session.user
    if not frappe.db.exists("Booking", booking_name):
        frappe.throw(_("Booking not found"))
    
    booking = frappe.get_doc("Booking", booking_name)
    booking.status = "In Progress"
    booking.save(ignore_permissions=True)
    frappe.db.commit()
    
    return {"success": True, "name": booking.name, "status": booking.status}

@frappe.whitelist(allow_guest=False)
def complete_ride(booking_name):
    booking = frappe.get_doc("Booking", booking_name)
    booking.status = "Confirmed"
    booking.save(ignore_permissions=True)
    frappe.db.commit()
    
    return {"success": True, "name": booking.name, "status": booking.status}

@frappe.whitelist(allow_guest=False)
def cancel_ride(booking_name):
    booking = frappe.get_doc("Booking", booking_name)
    booking.status = "Cancelled"
    booking.save(ignore_permissions=True)
    frappe.db.commit()
    
    return {"success": True, "name": booking.name, "status": booking.status}

@frappe.whitelist(allow_guest=False)
def get_driver_dashboard():
    user = frappe.session.user
    new_bookings = frappe.db.count("Booking", {"status": "New"})
    my_trips = frappe.db.count("Trip", {"driver": user})
    available = frappe.get_all("Booking", filters={"status": "New"}, fields=["name","customer_name","pickup_location","dropoff_location","travel_date","vehicle_type","passengers","message"], limit=20)
    
    return {
        "success": True,
        "data": {
            "new_requests": new_bookings,
            "my_trips": my_trips,
            "available_rides": available,
        }
    }

