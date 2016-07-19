
from __future__ import unicode_literals
import frappe
import json
import frappe.utils
from frappe.utils import cstr, flt, getdate, comma_and, cint
from frappe import _
from frappe.model.mapper import get_mapped_doc
from erpnext.stock.stock_balance import update_bin_qty, get_reserved_qty
from frappe.desk.notifications import clear_doctype_notifications
from erpnext.controllers.recurring_document import month_map, get_next_date

from erpnext.controllers.selling_controller import SellingController

@frappe.whitelist()
def make_delivery_note_cs(source_name=None, target_doc=None, item_code=None, test_list=None):
	test_list_json = json.loads(test_list)
	for source_name in test_list_json:
		def set_missing_values(source, target):
			if source.po_no:
				if target.po_no:
					target_po_no = target.po_no.split(", ")
					target_po_no.append(source.po_no)
					target.po_no = ", ".join(list(set(target_po_no))) if len(target_po_no) > 1 else target_po_no[0]
				else:
					target.po_no = source.po_no

			target.ignore_pricing_rule = 1
			target.run_method("set_missing_values")
			target.run_method("calculate_taxes_and_totals")

		def update_item(source, target, source_parent):
			target.base_amount = (flt(source.qty) - flt(source.delivered_qty)) * flt(source.base_rate)
			target.amount = (flt(source.qty) - flt(source.delivered_qty)) * flt(source.rate)
			target.qty = flt(source.qty) - flt(source.delivered_qty)

		target_doc = get_mapped_doc("Sales Order", source_name, {
		"Sales Order": {
			"doctype": "Delivery Note",
			"validation": {
				"docstatus": ["=", 1]
			}
		},
		"Sales Order Item": {
			"doctype": "Delivery Note Item",
			"field_map": {
				"rate": "rate",
				"name": "so_detail",
				"parent": "against_sales_order",
			},
			"postprocess": update_item,
			"condition": lambda doc: abs(doc.delivered_qty) < abs(doc.qty) and doc.delivered_by_supplier!=1 and doc.item_code==item_code
		},
		"Sales Taxes and Charges": {
			"doctype": "Sales Taxes and Charges",
			"add_if_empty": True
		},
		"Sales Team": {
			"doctype": "Sales Team",
			"add_if_empty": True
		},
	}, target_doc, set_missing_values)

	return target_doc

@frappe.whitelist()
def make_purchase_receipt(source_name=None, target_doc=None, item_code=None, test_list=None):
	test_list_json = json.loads(test_list)
	for source_name in test_list_json:
		def set_missing_values(source, target):
			target.ignore_pricing_rule = 1
			target.run_method("set_missing_values")
			target.run_method("calculate_taxes_and_totals")

		def update_item(obj, target, source_parent):
			target.qty = flt(obj.qty) - flt(obj.received_qty)
			target.stock_qty = (flt(obj.qty) - flt(obj.received_qty)) * flt(obj.conversion_factor)
			target.amount = (flt(obj.qty) - flt(obj.received_qty)) * flt(obj.rate)
			target.base_amount = (flt(obj.qty) - flt(obj.received_qty)) * \
				flt(obj.rate) * flt(source_parent.conversion_rate)

		target_doc = get_mapped_doc("Purchase Order", source_name,	{
			"Purchase Order": {
				"doctype": "Purchase Receipt",
				"validation": {
					"docstatus": ["=", 1],
				}
			},
			"Purchase Order Item": {
				"doctype": "Purchase Receipt Item",
				"field_map": {
					"name": "prevdoc_detail_docname",
					"parent": "prevdoc_docname",
					"parenttype": "prevdoc_doctype",
				},
				"postprocess": update_item,
				"condition": lambda doc: abs(doc.received_qty) < abs(doc.qty) and doc.delivered_by_supplier!=1 and doc.item_code==item_code
			},
			"Purchase Taxes and Charges": {
				"doctype": "Purchase Taxes and Charges",
				"add_if_empty": True
			}
	}, target_doc, set_missing_values)

	return target_doc


@frappe.whitelist()
def make_delivery_note(source_name, target_doc=None, item_code=None, test_list=None):
	def set_missing_values(source, target):
		if source.po_no:
			if target.po_no:
				target_po_no = target.po_no.split(", ")
				target_po_no.append(source.po_no)
				target.po_no = ", ".join(list(set(target_po_no))) if len(target_po_no) > 1 else target_po_no[0]
			else:
				target.po_no = source.po_no

		target.ignore_pricing_rule = 1
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	def update_item(source, target, source_parent):
		target.base_amount = (flt(source.qty) - flt(source.delivered_qty)) * flt(source.base_rate)
		target.amount = (flt(source.qty) - flt(source.delivered_qty)) * flt(source.rate)
		target.qty = flt(source.qty) - flt(source.delivered_qty)

	target_doc = get_mapped_doc("Sales Order", source_name, {
		"Sales Order": {
			"doctype": "Delivery Note",
			"validation": {
				"docstatus": ["=", 1]
			}
		},
		"Sales Order Item": {
			"doctype": "Delivery Note Item",
			"field_map": {
				"rate": "rate",
				"name": "so_detail",
				"parent": "against_sales_order",
			},
			"postprocess": update_item,
			"condition": lambda doc: abs(doc.delivered_qty) < abs(doc.qty) and doc.delivered_by_supplier!=1 and doc.item_code==item_code
		},
		"Sales Taxes and Charges": {
			"doctype": "Sales Taxes and Charges",
			"add_if_empty": True
		},
		"Sales Team": {
			"doctype": "Sales Team",
			"add_if_empty": True
		},
	}, target_doc, set_missing_values)

	frappe.msgprint(target_doc)
	return target_doc

