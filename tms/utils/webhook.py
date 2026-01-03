# apps/tms/tms/utils/webhook.py
import json
import requests
from werkzeug.wrappers import Response

import frappe
from frappe.utils import now_datetime


@frappe.whitelist(allow_guest=True)
def webhook():
    """Meta WhatsApp webhook endpoint."""
    if frappe.request.method == "GET":
        return get()
    return post()


def _get_settings():
    if not frappe.db.exists("DocType", "WhatsApp Settings"):
        frappe.throw("WhatsApp Settings DocType missing")
    return frappe.get_single("WhatsApp Settings")


def get():
    """Meta verification (Single doctype)."""
    s = _get_settings()
    hub_challenge = frappe.form_dict.get("hub.challenge") or ""
    verify_token = frappe.form_dict.get("hub.verify_token") or ""

    if (verify_token or "") != (s.webhook_verify_token or ""):
        return Response("Verify token does not match", status=403)

    return Response(hub_challenge, status=200)


def _already_saved_message(message_id: str) -> bool:
    return bool(message_id and frappe.db.exists("WhatsApp Message", {"message_id": message_id}))


def _run_bot(message_doc):
    """Run split-bot safely."""
    try:
        from tms.utils.whatsapp_bot.entry import handle_incoming_whatsapp
        handle_incoming_whatsapp(message_doc)
    except Exception:
        frappe.log_error("WA BOT FAIL", frappe.get_traceback())


def _log_payload(data):
    try:
        frappe.get_doc({
            "doctype": "WhatsApp Notification Log",
            "template": "Webhook",
            "meta_data": json.dumps(data),
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error("WA WEBHOOK LOG FAIL", frappe.get_traceback())


def _extract_value(data):
    try:
        return data["entry"][0]["changes"][0]["value"]
    except Exception:
        return None


def _get_profile_name(value):
    try:
        contacts = value.get("contacts") or []
        return contacts[0].get("profile", {}).get("name")
    except Exception:
        return None


def _download_media(s, media_id: str):
    """
    Meta flow:
    1) GET {url}/{version}/{media_id}
    2) GET returned 'url' with Bearer token
    """
    token = s.get_password("token") if hasattr(s, "get_password") else (getattr(s, "token", None) or "")
    if not token:
        return None, None

    base_url = (s.url or "https://graph.facebook.com").rstrip("/") + "/"
    version = (s.version or "v24.0").strip("/")

    headers = {"Authorization": f"Bearer {token}"}

    meta = requests.get(f"{base_url}{version}/{media_id}", headers=headers, timeout=30)
    if meta.status_code != 200:
        return None, None

    meta_json = meta.json() or {}
    media_url = meta_json.get("url")
    mime_type = meta_json.get("mime_type") or "application/octet-stream"
    if not media_url:
        return None, None

    blob = requests.get(media_url, headers=headers, timeout=60)
    if blob.status_code != 200:
        return None, None

    return blob.content, mime_type


def _attach_file_to_message(message_doc, file_data: bytes, mime_type: str):
    ext = (mime_type.split("/")[-1] or "bin")
    file_name = f"{frappe.generate_hash(length=10)}.{ext}"

    f = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "attached_to_doctype": "WhatsApp Message",
        "attached_to_name": message_doc.name,
        "content": file_data,
        "attached_to_field": "attach",
    }).save(ignore_permissions=True)

    message_doc.db_set("attach", f.file_url, update_modified=False)
    if not (message_doc.message or "").strip():
        message_doc.db_set("message", f.file_url, update_modified=False)

    message_doc.reload()
    return f


def post():
    s = _get_settings()

    # IMPORTANT: Meta sends JSON
    data = frappe.request.get_json(silent=True) or {}
    _log_payload(data)

    value = _extract_value(data)
    if not value:
        return Response("OK", status=200)

    # Optional: verify this webhook is for your phone id
    phone_id = (value.get("metadata") or {}).get("phone_number_id")
    if phone_id and (s.phone_id or "") and str(phone_id) != str(s.phone_id):
        # ignore other phone ids
        return Response("OK", status=200)

    # Status-only webhook
    messages = value.get("messages") or []
    if not messages:
        return Response("OK", status=200)

    profile_name = _get_profile_name(value)

    for m in messages:
        msg_id = m.get("id")
        msg_type = (m.get("type") or "").lower()
        wa_from = m.get("from")

        if _already_saved_message(msg_id):
            continue

        doc = {
            "doctype": "WhatsApp Message",
            "type": "Incoming",
            "from": wa_from,
            "message_id": msg_id,
            "content_type": msg_type or "text",
            "profile_name": profile_name,
        }

        if msg_type == "text":
            doc["message"] = (m.get("text") or {}).get("body") or ""
            msg_doc = frappe.get_doc(doc).insert(ignore_permissions=True)
            _run_bot(msg_doc)
            continue

        # media types: image/video/audio/document
        if msg_type in ("image", "video", "audio", "document"):
            doc["message"] = (m.get(msg_type) or {}).get("caption") or ""
            msg_doc = frappe.get_doc(doc).insert(ignore_permissions=True)

            media_id = (m.get(msg_type) or {}).get("id")
            if media_id:
                blob, mime = _download_media(s, media_id)
                if blob:
                    _attach_file_to_message(msg_doc, blob, mime)

            _run_bot(msg_doc)
            continue

        # fallback
        doc["message"] = json.dumps(m)
        msg_doc = frappe.get_doc(doc).insert(ignore_permissions=True)
        _run_bot(msg_doc)

    return Response("OK", status=200)

