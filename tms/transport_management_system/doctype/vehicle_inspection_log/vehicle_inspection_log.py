import frappe
from frappe.model.document import Document


def _get_master_checklist():
    return frappe.get_all(
        "Vehicle Inspection Checklist Item",
        filters={"is_active": 1},
        fields=["name", "category", "sort_order", "item"],
        order_by="category asc, sort_order asc, creation asc",
    )


@frappe.whitelist()
def get_checklist_rows():
    rows = []
    for m in _get_master_checklist():
        rows.append(
            {
                "section": m.category or "",
                "item_en": m.name,            # Link to master doc
                "category": m.category or "",
                "item": m.item or "",
                "sort_order": m.sort_order or 0,
                "status": "Sound | سليم",
            }
        )
    return rows


class VehicleInspectionLog(Document):
    def before_insert(self):
        # If user already has rows, don't overwrite
        if self.items:
            return

        # only auto-fill if checkbox enabled
        if int(self.auto_fill_checklist or 0) != 1:
            return

        for r in get_checklist_rows():
            row = self.append("items", {})
            row.section = r["section"]
            row.item_en = r["item_en"]      # ✅ correct child fieldname
            row.category = r["category"]
            row.item = r["item"]
            row.sort_order = r["sort_order"]
            row.status = r["status"]