@frappe.whitelist()
def get_so_details(item_code,customer):
	if not customer:
		frappe.throw("Please select Customer")

	return {
	"get_test_data": frappe.db.sql("""select so.name, si.qty, si.rate, si.delivered_qty, so.delivery_date, si.stock_uom, c.symbol, si.item_code 
		from `tabSales Order` as so, `tabSales Order Item` si, tabCurrency c 
		where si.parent=so.name and c.name=so.currency and so.docstatus=1 and so.customer='%s' and si.item_code='%s' and si.delivered_qty<si.qty order by so.delivery_date"""%(customer,item_code), as_list=1)
	}

@frappe.whitelist()
def get_po_details(item_code,supplier):
	if not supplier:
		frappe.throw("Please select Supplier")

	return {
	"get_test_data": frappe.db.sql("""select po.name, pi.qty, pi.rate, ( pi.qty - pi.received_qty), po.transaction_date, pi.stock_uom, pi.item_code 
		from `tabPurchase Order` as po, `tabPurchase Order Item` pi, tabCurrency c 
		where pi.parent=po.name and c.name=po.currency and po.docstatus=1 and po.supplier='%s' and pi.item_code='%s' and pi.received_qty<pi.qty order by po.transaction_date"""%(supplier,item_code), as_list=1)
	}




@frappe.whitelist()	
def get_items_from_production_order(item_code):
	return frappe.db.sql("""select t1.item_code,t1.description,t2.name,date_format(t2.planned_start_date,'%d-%m-%Y') as date,
							(t2.qty - t2.custom_manufactured_qty - t2.produced_qty) as qty 
							from `tabItem`t1,`tabProduction Order`t2 
							where t1.item_code = '{0}' and t2.name in (select name from `tabProduction Order` where production_item = '{0}') 
							order by date asc""".format(item_code),as_dict=1)
# def get_items_from_production_order(production_order):
# 	return frappe.db.sql("""select t1.item_code,t1.description,t2.name,date_format(t2.planned_start_date,'%d-%m-%Y') as date,
# 							(t2.qty - t2.custom_manufactured_qty - t2.produced_qty) as qty 
# 							from `tabItem`t1,`tabProduction Order`t2 
# 							where t1.item_code = t2.production_item 
# 							and t2.name ='{0}' order by date asc""".format(production_order),as_dict=1,debug=1)

@frappe.whitelist()	
def get_items_from_po(supplier,item_code):
	return frappe.db.sql("""select t1.item_code,t1.description,t2.name,(t1.qty - t1.received_qty) as qty,
							t1.price_list_rate,((t1.qty - t1.received_qty) * t1.price_list_rate) as amount,t2.transaction_date
							from `tabPurchase Order Item`t1 ,`tabPurchase Order`t2 
							where t1.parent = t2.name and t2.supplier = "{0}" 
							and t1.item_code = "{1}" and t2.docstatus = 1  order by t2.transaction_date asc """.format(supplier,item_code),as_dict=1)

# @frappe.whitelist()	
# def update_custom_received_qty(update_po):
# 	update_po = json.loads(update_po)
# 	for i in update_po:
# 		change_custom_received_qty(i['purchase_order'],i['item_code'],i['qty'])
		
# def change_custom_received_qty(purchase_order,item_code,qty):
# 	purchase_order = frappe.get_doc("Purchase Order",purchase_order)
# 	for row in purchase_order.items:
# 		if row.item_code == item_code:
# 			row.custom_received_qty = row.custom_received_qty + qty
# 			row.save(ignore_permissions = True)

@frappe.whitelist()
def update_custom_manufactured_qty(update_production_order):
	update_production_order = json.loads(update_production_order)
	for i in update_production_order:
		change_custom_manufactured_qty(i['production_order'],i['item_code'],i['qty'])
		
def change_custom_manufactured_qty(production_order,item_code,qty):
	production_order = frappe.get_doc("Production Order",production_order)
	if item_code == production_order.production_item:
		production_order.custom_manufactured_qty = production_order.custom_manufactured_qty + qty
		production_order.total_manufactured_qty = production_order.custom_manufactured_qty + production_order.produced_qty
		production_order.save(ignore_permissions = True)


def filter_items(doctype, txt, searchfield, start, page_len, filters):
	print filters['supplier']
	return frappe.db.sql("""select item_code,item_name from `tabPurchase Order Item`t1,
							`tabPurchase Order`t2 where t1.parent = t2.name 
							and t2.supplier = '{0}' and t2.docstatus = 1
							and (item_name like '{txt}' or item_code like '{txt}' )limit 20""".format(filters['supplier'],txt= "%%%s%%" % txt),as_list=1)


def filter_production_items(doctype, txt, searchfield, start, page_len, filters):
	return frappe.db.sql("""select distinct production_item from `tabProduction Order`
							where production_item like '{txt}' limit 20""".format(txt= "%%%s%%" % txt),as_list=1)	





@frappe.whitelist()
def get_format_list(naming_series):
	print naming_series
	if naming_series == "SINV-":	
		return 'Sales SINV'
	if naming_series == "SINV-RET-":	
		return 'Sales RET'


@frappe.whitelist()
def make_new_po(source_name, target_doc=None):
	print source_name

	target_doc = get_mapped_doc("Purchase Order", source_name,
		{
			"Purchase Order": {
				"doctype": "Purchase Order",
			},
		}, target_doc)
	
	target_doc.parent_name = source_name
	return target_doc

@frappe.whitelist()
def update_parent_po(po):
	po = frappe.get_doc("Purchase Order",po)
	if not po.po_closed:
		po.update({
			"po_closed":"Yes"
			})
		po.save(ignore_permissions=True)
	return "parent po updated"		
