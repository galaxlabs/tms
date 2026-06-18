import frappe
from frappe import _


PARTY_GROUP_DEFAULTS = {
    "Customer": {
        "group_doctype": "Customer Group",
        "name_field": "customer_group_name",
        "parent_field": "parent_customer_group",
        "default_name": "Default Customer Group",
        "parent_name": "All Customer Groups",
        "preferred_names": ("Default Customer Group", "Commercial", "Individual"),
    },
    "Supplier": {
        "group_doctype": "Supplier Group",
        "name_field": "supplier_group_name",
        "parent_field": "parent_supplier_group",
        "default_name": "Default Supplier Group",
        "parent_name": "All Supplier Groups",
        "preferred_names": ("Services", "Local", "Default Supplier Group"),
    },
}

TERRITORY_DEFAULTS = {
    "name": "Saudi Arabia",
    "name_field": "territory_name",
    "parent_field": "parent_territory",
    "parent_name": "All Territories",
    "preferred_names": ("Saudi Arabia", "Rest Of The World", "Pakistan"),
}


def _tree_is_leaf(doctype, value):
    if not value or not frappe.db.exists(doctype, value):
        return False
    return not frappe.db.get_value(doctype, value, "is_group")


def _get_first_leaf(doctype):
    rows = frappe.get_all(
        doctype,
        filters={"is_group": 0},
        pluck="name",
        order_by="lft asc",
        limit_page_length=1,
    )
    return rows[0] if rows else None


def _insert_tree_leaf(doctype, name_field, parent_field, node_name, parent_name):
    if not frappe.db.exists(doctype, node_name):
        payload = {
            "doctype": doctype,
            name_field: node_name,
            "is_group": 0,
        }
        if parent_field:
            payload[parent_field] = frappe.db.exists(doctype, parent_name) or None

        frappe.get_doc(payload).insert(ignore_permissions=True)

    if not _tree_is_leaf(doctype, node_name):
        frappe.throw(_("Tree node {0} in {1} must be a non-group record.").format(node_name, doctype))

    return node_name


def ensure_default_customer_group():
    settings = PARTY_GROUP_DEFAULTS["Customer"]
    return _insert_tree_leaf(
        settings["group_doctype"],
        settings["name_field"],
        settings["parent_field"],
        settings["default_name"],
        settings["parent_name"],
    )


def ensure_default_supplier_group():
    settings = PARTY_GROUP_DEFAULTS["Supplier"]
    return _insert_tree_leaf(
        settings["group_doctype"],
        settings["name_field"],
        settings["parent_field"],
        settings["default_name"],
        settings["parent_name"],
    )


def ensure_default_territory():
    settings = TERRITORY_DEFAULTS
    return _insert_tree_leaf(
        "Territory",
        settings["name_field"],
        settings["parent_field"],
        settings["name"],
        settings["parent_name"],
    )


def get_valid_default_customer_group(current_value=None):
    if _tree_is_leaf("Customer Group", current_value):
        return current_value

    ensured_group = ensure_default_customer_group()
    if _tree_is_leaf("Customer Group", ensured_group):
        return ensured_group

    settings = PARTY_GROUP_DEFAULTS["Customer"]
    for candidate in settings["preferred_names"]:
        if _tree_is_leaf("Customer Group", candidate):
            return candidate

    selling_group = frappe.db.get_single_value("Selling Settings", "customer_group")
    if _tree_is_leaf("Customer Group", selling_group):
        return selling_group

    fallback = _get_first_leaf("Customer Group")
    if not fallback:
        frappe.throw(_("Please create at least one non-group Customer Group."))

    return fallback


def get_valid_default_supplier_group(current_value=None):
    if _tree_is_leaf("Supplier Group", current_value):
        return current_value

    settings = PARTY_GROUP_DEFAULTS["Supplier"]
    for candidate in settings["preferred_names"]:
        if _tree_is_leaf("Supplier Group", candidate):
            return candidate

    ensured_group = ensure_default_supplier_group()
    if _tree_is_leaf("Supplier Group", ensured_group):
        return ensured_group

    fallback = _get_first_leaf("Supplier Group")
    if not fallback:
        frappe.throw(_("Please create at least one non-group Supplier Group."))

    return fallback


