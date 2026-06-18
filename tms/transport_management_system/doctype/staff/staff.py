import frappe
from frappe import _
from frappe.model.document import Document
from frappe.permissions import add_user_permission, remove_user_permission
from tms.utils.party_defaults import (
    get_valid_default_customer_group,
    get_valid_default_territory,
)


class Staff(Document):
    # ------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------

    def before_validate(self):
        self.normalize_fields()
        self.set_full_name()
        self.set_staff_title_fields()
        self.apply_restriction_defaults()

    def validate(self):
        self.validate_required_fields()

    def before_save(self):
        self.rename_staff_doc_if_needed()

    def after_insert(self):
        self.sync_all_related_docs()
        self.reset_and_assign_user_permissions()

    def on_update(self):
        self.sync_all_related_docs()
        self.reset_and_assign_user_permissions()

    def on_trash(self):
        self.remove_user_permissions_from_doc(self)

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def has_field(self, fieldname):
        return self.meta.has_field(fieldname)

    def get_clean_email(self):
        return (self.email or "").strip().lower()

    def get_employee_status(self):
        """
        ERPNext Employee status options:
        Active, Suspended, Left

        Staff enabled = 1 -> Employee Active
        Staff enabled = 0 -> Employee Suspended
        """
        return "Active" if getattr(self, "enabled", 0) else "Suspended"

    def get_driver_status(self):
        """
        ERPNext Driver status commonly accepts:
        Active, Suspended, Inactive

        If your Driver DocType uses different options, adjust here only.
        """
        return "Active" if getattr(self, "enabled", 0) else "Suspended"

    def normalize_fields(self):
        if self.has_field("first_name"):
            self.first_name = (self.first_name or "").strip()

        if self.has_field("middle_name"):
            self.middle_name = (self.middle_name or "").strip()

        if self.has_field("last_name"):
            self.last_name = (self.last_name or "").strip()

        if self.has_field("email"):
            self.email = self.get_clean_email()

        if self.has_field("mobile_no"):
            self.mobile_no = (self.mobile_no or "").strip()

        if self.has_field("phone"):
            self.phone = (self.phone or "").strip()

    def set_full_name(self):
        parts = [
            getattr(self, "first_name", None),
            getattr(self, "middle_name", None),
            getattr(self, "last_name", None),
        ]

        self.full_name = " ".join([
            p.strip() for p in parts if p and p.strip()
        ])

    def set_staff_title_fields(self):
        if self.has_field("staff_name"):
            self.staff_name = self.full_name

        if self.has_field("doc_title"):
            self.doc_title = self.full_name

        if self.has_field("title"):
            self.title = self.full_name

    def validate_required_fields(self):
        if not self.full_name:
            frappe.throw(_("First Name, Middle Name, or Last Name is required."))

        if getattr(self, "can_login", 0) and not self.email:
            frappe.throw(_("Email is required when Can Login is enabled."))

        if getattr(self, "is_employee", 0) and not getattr(self, "company_name", None):
            frappe.throw(_("Company is required when Is Employee is checked."))

    # ------------------------------------------------------------
    # Restriction Defaults
    # ------------------------------------------------------------

    def apply_restriction_defaults(self):
        """
        Staff field:
        restricted_to_staff

        Existing old field spelling:
        ristrcted_to_user
        ristrcted_to_company
        ristrcted_to_employee
        ristrcted_to_driver
        ristrcted_to_vehicle
        """

        if not getattr(self, "restricted_to_staff", 0):
            return

        if self.has_field("ristrcted_to_user"):
            self.ristrcted_to_user = 1

        if self.has_field("ristrcted_to_company"):
            self.ristrcted_to_company = 1

        if self.has_field("ristrcted_to_employee"):
            self.ristrcted_to_employee = 1

        if self.has_field("ristrcted_to_driver"):
            self.ristrcted_to_driver = 1 if getattr(self, "is_driver", 0) else 0

        if self.has_field("ristrcted_to_vehicle"):
            self.ristrcted_to_vehicle = 1 if getattr(self, "vehicle_assigned", None) else 0

    # ------------------------------------------------------------
    # Main Sync Entry Point
    # ------------------------------------------------------------

    def sync_all_related_docs(self):
        if getattr(self, "can_login", 0) or self.email:
            self.sync_user()

        if getattr(self, "is_employee", 0):
            self.sync_employee()

        if getattr(self, "is_driver", 0):
            if getattr(self, "is_employee", 0) and not getattr(self, "employee", None):
                self.sync_employee()

            self.sync_driver()
        else:
            self.disable_driver_if_unchecked()

        self.sync_customer()

    # ------------------------------------------------------------
    # User Sync
    # ------------------------------------------------------------

    def sync_user(self):
        if not self.email:
            return

        old_doc = self.get_doc_before_save()
        old_email = (old_doc.email or "").strip().lower() if old_doc else None

        if old_email and old_email != self.email and frappe.db.exists("User", old_email):
            if frappe.db.exists("User", self.email):
                frappe.throw(
                    _("Cannot change email to {0}, because a User already exists with this email.")
                    .format(self.email)
                )

            frappe.rename_doc(
                "User",
                old_email,
                self.email,
                force=True,
                merge=False,
                show_alert=False,
            )

        if frappe.db.exists("User", self.email):
            user = frappe.get_doc("User", self.email)
        else:
            user = frappe.get_doc({
                "doctype": "User",
                "email": self.email,
                "first_name": self.first_name or self.full_name,
                "middle_name": getattr(self, "middle_name", "") or "",
                "last_name": getattr(self, "last_name", "") or "",
                "send_welcome_email": 1 if getattr(self, "can_login", 0) else 0,
            })
            user.insert(ignore_permissions=True)

        user.first_name = self.first_name or self.full_name
        user.middle_name = getattr(self, "middle_name", "") or ""
        user.last_name = getattr(self, "last_name", "") or ""
        user.full_name = self.full_name
        user.enabled = 1 if getattr(self, "enabled", 0) else 0

        if self.has_field("time_zone"):
            user.time_zone = self.time_zone or ""

        if self.has_field("mobile_no") and self.mobile_no:
            user.mobile_no = self.mobile_no

        if getattr(self, "role_profile", None):
            user.role_profile_name = self.role_profile
        else:
            user.role_profile_name = None
            user.set("roles", [])

            for r in self.get("role") or []:
                if getattr(r, "role", None):
                    user.append("roles", {"role": r.role})

        if getattr(self, "module_profile", None):
            if user.meta.has_field("module_profile"):
                user.module_profile = self.module_profile

        user.save(ignore_permissions=True)

    # ------------------------------------------------------------
    # Employee Sync
    # ------------------------------------------------------------

    def sync_employee(self):
        employee_name = getattr(self, "employee", None)

        if employee_name and frappe.db.exists("Employee", employee_name):
            emp = frappe.get_doc("Employee", employee_name)
        else:
            emp = frappe.get_doc({
                "doctype": "Employee",
                "first_name": self.first_name or self.full_name,
                "middle_name": getattr(self, "middle_name", "") or "",
                "last_name": getattr(self, "last_name", "") or "",
                "employee_name": self.full_name,
                "date_of_birth": getattr(self, "date_of_birth", None),
                "date_of_joining": getattr(self, "date_of_joining", None),
                "company": getattr(self, "company_name", None),
                "user_id": self.email or None,
                "gender": getattr(self, "gender", None),
                "blood_group": getattr(self, "blood_group", "") or "",
                "department": getattr(self, "department", "") or "",
                "designation": getattr(self, "designation", "") or "",
                "status": self.get_employee_status(),
            })
            emp.insert(ignore_permissions=True)

            if self.has_field("employee"):
                self.db_set("employee", emp.name, update_modified=False)

        emp.first_name = self.first_name or self.full_name

        if emp.meta.has_field("middle_name"):
            emp.middle_name = getattr(self, "middle_name", "") or ""

        emp.last_name = getattr(self, "last_name", "") or ""
        emp.employee_name = self.full_name
        emp.date_of_birth = getattr(self, "date_of_birth", None)
        emp.date_of_joining = getattr(self, "date_of_joining", None)
        emp.company = getattr(self, "company_name", None)
        emp.user_id = self.email or None
        emp.gender = getattr(self, "gender", None)
        emp.blood_group = getattr(self, "blood_group", "") or ""
        emp.department = getattr(self, "department", "") or ""
        emp.designation = getattr(self, "designation", "") or ""
        emp.status = self.get_employee_status()

        emp.save(ignore_permissions=True)

    # ------------------------------------------------------------
    # Driver Sync
    # ------------------------------------------------------------

    def sync_driver(self):
        driver = None

        if getattr(self, "driver", None) and frappe.db.exists("Driver", self.driver):
            driver = frappe.get_doc("Driver", self.driver)

        if not driver:
            old_doc = self.get_doc_before_save()
            old_full_name = old_doc.full_name if old_doc else None

            driver_name = None

            if old_full_name:
                driver_name = frappe.db.exists("Driver", {"full_name": old_full_name})

            if not driver_name:
                driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})

            if driver_name:
                driver = frappe.get_doc("Driver", driver_name)

        if not driver:
            driver = frappe.get_doc({
                "doctype": "Driver",
                "full_name": self.full_name,
                "status": self.get_driver_status(),
                "employee": getattr(self, "employee", None) or None,
                "cell_number": getattr(self, "mobile_no", None) or getattr(self, "phone", None) or "",
            })
            driver.insert(ignore_permissions=True)

        driver.full_name = self.full_name
        driver.status = self.get_driver_status()
        driver.employee = getattr(self, "employee", None) or None
        driver.cell_number = getattr(self, "mobile_no", None) or getattr(self, "phone", None) or ""

        driver.save(ignore_permissions=True)

        if self.has_field("driver") and getattr(self, "driver", None) != driver.name:
            self.db_set("driver", driver.name, update_modified=False)

        self.copy_documents_to_driver(driver)

    def disable_driver_if_unchecked(self):
        if not getattr(self, "driver", None):
            return

        if frappe.db.exists("Driver", self.driver):
            driver = frappe.get_doc("Driver", self.driver)
            driver.status = "Suspended"
            driver.save(ignore_permissions=True)

    def copy_documents_to_driver(self, driver_doc):
        if not driver_doc.meta.has_field("documents"):
            return

        driver_doc.set("documents", [])

        for d in self.get("documents") or []:
            driver_doc.append("documents", {
                "document_type": getattr(d, "document_type", None),
                "document_no": getattr(d, "document_no", None),
                "issue_date": getattr(d, "issue_date", None),
                "expiry_date": getattr(d, "expiry_date", None),
            })

        driver_doc.save(ignore_permissions=True)

    # ------------------------------------------------------------
    # Customer Sync
    # ------------------------------------------------------------

    def sync_customer(self):
        if not self.email:
            return

        old_doc = self.get_doc_before_save()
        old_email = (old_doc.email or "").strip().lower() if old_doc else None

        customer_name = frappe.db.exists("Customer", {"email_id": self.email})

        if not customer_name and old_email:
            customer_name = frappe.db.exists("Customer", {"email_id": old_email})

        if not customer_name and frappe.db.exists("Customer", self.full_name):
            customer_name = self.full_name

        if not customer_name:
            customer_name = frappe.db.exists("Customer", {"customer_name": self.full_name})

        customer_country = self.get_customer_country()

        if customer_name:
            customer = frappe.get_doc("Customer", customer_name)
        else:
            customer = frappe.new_doc("Customer")
            customer.customer_name = self.full_name
            customer.customer_type = "Individual"
            customer.email_id = self.email

        customer.customer_name = self.full_name
        customer.email_id = self.email

        self.set_customer_country_field(customer, customer_country)
        self.set_customer_required_defaults(customer)

        if customer.meta.has_field("disabled"):
            customer.disabled = 0 if getattr(self, "enabled", 0) else 1

        customer.save(ignore_permissions=True)

    def set_customer_country_field(self, customer, country):
        if not country:
            country = "Saudi Arabia"

        possible_fieldnames = [
            "customer_country",
            "custom_customer_country",
            "country",
            "custom_country",
        ]

        for fieldname in possible_fieldnames:
            if customer.meta.has_field(fieldname):
                customer.set(fieldname, country)
                return

        for df in customer.meta.fields:
            if (df.label or "").strip().lower() == "customer country":
                customer.set(df.fieldname, country)
                return

    def set_customer_required_defaults(self, customer):
        if customer.meta.has_field("customer_group"):
            customer.customer_group = self.get_default_customer_group(customer.customer_group)

        if customer.meta.has_field("territory") and not customer.territory:
            customer.territory = self.get_default_territory()

    def get_customer_country(self):
        if getattr(self, "nationality", None):
            return self.nationality

        company = getattr(self, "company_name", None)

        if company and frappe.db.exists("Company", company):
            country = frappe.db.get_value("Company", company, "country")
            if country:
                return country

        return "Saudi Arabia"

    def get_default_customer_group(self, current_value=None):
        return get_valid_default_customer_group(current_value)

    def is_valid_customer_group(self, customer_group):
        if not customer_group or not frappe.db.exists("Customer Group", customer_group):
            return False

        return not frappe.db.get_value("Customer Group", customer_group, "is_group")

    def get_default_territory(self):
        return get_valid_default_territory()

    # ------------------------------------------------------------
    # Staff Rename
    # ------------------------------------------------------------

    def rename_staff_doc_if_needed(self):
        """
        Rename Staff docname when full_name changes.

        Important:
        autoname = field:full_name only works on insert.
        For existing Staff, we must explicitly rename the document.
        """

        if self.is_new():
            return

        if not self.full_name:
            return

        old_name = self.name
        new_name = self.full_name.strip()

        if old_name == new_name:
            return

        if frappe.db.exists("Staff", new_name):
            frappe.throw(
                _("Cannot rename Staff from {0} to {1}, because another Staff record already exists with this name.")
                .format(old_name, new_name)
            )

        frappe.rename_doc(
            "Staff",
            old_name,
            new_name,
            force=True,
            merge=False,
            show_alert=False,
        )

        # Very important: update current document object after rename
        self.name = new_name
    # ------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------

    def reset_and_assign_user_permissions(self):
        old_doc = self.get_doc_before_save()

        if old_doc:
            self.remove_user_permissions_from_doc(old_doc)

        self.remove_user_permissions_from_doc(self)
        self.assign_user_permissions()

    def assign_user_permissions(self):
        if not self.email:
            return

        if getattr(self, "ristrcted_to_user", 0):
            add_user_permission("User", self.email, self.email)

        if getattr(self, "restricted_to_staff", 0):
            add_user_permission("Staff", self.name, self.email)

        if getattr(self, "employee", None) and getattr(self, "ristrcted_to_employee", 0):
            add_user_permission("Employee", self.employee, self.email)

        if getattr(self, "driver", None) and getattr(self, "ristrcted_to_driver", 0):
            add_user_permission("Driver", self.driver, self.email)

        if getattr(self, "company_name", None) and getattr(self, "ristrcted_to_company", 0):
            add_user_permission("Company", self.company_name, self.email)

        if getattr(self, "vehicle_assigned", None) and getattr(self, "ristrcted_to_vehicle", 0):
            add_user_permission("Vehicle", self.vehicle_assigned, self.email)

    def remove_user_permissions_from_doc(self, doc):
        email = (getattr(doc, "email", None) or "").strip().lower()

        if not email:
            return

        permission_pairs = [
            ("User", email if getattr(doc, "ristrcted_to_user", 0) else None),
            ("Staff", getattr(doc, "name", None) if getattr(doc, "restricted_to_staff", 0) else None),
            ("Employee", getattr(doc, "employee", None)),
            ("Driver", getattr(doc, "driver", None)),
            ("Company", getattr(doc, "company_name", None)),
            ("Vehicle", getattr(doc, "vehicle_assigned", None)),
        ]

        for doctype, value in permission_pairs:
            if not value:
                continue

            try:
                remove_user_permission(doctype, value, email)
            except Exception:
                pass

