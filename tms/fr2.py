import frappe

def run():
    pf = frappe.get_doc("Print Format", "Celtco Quotation - No VAT")
    html = pf.html
    
    # Build the complete Jinja header 
    header = '''{# =========================
   CELTCO Quotation Print Format - NO VAT
   Proforma-style header + Quotation commercial layout
   No VAT columns, no tax summary
   Completely dynamic — all fields from DocType
   ========================= #}

{% set company = frappe.get_doc("Company", doc.company) if doc.company else None %}

{% set customer = None %}
{% if doc.party_name and frappe.db.exists("Customer", doc.party_name) %}
  {% set customer = frappe.get_doc("Customer", doc.party_name) %}
{% endif %}

{% set company_addr = frappe.get_doc("Address", doc.company_address) if doc.company_address else None %}
{% set customer_addr = frappe.get_doc("Address", doc.customer_address) if doc.customer_address else None %}

{% set company_addr_ar_name = frappe.db.get_value(
  "Address",
  {
    "address_title": "Address Arabic",
    "is_your_company_address": 1,
    "disabled": 0
  },
  "name"
) %}

{% set company_addr_ar = frappe.get_doc("Address", company_addr_ar_name) if company_addr_ar_name else None %}

{% set fallback_logo =
  frappe.db.get_value("File", {"file_name": "Celtco Logo.png"}, "file_url")
  or frappe.db.get_value("File", {"file_name": "Logo.png"}, "file_url")
  or frappe.db.get_value("File", {"file_name": "Logo.jpeg"}, "file_url")
%}

{% set company_logo =
  (company.company_logo if company else None)
  or fallback_logo
  or "/files/Celtco%20Logo.png"
%}

{% set company_en =
  (company.company_name if company else None)
  or "Al-Tamayuz Al-Shamilah Al-Ra'idah Company"
%}

{% set company_ar =
  (company.get("custom_company_name_arabic") if company else None)
  or (company.get("company_name_arabic") if company else None)
  or "شركة التميز الشاملة الرائدة"
%}

{% set company_phone =
  (company.phone_no if company else None)
  or (company_addr.phone if company_addr else None)
  or "0537051718"
%}

{% set company_email =
  (company.email if company else None)
  or (company_addr.email_id if company_addr else None)
  or "ceo@celtco.org"
%}

{% set company_website = (company.website if company else None) or "www.celtco.org" %}
{% set company_vat = doc.company_tax_id or (company.tax_id if company else None) or "312449289400003" %}
{% set company_cr = (company.registration_details if company else None) or (company.get("cr_number") if company else None) or "4650277231" %}

{% set customer_ar =
  (customer.get("customer_name_in_arabic") if customer else None)
  or doc.get("customer_name_in_arabic")
  or doc.customer_name
  or doc.party_name
%}

{% set ref_no = doc.get("custom_reference") or doc.name %}
{% set quote_date = frappe.utils.formatdate(doc.transaction_date, "MMMM d, yyyy") if doc.transaction_date else "" %}

{% set customer_display = doc.customer_name or doc.party_name or "" %}

{% set first_item = doc.items[0] if doc.items else None %}
{% set item_name_fallback = (first_item.item_name or first_item.item_code) if first_item else "Quotation" %}
{% set item_name_fallback = item_name_fallback | striptags | trim %}

{% set scope_text = doc.get("intro_service_text") or "" %}
{% set scope_text = scope_text | striptags | trim %}

{% if not scope_text %}
  {% set scope_text = item_name_fallback %}
{% endif %}

{% set quotation_subject_template = doc.get("print_subject") or "" %}
{% set quotation_subject_template = quotation_subject_template | striptags | trim %}

{% if not quotation_subject_template %}
  {% set quotation_subject_template = "Commercial Proposal: {scope} - {customer}" %}
{% endif %}

{% set quotation_subject =
  quotation_subject_template
  | replace("{customer}", customer_display)
  | replace("{company}", company_en)
  | replace("{scope}", scope_text)
  | replace("{item}", item_name_fallback)
%}

{% set intro_text_template = doc.get("intro_text") or "" %}
{% set intro_text_template = intro_text_template | striptags | trim %}

{% if not intro_text_template %}
  {% set intro_text_template = "With reference to the ongoing collaboration between {company} and {customer}, we are pleased to submit our formal commercial proposal for {scope}." %}
{% endif %}

{% set intro_text =
  intro_text_template
  | replace("{customer}", customer_display)
  | replace("{company}", company_en)
  | replace("{scope}", scope_text)
  | replace("{item}", item_name_fallback)
%}

{% set company_stamp_image =
  (company.get("company_stamp_image") if company else None)
  or (company.get("custom_company_stamp_image") if company else None)
  or ""
%}

{% set company_signature_image =
  (company.get("company_signature_image") if company else None)
  or (company.get("custom_company_signature_image") if company else None)
  or ""
%}

{% set contact_name = doc.contact_display or doc.contact_person or "" %}
{% set contact_mobile = doc.contact_mobile or "" %}
{% set contact_email = doc.contact_email or "" %}

{# Payment terms - dynamic #}
{% set ps = doc.payment_schedule[0] if doc.payment_schedule else None %}

{% set credit_days = frappe.utils.cint(ps.credit_days) if ps and ps.credit_days else 0 %}
{% set invoice_portion = frappe.utils.flt(ps.invoice_portion) if ps and ps.invoice_portion else 100 %}
{% set payment_term_name = ps.payment_term if ps and ps.get("payment_term") else "" %}

{% if not payment_term_name and doc.get("payment_terms_template") %}
  {% set template_terms = frappe.get_all(
    "Payment Terms Template Detail",
    filters={"parent": doc.payment_terms_template},
    fields=["payment_term", "credit_days", "invoice_portion"],
    order_by="idx asc",
    limit=1
  ) %}

  {% if template_terms %}
    {% set payment_term_name = template_terms[0].payment_term or "" %}
    {% set credit_days = frappe.utils.cint(template_terms[0].credit_days or credit_days) %}
    {% set invoice_portion = frappe.utils.flt(template_terms[0].invoice_portion or invoice_portion) %}
  {% endif %}
{% endif %}

{% set payment_term_key = payment_term_name | lower | trim %}
{% set payment_terms_text = frappe.utils.flt(invoice_portion or 100, 0) ~ "% Advance." %}

{% if "after delivery" in payment_term_key and credit_days %}
  {% set payment_terms_text = frappe.utils.flt(invoice_portion or 100, 0) ~ "% payment shall be processed within " ~ credit_days ~ " days after delivery and invoice submission." %}
{% elif "after invoice" in payment_term_key and credit_days %}
  {% set payment_terms_text = frappe.utils.flt(invoice_portion or 100, 0) ~ "% payment shall be processed within " ~ credit_days ~ " days from the date of invoice." %}
{% elif credit_days %}
  {% set payment_terms_text = frappe.utils.flt(invoice_portion or 100, 0) ~ "% payment shall be processed within " ~ credit_days ~ " days from the date of invoice." %}
{% elif "advance" in payment_term_key %}
  {% set payment_terms_text = frappe.utils.flt(invoice_portion or 100, 0) ~ "% Advance." %}
{% endif %}

{% macro money(value) -%}
  {%- set amount = frappe.utils.flt(value or 0, 2) -%}
  {{ "{:,.2f}".format(amount).replace(".00", "") }}
{%- endmacro %}

{# Totals #}
{% set total_ns = namespace(grand=0) %}

{% for row in doc.items or [] %}
  {% set total_ns.grand = total_ns.grand + frappe.utils.flt(row.amount or 0, 2) %}
{% endfor %}

'''
    
    # Remove everything before <div class="quotation-shell"> or <div class="sheet">
    shell_idx = html.find('<div class="quotation-shell">')
    if shell_idx < 0:
        shell_idx = html.find('<div class="sheet">')
    
    if shell_idx >= 0:
        html = html[shell_idx:]
    
    # Remove any duplicate macro + total_ns blocks inside the HTML
    # (they were mistakenly placed between items table and totals grid)
    dup_block = '{# Totals #}\n{% set total_ns = namespace(grand=0) %}\n\n{% for row in doc.items or [] %}\n  {% set total_ns.grand = total_ns.grand + frappe.utils.flt(row.amount or 0, 2) %}\n{% endfor %}'
    while dup_block in html:
        html = html.replace(dup_block, '')
        print("Removed duplicate total_ns block")
    
    # Prepend the header
    html = header + html
    
    pf.html = html
    pf.save()
    print("Saved! Full restore complete.")
    
    # Verify key components
    checks = {
        "company_en def": "{% set company_en",
        "company_ar def": "{% set company_ar",
        "company_logo def": "{% set company_logo",
        "money macro": "{% macro money",
        "total_ns def": "{% set total_ns = namespace",
        "quotation-shell": '<div class="quotation-shell">',
        "sheet start": '<div class="sheet">',
        "No {% set money": "{% set money" not in html,  # should NOT have this
    }
    for name, result in checks.items():
        status = "OK" if result else "FAIL"
        if isinstance(result, bool):
            status = "OK" if result else "FAIL"
        print(f"  {name}: {status}")
