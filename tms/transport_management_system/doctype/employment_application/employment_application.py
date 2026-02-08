# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class EmploymentApplication(Document):
	pass
    # def after_insert(self):
    #     # Web Form submission lands here
    #     self.create_employee_if_needed()

    # def create_employee_if_needed(self):
    #     if self.get("employee") or self.get("employee_created"):
    #         return

    #     # Basic duplicate guard (by email or mobile or id/iqama)
    #     filters = []
    #     if self.get("email"):
    #         filters.append(["Employee", "user_id", "=", self.email])
    #     if self.get("mobile"):
    #         filters.append(["Employee", "cell_number", "=", self.mobile])
    #     if self.get("id_iqama_no"):
    #         filters.append(["Employee", "custom_iqama_no", "=", self.id_iqama_no])

    #     # If any match, just link the first one
    #     for f in filters:
    #         existing = frappe.get_all("Employee", filters=[f], pluck="name", limit=1)
    #         if existing:
    #             self.db_set("employee", existing[0])
    #             self.db_set("employee_created", 1)
    #             return

    #     emp = frappe.new_doc("Employee")

    #     # Name
    #     first = (self.first_name or "").strip()
    #     father = (self.father_name or "").strip()
    #     family = (self.family_name or "").strip()
    #     emp.first_name = first or self.full_name or "Applicant"
    #     emp.last_name = family
    #     emp.employee_name = " ".join([x for x in [first, father, family] if x]).strip() or emp.first_name

    #     # Core info
    #     emp.gender = self.gender
    #     emp.date_of_birth = self.date_of_birth
    #     emp.blood_group = self.blood_group

    #     # Contact
    #     if self.email:
    #         emp.user_id = self.email
    #     if hasattr(emp, "cell_number"):
    #         emp.cell_number = self.mobile

    #     # Company + defaults
    #     emp.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")

    #     # Custom mapping (create these custom fields in Employee)
    #     # custom_iqama_no, custom_passport_no, custom_national_address, custom_iban
    #     emp.custom_iqama_no = self.id_iqama_no
    #     emp.custom_passport_no = self.passport_no
    #     emp.custom_national_address = self.national_address
    #     emp.custom_iban = self.iban

    #     # Image (Employee has image field in many setups)
    #     if hasattr(emp, "image") and self.photo:
    #         emp.image = self.photo

    #     emp.insert(ignore_permissions=True)

    #     self.db_set("employee", emp.name)
    #     self.db_set("employee_created", 1)


@frappe.whitelist()
def create_employee_from_application(application_name):
    app = frappe.get_doc("Employment Application", application_name)

    # If already linked, return existing
    if app.get("employee"):
        return app.employee

    # Basic duplicate guard (by email / mobile)
    if app.get("email"):
        existing = frappe.get_all("Employee", filters={"user_id": app.email}, pluck="name", limit=1)
        if existing:
            app.db_set("employee", existing[0])
            return existing[0]

    if app.get("mobile"):
        existing = frappe.get_all("Employee", filters={"cell_number": app.mobile}, pluck="name", limit=1)
        if existing:
            app.db_set("employee", existing[0])
            return existing[0]

    emp = frappe.new_doc("Employee")
    emp.first_name = app.first_name
    emp.last_name = app.family_name
    emp.employee_name = " ".join([x for x in [app.first_name, app.father_name, app.family_name] if x]).strip() \
        or (app.full_name or (app.first_name or ""))

    emp.date_of_birth = app.date_of_birth
    emp.gender = app.gender
    emp.blood_group = app.blood_group
    emp.user_id = app.email
    emp.cell_number = app.mobile
    emp.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")

    emp.insert(ignore_permissions=True)

    # Link back (create a Link field 'employee' in Employment Application)
    app.db_set("employee", emp.name)

    return emp.name
