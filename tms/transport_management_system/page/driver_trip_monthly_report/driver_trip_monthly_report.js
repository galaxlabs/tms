frappe.pages["driver_trip_monthly_report"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Driver Performance & VAT Analytics"),
		single_column: true,
	});

	let current_chart = null;

	// ── Filters ──
	page.period_filter = page.add_field({
		fieldname: "period", label: __("Period"), fieldtype: "Select",
		options: ["Daily", "Weekly", "Monthly"], default: "Monthly",
		on_change: () => refresh_dashboard(),
	});

	page.month_filter = page.add_field({
		fieldname: "month", label: __("Month"), fieldtype: "Select",
		options: ["January","February","March","April","May","June","July","August","September","October","November","December"],
		default: moment().format("MMMM"),
		on_change: () => refresh_dashboard(),
	});

	page.driver_filter = page.add_field({
		fieldname: "driver", label: __("Driver"), fieldtype: "Link",
		options: "Staff",
		on_change: () => refresh_dashboard(),
		get_query: () => ({ filters: { enabled: 1 } }),
	});

	page.dimension_filter = page.add_field({
		fieldname: "dimension", label: __("Group By"), fieldtype: "Select",
		options: [
			{ label: __("Driver"), value: "driver" },
			{ label: __("Date"), value: "date" },
			{ label: __("Route"), value: "route" },
		],
		default: "driver",
		on_change: () => refresh_dashboard(),
	});

	page.metric_filter = page.add_field({
		fieldname: "metric", label: __("Metric"), fieldtype: "Select",
		options: [
			{ label: __("VAT Amount"), value: "vat" },
			{ label: __("Trip Value"), value: "trip_value" },
			{ label: __("Net Revenue"), value: "net" },
			{ label: __("Grand Total"), value: "grand_total" },
			{ label: __("Trip Count"), value: "trip_count" },
			{ label: __("Distance (km)"), value: "distance" },
		],
		default: "vat",
		on_change: () => refresh_dashboard(),
	});

	page.set_primary_action(__("Print Report"), () => show_print_dialog());
	page.add_inner_button(__("Refresh"), () => refresh_dashboard());
	page.add_inner_button(__("Export CSV"), () => export_csv());

	// ── Layout ──
	page.main.html(`
		<div id="dash-summary" style="padding: 10px 15px;"></div>
		<div style="padding: 10px 15px; display: flex; gap: 15px;">
			<div style="flex: 0 0 62%;">
				<div id="dash-chart" class="border rounded" style="background: var(--card-bg); padding: 15px; min-height: 350px;">
					<div class="text-center text-muted" style="padding-top: 150px;">${__("Loading...")}</div>
				</div>
			</div>
			<div style="flex: 1;">
				<div id="dash-side-panel" class="border rounded" style="background: var(--card-bg); padding: 15px; max-height: 350px; overflow-y: auto;">
					<h6 class="text-muted">${__("Breakdown")}</h6>
					<div id="dash-side-content" class="text-muted small">${__("Loading...")}</div>
				</div>
			</div>
		</div>
		<div style="padding: 10px 15px;">
			<div id="dash-pivot" class="border rounded" style="background: var(--card-bg); padding: 15px;">
				<div class="d-flex justify-content-between align-items-center mb-2">
					<h6 class="text-muted m-0">${__("Analytics Pivot Table")}</h6>
					<small class="text-muted" id="pivot-desc"></small>
				</div>
				<div id="dash-pivot-content" style="max-height: 400px; overflow: auto;">
					<div class="text-muted small text-center py-4">${__("Loading...")}</div>
				</div>
			</div>
		</div>
		<div style="padding: 10px 15px;">
			<div id="dash-invoices" class="border rounded" style="background: var(--card-bg); padding: 15px;">
				<h6 class="text-muted">${__("Trip Invoices")}</h6>
				<div id="dash-invoice-table" style="max-height: 350px; overflow: auto;"></div>
			</div>
		</div>
		<div style="padding: 10px 15px;">
			<div id="dash-driver-table" class="border rounded" style="background: var(--card-bg); padding: 15px;">
				<h6 class="text-muted">${__("Driver Performance Detail")}</h6>
				<div id="dash-driver-table-content" style="max-height: 400px; overflow: auto;"></div>
			</div>
		</div>
	`);

	// ── Refresh ──
	const refresh_dashboard = () => {
		const args = {
			month: page.month_filter.get_value(),
			driver: page.driver_filter.get_value(),
			period: (page.period_filter.get_value() || "Monthly").toLowerCase(),
			dimension: page.dimension_filter.get_value() || "driver",
			metric: page.metric_filter.get_value() || "vat",
		};

		frappe.call({
			method: "tms.transport_management_system.page.driver_trip_monthly_report.driver_trip_monthly_report.get_dashboard_data",
			args: args,
			freeze: true,
			freeze_message: __("Loading analytics..."),
			callback: (r) => {
				if (!r.message) { frappe.msgprint(__("No data returned.")); return; }
				const data = r.message;
				render_summary(data.summary);
				render_chart(data.chart_data);
				render_side_panel(data);
				render_pivot(data.pivot, data.filters);
				render_driver_table(data.driver_breakdown);
				render_invoices(data.invoices);
				page._raw_data = data;
			},
		});
	};

	// ── SUMMARY CARDS ──
	const render_summary = (summary) => {
		const colors = { blue:"#3498db", green:"#2ecc71", purple:"#9b59b6", orange:"#e67e22", red:"#e74c3c", cyan:"#1abc9c", yellow:"#f39c12" };
		const cards = (summary || []).map(s => `
			<div style="flex: 1; min-width: 140px; padding: 0 5px; margin-bottom: 8px;">
				<div class="card p-2 text-center" style="border-left: 3px solid ${colors[s.indicator]||'#3498db'}; border-radius: 6px; background: var(--card-bg);">
					<div class="text-muted" style="font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;">${s.label}</div>
					<div class="font-weight-bold" style="font-size: 16px; color: ${colors[s.indicator]||'#3498db'};">${s.value}</div>
				</div>
			</div>
		`).join("");
		page.main.find("#dash-summary").html(`<div style="display: flex; flex-wrap: wrap;">${cards}</div>`);
	};

	// ── CHART ──
	const render_chart = (chart_data) => {
		const container = page.main.find("#dash-chart");
		container.empty();
		if (!chart_data || !chart_data.labels || !chart_data.labels.length) {
			container.html(`<div class="text-center text-muted" style="padding-top: 150px;">${__("No data")}</div>`);
			return;
		}
		const colors = ["#3498db","#e67e22","#2ecc71","#e74c3c","#9b59b6","#1abc9c"];
		const datasets = (chart_data.datasets || []).map((ds, i) => ({
			name: ds.name, values: ds.values || [],
			chartType: ds.chartType || "bar",
		}));
		current_chart = new frappe.Chart("#dash-chart", {
			title: chart_data.title || __("Analytics"),
			data: { labels: chart_data.labels, datasets: datasets },
			type: "axis-mixed", height: 320, colors: colors,
			barOptions: { stacked: 0, spaceRatio: 0.3 },
			lineOptions: { regionFill: 0, dotSize: 4, hideDots: chart_data.labels.length > 25 ? 1 : 0 },
			axisOptions: { xAxisMode: "tick", xIsSeries: 1 },
		});
	};

	// ── SIDE PANEL ──
	const render_side_panel = (data) => {
		const container = page.main.find("#dash-side-content");
		const drivers = data.driver_breakdown || [];
		const routes = data.top_routes || [];
		const dimension = data.filters?.dimension || "driver";

		if (dimension === "route" && routes.length) {
			let html = routes.slice(0, 10).map((r, i) => `
				<div class="d-flex justify-content-between py-1 border-bottom small">
					<span><b>${i+1}.</b> ${r.route || __("No Route")}</span>
					<span>SAR ${fmt(r.total_vat)}</span>
				</div>
			`).join("");
			container.html(html);
		} else if (drivers.length) {
			let html = drivers.slice(0, 10).map((d, i) => `
				<div class="d-flex justify-content-between py-1 border-bottom small">
					<span><b>${i+1}.</b> ${d.driver}</span>
					<span class="font-weight-bold">SAR ${fmt(d.total_vat)}</span>
				</div>
				<div class="d-flex justify-content-between small text-muted" style="padding-left: 20px; font-size: 10px;">
					<span>${d.trip_count} trips | ${fmt(d.total_distance)} km</span>
					<span>${fmt(d.vat_pct)}% VAT</span>
				</div>
			`).join("");
			container.html(html);
		} else {
			container.html(`<div class="text-muted">${__("No data")}</div>`);
		}
	};

	// ── PIVOT TABLE ──
	const render_pivot = (pivot, filters) => {
		const desc = page.main.find("#pivot-desc");
		const container = page.main.find("#dash-pivot-content");
		if (!pivot || !pivot.rows || !pivot.rows.length) {
			desc.text("");
			container.html(`<div class="text-muted small text-center py-4">${__("No data for pivot view.")}</div>`);
			return;
		}

		desc.text(`${pivot.metric || ""} — ${filters?.month_label || ""} (${filters?.period || ""})`);

		if (pivot.type === "cross_tab") {
			render_cross_tab(container, pivot);
		} else {
			render_ranking_bars(container, pivot);
		}
	};

	const render_cross_tab = (container, pivot) => {
		const maxVal = pivot.max_value || 1;
		const colLabels = pivot.column_labels || [];
		const rows = pivot.rows || [];
		const colTotals = pivot.column_totals || [];

		// Color scale function: white → orange → red
		const heatColor = (val) => {
			const pct = Math.min((val / maxVal) * 100, 100);
			if (pct < 5) return "transparent";
			if (pct < 25) return `rgba(255, 193, 7, ${0.2 + (pct/25)*0.3})`;
			if (pct < 50) return `rgba(255, 152, 0, ${0.3 + ((pct-25)/25)*0.4})`;
			if (pct < 75) return `rgba(244, 67, 54, ${0.3 + ((pct-50)/25)*0.4})`;
			return `rgba(211, 47, 47, ${0.4 + ((pct-75)/25)*0.5})`;
		};

		const textColor = (val) => {
			const pct = Math.min((val / maxVal) * 100, 100);
			return pct > 50 ? "#fff" : "#333";
		};

		let html = `<table class="table table-sm table-bordered" style="margin:0; font-size:11px; white-space:nowrap;">
			<thead><tr style="background:#f5f6fa;">
				<th style="position:sticky; left:0; background:#f5f6fa; z-index:1;">${__("Driver")}</th>`;

		colLabels.forEach(l => { html += `<th class="text-right">${l}</th>`; });
		html += `<th class="text-right" style="background:#e8eaf6;">${__("Total")}</th></tr></thead><tbody>`;

		rows.forEach(row => {
			html += `<tr><td style="position:sticky; left:0; background:var(--card-bg);" class="font-weight-bold">${row.label}</td>`;
			(row.values || []).forEach(v => {
				html += `<td class="text-right" style="background:${heatColor(v)}; color:${textColor(v)};">${fmt(v)}</td>`;
			});
			html += `<td class="text-right font-weight-bold" style="background:#e8eaf6;">${fmt(row.total)}</td></tr>`;
		});

		if (colTotals.length) {
			html += `<tr style="background:#e8eaf6; font-weight:bold;">
				<td style="position:sticky; left:0; background:#e8eaf6;">${__("TOTAL")}</td>`;
			colTotals.forEach(t => { html += `<td class="text-right">${fmt(t)}</td>`; });
			html += `<td class="text-right">${fmt(pivot.grand_total)}</td></tr>`;
		}

		html += `</tbody></table>`;
		html += `<small class="text-muted mt-1 d-block">${__("Heatmap: white=low → red=high")}</small>`;
		container.html(html);
	};

	const render_ranking_bars = (container, pivot) => {
		const maxVal = pivot.max_value || 1;
		const rows = pivot.rows || [];

		let html = "";
		rows.forEach((row, i) => {
			const pct = row.pct || Math.min((row.total / maxVal) * 100, 100);
			const barColor = pct > 80 ? "#e74c3c" : pct > 50 ? "#e67e22" : pct > 25 ? "#f1c40f" : "#3498db";
			html += `
			<div class="mb-2">
				<div class="d-flex justify-content-between small mb-1">
					<span><b>${i+1}.</b> ${row.label}</span>
					<span class="font-weight-bold">SAR ${fmt(row.total)}</span>
				</div>
				<div style="background: #eee; border-radius: 4px; height: 6px;">
					<div style="width: ${pct}%; height: 6px; background: ${barColor}; border-radius: 4px;"></div>
				</div>
			</div>`;
		});
		container.html(html);
	};

	// ── DRIVER TABLE ──
	const render_driver_table = (breakdown) => {
		const container = page.main.find("#dash-driver-table-content");
		if (!breakdown || !breakdown.length) {
			container.html(`<div class="text-muted small text-center py-3">${__("No driver data")}</div>`);
			return;
		}
		let rows = breakdown.map((d, i) => `
			<tr>
				<td>${i+1}</td>
				<td class="font-weight-bold">${d.driver}</td>
				<td class="text-right">${d.trip_count}</td>
				<td class="text-right">${fmt(d.total_distance)}</td>
				<td class="text-right">SAR ${fmt(d.total_trip_value)}</td>
				<td class="text-right">SAR ${fmt(d.total_net)}</td>
				<td class="text-right" style="color:#e67e22;">SAR ${fmt(d.total_vat)}</td>
				<td class="text-right font-weight-bold">SAR ${fmt(d.grand_total)}</td>
				<td class="text-right">SAR ${fmt(d.avg_per_trip)}</td>
				<td class="text-right">${fmt(d.vat_pct)}%</td>
			</tr>
		`).join("");

		const html = `
		<table class="table table-sm table-hover" style="margin:0; font-size:12px;">
			<thead><tr class="text-muted">
				<th>#</th><th>${__("Driver")}</th>
				<th class="text-right">${__("Trips")}</th>
				<th class="text-right">${__("Km")}</th>
				<th class="text-right">${__("Trip Value")}</th>
				<th class="text-right">${__("Net")}</th>
				<th class="text-right">${__("VAT")}</th>
				<th class="text-right">${__("Grand Total")}</th>
				<th class="text-right">${__("Avg/Trip")}</th>
				<th class="text-right">${__("VAT%")}</th>
			</tr></thead>
			<tbody>${rows}</tbody>
		</table>`;
		container.html(html);
	};

	// ── INVOICES ──
	const render_invoices = (invoices) => {
		const container = page.main.find("#dash-invoice-table");
		if (!invoices || !invoices.length) {
			container.html(`<div class="text-muted small text-center py-3">${__("No invoices")}</div>`);
			return;
		}
		let rows = invoices.map(inv => `
			<tr>
				<td class="small"><a href="/app/trip-invoice/${inv.name}" target="_blank">${inv.name}</a></td>
				<td class="small">${frappe.datetime.str_to_user(inv.invoice_date) || ""}</td>
				<td class="small">${inv.driver || "-"}</td>
				<td class="small">${inv.vehicle || "-"}</td>
				<td class="small text-right">SAR ${fmt(inv.trip_value)}</td>
				<td class="small text-right">SAR ${fmt(inv.net_total)}</td>
				<td class="small text-right" style="color:#e67e22;">SAR ${fmt(inv.vat_amount)}</td>
				<td class="small text-right font-weight-bold">SAR ${fmt(inv.grand_total)}</td>
				<td class="small"><span class="badge badge-${inv.status==='Ready'?'success':inv.status==='Draft'?'warning':'secondary'}">${inv.status}</span></td>
			</tr>
		`).join("");

		const html = `
		<table class="table table-sm table-hover" style="margin:0; font-size:12px;">
			<thead><tr class="text-muted small">
				<th>${__("Invoice")}</th><th>${__("Date")}</th><th>${__("Driver")}</th><th>${__("Vehicle")}</th>
				<th class="text-right">${__("Trip Value")}</th><th class="text-right">${__("Net")}</th>
				<th class="text-right">${__("VAT")}</th><th class="text-right">${__("Grand Total")}</th><th>${__("Status")}</th>
			</tr></thead>
			<tbody>${rows}</tbody>
		</table>`;
		container.html(html);
	};

	// ── PRINT ──
	const show_print_dialog = () => {
		const data = page._raw_data;
		if (!data) { frappe.msgprint(__("Load data first.")); return; }

		const d = new frappe.ui.Dialog({
			title: __("Print Report"),
			fields: [
				{ label: __("Summary Cards"), fieldname: "inc_summary", fieldtype: "Check", default: 1 },
				{ label: __("Driver Breakdown"), fieldname: "inc_drivers", fieldtype: "Check", default: 1 },
				{ label: __("Pivot Table"), fieldname: "inc_pivot", fieldtype: "Check", default: 1 },
				{ label: __("Invoice List"), fieldname: "inc_invoices", fieldtype: "Check", default: 1 },
			],
			primary_action_label: __("Print"),
			primary_action(values) {
				let h = `<html><head><title>${__("VAT Analytics Report")}</title>
				<style>body{font-family:sans-serif;padding:20px;color:#333;}h2{color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px;}h4{color:#7f8c8d;margin-top:20px;}
				.summary-grid{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0;}
				.card{flex:1;min-width:130px;border:1px solid #ddd;border-left:3px solid #3498db;border-radius:6px;padding:12px;text-align:center;}
				.card .lbl{font-size:10px;color:#888;text-transform:uppercase;}.card .val{font-size:18px;font-weight:bold;}
				table{width:100%;border-collapse:collapse;margin:10px 0;font-size:11px;}
				th{background:#f5f6fa;padding:6px 8px;text-align:left;border-bottom:2px solid #ddd;}
				td{padding:5px 8px;border-bottom:1px solid #eee;}.tr{text-align:right;}
				</style></head><body>
				<h2>${__("Driver Performance & VAT Analytics")}</h2>
				<p>${data.filters?.month_label||""} | ${data.filters?.period||""} | ${data.filters?.driver||__("All Drivers")}</p>`;

				if (values.inc_summary && data.summary) {
					h += `<div class="summary-grid">${data.summary.map(s=>`<div class="card"><div class="lbl">${s.label}</div><div class="val">${s.value}</div></div>`).join("")}</div>`;
				}

				if (values.inc_drivers && data.driver_breakdown && data.driver_breakdown.length) {
					h += `<h4>${__("Driver Breakdown")}</h4><table><thead><tr>
						<th>#</th><th>${__("Driver")}</th><th class="tr">${__("Trips")}</th><th class="tr">${__("Km")}</th>
						<th class="tr">${__("Trip Value")}</th><th class="tr">${__("Net")}</th><th class="tr">${__("VAT")}</th><th class="tr">${__("Grand Total")}</th>
					</tr></thead><tbody>`;
					data.driver_breakdown.forEach((d,i)=>{h+=`<tr><td>${i+1}</td><td>${d.driver}</td><td class="tr">${d.trip_count}</td><td class="tr">${fmt(d.total_distance)}</td><td class="tr">SAR ${fmt(d.total_trip_value)}</td><td class="tr">SAR ${fmt(d.total_net)}</td><td class="tr">SAR ${fmt(d.total_vat)}</td><td class="tr">SAR ${fmt(d.grand_total)}</td></tr>`;});
					h += `</tbody></table>`;
				}

				if (values.inc_invoices && data.invoices && data.invoices.length) {
					h += `<h4>${__("Trip Invoices")} (${data.invoices.length})</h4><table><thead><tr>
						<th>${__("Invoice")}</th><th>${__("Date")}</th><th>${__("Driver")}</th>
						<th class="tr">${__("Trip Value")}</th><th class="tr">${__("Net")}</th><th class="tr">${__("VAT")}</th><th class="tr">${__("Grand Total")}</th>
					</tr></thead><tbody>`;
					data.invoices.forEach(inv=>{h+=`<tr><td>${inv.name}</td><td>${inv.invoice_date}</td><td>${inv.driver||"-"}</td><td class="tr">SAR ${fmt(inv.trip_value)}</td><td class="tr">SAR ${fmt(inv.net_total)}</td><td class="tr">SAR ${fmt(inv.vat_amount)}</td><td class="tr">SAR ${fmt(inv.grand_total)}</td></tr>`;});
					h += `</tbody></table>`;
				}

				h += `</body></html>`;
				const w = window.open("","_blank"); w.document.write(h); w.document.close();
				setTimeout(() => w.print(), 500); d.hide();
			},
		});
		d.show();
	};

	// ── EXPORT ──
	const export_csv = () => {
		const data = page._raw_data;
		if (!data || !data.invoices || !data.invoices.length) { frappe.msgprint(__("No data")); return; }
		const h = "Invoice,Date,Driver,Vehicle,Trip Value,Net,VAT,Grand Total,Status";
		let csv = h + "\n" + data.invoices.map(inv => [
			inv.name, inv.invoice_date, (inv.driver||"").replace(/,/g," "), (inv.vehicle||"").replace(/,/g," "),
			inv.trip_value||0, inv.net_total||0, inv.vat_amount||0, inv.grand_total||0, inv.status||"",
		].join(",")).join("\n");
		const blob = new Blob([csv], { type: "text/csv" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a"); a.href = url;
		a.download = `vat_analytics_${moment().format("YYYY-MM-DD")}.csv`;
		a.click(); URL.revokeObjectURL(url);
		frappe.show_alert({ message: __("CSV exported"), indicator: "green" });
	};

	const fmt = (val) => {
		const n = parseFloat(val) || 0;
		return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	};

	refresh_dashboard();
};
