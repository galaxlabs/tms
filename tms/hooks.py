app_name = "tms"
app_title = "Transport Management System"
app_publisher = "Galaxy Labs"
app_description = "Transport Management System"
app_email = "galaxylab2020@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "tms",
# 		"logo": "/assets/tms/logo.png",
# 		"title": "Transport Management System",
# 		"route": "/tms",
# 		"has_permission": "tms.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/tms/css/tms.css"
# app_include_js = "/assets/tms/js/tms.js"

# include js, css files in header of web template
# web_include_css = "/assets/tms/css/tms.css"
# web_include_js = "/assets/tms/js/tms.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "tms/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "tms/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "tms.utils.jinja_methods",
# 	"filters": "tms.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "tms.install.before_install"
# after_install = "tms.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "tms.uninstall.before_uninstall"
# after_uninstall = "tms.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "tms.utils.before_app_install"
# after_app_install = "tms.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "tms.utils.before_app_uninstall"
# after_app_uninstall = "tms.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "tms.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------
# scheduler_events = {
# 	"all": [
# 		"tms.tasks.all"
# 	],
# 	"daily": [
# 		"tms.tasks.daily"
# 	],
# 	"hourly": [
# 		"tms.tasks.hourly"
# 	],
# 	"weekly": [
# 		"tms.tasks.weekly"
# 	],
# 	"monthly": [
# 		"tms.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "tms.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "tms.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "tms.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["tms.utils.before_request"]
# after_request = ["tms.utils.after_request"]

# Job Events
# ----------
# before_job = ["tms.utils.before_job"]
# after_job = ["tms.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]
fixtures = [
    # If you created standard (non-custom) doctypes inside your app module,
    # their DocType records are already inside the app, not needed as fixtures.

    # Export only records that belong to your app/module
    {"dt": "Custom Field", "filters": [["module", "=", "Transport Management System"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "Transport Management System"]]},
    {"dt": "Client Script", "filters": [["module", "=", "Transport Management System"]]},
    {"dt": "Server Script", "filters": [["module", "=", "Transport Management System"]]},
    # Print Formats / Reports / Workflows that belong to your module
]
# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"tms.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
after_migrate = "tms.override_frappe_get_pdf"
boot_session = "tms.override_frappe_get_pdf"

scheduler_events = {
    # -------------------------
    # CRON (specific times)
    # -------------------------
    "cron": {
        # At 06:00 on day 1 of every month
        "0 6 1 * *": [
            "tms.hotels.api.rental.auto_generate_rent_invoices",
        ],
        # "*/5 * * * *": [
        #     "tms.utils.trip_lifecycle.auto_mark_trips_arrived"
        # ]
    },

    # -------------------------
    # Standard frequencies
    # -------------------------
    "all": [
        "tms.utils.trigger_whatsapp_notifications_all",
    ],
    "hourly": [
        "tms.utils.trigger_whatsapp_notifications_hourly",
    ],
    "hourly_long": [
        "tms.utils.trigger_whatsapp_notifications_hourly_long",
    ],
    "daily": [
        "tms.utils.trigger_whatsapp_notifications_daily",
        "tms.transport_management_system.doctype.whatsapp_notification.whatsapp_notification.trigger_notifications",

        # ✅ your retention cleanup
        # "tms.utils.retention.run_daily_cleanup",
    ],
    "daily_long": [
        "tms.utils.trigger_whatsapp_notifications_daily_long",
    ],
    "weekly": [
        "tms.utils.trigger_whatsapp_notifications_weekly",
    ],
    "weekly_long": [
        "tms.utils.trigger_whatsapp_notifications_weekly_long",
    ],
    "monthly": [
        "tms.utils.trigger_whatsapp_notifications_monthly",
    ],
    "monthly_long": [
        "tms.utils.trigger_whatsapp_notifications_monthly_long",
    ],
}

doc_events = {
    "*": {
        "before_insert": "tms.utils.run_server_script_for_doc_event",
        "after_insert": "tms.utils.run_server_script_for_doc_event",
        "before_validate": "tms.utils.run_server_script_for_doc_event",
        "validate": "tms.utils.run_server_script_for_doc_event",
        "on_update": "tms.utils.run_server_script_for_doc_event",
        "before_submit": "tms.utils.run_server_script_for_doc_event",
        "on_submit": "tms.utils.run_server_script_for_doc_event",
        "before_cancel": "tms.utils.run_server_script_for_doc_event",
        "on_cancel": "tms.utils.run_server_script_for_doc_event",
        "on_trash": "tms.utils.run_server_script_for_doc_event",
        "after_delete": "tms.utils.run_server_script_for_doc_event",
        "before_update_after_submit": "tms.utils.run_server_script_for_doc_event",
        "on_update_after_submit": "tms.utils.run_server_script_for_doc_event",
    },

    "WhatsApp Message": {
        "after_insert": "tms.utils.whatsapp_bot.entry.handle_incoming_whatsapp",
        "on_update": "tms.utils.whatsapp_bot.entry.handle_incoming_whatsapp",
    },
    
    "Trip": {
        "after_save": "tms.utils.pdf_hooks.create_pdf_on_submit"
    },
    "Quotation": {
        "on_submit": "tms.utils.pdf_hooks.create_pdf_on_submit"
    },
    "Sales Order": {
        "on_submit": "tms.utils.pdf_hooks.create_pdf_on_submit"
    },
    "Sales Invoice": {
        "on_submit": "tms.utils.pdf_hooks.create_pdf_on_submit"
    },
    "Delivery Note": {
        "on_submit": "tms.utils.pdf_hooks.create_pdf_on_submit"
    },
    "Dunning": {
        "on_submit": "tms.utils.pdf_hooks.create_pdf_on_submit"
        }
        
}