# -------------------------old--------------------------------------------------
# from tms.utils.whatsapp_bot.entry import handle_incoming_whatsapp

# """Webhook."""
# import json
# import requests
# import frappe
# from werkzeug.wrappers import Response


# @frappe.whitelist(allow_guest=True)
# def webhook():
# 	"""Meta webhook endpoint."""
# 	if frappe.request.method == "GET":
# 		return get()
# 	return post()


# def get():
# 	"""Meta Webhook verification (GET hub.challenge)."""
# 	hub_challenge = frappe.form_dict.get("hub.challenge")
# 	verify_token = frappe.form_dict.get("hub.verify_token")

# 	webhook_verify_token = frappe.db.get_single_value("WhatsApp Settings", "webhook_verify_token")

# 	if verify_token != webhook_verify_token:
# 		return Response("Verify token does not match", status=403)

# 	return Response(hub_challenge, status=200)


# def _read_json_body():
# 	"""Read JSON reliably (Meta sends raw JSON body)."""
# 	data = frappe.request.get_json(silent=True)
# 	if data:
# 		return data

# 	raw = frappe.request.get_data(as_text=True) or "{}"
# 	try:
# 		return json.loads(raw)
# 	except Exception:
# 		return {}


# def _extract_change(data: dict):
# 	"""
# 	Supports BOTH:
# 	A) Full payload: {entry:[{changes:[{field,value}]}]}
# 	B) Change-only: {field,value}
# 	Returns: (field, value_dict)
# 	"""
# 	if isinstance(data, dict) and "entry" in data:
# 		try:
# 			change = (data.get("entry") or [{}])[0].get("changes", [{}])[0] or {}
# 			return change.get("field"), (change.get("value") or {})
# 		except Exception:
# 			return None, {}

# 	if isinstance(data, dict) and "field" in data and "value" in data:
# 		return data.get("field"), (data.get("value") or {})

# 	return None, {}


# def _log_webhook_payload(data: dict):
# 	"""Always log payload for debugging/audit."""
# 	frappe.get_doc({
# 		"doctype": "WhatsApp Notification Log",
# 		"template": "Webhook",
# 		"meta_data": json.dumps(data, ensure_ascii=False)
# 	}).insert(ignore_permissions=True)


# def _get_sender_profile_name(value: dict):
# 	contacts = value.get("contacts") or []
# 	for c in contacts:
# 		name = (c.get("profile") or {}).get("name")
# 		if name:
# 			return name
# 	return None


# def _already_saved_message(message_id: str) -> bool:
# 	if not message_id:
# 		return False
# 	return bool(frappe.db.exists("WhatsApp Message", {"message_id": message_id}))


# def _save_message_row(*, message, sender_profile_name, reply_to_message_id=None, is_reply=False, content_type="text", text=""):
# 	"""Insert ONE WhatsApp Message row (idempotent by message_id)."""
# 	msg_id = message.get("id")
# 	if _already_saved_message(msg_id):
# 		return None

# 	return frappe.get_doc({
# 		"doctype": "WhatsApp Message",
# 		"type": "Incoming",
# 		"from": message.get("from"),
# 		"message": text or "",
# 		"message_id": msg_id,
# 		"reply_to_message_id": reply_to_message_id,
# 		"is_reply": is_reply,
# 		"content_type": content_type,
# 		"profile_name": sender_profile_name
# 	}).insert(ignore_permissions=True)


# def _download_media_bytes(*, settings, media_id: str):
# 	"""Download media bytes from Meta Graph using media_id."""
# 	token = settings.get_password("token")
# 	base_url = f"{settings.url}/{settings.version}/"
# 	headers = {"Authorization": f"Bearer {token}"}

