import frappe, json, base64
from openai import OpenAI

@frappe.whitelist()
def extract_passengers_from_attachments(trip_name):
    """
    Extract passenger info from Trip attachments and auto-fill child table using GPT-4o OCR.
    """
    trip = frappe.get_doc("Trip", trip_name)
    client = OpenAI(api_key=frappe.conf.openai_api_key)

    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Trip", "attached_to_name": trip_name},
        fields=["file_url"]
    )

    passengers = []
    for f in files:
        file_path = frappe.get_site_path(f.file_url.lstrip("/"))
        with open(file_path, "rb") as img:
            img_b64 = base64.b64encode(img.read()).decode("utf-8")

        # 🧠 Use the new image object format here:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an OCR assistant for travel IDs."},
                {"role": "user", "content": [
                    {"type": "text", "text": "Extract JSON with fields: name, id_no, nationality."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]}
            ],
            response_format={"type": "json_object"}
        )

        try:
            data = json.loads(response.choices[0].message.content)
        except Exception:
            frappe.log_error("OpenAI OCR returned invalid JSON.")
            continue

        # ✅ Add to child table
        trip.append("passengers", {
            "passenger_name": data.get("name"),
            "idpassport_no": data.get("id_no"),
            "nationality": data.get("nationality")
        })
        passengers.append(data)

    trip.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "trip_name": trip.name,
        "passengers": passengers,
        "count": len(passengers),
        "ocr_source": "openai_gpt4o"
    }
@frappe.whitelist()
def extract_passengers_from_attachments(trip_name, file_urls=None):
    """
    Extract multiple passenger documents (attachments) at once.
    - Reads all attachments linked to the Trip, or specific file URLs if passed.
    - Uses GPT-4o OCR to extract structured passenger info.
    - Auto-fills the Passengers child table.
    """

    client = OpenAI(api_key=frappe.conf.openai_api_key)
    trip = frappe.get_doc("Trip", trip_name)

    # 1️⃣ Collect all attachments (or use provided file list)
    if file_urls:
        # Accept JSON list or comma-separated string
        if isinstance(file_urls, str):
            try:
                file_urls = json.loads(file_urls)
            except Exception:
                file_urls = [u.strip() for u in file_urls.split(",") if u.strip()]
    else:
        file_urls = [
            f.file_url
            for f in frappe.get_all(
                "File",
                filters={"attached_to_doctype": "Trip", "attached_to_name": trip_name},
                fields=["file_url"],
            )
        ]

    if not file_urls:
        frappe.throw("❌ No files found or attached to this Trip.")

    passengers = []

    # 2️⃣ Loop through all images
    for file_url in file_urls:
        try:
            file_path = frappe.get_site_path(file_url.lstrip("/"))
            with open(file_path, "rb") as img:
                b64 = base64.b64encode(img.read()).decode("utf-8")

            # 3️⃣ Send image to GPT-4o
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an OCR assistant that extracts passenger details."},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Extract JSON with: name, id_no, nationality"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ]},
                ],
                response_format={"type": "json_object"},
            )

            data = json.loads(resp.choices[0].message.content)

            # 4️⃣ Append to Passengers child table
            trip.append("passengers", {
                "passenger_name": data.get("name"),
                "idpassport_no": data.get("id_no"),
                "nationality": data.get("nationality"),
            })
            passengers.append(data)

        except Exception as e:
            frappe.log_error(f"OCR failed for {file_url}: {e}")
            continue

    # 5️⃣ Save once
    trip.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "trip_name": trip.name,
        "ocr_source": "openai_gpt4o",
        "processed_files": len(file_urls),
        "passengers_added": len(passengers),
        "passengers": passengers,
    }