# import frappe
# from frappe.model.document import Document
# from frappe.permissions import add_user_permission, remove_user_permission
from tms.utils.party_defaults import (
    get_valid_default_customer_group,
    get_valid_default_territory,
)


# class Staff(Document):

#     def after_insert(self):
#         # always recompute full_name
#         self.full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
#         self.create_related_docs()
#         self.assign_user_permissions()

#     def on_update(self):
#         # recompute full_name on update too
#         self.full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
#         self.sync_user()
#         self.sync_employee()
#         self.sync_driver()
#         self.assign_user_permissions()

#     def on_trash(self):
#         self.remove_user_permissions()

#     # -----------------------------
#     # User + Employee + Driver + Customer
#     # -----------------------------
#     def create_related_docs(self):
#         if not self.email:
#             frappe.throw("Email is required to create a User.")

#         # -------- USER --------
#         if not frappe.db.exists("User", self.email):
#             user = frappe.get_doc({
#                 "doctype": "User",
#                 "email": self.email,
#                 "first_name": self.first_name,
#                 "last_name": self.last_name,
#                 "enabled": 1 if self.enabled else 0,
#                 "time_zone": self.time_zone or "",
#                 "send_welcome_email": 1
#             })
#             user.insert(ignore_permissions=True)
#             frappe.msgprint(f"User created: {self.email}")
#         else:
#             user = frappe.get_doc("User", self.email)