# 	# 1) Get media URL + mime type
# 	meta_resp = requests.get(f"{base_url}{media_id}/", headers=headers, timeout=30)
# 	if meta_resp.status_code != 200:
# 		return None, None, None

# 	media_meta = meta_resp.json() or {}
# 	media_url = media_meta.get("url")
# 	mime_type = media_meta.get("mime_type") or "application/octet-stream"
# 	if not media_url:
# 		return None, None, None

# 	# 2) Download bytes
# 	media_resp = requests.get(media_url, headers=headers, timeout=60)
# 	if media_resp.status_code != 200:
# 		return None, None, None

# 	return media_resp.content, mime_type, media_url


# def _attach_file_to_message(*, message_doc, file_data: bytes, mime_type: str):
# 	"""Create File record and link it to WhatsApp Message."""
# 	file_extension = (mime_type.split("/")[-1] or "bin")
# 	file_name = f"{frappe.generate_hash(length=10)}.{file_extension}"

# 	file_doc = frappe.get_doc({
# 		"doctype": "File",
# 		"file_name": file_name,
# 		"attached_to_doctype": "WhatsApp Message",
# 		"attached_to_name": message_doc.name,
# 		"content": file_data,
# 		"attached_to_field": "attach"
# 	}).save(ignore_permissions=True)

# 	message_doc.attach = file_doc.file_url
# 	if not message_doc.message:
# 		message_doc.message = file_doc.file_url
# 	message_doc.save(ignore_permissions=True)

# 	# ✅ Run bot AFTER attach exists
# 	try:
# 		from tms.utils.whatsapp_bot.entry import handle_incoming_whatsapp
# 		handle_incoming_whatsapp(message_doc)
# 	except Exception:
# 		frappe.log_error("WA BOT FAIL (after attach)", frappe.get_traceback())

# 	return file_doc

# # def _attach_file_to_message(*, message_doc, file_data: bytes, mime_type: str):
# # 	"""Create File record and link it to WhatsApp Message."""
# # 	file_extension = (mime_type.split("/")[-1] or "bin")
# # 	file_name = f"{frappe.generate_hash(length=10)}.{file_extension}"

# # 	file_doc = frappe.get_doc({
# # 		"doctype": "File",
# # 		"file_name": file_name,
# # 		"attached_to_doctype": "WhatsApp Message",
# # 		"attached_to_name": message_doc.name,
# # 		"content": file_data,
# # 		"attached_to_field": "attach"
# # 	}).save(ignore_permissions=True)

# # 	message_doc.attach = file_doc.file_url
# # 	# If message text is empty, keep file url so user can click
# # 	if not message_doc.message:
# # 		message_doc.message = file_doc.file_url
# # 	message_doc.save(ignore_permissions=True)

# # 	return file_doc


# # def post():
# # 	"""Handle Meta webhook POST."""
# # 	data = _read_json_body()

# # 	# Always log payload (so we can prove Meta hit us)
# # 	_log_webhook_payload(data)

# # 	change_field, value = _extract_change(data)
# # 	if not (change_field and value):
# # 		return Response("OK", status=200)

# # 	# Messages / statuses are inside value
# # 	messages = value.get("messages") or []
# # 	sender_profile_name = _get_sender_profile_name(value)

# # 	# If messages exist -> create incoming WhatsApp Message docs
# # 	if messages:
# # 		settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")

# # 		auto_img = bool(getattr(settings, "automatically_download_images", 0))
# # 		auto_doc = bool(getattr(settings, "automatically_download_documents", 0))

# # 		for message in messages:
# # 			message_type = message.get("type") or "unknown"
# # 			context = message.get("context") or {}
# # 			is_reply = True if (context and "forwarded" not in context) else False
# # 			reply_to_message_id = context.get("id") if is_reply else None

# # 			# TEXT
# # 			if message_type == "text":
# # 				text = (message.get("text") or {}).get("body") or ""
# # 				_save_message_row(
# # 					message=message,
# # 					sender_profile_name=sender_profile_name,
# # 					reply_to_message_id=reply_to_message_id,
# # 					is_reply=is_reply,
# # 					content_type="text",
# # 					text=text
# # 				)

# # 			# REACTION
# # 			elif message_type == "reaction":
# # 				reaction = (message.get("reaction") or {})
# # 				emoji = reaction.get("emoji") or ""
# # 				_save_message_row(
# # 					message=message,
# # 					sender_profile_name=sender_profile_name,
# # 					reply_to_message_id=reaction.get("message_id"),
# # 					is_reply=True,
# # 					content_type="reaction",
# # 					text=emoji
# # 				)