def get_valid_default_territory(current_value=None):
    if _tree_is_leaf("Territory", current_value):
        return current_value

    ensured_territory = ensure_default_territory()
    if _tree_is_leaf("Territory", ensured_territory):
        return ensured_territory

    for candidate in TERRITORY_DEFAULTS["preferred_names"]:
        if _tree_is_leaf("Territory", candidate):
            return candidate

    selling_territory = frappe.db.get_single_value("Selling Settings", "territory")
    if _tree_is_leaf("Territory", selling_territory):
        return selling_territory

    fallback = _get_first_leaf("Territory")
    if not fallback:
        frappe.throw(_("Please create at least one non-group Territory."))

    return fallback


def ensure_customer_party_defaults():
    customer_group = get_valid_default_customer_group()
    territory = get_valid_default_territory()

    selling = frappe.get_single("Selling Settings")
    changed = False

    if hasattr(selling, "customer_group") and selling.customer_group != customer_group:
        selling.customer_group = customer_group
        changed = True

    if hasattr(selling, "territory") and selling.territory != territory:
        selling.territory = territory
        changed = True

    if changed:
        selling.save(ignore_permissions=True)

    return {"customer_group": customer_group, "territory": territory, "updated": changed}



def _has_field(doctype, fieldname):
    return bool(frappe.get_meta(doctype).has_field(fieldname))


def _has_db_field(doctype, fieldname):
    try:
        return fieldname in (frappe.db.get_table_columns(f'tab{doctype}') or [])
    except Exception:
        return False


def _set_if_has(doc, fieldname, value):
    if value and _has_field(doc.doctype, fieldname):
        doc.set(fieldname, value)


def find_customer_by_identifiers(customer_name=None, alternate_names=None, tax_id=None, registration_numbers=None):
    names = {value.strip() for value in (alternate_names or []) if value and value.strip()}
    if customer_name:
        names.add(customer_name.strip())

    tax_id = (tax_id or '').strip()
    registration_numbers = {str(value).strip() for value in (registration_numbers or []) if value}
    fields = ['name', 'customer_name']
    for extra in ('tax_id', 'custom_vat_information', 'custom_registration_number', 'custom_cr_number', 'custom_unified_national_number'):
        if _has_db_field('Customer', extra):
            fields.append(extra)

    for row in frappe.get_all('Customer', fields=fields, limit_page_length=0):
        row = frappe._dict(row)
        candidate_names = {str(row.get('name') or '').strip(), str(row.get('customer_name') or '').strip()}
        if names & candidate_names:
            return row.name

        if tax_id:
            for fieldname in ('tax_id', 'custom_vat_information'):
                if fieldname in fields and str(row.get(fieldname) or '').strip() == tax_id:
                    return row.name

        for fieldname in ('custom_registration_number', 'custom_cr_number', 'custom_unified_national_number'):
            if fieldname in fields and str(row.get(fieldname) or '').strip() in registration_numbers:
                return row.name

    return None