#         # Set role profile or roles
#         if self.role_profile:
#             user.role_profile_name = self.role_profile
#         else:
#             user.set("roles", [])
#             if self.role:
#                 for r in self.role:
#                     user.append("roles", {"role": r.role})

#         # Basic fields only
#         user.first_name = self.first_name
#         user.last_name = self.last_name
#         user.time_zone = self.time_zone or ""
#         user.enabled = 1 if self.enabled else 0
#         user.save(ignore_permissions=True)

#         # -------- EMPLOYEE --------
#         if self.is_employee and not self.employee:
#             emp = frappe.get_doc({
#                 "doctype": "Employee",
#                 "first_name": self.first_name,
#                 "last_name": self.last_name,
#                 "employee_name": self.full_name,
#                 "date_of_birth": self.date_of_birth,
#                 "date_of_joining": self.date_of_joining,
#                 "company": self.company_name,
#                 "user_id": self.email,
#                 "branch": self.branch,
#                 "gender": self.gender,
#                 "blood_group": getattr(self, "blood_group", "") or "",
#                 "department": self.department or "",
#                 "designation": self.designation or ""
#             })
#             emp.insert(ignore_permissions=True)
#             self.db_set("employee", emp.name)
#             frappe.msgprint(f"Employee created: {emp.name}")