# # 			# INTERACTIVE (Flow)
# # 			elif message_type == "interactive":
# # 				interactive = message.get("interactive") or {}
# # 				nfm = interactive.get("nfm_reply") or {}
# # 				resp_json = nfm.get("response_json")
# # 				_save_message_row(
# # 					message=message,
# # 					sender_profile_name=sender_profile_name,
# # 					reply_to_message_id=reply_to_message_id,
# # 					is_reply=is_reply,
# # 					content_type="flow",
# # 					text=resp_json or json.dumps(interactive, ensure_ascii=False)
# # 				)

# # 			# BUTTON
# # 			elif message_type == "button":
# # 				btn = message.get("button") or {}
# # 				_save_message_row(
# # 					message=message,
# # 					sender_profile_name=sender_profile_name,
# # 					reply_to_message_id=reply_to_message_id,
# # 					is_reply=is_reply,
# # 					content_type="button",
# # 					text=btn.get("text") or ""
# # 				)

# # 			# MEDIA (only auto-download IMAGE + DOCUMENT)
# # 			elif message_type in ["image", "document", "audio", "video"]:
# # 				media_block = message.get(message_type) or {}
# # 				media_id = media_block.get("id")
# # 				caption = media_block.get("caption") or ""

# # 				# Always create ONE message row first (even if not downloading)
# # 				msg = _save_message_row(
# # 					message=message,
# # 					sender_profile_name=sender_profile_name,
# # 					reply_to_message_id=reply_to_message_id,
# # 					is_reply=is_reply,
# # 					content_type=message_type,
# # 					text=caption or (f"media_id:{media_id}" if media_id else "")
# # 				)

# # 				# If duplicate (already saved), msg will be None -> skip download
# # 				if not msg or not media_id:
# # 					continue

# # 				# Only download image + document if enabled
# # 				should_download = (message_type == "image" and auto_img) or (message_type == "document" and auto_doc)
# # 				if not should_download:
# # 					# audio/video/manual, or disabled: keep media_id in text for manual download
# # 					if not msg.message:
# # 						msg.message = f"media_id:{media_id}"
# # 						msg.save(ignore_permissions=True)
# # 					continue

# # 				file_data, mime_type, _url = _download_media_bytes(settings=settings, media_id=media_id)
# # 				if not file_data:
# # 					# keep media_id so you can try manual download later
# # 					if not msg.message:
# # 						msg.message = f"media_id:{media_id}"
# # 						msg.save(ignore_permissions=True)
# # 					continue

# # 				_attach_file_to_message(message_doc=msg, file_data=file_data, mime_type=mime_type)

# # 			# UNKNOWN
# # 			else:
# # 				_save_message_row(
# # 					message=message,
# # 					sender_profile_name=sender_profile_name,
# # 					reply_to_message_id=reply_to_message_id,
# # 					is_reply=is_reply,
# # 					content_type=message_type,
# # 					text=json.dumps(message, ensure_ascii=False)
# # 				)

# # 		return Response("OK", status=200)

# # 	# If no messages, handle statuses/template updates
# # 	update_status({"field": change_field, "value": value})
# # 	return Response("OK", status=200)
# def post():
# 	"""Handle Meta webhook POST."""
# 	data = _read_json_body()

# 	# Always log payload (so we can prove Meta hit us)
# 	_log_webhook_payload(data)

# 	change_field, value = _extract_change(data)
# 	if not (change_field and value):
# 		return Response("OK", status=200)

# 	# Messages / statuses are inside value
# 	messages = value.get("messages") or []
# 	sender_profile_name = _get_sender_profile_name(value)

# 	# If messages exist -> create incoming WhatsApp Message docs
# 	if messages:
# 		settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")

# 		auto_img = bool(getattr(settings, "automatically_download_images", 0))
# 		auto_doc = bool(getattr(settings, "automatically_download_documents", 0))

# 		for message in messages:
# 			message_type = (message.get("type") or "").lower()
# 			context = message.get("context") or {}
# 			is_reply = True if (context and "forwarded" not in context) else False
# 			reply_to_message_id = context.get("id") if is_reply else None

# 			msg_doc = None  # will hold the WhatsApp Message doc we just created

# 			# ---------------- TEXT ----------------
# 			if message_type == "text":
# 				text = (message.get("text") or {}).get("body") or ""
# 				msg_doc = _save_message_row(
# 					message=message,
# 					sender_profile_name=sender_profile_name,
# 					reply_to_message_id=reply_to_message_id,
# 					is_reply=is_reply,
# 					content_type="text",
# 					text=text
# 				)

