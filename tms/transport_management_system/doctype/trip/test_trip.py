# Copyright (c) 2025, Galaxy Labs and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from tms.transport_management_system.api.driver_trip_monthly_report import get_driver_trip_monthly_report


class TestTrip(FrappeTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")

	def test_driver_trip_monthly_report_groups_driver_kpis(self):
		driver_a = self.make_staff("Driver Alpha")
		driver_b = self.make_staff("Driver Bravo")

		self.make_trip(
			driver=driver_a.name,
			date="2024-12-05",
			trip_value=500,
			distance=120,
			driver_commission_rate=10,
			driver_share=220,
			company_share=280,
			trip_status="Arrived",
			trip_route="Riyadh to Dammam",
		)
		self.make_trip(
			driver=driver_a.name,
			date="2024-12-11",
			trip_value=700,
			distance=80,
			driver_commission_rate=10,
			driver_share=300,
			company_share=400,
			trip_status="Scheduled",
			trip_route="Riyadh to Dammam",
		)
		self.make_trip(
			driver=driver_b.name,
			date="2024-12-18",
			trip_value=300,
			distance=60,
			driver_commission_rate=5,
			driver_share=100,
			company_share=200,
			trip_status="Cancelled",
			trip_route="Jeddah to Makkah",
		)
		self.make_trip(
			driver=driver_a.name,
			date="2024-11-09",
			trip_value=250,
			distance=40,
			driver_commission_rate=10,
			driver_share=90,
			company_share=160,
			trip_status="Arrived",
			trip_route="Riyadh to Dammam",
		)

		report = get_driver_trip_monthly_report(
			company=self.company,
			month="2024-12-01",
			include_cancelled=0,
		)

		self.assertEqual(report["summary"]["trip_count"], 2)
		self.assertEqual(report["summary"]["arrived_count"], 1)
		self.assertEqual(report["summary"]["scheduled_count"], 1)
		self.assertEqual(report["summary"]["cancelled_count"], 0)
		self.assertEqual(report["previous_summary"]["trip_count"], 1)
		self.assertEqual(report["summary"]["total_value"], 1200)
		self.assertEqual(report["summary"]["total_commission"], 120)
		self.assertEqual(report["driver_summary"][0]["driver"], driver_a.name)
		self.assertEqual(report["driver_summary"][0]["trip_count"], 2)
		self.assertEqual(report["top_routes"][0]["route_label"], "Riyadh to Dammam")
		self.assertEqual(len(report["daily_activity"]), 31)
		self.assertEqual(report["captain_month_matrix"]["summary"]["current_month_total"], 2)
		self.assertEqual(report["captain_month_matrix"]["summary"]["rolling_total"], 3)
		self.assertEqual(report["captain_month_matrix"]["rows"][0]["driver"], driver_a.name)
		self.assertEqual(report["captain_month_matrix"]["rows"][0]["counts"][-2], 1)
		self.assertEqual(report["captain_month_matrix"]["rows"][0]["counts"][-1], 2)

	def test_driver_trip_monthly_report_can_include_cancelled(self):
		driver = self.make_staff("Driver Cancelled")
		self.make_trip(
			driver=driver.name,
			date="2024-12-20",
			trip_value=450,
			distance=75,
			driver_commission_rate=8,
			driver_share=180,
			company_share=270,
			trip_status="Cancelled",
			trip_route="Dammam to Jubail",
		)

		report = get_driver_trip_monthly_report(
			company=self.company,
			month="2024-12-01",
			driver=driver.name,
			include_cancelled=1,
		)

		self.assertEqual(report["summary"]["trip_count"], 1)
		self.assertEqual(report["summary"]["cancelled_count"], 1)
		self.assertEqual(report["detail_rows"][0]["trip_status"], "Cancelled")
		self.assertEqual(report["captain_month_matrix"]["rows"][0]["counts"][-1], 1)

	def test_driver_trip_monthly_report_uses_vehicle_employee_company_history(self):
		employee = self.make_employee("Driver Vehicle History")
		vehicle_name = f"TEST-{frappe.generate_hash(length=6)}"
		self.make_vehicle(vehicle_name, employee.name)
		self.make_trip(
			driver=employee.employee_name,
			date="2024-12-22",
			trip_value=250,
			distance=42,
			driver_commission_rate=0,
			driver_share=0,
			company_share=250,
			trip_status="Scheduled",
			trip_route="Airport to City",
			assigned_vehicle=vehicle_name,
		)

		report = get_driver_trip_monthly_report(
			company=self.company,
			month="2024-12-01",
			driver=employee.employee_name,
			include_cancelled=0,
		)

		self.assertEqual(report["summary"]["trip_count"], 1)
		self.assertEqual(report["driver_summary"][0]["vehicle"], vehicle_name)
		self.assertEqual(report["detail_rows"][0]["resolved_company"], self.company)
		self.assertEqual(report["captain_month_matrix"]["rows"][0]["vehicle"], vehicle_name)

	def make_employee(self, employee_name):
		suffix = frappe.generate_hash(length=6)
		return frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": employee_name,
				"employee_name": f"{employee_name} {suffix}",
				"company": self.company,
				"date_of_joining": "2024-01-01",
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)

	def make_vehicle(self, vehicle_name, employee):
		return frappe.get_doc(
			{
				"doctype": "Vehicle",
				"title": vehicle_name,
				"license_plate": vehicle_name,
				"employee": employee,
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)

	def make_staff(self, first_name):
		suffix = frappe.generate_hash(length=6)
		return frappe.get_doc(
			{
				"doctype": "Staff",
				"enabled": 1,
				"first_name": first_name,
				"last_name": f"{first_name.replace(' ', '')}-{suffix}",
				"full_name": f"{first_name} {suffix}",
				"company_name": self.company,
			}
		).insert(ignore_permissions=True)

	def make_trip(
		self,
		driver,
		date,
		trip_value,
		distance,
		driver_commission_rate,
		driver_share,
		company_share,
		trip_status,
		trip_route,
		assigned_vehicle=None,
	):
		trip = {
			"doctype": "Trip",
			"driver": driver,
			"date": date,
			"departure": f"{date} 08:00:00",
			"arrival": f"{date} 10:00:00",
			"distance": distance,
			"trip_value": trip_value,
			"driver_commission_rate": driver_commission_rate,
			"driver_share": driver_share,
			"company_share": company_share,
			"trip_status": trip_status,
			"trip_route": trip_route,
			"from_location": "Origin",
			"to_location": "Destination",
		}
		if assigned_vehicle:
			trip["assigned_vehicle"] = assigned_vehicle
		return frappe.get_doc(trip).insert(ignore_permissions=True)
