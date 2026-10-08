frappe.pages['peta-gudang'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Warehouse Layout',
		single_column: true,
	});

	new WarehouseLayout(page);
};

class WarehouseLayout {
	constructor(page) {
		this.page = page;
		this.zones = [];
		this.canvas_width = 1100;
		this.canvas_height = 650;

		this.make_warehouse_selector();
		this.make_toolbar();
		this.make_canvas();
	}

	make_warehouse_selector() {
		this.warehouse_field = this.page.add_field({
			fieldtype: 'Link',
			fieldname: 'warehouse',
			label: 'Warehouse',
			options: 'Warehouse',
			change: () => this.load_zones(),
		});
	}

	make_toolbar() {
		this.page.add_inner_button('+ Add Zone', () => this.add_zone());
		this.save_btn = this.page.set_primary_action('Save Layout', () => this.save_all(), 'octicon octicon-check');
	}

	make_canvas() {
		this.$wrapper = $(
			`<div class="warehouse-layout-canvas-wrapper" style="border:1px solid var(--border-color); border-radius: 8px; overflow:hidden; margin-top: 15px; background: #fff; position: relative; max-width: ${this.canvas_width}px;">
				<div class="warehouse-layout-empty-state text-muted" style="padding: 60px 20px; text-align:center; display:none;">
					Select a Warehouse to start mapping zones/racks.
				</div>
				<svg class="warehouse-layout-svg" viewBox="0 0 ${this.canvas_width} ${this.canvas_height}" preserveAspectRatio="xMinYMin meet" style="display:block; width:100%; height:auto; background:#fafbfc;"></svg>
			</div>`
		).appendTo(this.page.main);
		this.svg = this.$wrapper.find('svg')[0];
		this.$empty_state = this.$wrapper.find('.warehouse-layout-empty-state');
		this.toggle_empty_state(true);
	}

	clamp_zone(zone) {
		zone.width = Math.min(Math.max(30, zone.width), this.canvas_width);
		zone.height = Math.min(Math.max(30, zone.height), this.canvas_height);
		zone.pos_x = Math.min(Math.max(0, zone.pos_x), this.canvas_width - zone.width);
		zone.pos_y = Math.min(Math.max(0, zone.pos_y), this.canvas_height - zone.height);
	}

	toggle_empty_state(show) {
		this.$empty_state.toggle(!!show);
		$(this.svg).toggle(!show);
	}

	load_zones() {
		const warehouse = this.warehouse_field.get_value();
		this.zones = [];
		this.render();

		if (!warehouse) {
			this.toggle_empty_state(true);
			return;
		}
		this.toggle_empty_state(false);

		frappe.dom.freeze(__('Loading layout...'));
		frappe.db
			.get_list('Warehouse Layout Zone', {
				filters: { warehouse },
				fields: [
					'name',
					'zone_name',
					'zone_code',
					'linked_warehouse',
					'pos_x',
					'pos_y',
					'width',
					'height',
					'color',
					'notes',
				],
				limit_page_length: 0,
			})
			.then((rows) => {
				frappe.dom.unfreeze();
				this.zones = rows || [];
				this.render();
			})
			.catch(() => {
				frappe.dom.unfreeze();
			});
	}

	render() {
		this.svg.innerHTML = '';
		this.zones.forEach((zone) => this.render_zone(zone));
	}