# 			# ---------------- REACTION ----------------
# 			elif message_type == "reaction":
# 				reaction = (message.get("reaction") or {})
# 				emoji = reaction.get("emoji") or ""
# 				msg_doc = _save_message_row(
# 					message=message,
# 					sender_profile_name=sender_profile_name,
# 					reply_to_message_id=reaction.get("message_id"),
# 					is_reply=True,
# 					content_type="reaction",
# 					text=emoji
# 				)

# 			# ---------------- INTERACTIVE (flow) ----------------
# 			elif message_type == "interactive":
# 				interactive = message.get("interactive") or {}
# 				nfm = interactive.get("nfm_reply") or {}
# 				resp_json = nfm.get("response_json")
# 				msg_doc = _save_message_row(
# 					message=message,
# 					sender_profile_name=sender_profile_name,
# 					reply_to_message_id=reply_to_message_id,
# 					is_reply=is_reply,
# 					content_type="flow",
# 					text=resp_json or json.dumps(interactive, ensure_ascii=False)
# 				)

# 			# ---------------- BUTTON ----------------
# 			elif message_type == "button":
# 				btn = message.get("button") or {}
# 				msg_doc = _save_message_row(
# 					message=message,
# 					sender_profile_name=sender_profile_name,
# 					reply_to_message_id=reply_to_message_id,
# 					is_reply=is_reply,
# 					content_type="button",
# 					text=btn.get("text") or ""
# 				)

# 			# ---------------- MEDIA (image / document / audio / video) ----------------
# 			elif message_type in ["image", "document", "audio", "video"]:
# 				media_block = message.get(message_type) or {}
# 				media_id = media_block.get("id")
# 				caption = media_block.get("caption") or ""

# 				# 1) Create the message row FIRST (idempotent)
# 				msg_doc = _save_message_row(
# 					message=message,
# 					sender_profile_name=sender_profile_name,
# 					reply_to_message_id=reply_to_message_id,
# 					is_reply=is_reply,
# 					content_type=message_type,
# 					text=caption or (f"media_id:{media_id}" if media_id else "")
# 				)

# 				# duplicate? then nothing to do
# 				if not msg_doc or not media_id:
# 					continue

# 				# 2) Only auto-download image/document (audio/video manual later)
# 				should_download = (
# 					message_type == "image" and auto_img
# 				) or (
# 					message_type == "document" and auto_doc
# 				)

# 				if not should_download:
# 					# keep media_id in text for manual work later
# 					if not msg_doc.message:
# 						msg_doc.message = f"media_id:{media_id}"
# 						msg_doc.save(ignore_permissions=True)
# 				else:
# 					file_data, mime_type, _url = _download_media_bytes(
# 						settings=settings,
# 						media_id=media_id
# 					)
# 					if file_data:
# 						_attach_file_to_message(
# 							message_doc=msg_doc,
# 							file_data=file_data,
# 							mime_type=mime_type
# 						)
# 					else:
# 						# download failed: keep media_id so you can retry manually
# 						if not msg_doc.message:
# 							msg_doc.message = f"media_id:{media_id}"
# 							msg_doc.save(ignore_permissions=True)

# 			# ---------------- UNKNOWN TYPE ----------------
# 			else:
# 				msg_doc = _save_message_row(
# 					message=message,
# 					sender_profile_name=sender_profile_name,
# 					reply_to_message_id=reply_to_message_id,
# 					is_reply=is_reply,
# 					content_type=message_type or "unknown",
# 					text=json.dumps(message, ensure_ascii=False)
# 				)

# 			# ---------------- Call bot AFTER message_doc is fully ready ----------------
# 			if msg_doc:
# 				try:
# 					handle_incoming_whatsapp(msg_doc)
# 				except Exception as e:
# 					frappe.log_error(
# 						frappe.get_traceback(),
# 						f"WhatsApp Bot Error for message {msg_doc.name}"
# 					)

# 		return Response("OK", status=200)

# 	# If no messages, handle statuses/template updates
# 	update_status({"field": change_field, "value": value})
# 	return Response("OK", status=200)


# def update_status(data):
# 	"""Update status hook."""
# 	if data.get("field") == "message_template_status_update":
# 		update_template_status(data.get("value") or {})
# 	elif data.get("field") == "messages":
# 		update_message_status(data.get("value") or {})


# def update_template_status(data):
# 	"""Update template status."""
# 	# Keep as you had
# 	frappe.db.sql(
# 		"""UPDATE `tabWhatsApp Templates`
# 		SET status = %(event)s
# 		WHERE id = %(message_template_id)s""",
# 		data
# 	)


