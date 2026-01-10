# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document


def _normalize_doc_no(dn: str) -> str:
    dn = (dn or "").strip().upper()
    # remove spaces + dashes + underscores
    dn = dn.replace(" ", "").replace("-", "").replace("_", "")
    return dn


class PassengerMaster(Document):
    def autoname(self):
        # Must be ready before Frappe assigns name
        dt = (self.document_type or "").strip()
        dn = _normalize_doc_no(self.document_number)

        self.document_number = dn
        self.identity_key = f"{dt}:{dn}"

        # NOTE: do NOT set self.name here
        # autoname = field:identity_key will use identity_key automatically

    def validate(self):
        # keep consistent on every save
        dt = (self.document_type or "").strip()
        dn = _normalize_doc_no(self.document_number)

        self.document_number = dn
        self.identity_key = f"{dt}:{dn}"

        if not self.first_seen_at:
            self.first_seen_at = frappe.utils.now_datetime()
        self.last_seen_at = frappe.utils.now_datetime()