	render_zone(zone) {
		const ns = 'http://www.w3.org/2000/svg';

		const g = document.createElementNS(ns, 'g');
		g.setAttribute('class', 'wlz-group');
		g.style.cursor = 'move';

		const rect = document.createElementNS(ns, 'rect');
		rect.setAttribute('x', zone.pos_x || 0);
		rect.setAttribute('y', zone.pos_y || 0);
		rect.setAttribute('width', zone.width || 100);
		rect.setAttribute('height', zone.height || 60);
		rect.setAttribute('fill', zone.color || '#d1e7ff');
		rect.setAttribute('stroke', '#4a5568');
		rect.setAttribute('stroke-width', '1.5');
		rect.setAttribute('rx', 6);
		g.appendChild(rect);

		const text = document.createElementNS(ns, 'text');
		text.setAttribute('x', (zone.pos_x || 0) + (zone.width || 100) / 2);
		text.setAttribute('y', (zone.pos_y || 0) + (zone.height || 60) / 2 - (zone.linked_warehouse ? 7 : 0));
		text.setAttribute('text-anchor', 'middle');
		text.setAttribute('dominant-baseline', 'middle');
		text.setAttribute('font-size', '13');
		text.setAttribute('font-weight', '600');
		text.setAttribute('fill', '#1f2937');
		text.setAttribute('pointer-events', 'none');
		text.textContent = zone.zone_name;
		g.appendChild(text);

		let subtext = null;
		if (zone.linked_warehouse) {
			subtext = document.createElementNS(ns, 'text');
			subtext.setAttribute('x', (zone.pos_x || 0) + (zone.width || 100) / 2);
			subtext.setAttribute('y', (zone.pos_y || 0) + (zone.height || 60) / 2 + 10);
			subtext.setAttribute('text-anchor', 'middle');
			subtext.setAttribute('dominant-baseline', 'middle');
			subtext.setAttribute('font-size', '10');
			subtext.setAttribute('fill', '#4b5563');
			subtext.setAttribute('pointer-events', 'none');
			subtext.textContent = zone.linked_warehouse;
			g.appendChild(subtext);
		}

		const handle = document.createElementNS(ns, 'rect');
		handle.setAttribute('width', 12);
		handle.setAttribute('height', 12);
		handle.setAttribute('x', (zone.pos_x || 0) + (zone.width || 100) - 12);
		handle.setAttribute('y', (zone.pos_y || 0) + (zone.height || 60) - 12);
		handle.setAttribute('fill', '#4a5568');
		handle.setAttribute('class', 'wlz-resize-handle');
		handle.style.cursor = 'nwse-resize';
		g.appendChild(handle);

		this.make_interactive(g, rect, subtext ? [text, subtext] : [text], handle, zone);

		g.addEventListener('dblclick', (e) => {
			e.stopPropagation();
			this.edit_zone(zone);
		});

		this.svg.appendChild(g);
	}

	make_interactive(g, rect, texts, handle, zone) {
		let mode = null;
		let start = {};

		const start_move = (e) => {
			mode = 'move';
			start = { x: e.clientX, y: e.clientY, ox: zone.pos_x || 0, oy: zone.pos_y || 0 };
			e.stopPropagation();
			e.preventDefault();
		};
		const start_resize = (e) => {
			mode = 'resize';
			start = { x: e.clientX, y: e.clientY, ow: zone.width || 100, oh: zone.height || 60 };
			e.stopPropagation();
			e.preventDefault();
		};

		rect.addEventListener('mousedown', start_move);
		texts.forEach((t) => t && t.addEventListener('mousedown', start_move));
		handle.addEventListener('mousedown', start_resize);

		const svg_scale = () => this.svg.getBoundingClientRect().width / this.canvas_width || 1;

		const on_move = (e) => {
			if (!mode) return;
			const scale = svg_scale();
			const dx = (e.clientX - start.x) / scale;
			const dy = (e.clientY - start.y) / scale;

			if (mode === 'move') {
				zone.pos_x = Math.round(start.ox + dx);
				zone.pos_y = Math.round(start.oy + dy);
			} else if (mode === 'resize') {
				zone.width = Math.round(start.ow + dx);
				zone.height = Math.round(start.oh + dy);
			}
			this.clamp_zone(zone);
			zone.__dirty = true;
			this.update_zone_dom(rect, texts, handle, zone);
		};
		const on_up = () => {
			mode = null;
		};

		document.addEventListener('mousemove', on_move);
		document.addEventListener('mouseup', on_up);

		// keep references so listeners can be cleaned up if needed later
		zone.__listeners = { on_move, on_up };
	}

	update_zone_dom(rect, texts, handle, zone) {
		rect.setAttribute('x', zone.pos_x);
		rect.setAttribute('y', zone.pos_y);
		rect.setAttribute('width', zone.width);
		rect.setAttribute('height', zone.height);
		const cx = zone.pos_x + zone.width / 2;
		const cy = zone.pos_y + zone.height / 2;
		if (texts[0]) {
			texts[0].setAttribute('x', cx);
			texts[0].setAttribute('y', cy - (zone.linked_warehouse ? 7 : 0));
		}
		if (texts[1]) {
			texts[1].setAttribute('x', cx);
			texts[1].setAttribute('y', cy + 10);
		}
		handle.setAttribute('x', zone.pos_x + zone.width - 12);
		handle.setAttribute('y', zone.pos_y + zone.height - 12);
	}