# def update_message_status(data):
# 	"""Update message status."""
# 	statuses = data.get("statuses") or []
# 	if not statuses:
# 		return

# 	st = statuses[0] or {}
# 	msg_id = st.get("id")
# 	status = st.get("status")
# 	conversation = (st.get("conversation") or {}).get("id")

# 	if not msg_id:
# 		return

# 	name = frappe.db.get_value("WhatsApp Message", filters={"message_id": msg_id})
# 	if not name:
# 		# message not found yet (out-of-order delivery) -> ignore safely
# 		return

# 	doc = frappe.get_doc("WhatsApp Message", name)
# 	if status:
# 		doc.status = status
# 	if conversation:
# 		doc.conversation_id = conversation
# 	doc.save(ignore_permissions=True)

# # """Webhook."""
# # import frappe
# # import json
# # import requests
# # import time
# # from werkzeug.wrappers import Response
# # import frappe.utils


# # @frappe.whitelist(allow_guest=True)
# # def webhook():
# # 	"""Meta webhook."""
# # 	if frappe.request.method == "GET":
# # 		return get()
# # 	return post()


# # def get():
# # 	"""Get."""
# # 	hub_challenge = frappe.form_dict.get("hub.challenge")
# # 	webhook_verify_token = frappe.db.get_single_value(
# # 		"WhatsApp Settings", "webhook_verify_token"
# # 	)

# # 	if frappe.form_dict.get("hub.verify_token") != webhook_verify_token:
# # 		frappe.throw("Verify token does not match")

# # 	return Response(hub_challenge, status=200)

# # def post():
# # 	"""Post."""
# # 	# 1) Read Meta webhook JSON body reliably
# # 	data = frappe.request.get_json(silent=True)
# # 	if not data:
# # 		raw = frappe.request.get_data(as_text=True) or "{}"
# # 		try:
# # 			data = json.loads(raw)
# # 		except Exception:
# # 			data = {}

# # 	# 2) Log what Meta actually sent
# # 	frappe.get_doc({
# # 		"doctype": "WhatsApp Notification Log",
# # 		"template": "Webhook",
# # 		"meta_data": json.dumps(data)
# # 	}).insert(ignore_permissions=True)

# # 	# 3) Support BOTH payload shapes:
# # 	# A) Full payload: { object, entry:[{changes:[{field,value}]}] }
# # 	# B) Change-only: { field, value }
# # 	change_field = None
# # 	value = {}

# # 	if isinstance(data, dict) and "entry" in data:
# # 		try:
# # 			change = (data.get("entry") or [{}])[0].get("changes", [{}])[0] or {}
# # 			change_field = change.get("field")
# # 			value = change.get("value") or {}
# # 		except Exception:
# # 			change_field, value = None, {}
# # 	elif isinstance(data, dict) and "field" in data and "value" in data:
# # 		change_field = data.get("field")
# # 		value = data.get("value") or {}

# # 	messages = value.get("messages") or []

# # 	sender_profile_name = next(
# # 		(
# # 			contact.get("profile", {}).get("name")
# # 			for contact in (value.get("contacts") or [])
# # 		),
# # 		None
# # 	)

# # 	if messages:
# # 		for message in messages:
# # 			message_type = message.get("type")
# # 			is_reply = True if (message.get("context") and "forwarded" not in message.get("context", {})) else False
# # 			reply_to_message_id = (message.get("context") or {}).get("id") if is_reply else None

# # 			if message_type == "text":
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message": (message.get("text") or {}).get("body"),
# # 					"message_id": message.get("id"),
# # 					"reply_to_message_id": reply_to_message_id,
# # 					"is_reply": is_reply,
# # 					"content_type": message_type,
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 			elif message_type == "reaction":
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message": (message.get("reaction") or {}).get("emoji"),
# # 					"reply_to_message_id": (message.get("reaction") or {}).get("message_id"),
# # 					"message_id": message.get("id"),
# # 					"content_type": "reaction",
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 			elif message_type == "interactive":
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message": ((message.get("interactive") or {}).get("nfm_reply") or {}).get("response_json"),
# # 					"message_id": message.get("id"),
# # 					"reply_to_message_id": reply_to_message_id,
# # 					"is_reply": is_reply,
# # 					"content_type": "flow",
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 			elif message_type in ["image", "audio", "video", "document"]:
# # 				settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
# # 				token = settings.get_password("token")
# # 				base_url = f"{settings.url}/{settings.version}/"

# # 				media_id = ((message.get(message_type) or {}).get("id"))
# # 				if not media_id:
# # 					continue

# # 				headers = {"Authorization": f"Bearer {token}"}