#         # -------- DRIVER --------
#         if self.is_driver:
#             driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})
#             if not driver_name:
#                 driver = frappe.get_doc({
#                     "doctype": "Driver",
#                     "full_name": self.full_name,
#                     "status": "Active",
#                     "employee": self.employee or None,
#                     "cell_number": self.mobile_no or self.phone or ""
#                 })
#                 driver.insert(ignore_permissions=True)
#                 frappe.msgprint(f"Driver created: {driver.name}")
#                 self.copy_documents(driver)
#             else:
#                 # Driver already exists, just sync documents
#                 driver = frappe.get_doc("Driver", driver_name)
#                 self.copy_documents(driver)

#         # -------- CUSTOMER --------
#         if not frappe.db.exists("Customer", {"email_id": self.email}):
#             customer = frappe.get_doc({
#                 "doctype": "Customer",
#                 "customer_name": self.full_name,
#                 "customer_type": "Individual",
#                 "email_id": self.email
#             })
#             customer.insert(ignore_permissions=True)
#             frappe.msgprint(f"Customer created for {self.full_name} ({self.email})")

#     # -----------------------------
#     # Sync Methods
#     # -----------------------------
#     def sync_user(self):
#         if frappe.db.exists("User", self.email):
#             user = frappe.get_doc("User", self.email)
#             user.first_name = self.first_name
#             user.last_name = self.last_name
#             user.enabled = 1 if self.enabled else 0
#             user.time_zone = self.time_zone or ""