def create_or_update_customer_profile(
    customer_name,
    tax_id=None,
    registration_number=None,
    cr_number=None,
    unified_national_number=None,
    alternate_names=None,
    customer_type='Company',
    tax_period=None,
    vat_effective_date=None,
    address_text=None,
    country='Saudi Arabia',
):
    customer_id = find_customer_by_identifiers(
        customer_name=customer_name,
        alternate_names=alternate_names,
        tax_id=tax_id,
        registration_numbers=[registration_number, cr_number, unified_national_number],
    )

    if customer_id:
        customer = frappe.get_doc('Customer', customer_id)
    else:
        customer = frappe.new_doc('Customer')

    customer.customer_name = customer_name
    if _has_field('Customer', 'customer_type'):
        customer.customer_type = customer_type or 'Company'
    if _has_field('Customer', 'customer_group') and not customer.get('customer_group'):
        customer.customer_group = get_valid_default_customer_group()
    if _has_field('Customer', 'territory') and not customer.get('territory'):
        customer.territory = get_valid_default_territory()

    _set_if_has(customer, 'tax_id', tax_id)
    _set_if_has(customer, 'custom_vat_information', tax_id)
    _set_if_has(customer, 'custom_registration_number', registration_number)
    _set_if_has(customer, 'custom_cr_number', cr_number)
    _set_if_has(customer, 'custom_unified_national_number', unified_national_number)
    _set_if_has(customer, 'custom_tax_period', tax_period)
    _set_if_has(customer, 'custom_vat_effective_date', vat_effective_date)
    for fieldname in ('custom_country', 'country', 'customer_country', 'custom_customer_country'):
        _set_if_has(customer, fieldname, country)
    for fieldname in ('customer_name_in_arabic', 'custom_customer_name_arabic'):
        if alternate_names:
            _set_if_has(customer, fieldname, alternate_names[0])
    for fieldname in ('custom_address', 'address_text', 'custom_address_text'):
        _set_if_has(customer, fieldname, address_text)

    customer.save(ignore_permissions=True)
    frappe.db.commit()
    return customer.name


def ensure_service_item(item_code='Transport Service', item_name='Transport Service'):
    item_id = frappe.db.get_value('Item', {'item_code': item_code}, 'name') or frappe.db.get_value('Item', {'item_name': item_name}, 'name')
    if item_id:
        item = frappe.get_doc('Item', item_id)
    else:
        item = frappe.new_doc('Item')
        item.item_code = item_code
        item.item_name = item_name
        item.item_group = 'Services' if frappe.db.exists('Item Group', 'Services') else frappe.db.get_single_value('Stock Settings', 'item_group')
        item.stock_uom = 'Nos'

    item.is_stock_item = 0
    if _has_field('Item', 'is_sales_item'):
        item.is_sales_item = 1
    if _has_field('Item', 'is_purchase_item'):
        item.is_purchase_item = 1
    if _has_field('Item', 'include_item_in_manufacturing'):
        item.include_item_in_manufacturing = 0
    if _has_field('Item', 'disabled'):
        item.disabled = 0

    item.save(ignore_permissions=True)
    frappe.db.commit()
    return item.name


def create_draft_sales_invoice_for_service(customer, amount, description, company=None, posting_date=None, item_code='Transport Service'):
    company = company or frappe.db.get_single_value('Global Defaults', 'default_company') or frappe.db.get_value('Company', {}, 'name')
    item_name = ensure_service_item(item_code=item_code, item_name=item_code)
    item = frappe.get_doc('Item', item_name)

    invoice = frappe.new_doc('Sales Invoice')
    invoice.customer = customer
    if _has_field('Sales Invoice', 'company'):
        invoice.company = company
    if _has_field('Sales Invoice', 'posting_date') and posting_date:
        invoice.posting_date = posting_date
    if _has_field('Sales Invoice', 'due_date') and posting_date:
        invoice.due_date = posting_date

    default_template = None
    if frappe.db.exists('DocType', 'Sales Taxes and Charges Template'):
        default_template = frappe.db.get_value(
            'Sales Taxes and Charges Template',
            {'company': company, 'disabled': 0, 'is_default': 1},
            'name',
        ) or frappe.db.get_value(
            'Sales Taxes and Charges Template',
            {'company': company, 'disabled': 0},
            'name',
        )
        if default_template and _has_field('Sales Invoice', 'taxes_and_charges'):
            invoice.taxes_and_charges = default_template

    invoice.append('items', {
        'item_code': item.item_code,
        'qty': 1,
        'rate': amount,
        'description': description,
    })

    if hasattr(invoice, 'set_missing_values'):
        invoice.set_missing_values()
    if hasattr(invoice, 'calculate_taxes_and_totals'):
        invoice.calculate_taxes_and_totals()

    invoice.insert(ignore_permissions=True)
    frappe.db.commit()
    return {'name': invoice.name, 'docstatus': invoice.docstatus, 'taxes_template': default_template, 'grand_total': invoice.grand_total}