# # 				resp = requests.get(f"{base_url}{media_id}/", headers=headers, timeout=30)
# # 				if resp.status_code != 200:
# # 					continue

# # 				media_data = resp.json() or {}
# # 				media_url = media_data.get("url")
# # 				mime_type = media_data.get("mime_type") or "application/octet-stream"
# # 				file_extension = (mime_type.split("/")[-1] or "bin")

# # 				media_resp = requests.get(media_url, headers=headers, timeout=60)
# # 				if media_resp.status_code != 200:
# # 					continue

# # 				file_data = media_resp.content
# # 				file_name = f"{frappe.generate_hash(length=10)}.{file_extension}"

# # 				message_doc = frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message_id": message.get("id"),
# # 					"reply_to_message_id": reply_to_message_id,
# # 					"is_reply": is_reply,
# # 					"message": (message.get(message_type) or {}).get("caption", f"/files/{file_name}"),
# # 					"content_type": message_type,
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 				file = frappe.get_doc({
# # 					"doctype": "File",
# # 					"file_name": file_name,
# # 					"attached_to_doctype": "WhatsApp Message",
# # 					"attached_to_name": message_doc.name,
# # 					"content": file_data,
# # 					"attached_to_field": "attach"
# # 				}).save(ignore_permissions=True)

# # 				message_doc.attach = file.file_url
# # 				message_doc.save(ignore_permissions=True)

# # 			elif message_type == "button":
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message": (message.get("button") or {}).get("text"),
# # 					"message_id": message.get("id"),
# # 					"reply_to_message_id": reply_to_message_id,
# # 					"is_reply": is_reply,
# # 					"content_type": message_type,
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 			else:
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message_id": message.get("id"),
# # 					"message": json.dumps(message, ensure_ascii=False),
# # 					"content_type": message_type or "unknown",
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 	else:
# # 		# handle statuses / template updates even in change-only shape
# # 		if change_field and value:
# # 			update_status({"field": change_field, "value": value})

# # 	return Response("OK", status=200)

# # 	"""Post."""
# # 	# 1) Read Meta webhook JSON body reliably
# # 	data = frappe.request.get_json(silent=True)
# # 	if not data:
# # 		raw = frappe.request.get_data(as_text=True) or "{}"
# # 		try:
# # 			data = json.loads(raw)
# # 		except Exception:
# # 			data = {}

# # 	# 2) Log what Meta actually sent (super important for debugging)
# # 	frappe.get_doc({
# # 		"doctype": "WhatsApp Notification Log",
# # 		"template": "Webhook",
# # 		"meta_data": json.dumps(data)
# # 	}).insert(ignore_permissions=True)

# # 	# 3) Extract messages safely (Meta format: entry -> changes -> value -> messages/statuses)
# # 	value = {}
# # 	try:
# # 		value = (data.get("entry") or [{}])[0].get("changes", [{}])[0].get("value", {}) or {}
# # 	except Exception:
# # 		value = {}

# # 	messages = value.get("messages", []) or []

# # 	sender_profile_name = next(
# # 		(
# # 			contact.get("profile", {}).get("name")
# # 			for entry in data.get("entry", [])
# # 			for change in entry.get("changes", [])
# # 			for contact in (change.get("value", {}) or {}).get("contacts", [])
# # 		),
# # 		None,
# # 	)

# # 	if messages:
# # 		for message in messages:
# # 			message_type = message.get("type")
# # 			is_reply = True if (message.get("context") and "forwarded" not in message.get("context", {})) else False
# # 			reply_to_message_id = (message.get("context") or {}).get("id") if is_reply else None

# # 			if message_type == "text":
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message": (message.get("text") or {}).get("body"),
# # 					"message_id": message.get("id"),
# # 					"reply_to_message_id": reply_to_message_id,
# # 					"is_reply": is_reply,
# # 					"content_type": message_type,
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 			elif message_type == "reaction":
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message": (message.get("reaction") or {}).get("emoji"),
# # 					"reply_to_message_id": (message.get("reaction") or {}).get("message_id"),
# # 					"message_id": message.get("id"),
# # 					"content_type": "reaction",
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 			elif message_type == "interactive":
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message": ((message.get("interactive") or {}).get("nfm_reply") or {}).get("response_json"),
# # 					"message_id": message.get("id"),
# # 					"reply_to_message_id": reply_to_message_id,
# # 					"is_reply": is_reply,
# # 					"content_type": "flow",
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 			elif message_type in ["image", "audio", "video", "document"]:
# # 				settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")

# # 				download_allowed = (
# # 					(message_type == "image" and settings.automatically_download_images) or
# # 					(message_type == "audio" and settings.automatically_download_audio) or
# # 					(message_type == "video" and getattr(settings, "automatically_download_video", 0)) or
# # 					(message_type == "document" and getattr(settings, "automatically_download_documents", 0))
# # 				)

# # 				media_id = (message.get(message_type) or {}).get("id")

# # 				# Always create ONE message row
# # 				message_doc = frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message_id": message.get("id"),
# # 					"reply_to_message_id": reply_to_message_id,
# # 					"is_reply": is_reply,
# # 					"message": (message.get(message_type) or {}).get("caption") or (f"media_id:{media_id}" if media_id else ""),
# # 					"content_type": message_type,
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 				# If disabled or no media_id, stop here
# # 				if not download_allowed or not media_id:
# # 					continue

# # 				token = settings.get_password("token")
# # 				base_url = f"{settings.url}/{settings.version}/"
# # 				headers = {"Authorization": f"Bearer {token}"}

# # 				# 1) Get media URL + mime type
# # 				resp = requests.get(f"{base_url}{media_id}/", headers=headers, timeout=30)
# # 				if resp.status_code != 200:
# # 					continue

# # 				media_data = resp.json() or {}
# # 				media_url = media_data.get("url")
# # 				mime_type = media_data.get("mime_type") or "application/octet-stream"
# # 				file_extension = (mime_type.split("/")[-1] or "bin")

# # 				# 2) Download media bytes
# # 				media_resp = requests.get(media_url, headers=headers, timeout=60)
# # 				if media_resp.status_code != 200:
# # 					continue

# # 				file_data = media_resp.content
# # 				file_name = f"{frappe.generate_hash(length=10)}.{file_extension}"

# # 			# 3) Create ONE File and attach to the SAME message_doc
# # 				file_doc = frappe.get_doc({
# # 					"doctype": "File",
# # 					"file_name": file_name,
# # 					"attached_to_doctype": "WhatsApp Message",
# # 					"attached_to_name": message_doc.name,
# # 					"content": file_data,
# # 					"attached_to_field": "attach"
# # 				}).save(ignore_permissions=True)

# # 				# 4) Update existing message_doc (do NOT create another WhatsApp Message)
# # 				message_doc.attach = file_doc.file_url
# # 				# optional: store a nicer message text
# # 				if not message_doc.message:
# # 					message_doc.message = file_doc.file_url
# # 				message_doc.save(ignore_permissions=True)

# # 			elif message_type == "button":
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message": (message.get("button") or {}).get("text"),
# # 					"message_id": message.get("id"),
# # 					"reply_to_message_id": reply_to_message_id,
# # 					"is_reply": is_reply,
# # 					"content_type": message_type,
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 			else:
# # 				frappe.get_doc({
# # 					"doctype": "WhatsApp Message",
# # 					"type": "Incoming",
# # 					"from": message.get("from"),
# # 					"message_id": message.get("id"),
# # 					"message": json.dumps(message, ensure_ascii=False),
# # 					"content_type": message_type or "unknown",
# # 					"profile_name": sender_profile_name
# # 				}).insert(ignore_permissions=True)

# # 	else:
# # 		# status updates come in `value.statuses`
# # 		# your update_status expects changes dict with field/value
# # 		changes = None
# # 		try:
# # 			changes = (data.get("entry") or [{}])[0].get("changes", [{}])[0]
# # 		except Exception:
# # 			changes = None

# # 		if changes:
# # 			update_status(changes)

# # 	# 4) Always return 200 quickly to Meta
# # 	return Response("OK", status=200)

# # def update_status(data):
# # 	"""Update status hook."""
# # 	if data.get("field") == "message_template_status_update":
# # 		update_template_status(data['value'])

# # 	elif data.get("field") == "messages":
# # 		update_message_status(data['value'])

# # def update_template_status(data):
# # 	"""Update template status."""
# # 	frappe.db.sql(
# # 		"""UPDATE `tabWhatsApp Templates`
# # 		SET status = %(event)s
# # 		WHERE id = %(message_template_id)s""",
# # 		data
# # 	)

# # def update_message_status(data):
# # 	"""Update message status."""
# # 	id = data['statuses'][0]['id']
# # 	status = data['statuses'][0]['status']
# # 	conversation = data['statuses'][0].get('conversation', {}).get('id')
# # 	name = frappe.db.get_value("WhatsApp Message", filters={"message_id": id})

# # 	doc = frappe.get_doc("WhatsApp Message", name)
# # 	doc.status = status
# # 	if conversation:
# # 		doc.conversation_id = conversation
# # 	doc.save(ignore_permissions=True)