#             if self.role_profile:
#                 user.role_profile_name = self.role_profile
#             else:
#                 user.set("roles", [])
#                 if self.role:
#                     for r in self.role:
#                         user.append("roles", {"role": r.role})

#             user.save(ignore_permissions=True)

#     def sync_employee(self):
#         if self.employee and frappe.db.exists("Employee", self.employee):
#             emp = frappe.get_doc("Employee", self.employee)
#             emp.employee_name = self.full_name
#             emp.first_name = self.first_name
#             emp.last_name = self.last_name
#             emp.company = self.company_name
#             emp.user_id = self.email
#             emp.branch = self.branch
#             emp.gender = self.gender
#             emp.blood_group = getattr(self, "blood_group", "") or ""
#             emp.department = self.department or ""
#             emp.designation = self.designation or ""
#             emp.save(ignore_permissions=True)

#     def sync_driver(self):
#         if self.is_driver:
#             driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})
#             if driver_name:
#                 driver = frappe.get_doc("Driver", driver_name)
#                 driver.full_name = self.full_name
#                 driver.employee = self.employee or None
#                 driver.cell_number = self.mobile_no or self.phone or ""
#                 driver.save(ignore_permissions=True)
#                 self.copy_documents(driver)

#     def copy_documents(self, driver_doc):
#         driver_doc.set("documents", [])
#         for d in self.documents:
#             driver_doc.append("documents", {
#                 "document_type": d.document_type,
#                 "document_no": d.document_no,
#                 "issue_date": d.issue_date,
#                 "expiry_date": d.expiry_date
#             })
#         driver_doc.save(ignore_permissions=True)

