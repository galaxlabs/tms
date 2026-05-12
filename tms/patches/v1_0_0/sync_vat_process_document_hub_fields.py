import frappe


PROCESS_TYPE_MAP = {
	"Purchase": "Purchase Invoice",
	"Sales": "Sales Invoice",
	"Quotation": "Sales Quotation",
}

STATUS_MAP = {
	"Extracted": "Draft",
	"Needs Review": "Draft",
	"Reviewed": "Ready",
	"Invoice Created": "Document Created",
}


def execute():
	if not frappe.db.exists("DocType", "VAT Process"):
		return

	records = frappe.get_all(
		"VAT Process",
		fields=["name", "process_type", "status", "review_status", "created_doctype", "created_document_type"],
		limit_page_length=0,
	)

	for row in records:
		process_type = PROCESS_TYPE_MAP.get(row.process_type, row.process_type)
		status = STATUS_MAP.get(row.status, row.status) or "Draft"
		review_status = STATUS_MAP.get(row.review_status, row.review_status) or status
		created_document_type = row.created_document_type or row.created_doctype

		frappe.db.set_value(
			"VAT Process",
			row.name,
			{
				"process_type": process_type,
				"status": review_status,
				"review_status": review_status,
				"created_document_type": created_document_type,
			},
			update_modified=False,
		)
