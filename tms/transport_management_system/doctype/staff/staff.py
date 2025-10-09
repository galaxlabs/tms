import frappe
from frappe.model.document import Document
from frappe.permissions import add_user_permission, remove_user_permission


class Staff(Document):

    def after_insert(self):
        # always recompute full_name
        self.full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        self.create_related_docs()
        self.assign_user_permissions()

    def on_update(self):
        # recompute full_name on update too
        self.full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        self.sync_user()
        self.sync_employee()
        self.sync_driver()
        self.assign_user_permissions()

    def on_trash(self):
        self.remove_user_permissions()

    # -----------------------------
    # User + Employee + Driver + Customer
    # -----------------------------
    def create_related_docs(self):
        if not self.email:
            frappe.throw("Email is required to create a User.")

        # -------- USER --------
        if not frappe.db.exists("User", self.email):
            user = frappe.get_doc({
                "doctype": "User",
                "email": self.email,
                "first_name": self.first_name,
                "last_name": self.last_name,
                "enabled": 1 if self.enabled else 0,
                "time_zone": self.time_zone or "",
                "send_welcome_email": 1
            })
            user.insert(ignore_permissions=True)
            frappe.msgprint(f"User created: {self.email}")
        else:
            user = frappe.get_doc("User", self.email)

        # Set role profile or roles
        if self.role_profile:
            user.role_profile_name = self.role_profile
        else:
            user.set("roles", [])
            if self.role:
                for r in self.role:
                    user.append("roles", {"role": r.role})

        # Basic fields only
        user.first_name = self.first_name
        user.last_name = self.last_name
        user.time_zone = self.time_zone or ""
        user.enabled = 1 if self.enabled else 0
        user.save(ignore_permissions=True)

        # -------- EMPLOYEE --------
        if self.is_employee and not self.employee:
            emp = frappe.get_doc({
                "doctype": "Employee",
                "first_name": self.first_name,
                "last_name": self.last_name,
                "employee_name": self.full_name,
                "date_of_birth": self.date_of_birth,
                "date_of_joining": self.date_of_joining,
                "company": self.company_name,
                "user_id": self.email,
                "branch": self.branch,
                "gender": self.gender,
                "blood_group": getattr(self, "blood_group", "") or "",
                "department": self.department or "",
                "designation": self.designation or ""
            })
            emp.insert(ignore_permissions=True)
            self.db_set("employee", emp.name)
            frappe.msgprint(f"Employee created: {emp.name}")

        # -------- DRIVER --------
        if self.is_driver:
            driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})
            if not driver_name:
                driver = frappe.get_doc({
                    "doctype": "Driver",
                    "full_name": self.full_name,
                    "status": "Active",
                    "employee": self.employee or None,
                    "cell_number": self.mobile_no or self.phone or ""
                })
                driver.insert(ignore_permissions=True)
                frappe.msgprint(f"Driver created: {driver.name}")
                self.copy_documents(driver)
            else:
                # Driver already exists, just sync documents
                driver = frappe.get_doc("Driver", driver_name)
                self.copy_documents(driver)

        # -------- CUSTOMER --------
        if not frappe.db.exists("Customer", {"email_id": self.email}):
            customer = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": self.full_name,
                "customer_type": "Individual",
                "email_id": self.email
            })
            customer.insert(ignore_permissions=True)
            frappe.msgprint(f"Customer created for {self.full_name} ({self.email})")

    # -----------------------------
    # Sync Methods
    # -----------------------------
    def sync_user(self):
        if frappe.db.exists("User", self.email):
            user = frappe.get_doc("User", self.email)
            user.first_name = self.first_name
            user.last_name = self.last_name
            user.enabled = 1 if self.enabled else 0
            user.time_zone = self.time_zone or ""

            if self.role_profile:
                user.role_profile_name = self.role_profile
            else:
                user.set("roles", [])
                if self.role:
                    for r in self.role:
                        user.append("roles", {"role": r.role})

            user.save(ignore_permissions=True)

    def sync_employee(self):
        if self.employee and frappe.db.exists("Employee", self.employee):
            emp = frappe.get_doc("Employee", self.employee)
            emp.employee_name = self.full_name
            emp.first_name = self.first_name
            emp.last_name = self.last_name
            emp.company = self.company_name
            emp.user_id = self.email
            emp.branch = self.branch
            emp.gender = self.gender
            emp.blood_group = getattr(self, "blood_group", "") or ""
            emp.department = self.department or ""
            emp.designation = self.designation or ""
            emp.save(ignore_permissions=True)

    def sync_driver(self):
        if self.is_driver:
            driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})
            if driver_name:
                driver = frappe.get_doc("Driver", driver_name)
                driver.full_name = self.full_name
                driver.employee = self.employee or None
                driver.cell_number = self.mobile_no or self.phone or ""
                driver.save(ignore_permissions=True)
                self.copy_documents(driver)

    def copy_documents(self, driver_doc):
        driver_doc.set("documents", [])
        for d in self.documents:
            driver_doc.append("documents", {
                "document_type": d.document_type,
                "document_no": d.document_no,
                "issue_date": d.issue_date,
                "expiry_date": d.expiry_date
            })
        driver_doc.save(ignore_permissions=True)

    # -----------------------------
    # Permissions
    # -----------------------------
    def assign_user_permissions(self):
        if not self.email:
            return

        if self.employee and self.ristrcted_to_employee:
            add_user_permission("Employee", self.employee, self.email)

        # since Staff has no driver field → lookup by full_name
        if self.is_driver and self.ristrcted_to_driver:
            driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})
            if driver_name:
                add_user_permission("Driver", driver_name, self.email)

        if self.company_name and self.ristrcted_to_company:
            add_user_permission("Company", self.company_name, self.email)

        if self.branch and self.ristrcted_to_branch:
            add_user_permission("Branch", self.branch, self.email)

        if self.vehicle_assigned and self.ristrcted_to_vehicle:
            add_user_permission("Vehicle", self.vehicle_assigned, self.email)

        frappe.msgprint(f"Permissions set for {self.email}.")

    def remove_user_permissions(self):
        if not self.email:
            return

        if self.employee:
            remove_user_permission("Employee", self.employee, self.email)

        if self.is_driver:
            driver_name = frappe.db.exists("Driver", {"full_name": self.full_name})
            if driver_name:
                remove_user_permission("Driver", driver_name, self.email)

        if self.company_name:
            remove_user_permission("Company", self.company_name, self.email)

        if self.branch:
            remove_user_permission("Branch", self.branch, self.email)

        if self.vehicle_assigned:
            remove_user_permission("Vehicle", self.vehicle_assigned, self.email)

        frappe.msgprint(f"Permissions removed for {self.email}.")