#     # -----------------------------
#     # Permissions
#     # -----------------------------
#     def assign_user_permissions(self):
#         if not self.email:
#             return

#         if self.employee and self.ristrcted_to_employee:
#             add_user_permission("Employee", self.employee, self.email)

#         # since Staff has no driver field → lookup by full_name
#         if self.is_driver and self.ristrcted_to_driver:
#             driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})
#             if driver_name:
#                 add_user_permission("Driver", driver_name, self.email)

#         if self.company_name and self.ristrcted_to_company:
#             add_user_permission("Company", self.company_name, self.email)

#         if self.branch and self.ristrcted_to_branch:
#             add_user_permission("Branch", self.branch, self.email)

#         if self.vehicle_assigned and self.ristrcted_to_vehicle:
#             add_user_permission("Vehicle", self.vehicle_assigned, self.email)

#         frappe.msgprint(f"Permissions set for {self.email}.")

#     def remove_user_permissions(self):
#         if not self.email:
#             return

#         if self.employee:
#             remove_user_permission("Employee", self.employee, self.email)

#         if self.is_driver:
#             driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})
#             if driver_name:
#                 remove_user_permission("Driver", driver_name, self.email)

#         if self.company_name:
#             remove_user_permission("Company", self.company_name, self.email)

#         if self.branch:
#             remove_user_permission("Branch", self.branch, self.email)

#         if self.vehicle_assigned:
#             remove_user_permission("Vehicle", self.vehicle_assigned, self.email)

#         frappe.msgprint(f"Permissions removed for {self.email}.")