	get_child_warehouse_filters(warehouse) {
		return { parent_warehouse: warehouse };
	}

	add_zone() {
		const warehouse = this.warehouse_field.get_value();
		if (!warehouse) {
			frappe.msgprint(__('Please select a Warehouse first.'));
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __('Add Zone'),
			fields: [
				{ fieldtype: 'Data', fieldname: 'zone_name', label: 'Zone Name', reqd: 1 },
				{ fieldtype: 'Data', fieldname: 'zone_code', label: 'Code (optional)' },
				{
					fieldtype: 'Link',
					fieldname: 'linked_warehouse',
					label: 'Child Warehouse (optional)',
					options: 'Warehouse',
					get_query: () => ({ filters: this.get_child_warehouse_filters(warehouse) }),
					onchange: () => {
						const wh = d.get_value('linked_warehouse');
						if (wh && !d.get_value('zone_name')) {
							d.set_value('zone_name', wh);
						}
					},
				},
				{ fieldtype: 'Color', fieldname: 'color', label: 'Color', default: '#d1e7ff' },
			],
			primary_action_label: __('Add'),
			primary_action: (values) => {
				frappe.dom.freeze();
				frappe.db
					.insert({
						doctype: 'Warehouse Layout Zone',
						warehouse: warehouse,
						zone_name: values.zone_name,
						zone_code: values.zone_code,
						linked_warehouse: values.linked_warehouse,
						color: values.color,
						pos_x: 20,
						pos_y: 20,
						width: 120,
						height: 70,
					})
					.then(() => {
						frappe.dom.unfreeze();
						d.hide();
						this.load_zones();
					})
					.catch(() => {
						frappe.dom.unfreeze();
					});
			},
		});
		d.show();
	}

	edit_zone(zone) {
		const warehouse = this.warehouse_field.get_value();
		const d = new frappe.ui.Dialog({
			title: __('Edit Zone'),
			fields: [
				{ fieldtype: 'Data', fieldname: 'zone_name', label: 'Zone Name', default: zone.zone_name, reqd: 1 },
				{ fieldtype: 'Data', fieldname: 'zone_code', label: 'Code', default: zone.zone_code },
				{
					fieldtype: 'Link',
					fieldname: 'linked_warehouse',
					label: 'Child Warehouse (optional)',
					options: 'Warehouse',
					default: zone.linked_warehouse,
					get_query: () => ({ filters: this.get_child_warehouse_filters(warehouse) }),
				},
				{ fieldtype: 'Color', fieldname: 'color', label: 'Color', default: zone.color },
				{ fieldtype: 'Small Text', fieldname: 'notes', label: 'Notes', default: zone.notes },
			],
			primary_action_label: __('Save'),
			primary_action: (values) => {
				Object.assign(zone, values);
				zone.__dirty = true;
				this.render();
				d.hide();
			},
			secondary_action_label: __('Delete Zone'),
			secondary_action: () => {
				frappe.confirm(__('Delete zone "{0}"? This cannot be undone.', [zone.zone_name]), () => {
					frappe.dom.freeze();
					frappe.db
						.delete_doc('Warehouse Layout Zone', zone.name)
						.then(() => {
							frappe.dom.unfreeze();
							d.hide();
							this.load_zones();
						})
						.catch(() => {
							frappe.dom.unfreeze();
						});
				});
			},
		});
		d.show();
	}

	save_all() {
		const dirty = this.zones.filter((z) => z.__dirty);
		if (!dirty.length) {
			frappe.show_alert({ message: __('No changes to save'), indicator: 'blue' });
			return;
		}
		frappe.dom.freeze(__('Saving layout...'));
		Promise.all(
			dirty.map((z) =>
				frappe.db.set_value('Warehouse Layout Zone', z.name, {
					pos_x: z.pos_x,
					pos_y: z.pos_y,
					width: z.width,
					height: z.height,
					zone_name: z.zone_name,
					zone_code: z.zone_code,
					linked_warehouse: z.linked_warehouse,
					color: z.color,
					notes: z.notes,
				})
			)
		)
			.then(() => {
				frappe.dom.unfreeze();
				this.zones.forEach((z) => (z.__dirty = false));
				frappe.show_alert({ message: __('Layout saved'), indicator: 'green' });
			})
			.catch(() => {
				frappe.dom.unfreeze();
				frappe.msgprint(__('Failed to save some/all zones. Please try again.'));
			});
	}
}
