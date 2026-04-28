frappe.provide("tms.vat_dashboard");

frappe.pages["vat_dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("VAT Dashboard"),
		single_column: true,
	});

	wrapper.vat_dashboard = new tms.vat_dashboard.Page(wrapper, page);
};

frappe.pages["vat_dashboard"].on_page_show = function (wrapper) {
	wrapper.vat_dashboard?.refresh();
};

tms.vat_dashboard.Page = class VATDashboardPage {
	constructor(wrapper, page) {
		this.wrapper = $(wrapper);
		this.page = page;
		this.charts = {};
		this.setup();
	}

	setup() {
		this.injectStyles();
		this.setupFilters();
		this.setupActions();
		this.renderShell();
		this.refresh();
	}

	setupFilters() {
		const today = frappe.datetime.get_today();
		const yearStart = `${today.slice(0, 4)}-01-01`;

		this.companyField = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		});

		this.fromDateField = this.page.add_field({
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: yearStart,
		});

		this.toDateField = this.page.add_field({
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: today,
		});

		this.documentModeField = this.page.add_field({
			fieldname: "document_mode",
			label: __("Invoice Mode"),
			fieldtype: "Select",
			options: "live\nsubmitted",
			default: "live",
		});
		this.documentModeField.set_value("live");
		this.documentModeField.df.change = () => this.refresh();

		[this.companyField, this.fromDateField, this.toDateField, this.documentModeField].forEach((field) => {
			if (!field?.$input) {
				return;
			}
			field.$input.on("change", () => this.refresh());
		});
	}

	setupActions() {
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
		this.page.add_inner_button(__("VAT Process"), () => frappe.set_route("List", "VAT Process"));
		this.page.add_inner_button(__("Sales Invoices"), () => frappe.set_route("List", "Sales Invoice"));
		this.page.add_inner_button(__("Purchase Invoices"), () => frappe.set_route("List", "Purchase Invoice"));
	}

	renderShell() {
		this.body = $(`
			<div class="vat-dashboard-root">
				<div class="vat-dashboard-hero">
					<div>
						<p class="vat-dashboard-kicker">${__("Compliance Pulse")}</p>
						<h1>${__("VAT Collection vs Recovery")}</h1>
						<p class="vat-dashboard-subtitle">
							${__("Track live or submitted invoice VAT, review pipeline pressure, and surface audit-watch gaps before filing.")}
						</p>
					</div>
					<div class="vat-dashboard-hero-chip">
						<span class="chip-label">${__("Period")}</span>
						<span class="chip-value" data-field="active-period">${__("Loading...")}</span>
						<small class="chip-mode" data-field="active-mode"></small>
					</div>
				</div>
				<div class="vat-dashboard-alert" data-field="alert"></div>
				<div class="vat-dashboard-cards" data-field="summary-cards"></div>
				<div class="vat-dashboard-insights" data-field="insights"></div>
				<div class="vat-dashboard-grid">
					<section class="vat-panel vat-panel-wide">
						<div class="vat-panel-head">
							<h3>${__("VAT Trend")}</h3>
							<p>${__("Sales VAT collected vs purchase VAT paid by month, based on the selected invoice mode")}</p>
						</div>
						<div class="vat-chart" data-chart="vat_trend"></div>
					</section>
					<section class="vat-panel">
						<div class="vat-panel-head">
							<h3>${__("Status Mix")}</h3>
							<p>${__("Current VAT Process pipeline by status")}</p>
						</div>
						<div class="vat-chart" data-chart="status_distribution"></div>
					</section>
					<section class="vat-panel vat-panel-wide">
						<div class="vat-panel-head">
							<h3>${__("Taxable Base Trend")}</h3>
							<p>${__("Net sales vs net purchases from live or submitted invoices")}</p>
						</div>
						<div class="vat-chart" data-chart="net_trend"></div>
					</section>
					<section class="vat-panel">
						<div class="vat-panel-head">
							<h3>${__("VAT Process Queue")}</h3>
							<p>${__("Operational pressure and reviewed backlog")}</p>
						</div>
						<div data-field="status-table"></div>
					</section>
					<section class="vat-panel">
						<div class="vat-panel-head">
							<h3>${__("Top Customers")}</h3>
							<p>${__("Highest VAT collection drivers")}</p>
						</div>
						<div data-field="customers-table"></div>
					</section>
					<section class="vat-panel">
						<div class="vat-panel-head">
							<h3>${__("Top Suppliers")}</h3>
							<p>${__("Largest purchase VAT offsets")}</p>
						</div>
						<div data-field="suppliers-table"></div>
					</section>
				</div>
			</div>
		`);

		this.page.main.empty().append(this.body);
	}

	refresh() {
		if (!this.body) {
			return;
		}

		this.setLoading(true);
		frappe.call({
			method: "tms.transport_management_system.api.vat_dashboard.get_vat_dashboard_data",
			args: {
				company: this.companyField.get_value(),
				from_date: this.fromDateField.get_value(),
				to_date: this.toDateField.get_value(),
				document_mode: this.documentModeField.get_value(),
			},
			callback: (response) => {
				this.setLoading(false);
				if (!response.message) {
					this.renderEmptyState();
					return;
				}
				this.render(response.message);
			},
			error: () => {
				this.setLoading(false);
				this.renderErrorState();
			},
		});
	}

	setLoading(isLoading) {
		this.body.toggleClass("is-loading", Boolean(isLoading));
	}

	render(data) {
		this.data = data;
		const currency = data.filters.currency;
		this.body.find('[data-field="active-period"]').text(
			`${frappe.datetime.str_to_user(data.filters.from_date)} - ${frappe.datetime.str_to_user(data.filters.to_date)}`
		);
		this.body.find('[data-field="active-mode"]').text(
			data.filters.document_mode === "submitted" ? __("Submitted Only") : __("Live: Draft + Submitted")
		);
		this.renderAlert(data.audit_signal, currency);
		this.renderSummaryCards(data, currency);
		this.renderInsights(data.insights || []);
		this.renderStatusTable(data.status_breakdown || [], currency);
		this.renderPartyTable('[data-field="customers-table"]', data.top_parties.customers || [], currency, __("No customer VAT data found."));
		this.renderPartyTable('[data-field="suppliers-table"]', data.top_parties.suppliers || [], currency, __("No supplier VAT data found."));
		this.renderCharts(data.charts || {});
	}

	renderAlert(alert, currency) {
		const difference = alert?.difference || 0;
		const badgeLabel = {
			red: __("Immediate Review"),
			amber: __("Balanced"),
			green: __("Covered"),
		}[alert?.level || "amber"];

		this.body.find('[data-field="alert"]').attr("data-level", alert?.level || "amber").html(`
			<div class="alert-copy">
				<p class="alert-kicker">${__("Audit Watch")}</p>
				<h2>${frappe.utils.escape_html(alert?.title || __("VAT Position"))}</h2>
				<p>${frappe.utils.escape_html(alert?.message || "")}</p>
			</div>
			<div class="alert-metric">
				<span class="alert-badge">${badgeLabel}</span>
				<strong>${this.formatCurrency(Math.abs(difference), currency)}</strong>
				<small>${difference >= 0 ? __("Gap") : __("Coverage")}</small>
			</div>
		`);
	}

	renderSummaryCards(data, currency) {
		const totals = data.totals || {};
		const stats = data.stats || {};
		const isSubmitted = data.filters?.document_mode === "submitted";
		const salesMetaLabel = isSubmitted ? __("submitted sales invoices") : __("live sales invoices");
		const purchaseMetaLabel = isSubmitted ? __("submitted purchase invoices") : __("live purchase invoices");
		const cards = [
			{
				label: __("VAT Collected"),
				value: this.formatCurrency(totals.vat_collected, currency),
				meta: `${totals.submitted_sales_invoices || 0} ${salesMetaLabel}`,
			},
			{
				label: __("VAT Paid"),
				value: this.formatCurrency(totals.vat_paid, currency),
				meta: `${totals.submitted_purchase_invoices || 0} ${purchaseMetaLabel}`,
			},
			{
				label: __("Net VAT Position"),
				value: this.formatCurrency(totals.net_vat_payable, currency),
				meta: totals.net_vat_payable > 0 ? __("Payable exposure") : __("Recovery coverage"),
			},
			{
				label: __("Coverage Ratio"),
				value: `${Number(stats.vat_coverage_ratio || 0).toFixed(2)}%`,
				meta: __("Purchase VAT vs collected VAT"),
			},
			{
				label: __("Pending Review"),
				value: String(stats.pending_review_count || 0),
				meta: __("Draft + Extracted + Needs Review"),
			},
			{
				label: __("Invoices Created"),
				value: String(stats.invoice_created_count || 0),
				meta: __("VAT Process converted to ERPNext invoices"),
			},
		];

		this.body.find('[data-field="summary-cards"]').html(
			cards
				.map(
					(card) => `
						<div class="vat-summary-card">
							<p>${frappe.utils.escape_html(card.label)}</p>
							<h3>${frappe.utils.escape_html(card.value)}</h3>
							<span>${frappe.utils.escape_html(card.meta)}</span>
						</div>
					`
				)
				.join("")
		);
	}

	renderInsights(insights) {
		if (!insights.length) {
			this.body.find('[data-field="insights"]').empty();
			return;
		}

		this.body.find('[data-field="insights"]').html(
			insights
				.map(
					(insight) => `
						<div class="vat-insight" data-tone="${frappe.utils.escape_html(insight.tone || "neutral")}">
							<span>${frappe.utils.escape_html(insight.label || __("Insight"))}</span>
							<strong>${frappe.utils.escape_html(insight.value || "")}</strong>
						</div>
					`
				)
				.join("")
		);
	}

	renderStatusTable(rows, currency) {
		this.body.find('[data-field="status-table"]').html(this.buildMetricTable(rows, currency, __("No VAT Process records found.")));
	}

	renderPartyTable(selector, rows, currency, emptyMessage) {
		const mapped = (rows || []).map((row) => ({
			label: row.party || __("Unknown"),
			value: this.formatCurrency(row.vat_total, currency),
			meta: `${__("Net")}: ${this.formatCurrency(row.net_total, currency)}`,
		}));

		this.body.find(selector).html(this.buildMetricTable(mapped, currency, emptyMessage, true));
	}

	buildMetricTable(rows, currency, emptyMessage, useValueMetaColumns) {
		if (!rows.length) {
			return `<div class="vat-empty">${frappe.utils.escape_html(emptyMessage)}</div>`;
		}

		if (useValueMetaColumns) {
			return `
				<table class="vat-table">
					<tbody>
						${rows
							.map(
								(row) => `
									<tr>
										<td>${frappe.utils.escape_html(row.label)}</td>
										<td>${frappe.utils.escape_html(row.value)}</td>
										<td>${frappe.utils.escape_html(row.meta)}</td>
									</tr>
								`
							)
							.join("")}
					</tbody>
				</table>
			`;
		}

		return `
			<table class="vat-table">
				<tbody>
					${rows
						.map(
							(row) => `
									<tr>
										<td>${frappe.utils.escape_html(row.status || row.label)}</td>
										<td>${frappe.utils.escape_html(String(row.count || 0))}</td>
										<td>${frappe.utils.escape_html(this.formatCurrency(row.grand_total || 0, currency))}</td>
									</tr>
								`
						)
						.join("")}
				</tbody>
			</table>
		`;
	}

	renderCharts(charts) {
		this.renderChart("vat_trend", "line", charts.vat_trend, ["#D96C06", "#0A7E8C"]);
		this.renderChart("net_trend", "bar", charts.net_trend, ["#1E5B52", "#B85C38"]);
		this.renderChart("status_distribution", "donut", charts.status_distribution, ["#0A7E8C", "#D96C06", "#1E5B52", "#B23A48", "#6C757D", "#B08968"]);
	}

	renderChart(chartKey, type, data, colors) {
		const container = this.body.find(`[data-chart="${chartKey}"]`).get(0);
		if (!container) {
			return;
		}

		if (this.charts[chartKey] && this.charts[chartKey].destroy) {
			this.charts[chartKey].destroy();
		}

		container.innerHTML = "";
		if (!data?.labels?.length) {
			container.innerHTML = `<div class="vat-empty">${__("No chart data in the selected range.")}</div>`;
			return;
		}

		this.charts[chartKey] = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: data.datasets || [],
			},
			type,
			height: 260,
			colors,
			barOptions: {
				spaceRatio: 0.35,
			},
			lineOptions: {
				hideDots: 0,
				regionFill: 1,
			},
		});
	}

	renderEmptyState() {
		this.body.find('[data-field="alert"]').html(`<div class="vat-empty">${__("No VAT dashboard data was returned.")}</div>`);
	}

	renderErrorState() {
		this.body.find('[data-field="alert"]').html(`<div class="vat-empty">${__("Unable to load VAT dashboard data right now.")}</div>`);
	}

	formatCurrency(value, currency) {
		return format_currency(value || 0, currency);
	}

	injectStyles() {
		if (document.getElementById("vat-dashboard-page-styles")) {
			return;
		}

		const style = document.createElement("style");
		style.id = "vat-dashboard-page-styles";
		style.textContent = `
			.vat-dashboard-root {
				--vat-ink: #19323c;
				--vat-shell: #f6f1e8;
				--vat-panel: #fffdf8;
				--vat-line: rgba(25, 50, 60, 0.1);
				--vat-accent: #d96c06;
				--vat-teal: #0a7e8c;
				--vat-red: #b23a48;
				--vat-green: #1e5b52;
				padding: 18px 8px 32px;
				color: var(--vat-ink);
			}

			.vat-dashboard-root.is-loading {
				opacity: 0.7;
				pointer-events: none;
			}

			.vat-dashboard-hero {
				display: grid;
				grid-template-columns: minmax(0, 1fr) auto;
				gap: 16px;
				padding: 24px;
				border-radius: 24px;
				background:
					radial-gradient(circle at top left, rgba(217, 108, 6, 0.18), transparent 38%),
					linear-gradient(135deg, #fff6df 0%, #f5fbfb 100%);
				border: 1px solid rgba(25, 50, 60, 0.08);
				box-shadow: 0 24px 60px rgba(25, 50, 60, 0.08);
			}

			.vat-dashboard-kicker,
			.alert-kicker,
			.vat-summary-card p,
			.vat-insight span,
			.chip-label {
				margin: 0 0 6px;
				font-size: 11px;
				font-weight: 700;
				letter-spacing: 0.12em;
				text-transform: uppercase;
			}

			.vat-dashboard-hero h1,
			.vat-dashboard-alert h2 {
				margin: 0;
				font-size: 32px;
				font-weight: 700;
				line-height: 1.05;
			}

			.vat-dashboard-subtitle,
			.vat-panel-head p,
			.vat-dashboard-alert p {
				margin: 8px 0 0;
				font-size: 14px;
				line-height: 1.6;
				color: rgba(25, 50, 60, 0.75);
			}

			.vat-dashboard-hero-chip,
			.vat-summary-card,
			.vat-insight,
			.vat-panel,
			.vat-dashboard-alert {
				border: 1px solid var(--vat-line);
				background: var(--vat-panel);
				box-shadow: 0 18px 40px rgba(25, 50, 60, 0.06);
			}

			.vat-dashboard-hero-chip {
				display: flex;
				flex-direction: column;
				justify-content: center;
				min-width: 200px;
				padding: 18px;
				border-radius: 18px;
			}

			.chip-value,
			.vat-summary-card h3,
			.alert-metric strong {
				font-size: 28px;
				font-weight: 700;
				line-height: 1;
			}

			.vat-dashboard-alert {
				margin-top: 18px;
				padding: 20px 24px;
				border-radius: 22px;
				display: grid;
				grid-template-columns: minmax(0, 1fr) auto;
				gap: 18px;
				align-items: center;
				position: relative;
				overflow: hidden;
			}

			.vat-dashboard-alert[data-level="red"] {
				background: linear-gradient(135deg, #fff4f3 0%, #fffdf8 100%);
				border-color: rgba(178, 58, 72, 0.28);
			}

			.vat-dashboard-alert[data-level="green"] {
				background: linear-gradient(135deg, #f0faf7 0%, #fffdf8 100%);
				border-color: rgba(30, 91, 82, 0.24);
			}

			.vat-dashboard-alert[data-level="amber"] {
				background: linear-gradient(135deg, #fff8e8 0%, #fffdf8 100%);
				border-color: rgba(217, 108, 6, 0.24);
			}

			.alert-metric {
				display: flex;
				flex-direction: column;
				align-items: flex-end;
				gap: 4px;
			}

			.alert-badge {
				padding: 6px 10px;
				border-radius: 999px;
				background: rgba(25, 50, 60, 0.08);
				font-size: 11px;
				font-weight: 700;
				letter-spacing: 0.08em;
				text-transform: uppercase;
			}

			.vat-dashboard-cards {
				margin-top: 18px;
				display: grid;
				grid-template-columns: repeat(6, minmax(0, 1fr));
				gap: 14px;
			}

			.vat-summary-card {
				padding: 18px;
				border-radius: 18px;
			}

			.vat-summary-card h3 {
				margin: 0;
			}

			.vat-summary-card span,
			.vat-insight strong,
			.alert-metric small {
				font-size: 13px;
				color: rgba(25, 50, 60, 0.72);
			}

			.vat-dashboard-insights {
				margin-top: 18px;
				display: grid;
				grid-template-columns: repeat(4, minmax(0, 1fr));
				gap: 14px;
			}

			.vat-insight {
				padding: 16px 18px;
				border-radius: 18px;
			}

			.vat-insight[data-tone="red"] {
				border-color: rgba(178, 58, 72, 0.28);
			}

			.vat-insight[data-tone="green"] {
				border-color: rgba(30, 91, 82, 0.24);
			}

			.vat-dashboard-grid {
				margin-top: 18px;
				display: grid;
				grid-template-columns: repeat(2, minmax(0, 1fr));
				gap: 16px;
			}

			.vat-panel {
				padding: 18px;
				border-radius: 22px;
				min-height: 320px;
			}

			.vat-panel-wide {
				grid-column: span 2;
			}

			.vat-panel-head h3 {
				margin: 0;
				font-size: 20px;
				font-weight: 700;
			}

			.vat-chart {
				margin-top: 12px;
				min-height: 240px;
			}

			.vat-table {
				width: 100%;
				margin-top: 12px;
				border-collapse: collapse;
			}

			.vat-table td {
				padding: 12px 0;
				border-bottom: 1px solid var(--vat-line);
				font-size: 14px;
			}

			.vat-table td:nth-child(2),
			.vat-table td:nth-child(3) {
				text-align: right;
				white-space: nowrap;
			}

			.vat-empty {
				display: flex;
				align-items: center;
				justify-content: center;
				min-height: 220px;
				border: 1px dashed var(--vat-line);
				border-radius: 18px;
				color: rgba(25, 50, 60, 0.56);
				font-size: 14px;
			}

			@media (max-width: 1400px) {
				.vat-dashboard-cards {
					grid-template-columns: repeat(3, minmax(0, 1fr));
				}

				.vat-dashboard-insights {
					grid-template-columns: repeat(2, minmax(0, 1fr));
				}
			}

			@media (max-width: 992px) {
				.vat-dashboard-hero,
				.vat-dashboard-alert,
				.vat-dashboard-grid {
					grid-template-columns: 1fr;
				}

				.vat-dashboard-cards,
				.vat-dashboard-insights {
					grid-template-columns: 1fr;
				}

				.vat-panel-wide {
					grid-column: span 1;
				}
			}
		`;

		document.head.appendChild(style);
	}
};
