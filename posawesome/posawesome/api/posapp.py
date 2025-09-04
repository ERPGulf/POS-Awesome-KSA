# -*- coding: utf-8 -*-
# Copyright (c) 2020, Youssef Restom and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import json
import frappe
from frappe.utils import cint
from frappe.utils import nowdate, flt, cstr, getdate
from frappe import _
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.stock.get_item_details import get_item_details
from erpnext.accounts.doctype.pos_profile.pos_profile import get_item_groups
from frappe.utils.background_jobs import enqueue
from erpnext.accounts.party import get_party_bank_account
from erpnext.stock.doctype.batch.batch import (
    get_batch_no,
    get_batch_qty,
)
from erpnext.accounts.doctype.payment_request.payment_request import (
    get_dummy_message,
    get_existing_payment_request_amount,
)

from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
    get_loyalty_program_details_with_points,
)
from posawesome.posawesome.doctype.pos_coupon.pos_coupon import check_coupon_code
from posawesome.posawesome.doctype.delivery_charges.delivery_charges import (
    get_applicable_delivery_charges as _get_applicable_delivery_charges,
)
from frappe.utils.caching import redis_cache


@frappe.whitelist()
def get_opening_dialog_data():
    data = {}
    data["companies"] = frappe.get_list("Company", limit_page_length=0, order_by="name")
    data["pos_profiles_data"] = frappe.get_list(
        "POS Profile",
        filters={"disabled": 0},
        fields=["name", "company", "currency"],
        limit_page_length=0,
        order_by="name",
    )

    pos_profiles_list = []
    for i in data["pos_profiles_data"]:
        pos_profiles_list.append(i.name)

    payment_method_table = (
        "POS Payment Method" if get_version() == 13 else "Sales Invoice Payment"
    )
    data["payments_method"] = frappe.get_list(
        payment_method_table,
        filters={"parent": ["in", pos_profiles_list]},
        fields=["*"],
        limit_page_length=0,
        order_by="parent",
        ignore_permissions=True,
    )
    # set currency from pos profile
    for mode in data["payments_method"]:
        mode["currency"] = frappe.get_cached_value(
            "POS Profile", mode["parent"], "currency"
        )

    return data


@frappe.whitelist()
def create_opening_voucher(pos_profile, company, balance_details):
    balance_details = json.loads(balance_details)

    new_pos_opening = frappe.get_doc(
        {
            "doctype": "POS Opening Shift",
            "period_start_date": frappe.utils.get_datetime(),
            "posting_date": frappe.utils.getdate(),
            "user": frappe.session.user,
            "pos_profile": pos_profile,
            "company": company,
            "docstatus": 1,
        }
    )
    new_pos_opening.set("balance_details", balance_details)
    new_pos_opening.insert(ignore_permissions=True)

    data = {}
    data["pos_opening_shift"] = new_pos_opening.as_dict()
    update_opening_shift_data(data, new_pos_opening.pos_profile)
    return data


@frappe.whitelist()
def check_opening_shift(user):
    # frappe.log_error("check_opening_shift user", user)
    open_vouchers = frappe.db.get_all(
        "POS Opening Shift",
        filters={
            "user": user,
            "pos_closing_shift": ["in", ["", None]],
            "docstatus": 1,
            "status": "Open",
        },
        fields=["name", "pos_profile"],
        order_by="period_start_date desc",
    )
    data = ""
    if len(open_vouchers) > 0:
        data = {}
        data["pos_opening_shift"] = frappe.get_doc(
            "POS Opening Shift", open_vouchers[0]["name"]
        )
        update_opening_shift_data(data, open_vouchers[0]["pos_profile"])
    # frappe.log_error("check_opening_shift data", data)
    return data

# @frappe.whitelist()
# def check_opening_shift(user):
#     open_vouchers = frappe.db.get_all(
#         "POS Opening Shift",
#         filters={
#             "user": user,
#             "pos_closing_shift": ["in", ["", None]],
#             "docstatus": 1,
#             "status": "Open",
#         },
#         fields=["name", "pos_profile"],
#         order_by="period_start_date desc",
#     )

#     if open_vouchers:
#         data = {
#             "pos_opening_shift": frappe.get_doc(
#                 "POS Opening Shift", open_vouchers[0]["name"]
#             )
#         }
#         update_opening_shift_data(data, open_vouchers[0]["pos_profile"])
#         return data

#     # return None if no open shift
#     return None



def update_opening_shift_data(data, pos_profile):
    data["pos_profile"] = frappe.get_doc("POS Profile", pos_profile)
    data["company"] = frappe.get_doc("Company", data["pos_profile"].company)
    allow_negative_stock = frappe.get_value(
        "Stock Settings", None, "allow_negative_stock"
    )
    data["stock_settings"] = {}
    data["stock_settings"].update({"allow_negative_stock": allow_negative_stock})

@frappe.whitelist()
def get_items(
    pos_profile, price_list=None, item_group="", search_value="", customer=None
):

    _pos_profile = json.loads(pos_profile)
    ttl = _pos_profile.get("posa_server_cache_duration")
    if ttl:
        ttl = int(ttl) * 30

    @redis_cache(ttl=ttl or 1800)
    def __get_items(pos_profile, price_list, item_group, search_value, customer=None):
        return _get_items(pos_profile, price_list, item_group, search_value, customer)

    def _get_items(pos_profile, price_list, item_group, search_value, customer=None):
        pos_profile = json.loads(pos_profile)
        today = nowdate()
        data = dict()
        posa_display_items_in_stock = pos_profile.get("posa_display_items_in_stock")
        search_serial_no = pos_profile.get("posa_search_serial_no")
        search_batch_no = pos_profile.get("posa_search_batch_no")
        posa_show_template_items = pos_profile.get("posa_show_template_items")
        warehouse = pos_profile.get("warehouse")
        use_limit_search = pos_profile.get("pose_use_limit_search")
        search_limit = 0

        if not price_list:
            price_list = pos_profile.get("selling_price_list")

        limit = ""

        condition = ""
        condition += get_item_group_condition(pos_profile.get("name"))

        if use_limit_search:
            search_limit = pos_profile.get("posa_search_limit") or 500
            if search_value:
                data = search_serial_or_batch_or_barcode_number(
                    search_value, search_serial_no
                )

            item_code = data.get("item_code") if data.get("item_code") else search_value
            serial_no = data.get("serial_no") if data.get("serial_no") else ""
            batch_no = data.get("batch_no") if data.get("batch_no") else ""
            barcode = data.get("barcode") if data.get("barcode") else ""

            condition += get_seearch_items_conditions(
                item_code, serial_no, batch_no, barcode
            )
            if item_group:
                condition += " AND item_group like '%{item_group}%'".format(
                    item_group=item_group
                )
            limit = " LIMIT {search_limit}".format(search_limit=search_limit)

        if not posa_show_template_items:
            condition += " AND has_variants = 0"

        result = []

        items_data = frappe.db.sql(
            """
            SELECT
                name AS item_code,
                item_name,
                description,
                stock_uom,
                image,
                is_stock_item,
                has_variants,
                variant_of,
                item_group,
                idx as idx,
                has_batch_no,
                has_serial_no,
                max_discount,
                brand
            FROM
                `tabItem`
            WHERE
                disabled = 0
                    AND is_sales_item = 1
                    AND is_fixed_asset = 0
                    {condition}
            ORDER BY
                item_name asc
            {limit}
            """.format(
                condition=condition, limit=limit
            ),
            as_dict=1,
        )

        item_codes = [item["item_code"] for item in items_data]

        if item_codes:
            alternative_links = frappe.db.sql(
                """
                SELECT DISTINCT alternative_item_code
                FROM `tabItem Alternative`
                WHERE item_code IN %(item_codes)s
                """,
                {"item_codes": item_codes},
                as_dict=1,
            )
        else:
            alternative_links = []

        alternative_item_codes = [link["alternative_item_code"] for link in alternative_links]

        alternative_items_data = []

        if alternative_item_codes:
            alternative_items_data = frappe.db.sql(
                """
                SELECT
                    name AS item_code,
                    item_name,
                    description,
                    stock_uom,
                    image,
                    is_stock_item,
                    has_variants,
                    variant_of,
                    item_group,
                    idx as idx,
                    has_batch_no,
                    has_serial_no,
                    max_discount,
                    brand
                FROM
                    `tabItem`
                WHERE
                    name IN %(alternative_items)s
                """,
                {"alternative_items": alternative_item_codes},
                as_dict=1,
            )

        items_data += alternative_items_data

        unique_items = {item["item_code"]: item for item in items_data}
        items_data = list(unique_items.values())

        if items_data:
            items = [d.item_code for d in items_data]
            # wholesale_rate_field = _pos_profile.get("custom_wholesale_rate") or "wholesale_rate"
            item_prices_data = frappe.get_all(
                "Item Price",
                fields=["item_code", "price_list_rate", "currency", "uom"],
                filters={
                    "price_list": price_list,
                    "item_code": ["in", items],
                    "currency": pos_profile.get("currency"),
                    "selling": 1,
                    "valid_from": ["<=", today],
                    "customer": ["in", ["", None, customer]],
                },
                or_filters=[
                    ["valid_upto", ">=", today],
                    ["valid_upto", "in", ["", None]],
                ],
                order_by="valid_from ASC, valid_upto DESC",
            )
            # frappe.log_error("Wholesale Rate", item_prices_data)

            item_prices = {}
            for d in item_prices_data:
                item_prices.setdefault(d.item_code, {})
                item_prices[d.item_code][d.get("uom") or "None"] = d

            # 🔥🔥🔥 Add POS Profile Logic Here
            # wholesale_profiles = [
            #     "Wholesale POS",
            #     "Wholesale - Western",
            #     "Wholesale - Eastern",
            #     "Wholesale - Central",
            #     "Orange Station POS",
            #     "Wholesale Central 2 POS"
            # ]

            for item in items_data:
                item_code = item.item_code
                # item_manufacturer_part_no = item.manufacturer_part_no
                item_price = {}
                if item_prices.get(item_code):
                    item_price = (
                        item_prices.get(item_code).get(item.stock_uom)
                        or item_prices.get(item_code).get("None")
                        or {}
                    )
                item_barcode = frappe.get_all(
                    "Item Barcode",
                    filters={"parent": item_code},
                    fields=["barcode", "posa_uom"],
                )

                batch_no_data = []
                if search_batch_no:
                    batch_list = get_batch_qty(warehouse=warehouse, item_code=item_code)
                    if batch_list:
                        for batch in batch_list:
                            if batch.qty > 0 and batch.batch_no:
                                batch_doc = frappe.get_cached_doc(
                                    "Batch", batch.batch_no
                                )
                                if (
                                    str(batch_doc.expiry_date) > str(today)
                                    or batch_doc.expiry_date in ["", None]
                                ) and batch_doc.disabled == 0:
                                    batch_no_data.append(
                                        {
                                            "batch_no": batch.batch_no,
                                            "batch_qty": batch.qty,
                                            "expiry_date": batch_doc.expiry_date,
                                            "batch_price": batch_doc.posa_batch_price,
                                            "manufacturing_date": batch_doc.manufacturing_date,
                                        }
                                    )

                serial_no_data = []
                if search_serial_no:
                    serial_no_data = frappe.get_all(
                        "Serial No",
                        filters={
                            "item_code": item_code,
                            "status": "Active",
                            "warehouse": warehouse,
                        },
                        fields=["name as serial_no"],
                    )

                alternative_items = frappe.get_all(
                    "Item Alternative",
                    filters={"item_code": item_code},
                    fields=["alternative_item_code"],
                ) or []

                item_stock_qty = 0
                if pos_profile.get("posa_display_items_in_stock") or use_limit_search:
                    item_stock_qty = get_stock_availability(
                        item_code, pos_profile.get("warehouse")
                    )

                attributes = ""
                if pos_profile.get("posa_show_template_items") and item.has_variants:
                    attributes = get_item_attributes(item.item_code)

                item_attributes = ""
                if pos_profile.get("posa_show_template_items") and item.variant_of:
                    item_attributes = frappe.get_all(
                        "Item Variant Attribute",
                        fields=["attribute", "attribute_value"],
                        filters={"parent": item.item_code, "parentfield": "attributes"},
                    )

                if posa_display_items_in_stock and (not item_stock_qty or item_stock_qty < 0):
                    pass
                else:
                    # 👇👇 Correct rate selection depending on POS profile
                    # if pos_profile.get("name") in wholesale_profiles:
                    #     wholesale_rate = _pos_profile.get("custom_wholesale_rate") or "wholesale_rate"
                    #     item_pos_rate = item_price.get(wholesale_rate) or 0
                    # else:
                    item_pos_rate = item_price.get("price_list_rate") or 0

                    row = {}
                    row.update(item)
                    row.update(
                        {
                            "rate": item_pos_rate,
                            "currency": item_price.get("currency") or pos_profile.get("currency"),
                            "item_barcode": item_barcode or [],
                            "actual_qty": item_stock_qty or 0,
                            "serial_no_data": serial_no_data or [],
                            "batch_no_data": batch_no_data or [],
                            "attributes": attributes or "",
                            "item_attributes": item_attributes or "",
                            # "item_manufacturer_part_no": item_manufacturer_part_no or "",
                            "alternative_items": alternative_items or [],
                        }
                    )
                    # Get all wholesale rates from item_price
                    # item_wholesale_rate = item_price.get("wholesale_rate") or 0
                    # item_wholesale_rate2 = item_price.get("wholesale_rate2") or 0
                    # item_wholesale_rate3 = item_price.get("wholesale_rate3") or 0

                    row.update({
                        "rate": item_pos_rate,
                        # "wholesale_rate": item_wholesale_rate,
                        # "wholesale_rate2": item_wholesale_rate2,
                        # "wholesale_rate3": item_wholesale_rate3,
                    })

                    result.append(row)

        # frappe.log_error("✅ Final result", result)
        return result

    if _pos_profile.get("posa_use_server_cache"):
        return __get_items(pos_profile, price_list, item_group, search_value, customer)
    else:
        return _get_items(pos_profile, price_list, item_group, search_value, customer)

def get_item_group_condition(pos_profile):
    cond = " and 1=1"
    item_groups = get_item_groups(pos_profile)
    if item_groups:
        cond = " and item_group in (%s)" % (", ".join(["%s"] * len(item_groups)))

    return cond % tuple(item_groups)


def get_root_of(doctype):
    """Get root element of a DocType with a tree structure"""
    result = frappe.db.sql(
        """select t1.name from `tab{0}` t1 where
		(select count(*) from `tab{1}` t2 where
			t2.lft < t1.lft and t2.rgt > t1.rgt) = 0
		and t1.rgt > t1.lft""".format(
            doctype, doctype
        )
    )
    return result[0][0] if result else None


@frappe.whitelist()
def get_items_groups():
    return frappe.db.sql(
        """
        select name
        from `tabItem Group`
        where is_group = 0
        order by name
        LIMIT 0, 200 """,
        as_dict=1,
    )


@frappe.whitelist()
def get_customers_groups(posProfile):
    # pos_profile_data = json.loads(posProfile)
    pos_profile = frappe.get_doc("POS Profile", posProfile)
    current_user = frappe.session.user
    customer_groups = []
    if pos_profile.get("customer_groups"):
        # Get items based on the item groups defined in the POS profile
        for data in pos_profile.get("customer_groups"):
            if data.get("customer_group")== "Retail customers center - عملاء تجزئة-مراكز" and "Employee Self Service" in frappe.get_roles(current_user):
                customer_groups.append(data.get("customer_group"))
            elif data.get("customer_group")!= "Retail customers center - عملاء تجزئة-مراكز":
                customer_groups.append(data.get("customer_group"))
            elif data.get("customer_group")!= "Wholesale customers - عميل جملة":
                customer_groups.append(data.get("customer_group"))

    return customer_groups

def get_customer_groups(pos_profile):
    customer_groups = []
    if pos_profile.get("customer_groups"):
        # Get items based on the item groups defined in the POS profile
        for data in pos_profile.get("customer_groups"):
            customer_groups.extend(
                [
                    "%s" % frappe.db.escape(d.get("name"))
                    for d in get_child_nodes(
                        "Customer Group", data.get("customer_group")
                    )
                ]
            )

    return list(set(customer_groups))


def get_child_nodes(group_type, root):
    lft, rgt = frappe.db.get_value(group_type, root, ["lft", "rgt"])
    return frappe.db.sql(
        """ Select name, lft, rgt from `tab{tab}` where
			lft >= {lft} and rgt <= {rgt} order by lft""".format(
            tab=group_type, lft=lft, rgt=rgt
        ),
        as_dict=1,
    )


def get_customer_group_condition(pos_profile):
    cond = "disabled = 0"
    customer_groups = get_customer_groups(pos_profile)
    if customer_groups:
        cond = " customer_group in (%s)" % (", ".join(["%s"] * len(customer_groups)))

    return cond % tuple(customer_groups)


@frappe.whitelist()
def get_customer_names(pos_profile):
    pos_profile = json.loads(pos_profile)
    condition = ""
    condition += get_customer_group_condition(pos_profile)
    # pos_profile_doc = frappe.get_doc("POS Profile", pos_profile.get("name"))
    customers = frappe.db.sql(
        """
        SELECT name, mobile_no, email_id, tax_id, customer_name,customer_group
        FROM `tabCustomer`
        where {0}
        ORDER by name
        """.format(
            condition
        ),
        as_dict=1,
    )
    # frappe.log_error("get_customer_names", customers)
    return {
        "customers": customers,
        # "custom_profile_type": pos_profile_doc.custom_profile_type,
    }


# @frappe.whitelist()
# def get_customer_names(pos_profile):
#     pos_profile = json.loads(pos_profile)
#     condition = ""
#     condition += get_customer_group_condition(pos_profile)
#     customers = frappe.db.sql(
#         """
#         SELECT name, mobile_no, email_id, tax_id, customer_name, loyalty_program, customer_group, customer_type, territory,  gender, posa_discount, image
#         FROM `tabCustomer`
#         where {0}
#         ORDER by name
#         """.format(
#             condition
#         ),
#         as_dict=1,
#     )
#     for customer in customers:
#         try:
#             # Get loyalty info if applicable
#             if customer.get("loyalty_program"):
#                 lp_details = get_loyalty_program_details_with_points(
#                     customer["name"],
#                     customer["loyalty_program"],
#                     silent=True,
#                     include_expired_entry=False,
#                 )
#                 customer["loyalty_points"] = lp_details.get("loyalty_points")
#                 customer["conversion_factor"] = lp_details.get("conversion_factor")
#             else:
#                 customer["loyalty_points"] = 0
#                 customer["conversion_factor"] = 1.0

#             # Get additional fields from customer doc
#             doc = frappe.get_doc("Customer", customer["name"])
#             customer["customer_price_list"] = doc.get("customer_price_list")
#             customer["birthday"] = doc.get("birthday")
#             customer["customer_group_price_list"] = doc.get("customer_group_price_list")

#         except Exception as e:
#             frappe.log_error(f"Error enriching customer {customer.get('name')}: {e}")
#     frappe.log_error("get_customer_names", customers)

#     return customers



@frappe.whitelist()
def get_default_sales_person():
    user = frappe.session.user
    sales_person = frappe.get_value("Sales Person", {"name": user, "enabled": 1}, ["name", "sales_person_name"])
    frappe.log_error("get_default_sales_person user", sales_person)
    return sales_person




# @frappe.whitelist()
# def get_sales_person_names():
#     sales_persons = frappe.get_list(
#         "Sales Person",
#         filters={"enabled": 1},
#         fields=["name", "sales_person_name"],
#         limit_page_length=100000,
#     )
#     return sales_persons


@frappe.whitelist()
def get_sales_person_names():
    user = frappe.session.user
    frappe.log_error("get_sales_person_names user", user)

    # Step 1: Get employee based on current user
    employee = frappe.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    frappe.log_error("employee for user", employee)

    # Step 2: Get Sales Person linked to that employee
    default_sales_person = None
    if employee:
        default_sales_person = frappe.get_value(
            "Sales Person",
            {"employee": employee, "enabled": 1},
            "name"
        )

    # Step 3: Get all enabled Sales Persons
    sales_persons = frappe.get_all(
        "Sales Person",
        filters={"enabled": 1},
        fields=["name", "sales_person_name"]
    )

    return {
        "sales_persons": sales_persons,
        "default_sales_person": default_sales_person or ""
    }



def add_taxes_from_tax_template(item, parent_doc):
    accounts_settings = frappe.get_cached_doc("Accounts Settings")
    add_taxes_from_item_tax_template = (
        accounts_settings.add_taxes_from_item_tax_template
    )
    if item.get("item_tax_template") and add_taxes_from_item_tax_template:
        item_tax_template = item.get("item_tax_template")
        taxes_template_details = frappe.get_all(
            "Item Tax Template Detail",
            filters={"parent": item_tax_template},
            fields=["tax_type"],
        )

        for tax_detail in taxes_template_details:
            tax_type = tax_detail.get("tax_type")

            found = any(tax.account_head == tax_type for tax in parent_doc.taxes)
            if not found:
                tax_row = parent_doc.append("taxes", {})
                tax_row.update(
                    {
                        "description": str(tax_type).split(" - ")[0],
                        "charge_type": "On Net Total",
                        "account_head": tax_type,
                    }
                )

                if parent_doc.doctype == "Purchase Order":
                    tax_row.update({"category": "Total", "add_deduct_tax": "Add"})
                tax_row.db_insert()


@frappe.whitelist()
def update_invoice_from_order(data):
    data = json.loads(data)
    invoice_doc = frappe.get_doc("Sales Invoice", data.get("name"))
    invoice_doc.update(data)
    invoice_doc.save()
    return invoice_doc


@frappe.whitelist(allow_guest=True)
def get_shipping_rule_names():

    shipping_rules = frappe.db.sql(
        """
        SELECT name
        FROM `tabShipping Rule`
        ORDER by name
        LIMIT 0, 10000
        """,
        as_dict=1,
    )
    # frappe.log_error("shipping_rules",shipping_rules)

    return shipping_rules

@frappe.whitelist()
def update_invoice(data):
    data = json.loads(data)
    
     
    # Added by Farook for adding sales_invoice_item for  return invoice
    if data.get("is_return") and data.get("return_against"):
        # Load the original invoice
        original_invoice = frappe.get_doc("Sales Invoice", data["return_against"])
        
        # Map original item codes to their names
        original_items = {item.item_code: item.name for item in original_invoice.items}

        for item in data.get("items", []):
            original_item_name = original_items.get(item.get("item_code"))
            if original_item_name:
                item["sales_invoice_item"] = original_item_name
        
        
    
    if isinstance(data.get("shipping_rule"), dict):
        data["shipping_rule"] = data["shipping_rule"].get("name")
    if data.get("name"):
        invoice_doc = frappe.get_doc("Sales Invoice", data.get("name"))
        invoice_doc.update(data)
    else:
        invoice_doc = frappe.get_doc(data)
    invoice_doc.flags.ignore_permissions = True
    frappe.flags.ignore_account_permission = True
    invoice_doc.set_missing_values()
    invoice_doc.calculate_taxes_and_totals()
    # invoice_doc.rounded_total = frappe.utils.rounded(invoice_doc.grand_total)
    for item in invoice_doc.items:
        # discount_level = cint(frappe.get_value("Customer", invoice_doc.customer, "custom_discount_level") or 0)
        customer = frappe.get_doc("Customer", invoice_doc.customer)
        customer_group = customer.get("customer_group") or ""
        # profile_type = frappe.get_value("POS Profile", invoice_doc.pos_profile, "custom_profile_type")
        wholesale_price_list = frappe.get_value("POS Profile", invoice_doc.pos_profile, "selling_price_list")

        for item in invoice_doc.items:
            # Fetch wholesale rates from Item Price
            item_price_doc = frappe.get_all("Item Price",
                filters={
                    "item_code": item.item_code,
                    "price_list": wholesale_price_list
                },
                # fields=["wholesale_rate", "wholesale_rate2", "wholesale_rate3", "price_list_rate"]
                fields=["price_list_rate"]
            )

            item_rates = item_price_doc[0] if item_price_doc else {}
            # wholesale_rate = item_rates.get("wholesale_rate") or 0
            # wholesale_rate2 = item_rates.get("wholesale_rate2") or 0
            # wholesale_rate3 = item_rates.get("wholesale_rate3") or 0
            original_rate = item_rates.get("price_list_rate") or 0


            # Apply rate logic
            new_rate = original_rate  # fallback
            # if profile_type == "Wholesale Customer":
                # if discount_level == 1 and wholesale_rate:
                #     new_rate = wholesale_rate
                # elif discount_level == 2 and wholesale_rate2:
                #     new_rate = wholesale_rate2
            # elif (
            #     profile_type == "Distribution Eastern"
            #     # and customer_group.strip() == "Retail customers center - عملاء تجزئة-مراكز"
            #     and wholesale_rate3
            # ):
            #     new_rate = wholesale_rate3

            # Set the chosen rate
            item.rate = new_rate
            item.price_list_rate = new_rate
            item.base_rate = new_rate
            item.base_price_list_rate = new_rate
            item.amount = new_rate * item.qty
            item.base_amount = new_rate * item.qty

            add_taxes_from_tax_template(item, invoice_doc)

        #         # Only set the rate from backend if not already set by frontend
        # # if not item.rate or item.rate == 0:
        # wholesale_profiles = [
        #     "Wholesale POS",
        #     "Wholesale - Western",
        #     "Wholesale - Eastern",
        #     "Wholesale - Central",
        #     "Orange Station POS",
        #     "Wholesale Central 2 POS",
        # ]
        # if invoice_doc.pos_profile in wholesale_profiles:
        #     # frappe.log_error("Wholesale Profile1", invoice_doc.pos_profile)
        #     # Get customer's custom discount level
        #     discount_level = frappe.get_value("Customer", invoice_doc.customer, "custom_discount_level") or 0

        #     # Get price list and field to use
        #     wholesale_price_list = frappe.get_value("POS Profile", invoice_doc.pos_profile, "selling_price_list")

        #     # Decide rate field based on level
        #     rate_field = "wholesale_rate"  # default
        #     if discount_level == 2:
        #         rate_field = "wholesale_rate2"

        #     # Fetch the correct rate
        #     wholesale_rate = frappe.get_value(
        #         "Item Price",
        #         {
        #             "item_code": item.item_code,
        #             "price_list": wholesale_price_list,
        #         },
        #         rate_field,
        #     ) or 0
        #     # frappe.log_error("Wholesale Rate for item", wholesale_rate)

        #     # Assign rate fields
        #     item.rate = wholesale_rate
        #     item.price_list_rate = wholesale_rate
        #     item.base_rate = wholesale_rate
        #     item.base_price_list_rate = wholesale_rate
        #     item.amount = item.rate * item.qty
        #     item.base_amount = item.base_rate * item.qty
        #     # frappe.log_error("Wholesale Rate for item", item.rate)

        # add_taxes_from_tax_template(item, invoice_doc)
    invoice_doc.calculate_taxes_and_totals()
    if frappe.get_value("POS Profile", invoice_doc.pos_profile, "posa_tax_inclusive"):
        if invoice_doc.get("taxes"):
            for tax in invoice_doc.taxes:
                tax.included_in_print_rate = 1
#    if invoice_doc.is_return:
#        if invoice_doc.get("taxes"):
#            for tax in invoice_doc.taxes:
#                if tax.tax_amount > 0
#                    tax.tax_amount = tax.tax_amount* -1

    invoice_doc.base_discount_amount  = data.get("discount_amount")
    invoice_doc.discount_amount = data.get("discount_amount")
    invoice_doc.rounded_total = frappe.utils.rounded(invoice_doc.grand_total)
    
    


    if invoice_doc.is_return:
        _add_payments_to_return_invoice(invoice_doc)  # This will modify invoice_doc locally

    # if invoice_doc.customer:
    #     customer_addresses = frappe.db.sql("""
    #         SELECT parent
    #         FROM `tabDynamic Link`
    #         WHERE link_doctype = 'Customer' AND link_name = %s
    #         AND parenttype = 'Address'
    #         LIMIT 1
    #     """, (invoice_doc.customer,), as_dict=True)

    #     if customer_addresses:
    #         invoice_doc.customer_address = customer_addresses[0].parent
    # if invoice_doc.is_return and not data.get("is_cashback"):
    #     # Zero out all item amounts/rates
    #     for item in invoice_doc.items:
    #         item.rate = 0
    #         item.amount = 0
    #         item.base_rate = 0
    #         item.base_amount = 0
    #         item.price_list_rate = 0
    #         item.base_price_list_rate = 0
    #     # Zero out all taxes
    #     if hasattr(invoice_doc, "taxes"):
    #         for tax in invoice_doc.taxes:
    #             tax.tax_amount = 0
    #             tax.base_tax_amount = 0
    #             tax.tax_amount_after_discount_amount = 0
    #             tax.base_tax_amount_after_discount_amount = 0
    #     # Zero out totals
    #     invoice_doc.net_total = 0
    #     invoice_doc.total = 0
    #     invoice_doc.total_taxes_and_charges = 0
    #     invoice_doc.grand_total = 0
    #     invoice_doc.rounded_total = 0
    # Apply wholesale pricing based on customer's custom_discount_level
    invoice_doc.save()
    frappe.db.commit()
    if(invoice_doc.shipping_rule):
        apply_shipping_charges(invoice_doc)
    invoice_doc.save()
    return invoice_doc


@frappe.whitelist()
def submit_invoice(invoice, data):
    data = json.loads(data)
    invoice = json.loads(invoice)
    invoice_doc = frappe.get_doc("Sales Invoice", invoice.get("name"))
    invoice_doc.update(invoice)

    # Ensure return invoices have "Cash" as mode of payment
    # if invoice_doc.is_return:
    #     invoice_doc.payments = [
    #         {
    #             "mode_of_payment": "Cash",
    #             "amount": invoice_doc.rounded_total or invoice_doc.grand_total,
    #             "type": "Cash",
    #         }
    #     ]
    # if invoice_doc.is_return:
    #     invoice_doc.append("payments", {
    #     "amount": invoice_doc.rounded_total or invoice_doc.grand_total
    # })

    # If the POS Profile is wholesale, set wholesale rate for each item
    # discount_level = cint(frappe.get_value("Customer", invoice_doc.customer, "custom_discount_level") or 0)
    customer = frappe.get_doc("Customer", invoice_doc.customer)
    customer_group = customer.get("customer_group") or ""
    # profile_type = frappe.get_value("POS Profile", invoice_doc.pos_profile, "custom_profile_type")
    wholesale_price_list = frappe.get_value("POS Profile", invoice_doc.pos_profile, "selling_price_list")

    for item in invoice_doc.items:
        # Fetch wholesale rates from Item Price
        item_price_doc = frappe.get_all("Item Price",
            filters={
                "item_code": item.item_code,
                "price_list": wholesale_price_list
            },
            # fields=["wholesale_rate", "wholesale_rate2", "wholesale_rate3", "price_list_rate"]
            fields=["price_list_rate"]
        )

        item_rates = item_price_doc[0] if item_price_doc else {}
        # wholesale_rate = item_rates.get("wholesale_rate") or 0
        # wholesale_rate2 = item_rates.get("wholesale_rate2") or 0
        # wholesale_rate3 = item_rates.get("wholesale_rate3") or 0
        original_rate = item_rates.get("price_list_rate") or 0


        # Apply rate logic
        new_rate = original_rate  # fallback
        # if profile_type == "Wholesale Customer":
        #     if discount_level == 1 and wholesale_rate:
        #         new_rate = wholesale_rate
        #     elif discount_level == 2 and wholesale_rate2:
        #         new_rate = wholesale_rate2
        # elif (
        #     profile_type == "Distribution Eastern"
        #     # and customer_group.strip() == "Retail customers center - عملاء تجزئة-مراكز"
        #     and wholesale_rate3
        # ):
        #     new_rate = wholesale_rate3

        # Set the chosen rate
        item.rate = new_rate
        item.price_list_rate = new_rate
        item.base_rate = new_rate
        item.base_price_list_rate = new_rate
        item.amount = new_rate * item.qty
        item.base_amount = new_rate * item.qty

        add_taxes_from_tax_template(item, invoice_doc)

    # wholesale_profiles = [
    #     "Wholesale POS",
    #     "Wholesale - Western",
    #     "Wholesale - Eastern",
    #     "Wholesale - Central",
    #     "Orange Station POS",
    #     "Wholesale Central 2 POS",
    # ]
    # if invoice_doc.pos_profile in wholesale_profiles:
    #     for item in invoice_doc.items:
    #         # frappe.log_error("Wholesale Profile1", invoice_doc.pos_profile)
    #         # Get customer's custom discount level
    #         discount_level = frappe.get_value("Customer", invoice_doc.customer, "custom_discount_level") or 0

    #         # Get price list and field to use
    #         wholesale_price_list = frappe.get_value("POS Profile", invoice_doc.pos_profile, "selling_price_list")

    #         # Decide rate field based on level
    #         rate_field = "wholesale_rate"  # default
    #         if discount_level == 2:
    #             rate_field = "wholesale_rate2"

    #         # Fetch the correct rate
    #         wholesale_rate = frappe.get_value(
    #             "Item Price",
    #             {
    #                 "item_code": item.item_code,
    #                 "price_list": wholesale_price_list,
    #             },
    #             rate_field,
    #         ) or 0
    #         # frappe.log_error("Wholesale Rate for item", wholesale_rate)

    #         # Assign rate fields
    #         item.rate = wholesale_rate
    #         item.price_list_rate = wholesale_rate
    #         item.base_rate = wholesale_rate
    #         item.base_price_list_rate = wholesale_rate
    #         item.amount = item.rate * item.qty
    #         item.base_amount = item.base_rate * item.qty
    #         # frappe.log_error("Wholesale Rate for item", item.rate)

    #     add_taxes_from_tax_template(item, invoice_doc)
        # wholesale_price_list = frappe.get_value("POS Profile", invoice_doc.pos_profile, "selling_price_list")
        # rate_field = frappe.get_value("POS Profile", invoice_doc.pos_profile, "custom_wholesale_rate") or "wholesale_rate"
        # # frappe.log_error("Wholesale Price List", wholesale_price_list)
        # for item in invoice_doc.items:
        #     wholesale_rate = frappe.get_value(
        #         "Item Price",
        #         {
        #             "item_code": item.item_code,
        #             "price_list": wholesale_price_list,
        #         },
        #         rate_field,
        #     ) or 0
        #     item.rate = wholesale_rate
        #     # frappe.log_error("Wholesale Rate", wholesale_rate)
        #     item.price_list_rate = wholesale_rate
        #     item.base_rate = wholesale_rate
        #     item.base_price_list_rate = wholesale_rate
        #     item.amount = item.rate * item.qty
        #     item.base_amount = item.base_rate * item.qty


    if invoice.get("posa_delivery_date"):
        invoice_doc.update_stock = 0
    mop_cash_list = [
        i.mode_of_payment
        for i in invoice_doc.payments
        if "cash" in i.mode_of_payment.lower() and i.type == "Cash"
    ]
    if len(mop_cash_list) > 0:
        cash_account = get_bank_cash_account(mop_cash_list[0], invoice_doc.company)
    else:
        cash_account = {
            "account": frappe.get_value(
                "Company", invoice_doc.company, "default_cash_account"
            )
        }
        
    # if invoice_doc.is_return:
    #     payment_entry = frappe.get_doc(
    #         {
    #             "doctype": "Sales Invoice Payment",
    #             "amount": invoice_doc.rounded_total or invoice_doc.grand_total,
    #             "mode_of_payment": "Cash",
    #             "type": "Cash",
    #         }
    #     )

    #     payment_entry.flags.ignore_permissions = True
    #     frappe.flags.ignore_account_permission = True
    #     payment_entry.save()
    #     payment_entry.submit()

    # if invoice_doc.is_return:
        
    #     invoice_doc.payments = []  # Clear any existing payments, if needed
    #     invoice_doc.append("payments", {
    #         "mode_of_payment": "Cash",
    #         "type": "Cash",
    #         "amount": invoice_doc.rounded_total or invoice_doc.grand_total
    #     })
    #     # frappe.log_error("amount",invoice_doc.payments[0].amount)


    # creating advance payment
    if data.get("credit_change"):
        advance_payment_entry = frappe.get_doc(
            {
                "doctype": "Payment Entry",
                "mode_of_payment": "Cash",
                "paid_to": cash_account["account"],
                "payment_type": "Receive",
                "party_type": "Customer",
                "party": invoice_doc.get("customer"),
                "paid_amount": invoice_doc.get("credit_change"),
                "received_amount": invoice_doc.get("credit_change"),
                "company": invoice_doc.get("company"),
            }
        )

        advance_payment_entry.flags.ignore_permissions = True
        frappe.flags.ignore_account_permission = True
        advance_payment_entry.save()
        advance_payment_entry.submit()


    # calculating cash
    total_cash = 0
    if data.get("redeemed_customer_credit"):
        total_cash = invoice_doc.total - float(data.get("redeemed_customer_credit"))

    is_payment_entry = 0
    if data.get("redeemed_customer_credit"):
        for row in data.get("customer_credit_dict"):
            if row["type"] == "Advance" and row["credit_to_redeem"]:
                advance = frappe.get_doc("Payment Entry", row["credit_origin"])

                advance_payment = {
                    "reference_type": "Payment Entry",
                    "reference_name": advance.name,
                    "remarks": advance.remarks,
                    "advance_amount": advance.unallocated_amount,
                    "allocated_amount": row["credit_to_redeem"],
                }

                invoice_doc.append("advances", advance_payment)
                invoice_doc.is_pos = 0
                is_payment_entry = 1

    payments = invoice_doc.payments
    
    if invoice_doc.is_return and not data.get("is_cashback"):
        invoice_doc.is_pos = 0


    # if frappe.get_value("POS Profile", invoice_doc.pos_profile, "posa_auto_set_batch"):
    #     set_batch_nos(invoice_doc, "warehouse", throw=True)
    set_batch_nos_for_bundels(invoice_doc, "warehouse", throw=True)

    invoice_doc.flags.ignore_permissions = True
    frappe.flags.ignore_account_permission = True
    invoice_doc.posa_is_printed = 1
    invoice_doc.save()

    if data.get("due_date"):
        frappe.db.set_value(
            "Sales Invoice",
            invoice_doc.name,
            "due_date",
            data.get("due_date"),
            update_modified=False,
        )

    if frappe.get_value(
        "POS Profile",
        invoice_doc.pos_profile,
        "posa_allow_submissions_in_background_job",
    ):
        invoices_list = frappe.get_all(
            "Sales Invoice",
            filters={
                "posa_pos_opening_shift": invoice_doc.posa_pos_opening_shift,
                "docstatus": 0,
                "posa_is_printed": 1,
            },
        )
        for invoice in invoices_list:
            enqueue(
                method=submit_in_background_job,
                queue="short",
                timeout=1000,
                is_async=True,
                kwargs={
                    "invoice": invoice.name,
                    "data": data,
                    "is_payment_entry": is_payment_entry,
                    "total_cash": total_cash,
                    "cash_account": cash_account,
                    "payments": payments,
                },
            )
    else:
        # if invoice_doc.is_return and not data.get("is_cashback"):
        #     # Zero out all item amounts/rates
        #     for item in invoice_doc.items:
        #         item.rate = 0
        #         item.amount = 0
        #         item.base_rate = 0
        #         item.base_amount = 0
        #         item.price_list_rate = 0
        #         item.base_price_list_rate = 0
        #     # Zero out all taxes
        #     if hasattr(invoice_doc, "taxes"):
        #         for tax in invoice_doc.taxes:
        #             tax.tax_amount = 0
        #             tax.base_tax_amount = 0
        #             tax.tax_amount_after_discount_amount = 0
        #             tax.base_tax_amount_after_discount_amount = 0
        #     # Zero out totals
        #     invoice_doc.net_total = 0
        #     invoice_doc.total = 0
        #     invoice_doc.total_taxes_and_charges = 0
        #     invoice_doc.grand_total = 0
        #     invoice_doc.rounded_total = 0
            
        if invoice_doc.is_return:
            invoice_doc.update_outstanding_for_self = 0

        invoice_doc.submit()
        redeeming_customer_credit(
            invoice_doc, data, is_payment_entry, total_cash, cash_account, payments
        )
    return {"name": invoice_doc.name, "status": invoice_doc.docstatus}


def set_batch_nos_for_bundels(doc, warehouse_field, throw=False):
    """Automatically select `batch_no` for outgoing items in item table"""
    for d in doc.packed_items:
        qty = d.get("stock_qty") or d.get("transfer_qty") or d.get("qty") or 0
        has_batch_no = frappe.db.get_value("Item", d.item_code, "has_batch_no")
        warehouse = d.get(warehouse_field, None)
        if has_batch_no and warehouse and qty > 0:
            if not d.batch_no:
                d.batch_no = get_batch_no(
                    d.item_code
                )
                # d.batch_no = get_batch_no(
                #     d.item_code, warehouse, qty, throw, d.serial_no
                # )
            else:
                batch_qty = get_batch_qty(batch_no=d.batch_no, warehouse=warehouse)
                if flt(batch_qty, d.precision("qty")) < flt(qty, d.precision("qty")):
                    frappe.throw(
                        _(
                            "Row #{0}: The batch {1} has only {2} qty. Please select another batch which has {3} qty available or split the row into multiple rows, to deliver/issue from multiple batches"
                        ).format(d.idx, d.batch_no, batch_qty, qty)
                    )


def redeeming_customer_credit(
    invoice_doc, data, is_payment_entry, total_cash, cash_account, payments
):
    # redeeming customer credit with journal voucher
    today = nowdate()
    if data.get("redeemed_customer_credit"):
        cost_center = frappe.get_value(
            "POS Profile", invoice_doc.pos_profile, "cost_center"
        )
        if not cost_center:
            cost_center = frappe.get_value(
                "Company", invoice_doc.company, "cost_center"
            )
        if not cost_center:
            frappe.throw(
                _("Cost Center is not set in pos profile {}").format(
                    invoice_doc.pos_profile
                )
            )
        for row in data.get("customer_credit_dict"):
            if row["type"] == "Invoice" and row["credit_to_redeem"]:
                outstanding_invoice = frappe.get_doc(
                    "Sales Invoice", row["credit_origin"]
                )

                jv_doc = frappe.get_doc(
                    {
                        "doctype": "Journal Entry",
                        "voucher_type": "Journal Entry",
                        "posting_date": today,
                        "company": invoice_doc.company,
                    }
                )

                jv_debit_entry = {
                    "account": outstanding_invoice.debit_to,
                    "party_type": "Customer",
                    "party": invoice_doc.customer,
                    "reference_type": "Sales Invoice",
                    "reference_name": outstanding_invoice.name,
                    "debit_in_account_currency": row["credit_to_redeem"],
                    "cost_center": cost_center,
                }

                jv_credit_entry = {
                    "account": invoice_doc.debit_to,
                    "party_type": "Customer",
                    "party": invoice_doc.customer,
                    "reference_type": "Sales Invoice",
                    "reference_name": invoice_doc.name,
                    "credit_in_account_currency": row["credit_to_redeem"],
                    "cost_center": cost_center,
                }

                jv_doc.append("accounts", jv_debit_entry)
                jv_doc.append("accounts", jv_credit_entry)

                jv_doc.flags.ignore_permissions = True
                frappe.flags.ignore_account_permission = True
                jv_doc.set_missing_values()
                jv_doc.save()
                jv_doc.submit()

    if is_payment_entry and total_cash > 0:
        for payment in payments:
            if not payment.amount:
                continue
            payment_entry_doc = frappe.get_doc(
                {
                    "doctype": "Payment Entry",
                    "posting_date": today,
                    "payment_type": "Receive",
                    "party_type": "Customer",
                    "party": invoice_doc.customer,
                    "paid_amount": payment.amount,
                    "received_amount": payment.amount,
                    "paid_from": invoice_doc.debit_to,
                    "paid_to": payment.account,
                    "company": invoice_doc.company,
                    "mode_of_payment": payment.mode_of_payment,
                    "reference_no": invoice_doc.posa_pos_opening_shift,
                    "reference_date": today,
                }
            )

            payment_reference = {
                "allocated_amount": payment.amount,
                "due_date": data.get("due_date"),
                "reference_doctype": "Sales Invoice",
                "reference_name": invoice_doc.name,
            }

            payment_entry_doc.append("references", payment_reference)
            payment_entry_doc.flags.ignore_permissions = True
            frappe.flags.ignore_account_permission = True
            payment_entry_doc.save()
            payment_entry_doc.submit()


def submit_in_background_job(kwargs):
    invoice = kwargs.get("invoice")
    invoice_doc = kwargs.get("invoice_doc")
    data = kwargs.get("data")
    is_payment_entry = kwargs.get("is_payment_entry")
    total_cash = kwargs.get("total_cash")
    cash_account = kwargs.get("cash_account")
    payments = kwargs.get("payments")

    invoice_doc = frappe.get_doc("Sales Invoice", invoice)
    invoice_doc.submit()
    redeeming_customer_credit(
        invoice_doc, data, is_payment_entry, total_cash, cash_account, payments
    )


@frappe.whitelist()
def get_available_credit(customer, company):
    total_credit = []

    outstanding_invoices = frappe.get_all(
        "Sales Invoice",
        {
            "outstanding_amount": ["<", 0],
            "docstatus": 1,
            "is_return": 0,
            "customer": customer,
            "company": company,
        },
        ["name", "outstanding_amount"],
    )

    for row in outstanding_invoices:
        outstanding_amount = -(row.outstanding_amount)
        row = {
            "type": "Invoice",
            "credit_origin": row.name,
            "total_credit": outstanding_amount,
            "credit_to_redeem": 0,
        }

        total_credit.append(row)

    advances = frappe.get_all(
        "Payment Entry",
        {
            "unallocated_amount": [">", 0],
            "party_type": "Customer",
            "party": customer,
            "company": company,
            "docstatus": 1,
        },
        ["name", "unallocated_amount"],
    )

    for row in advances:
        row = {
            "type": "Advance",
            "credit_origin": row.name,
            "total_credit": row.unallocated_amount,
            "credit_to_redeem": 0,
        }

        total_credit.append(row)

    return total_credit


@frappe.whitelist()
def get_draft_invoices(pos_opening_shift):
    invoices_list = frappe.get_list(
        "Sales Invoice",
        filters={
            "posa_pos_opening_shift": pos_opening_shift,
            "docstatus": 0,
            "posa_is_printed": 0,
        },
        fields=["name"],
        limit_page_length=0,
        order_by="modified desc",
    )
    data = []
    for invoice in invoices_list:
        data.append(frappe.get_cached_doc("Sales Invoice", invoice["name"]))
    return data


@frappe.whitelist()
def delete_invoice(invoice):
    if frappe.get_value("Sales Invoice", invoice, "posa_is_printed"):
        frappe.throw(_("This invoice {0} cannot be deleted").format(invoice))
    frappe.delete_doc("Sales Invoice", invoice, force=1)
    return _("Invoice {0} Deleted").format(invoice)


@frappe.whitelist()
def get_items_details(pos_profile, items_data):
    _pos_profile = json.loads(pos_profile)
    ttl = _pos_profile.get("posa_server_cache_duration")
    if ttl:
        ttl = int(ttl) * 60

    @redis_cache(ttl=ttl or 1800)
    def __get_items_details(pos_profile, items_data):
        return _get_items_details(pos_profile, items_data)

    def _get_items_details(pos_profile, items_data):
        today = nowdate()
        pos_profile = json.loads(pos_profile)
        items_data = json.loads(items_data)
        warehouse = pos_profile.get("warehouse")
        result = []

        if len(items_data) > 0:
            for item in items_data:
                item_code = item.get("item_code")
                item_stock_qty = get_stock_availability(item_code, warehouse)
                # (has_batch_no, has_serial_no, manufacturer_part_no) = frappe.db.get_value(
                #     "Item", item_code, ["has_batch_no", "has_serial_no", "manufacturer_part_no"]
                # )
                (has_batch_no, has_serial_no) = frappe.db.get_value(
                    "Item", item_code, ["has_batch_no", "has_serial_no"]
                )

                uoms = frappe.get_all(
                    "UOM Conversion Detail",
                    filters={"parent": item_code},
                    fields=["uom", "conversion_factor"],
                )

                serial_no_data = frappe.get_all(
                    "Serial No",
                    filters={
                        "item_code": item_code,
                        "status": "Active",
                        "warehouse": warehouse,
                    },
                    fields=["name as serial_no"],
                )

                batch_no_data = []

                batch_list = get_batch_qty(warehouse=warehouse, item_code=item_code)

                if batch_list:
                    for batch in batch_list:
                        if batch.qty > 0 and batch.batch_no:
                            batch_doc = frappe.get_cached_doc("Batch", batch.batch_no)
                            if (
                                str(batch_doc.expiry_date) > str(today)
                                or batch_doc.expiry_date in ["", None]
                            ) and batch_doc.disabled == 0:
                                batch_no_data.append(
                                    {
                                        "batch_no": batch.batch_no,
                                        "batch_qty": batch.qty,
                                        "expiry_date": batch_doc.expiry_date,
                                        "batch_price": batch_doc.posa_batch_price,
                                        "manufacturing_date": batch_doc.manufacturing_date,
                                    }
                                )

                row = {}
                row.update(item)
                row.update(
                    {
                        "item_uoms": uoms or [],
                        "serial_no_data": serial_no_data or [],
                        "batch_no_data": batch_no_data or [],
                        "actual_qty": item_stock_qty or 0,
                        "has_batch_no": has_batch_no,
                        "has_serial_no": has_serial_no,
                        # "manufacturer_part_no": manufacturer_part_no,

                    }
                )

                result.append(row)


        return result

    if _pos_profile.get("posa_use_server_cache"):
        return __get_items_details(pos_profile, items_data)
    else:
        return _get_items_details(pos_profile, items_data)


@frappe.whitelist()
def get_item_detail(item, doc=None, warehouse=None, price_list=None):
    item = json.loads(item)
    today = nowdate()
    item_code = item.get("item_code")
    batch_no_data = []
    if warehouse and item.get("has_batch_no"):
        batch_list = get_batch_qty(warehouse=warehouse, item_code=item_code)
        if batch_list:
            for batch in batch_list:
                if batch.qty > 0 and batch.batch_no:
                    batch_doc = frappe.get_cached_doc("Batch", batch.batch_no)
                    if (
                        str(batch_doc.expiry_date) > str(today)
                        or batch_doc.expiry_date in ["", None]
                    ) and batch_doc.disabled == 0:
                        batch_no_data.append(
                            {
                                "batch_no": batch.batch_no,
                                "batch_qty": batch.qty,
                                "expiry_date": batch_doc.expiry_date,
                                "batch_price": batch_doc.posa_batch_price,
                                "manufacturing_date": batch_doc.manufacturing_date,
                            }
                        )

    item["selling_price_list"] = price_list

    max_discount = frappe.get_value("Item", item_code, "max_discount")
    res = get_item_details(
        item,
        doc,
        overwrite_warehouse=False,
    )
    if item.get("is_stock_item") and warehouse:
        res["actual_qty"] = get_stock_availability(item_code, warehouse)
    res["max_discount"] = max_discount
    res["batch_no_data"] = batch_no_data
    return res


@frappe.whitelist()
def get_item_details_by_itemcode(item_code,profile,parent=None):
    pos_profile = json.loads(profile)
    item = frappe.db.sql(
        """SELECT
            name AS item_code,
            item_name,
            description,
            stock_uom,
            image,
            is_stock_item,
            has_variants,
            variant_of,
            item_group,
            idx as idx,
            has_batch_no,
            has_serial_no,
            max_discount,
            brand
        FROM
            `tabItem`
        WHERE
            item_code = %s
            """,(item_code),
        as_dict=1,
    )
    item_stock_qty = get_stock_availability(item_code, pos_profile.get("warehouse"))
    has_batch_no = frappe.get_value("Item",item[0].item_code,"has_batch_no")
    has_serial_no = frappe.get_value("Item",item[0].item_code,"has_serial_no")

    uoms = frappe.get_all(
                "UOM Conversion Detail",
                filters={"parent": item[0].item_code},
                fields=["uom", "conversion_factor"],
            )

    serial_no_data = frappe.get_all(
                "Serial No",
                filters={"item_code": item[0].item_code, "status": "Active"},
                fields=["name as serial_no"],
            )

    batch_no_data = []
    from erpnext.stock.doctype.batch.batch import get_batch_qty

    batch_list = get_batch_qty(warehouse=pos_profile.get("warehouse"), item_code=item[0].item_code)

    if batch_list:
        for batch in batch_list:
            if batch.qty > 0 and batch.batch_no:
                batch_doc = frappe.get_doc("Batch", batch.batch_no)
                if (
                            str(batch_doc.expiry_date) > str(nowdate())
                            or batch_doc.expiry_date in ["", None]
                        ) and batch_doc.disabled == 0:
                    batch_no_data.append(
                                {
                                    "batch_no": batch.batch_no,
                                    "batch_qty": batch.qty,
                                    "expiry_date": batch_doc.expiry_date,
                                    "btach_price": batch_doc.posa_btach_price,
                                }
                            )
    # wholesale_rate = pos_profile.get("custom_wholesale_rate") or "wholesale_rate"
    item_prices_data = frappe.get_all(
            "Item Price",
            # fields=["item_code", "price_list_rate", "currency",wholesale_rate],
            fields=["item_code", "price_list_rate", "currency"],
            filters={"price_list": "Standard Selling", "item_code": item[0].item_code    },
        )

    # if pos_profile.get("name") == "Wholesale POS" or pos_profile.get("name") == "Wholesale - Western" or pos_profile.get("name") == "Wholesale - Eastern" or pos_profile.get("name") == "Wholesale - Central" or pos_profile.get("name") == "Orange Station POS" or pos_profile.get("name") == "Wholesale Central 2 POS":
    #     item_pos_rate = item_prices_data[0].wholesale_rate
    # custom_rate_field = pos_profile.get("custom_wholesale_rate") or "wholesale_rate"

    # if pos_profile.get("name") in [
    #     "Wholesale POS",
    #     "Wholesale - Western",
    #     "Wholesale - Eastern",
    #     "Wholesale - Central",
    #     "Orange Station POS",
    #     "Wholesale Central 2 POS"
    # ]:
        # item_pos_rate = item_prices_data.get(custom_rate_field) or 0

    # else :
    item_pos_rate = item_prices_data[0].price_list_rate or 0
    item_qty = 0
    if parent:
        item_qty = frappe.db.sql(
        """select qty
        from `tabProduct Bundle Item`
        where parent = %s and item_code = %s
        """,
        (parent,item_code),
        as_dict=1,
    )
    item_qty = item_qty[0].qty or 0
    item[0].item_uoms = uoms or []
    item[0].serial_no_data = serial_no_data or []
    item[0].batch_no_data = batch_no_data or []
    item[0].actual_qty = item_stock_qty or 0
    item[0].has_batch_no = has_batch_no
    item[0].has_serial_no = has_serial_no
    item[0].rate = item_pos_rate
    item[0].qty = item_qty
    return item[0]


@frappe.whitelist(allow_guest=True)
def get_stock_availability(item_code, warehouse):
    latest_sle = frappe.db.sql(
        """select actual_qty
        from `tabBin`
        where item_code = %s and warehouse = %s
        """,
        (item_code, warehouse),
        as_dict=1,
    )
    sle_qty = latest_sle[0].actual_qty or 0 if latest_sle else 0
    return sle_qty


@frappe.whitelist()
def get_wholesale_rate(item_code, price_list, pos_profile=None):
    if not pos_profile:
        user = frappe.session.user
        pos_profile = frappe.get_value("POS Profile User", {"user": user}, "parent")

    # frappe.log_error(f"get_wholesale_rate POS Profile: {pos_profile}")
    rate_field = "wholesale_rate"  # default fallback

    if pos_profile:
        rate_field = frappe.get_value("POS Profile", pos_profile, "custom_wholesale_rate") or "wholesale_rate"

    wh_rate = frappe.db.sql(
        f"""SELECT `{rate_field}` as rate
            FROM `tabItem Price`
            WHERE item_code = %s AND price_list = %s
        """,
        (item_code, price_list),
        as_dict=1,
    )

    return wh_rate[0].rate if wh_rate and wh_rate[0].rate else 0


# @frappe.whitelist()
# def get_wholesale_rate(item_code,price_list):
#     wh_rate = frappe.db.sql(
#         """select wholesale_rate
#         from `tabItem Price`
#         where item_code = %s and price_list = %s
#         """,
#         (item_code, price_list),
#         as_dict=1,
#     )
#     frappe.log_error("wh_rate",wh_rate)
#     return wh_rate[0].wholesale_rate or 0 if wh_rate else 0


@frappe.whitelist()
def apply_shipping_charges(invoice_doc):


    invoice_doc.apply_shipping_charge()
    return "done"

@frappe.whitelist()
def create_customer(
    customer_name,
    company,
    tax_id,
    mobile_no,
    email_id,
    city,
    referral_code=None,
    birthday=None,
    customer_group=None,
    territory=None,
    # custom_b2c=None,
    # custom_buyer_id_type=None,
    # custom_buyer_id=None,
    address_line1=None,
    address_line2=None,
    custom_building_number=None,
    pincode=None,

    # customer_name_in_arabic=None,

):
    if customer_group == "Wholesale customers - عميل جملة":
        if frappe.db.exists("Customer", {"tax_id": tax_id}):
            frappe.throw(_("A customer with this Tax ID already exists!"))
    if address_line1 and not city:
        frappe.throw(_("City is mandatory when address is provided."))
    if not frappe.db.exists("Customer", {"mobile_no": mobile_no}):
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": customer_name,
                "posa_referral_company": frappe.defaults.get_user_default("Company"),
                "tax_id": tax_id,
                "mobile_no": mobile_no,
                "email_id": email_id,
                "posa_referral_code": referral_code, #referral_code
                "posa_birthday": birthday,
                "company": frappe.defaults.get_user_default("Company")
            }
        )
        if customer_group:
            customer.customer_group = customer_group
        if territory:
            customer.territory = territory
        # if isinstance(custom_b2c, str):
        #     custom_b2c = custom_b2c.lower() in ("true", "1", "yes")

        # if custom_b2c:
            # customer.custom_b2c = 1 if custom_b2c else 0
        # if custom_buyer_id_type:
        #     customer.custom_buyer_id_type = custom_buyer_id_type
        # if custom_buyer_id:
        #     customer.custom_buyer_id = custom_buyer_id
        # if customer_name_in_arabic:
            # customer.customer_name_in_arabic = customer_name_in_arabic
        customer.save(ignore_permissions=True)

        if address_line1:
            # if not city:
            #     frappe.throw(_("City is mandatory when address is provided."))
            # else:

            address = frappe.get_doc({
                "doctype": "Address",
                "address_title": customer_name,
                "address_type": "Billing",
                "customer": customer.name,
                "address_line1": address_line1,
                "city": city,
                "links": [
                    {
                        "link_doctype": "Customer",
                        "link_name": customer.name
                    }
            ]
            })

            if address_line2:
                address.address_line2 = address_line2
            if custom_building_number:
                address.custom_building_number = custom_building_number  # assuming you have this custom field
            if pincode:
                address.pincode = pincode

            address.insert(ignore_permissions=True)
            customer.customer_primary_address = address.name
            customer.save(ignore_permissions=True)

        return customer
    else:
        frappe.throw(_("Mobile Number is already exist!"))


@frappe.whitelist()
def get_items_from_barcode(selling_price_list, currency, barcode):
    search_item = frappe.get_all(
        "Item Barcode",
        filters={"barcode": barcode},
        fields=["parent", "barcode", "posa_uom"],
    )
    if len(search_item) == 0:
        return ""
    item_code = search_item[0].parent
    item_list = frappe.get_all(
        "Item",
        filters={"name": item_code},
        fields=[
            "name",
            "item_name",
            "description",
            "stock_uom",
            "image",
            "is_stock_item",
            "has_variants",
            "variant_of",
            "item_group",
            "has_batch_no",
            "has_serial_no",
        ],
    )

    if item_list[0]:
        item = item_list[0]
        filters = {"price_list": selling_price_list, "item_code": item_code}
        prices_with_uom = frappe.db.count(
            "Item Price",
            filters={
                "price_list": selling_price_list,
                "item_code": item_code,
                "uom": item.stock_uom,
            },
        )

        if prices_with_uom > 0:
            filters["uom"] = item.stock_uom
        else:
            filters["uom"] = ["in", ["", None, item.stock_uom]]

        item_prices_data = frappe.get_all(
            "Item Price",
            fields=["item_code", "price_list_rate", "currency"],
            filters=filters,
        )

        item_price = 0
        if len(item_prices_data):
            item_price = item_prices_data[0].get("price_list_rate")
            currency = item_prices_data[0].get("currency")

        item.update(
            {
                "rate": item_price,
                "currency": currency,
                "item_code": item_code,
                "barcode": barcode,
                "actual_qty": 0,
                "item_barcode": search_item,
            }
        )
        return item


@frappe.whitelist()
def set_customer_info(customer, fieldname, value=""):
    if fieldname == "referral_code": 
        fieldname = "posa_referral_code"
    address_fields = [
        "address_line1", "address_line2", "custom_building_number", "pincode", "city"
    ]

    if fieldname in address_fields:
        # frappe.log_error(f"Setting {fieldname} for customer {customer} to {value}", "POS App Customer Update")
        address_name = frappe.db.get_value("Dynamic Link", {
            "link_doctype": "Customer",
            "link_name": customer,
            "parenttype": "Address"
        }, "parent")

        if address_name:
            frappe.log_error("if address name")
            frappe.db.set_value("Address", address_name, fieldname, value)
            customer_doc = frappe.get_doc("Customer", customer)
            customer_doc.customer_primary_address = address_name
            customer_doc.save()
        else:
            frappe.log_error("else address name")
            address = frappe.get_doc({
                "doctype": "Address",
                "address_title": customer,
                "address_type": "Billing",
                fieldname: value,
                "links": [{"link_doctype": "Customer", "link_name": customer}]
            })

            address.insert(ignore_mandatory=True)

            # Now load and update Customer doc properly
            customer_doc = frappe.get_doc("Customer", customer)
            customer_doc.customer_primary_address = address.name
            customer_doc.save()

    else:
        frappe.log_error(f"Setting {fieldname} for customer {customer} to {value}", "POS App Customer Update2")
        frappe.db.set_value("Customer", customer, fieldname, value)

    contact = frappe.get_cached_value("Customer", customer, "customer_primary_contact") or ""
    if contact:
        contact_doc = frappe.get_doc("Contact", contact)
        contact_doc.reload()  # Ensure latest version

        if fieldname == "email_id":
            contact_doc.set("email_ids", [{"email_id": value, "is_primary": 1}])
            frappe.db.set_value("Customer", customer, "email_id", value)
        elif fieldname == "mobile_no":
            contact_doc.set("phone_nos", [{"phone": value, "is_primary_mobile_no": 1}])
            frappe.db.set_value("Customer", customer, "mobile_no", value)

        contact_doc.save(ignore_version=True)


# @frappe.whitelist()
# def set_customer_info(customer, fieldname, value=""):
#     address_fields = [
#         "address_line1", "address_line2", "custom_building_number", "pincode", "city"
#     ]
    
#     if fieldname in address_fields:
#         address_name = frappe.db.get_value("Dynamic Link", {
#             "link_doctype": "Customer",
#             "link_name": customer,
#             "parenttype": "Address"
#         }, "parent")
        
#         if address_name:
#             frappe.db.set_value("Address", address_name, fieldname, value)
#         else:
#             address = frappe.get_doc({
#                 "doctype": "Address",
#                 "address_title": customer,
#                 "address_type": "Billing",
#                 fieldname: value,
#                 "links": [{"link_doctype": "Customer", "link_name": customer}]
#             })
#             address.insert(ignore_mandatory=True)
#             frappe.db.set_value("Customer", customer, "customer_primary_address", address.name)
#     else:
#         frappe.db.set_value("Customer", customer, fieldname, value)

#     contact = frappe.get_cached_value("Customer", customer, "customer_primary_contact") or ""
#     # if contact:
#     #     contact_doc = frappe.get_doc("Contact", contact)
#     #     if fieldname == "email_id":
#     #         contact_doc.set("email_ids", [{"email_id": value, "is_primary": 1}])
#     #         frappe.db.set_value("Customer", customer, "email_id", value)
#     #     elif fieldname == "mobile_no":
#     #         contact_doc.set("phone_nos", [{"phone": value, "is_primary_mobile_no": 1}])
#     #         frappe.db.set_value("Customer", customer, "mobile_no", value)
#     #     contact_doc.save()\
#     if contact:
#         contact_doc = frappe.get_doc("Contact", contact)
#         contact_doc.reload()  # Ensure latest version

#         if fieldname == "email_id":
#             contact_doc.set("email_ids", [{"email_id": value, "is_primary": 1}])
#             frappe.db.set_value("Customer", customer, "email_id", value)
#         elif fieldname == "mobile_no":
#             contact_doc.set("phone_nos", [{"phone": value, "is_primary_mobile_no": 1}])
#             frappe.db.set_value("Customer", customer, "mobile_no", value)

#         contact_doc.save(ignore_version=True)



@frappe.whitelist()
def get_full_customer_info(customer_name):
    customer = frappe.get_doc("Customer", customer_name)
    address = frappe.db.get_value(
        "Address",
        {"name": customer.get("customer_primary_address")},
        ["address_line1", "address_line2", "city", "pincode", "custom_building_number"],
        as_dict=True,
    )
    customer_dict = customer.as_dict()
    if address:
        customer_dict.update(address)
    return customer_dict


@frappe.whitelist()
def get_customer_address(customer_name):
    # Fetches address linked to the customer
    address = frappe.get_all(
        "Address",
        filters={
            "link_name": customer_name,
            "link_doctype": "Customer",
        },
        fields=[
            "name",
            "address_line1",
            "address_line2",
            "city",
            "pincode"
        ],
        limit_page_length=1
    )
    return address[0] if address else {}



# @frappe.whitelist()
# def search_invoices_for_return(invoice_name, company):
#     invoices_list = frappe.get_list(
#         "Sales Invoice",
#         filters={
#             "name": ["like", f"%{invoice_name}%"],
#             "company": company,
#             "docstatus": 1,
#             "is_return": 0,
#         },
#         fields=["name"],
#         limit_page_length=0,
#         order_by="customer",
#     )
#     data = []
#     is_returned = frappe.get_all(
#         "Sales Invoice",
#         filters={"return_against": invoice_name, "docstatus": 1},
#         fields=["name"],
#         order_by="customer",
#     )
#     if len(is_returned):
#         return data
#     for invoice in invoices_list:
#         data.append(frappe.get_doc("Sales Invoice", invoice["name"]))
#     return data

@frappe.whitelist()
def search_invoices_for_return(invoice_name, company):
    frappe.log_error("1", invoice_name)
    invoices_list = frappe.get_list(
        "Sales Invoice",
        filters={
            "name": ["like", f"%{invoice_name}%"],
            "company": company,
            "docstatus": 1,
            "is_return": 0,
        },
        fields=["name"],
        limit_page_length=0,
        order_by="customer",
    )
    frappe.log_error("2", invoice_name)
    data = []

    for invoice in invoices_list:
        doc = frappe.get_doc("Sales Invoice", invoice.name)
        valid_items = []

        for item in doc.items:
            # Total qty in original invoice
            original_qty = item.qty

            # Total already returned qty for this item (negative qtys)
            # returned_qty = sum(
            #     abs(r.qty)
                # for r in frappe.get_all(
                #     "Sales Invoice Item",
                #     filters={
                #         "docstatus": 1,
                #         "return_against": doc.name,
                #         "item_code": item.item_code,
                #         "parenttype": "Sales Invoice"
                #     },
                #     fields=["qty"]
                # )
            return_invoices = frappe.get_all(
                "Sales Invoice",
                filters={
                    "return_against": doc.name,
                    "docstatus": 1,
                    "is_return": 1
                },
                pluck="name"
            )

            returned_qty = 0
            if return_invoices:
                returned_items = frappe.get_all(
                    "Sales Invoice Item",
                    filters={
                        "parent": ["in", return_invoices],
                        "item_code": item.item_code
                    },
                    fields=["qty"]
                )
                returned_qty = sum(abs(r.qty) for r in returned_items)

            # )

            # If there's remaining quantity to return
            if abs(returned_qty) < abs(original_qty):
                # Add only the returnable quantity
                remaining_qty = original_qty - returned_qty
                item.qty = remaining_qty
                item.amount = item.rate * remaining_qty
                item.stock_qty = item.stock_qty * (remaining_qty / original_qty) if item.stock_qty else 0
                valid_items.append(item)

        if valid_items:
            doc.items = valid_items
            data.append(doc)

    return data



@frappe.whitelist()
def search_orders(company, currency, order_name=None):
    filters = {
        "billing_status": ["in", ["Not Billed", "Partly Billed"]],
        "docstatus": 1,
        "company": company,
        "currency": currency,
    }
    if order_name:
        filters["name"] = ["like", f"%{order_name}%"]
    orders_list = frappe.get_list(
        "Sales Order",
        filters=filters,
        fields=["name"],
        limit_page_length=0,
        order_by="customer",
    )
    data = []
    for order in orders_list:
        data.append(frappe.get_doc("Sales Order", order["name"]))
    return data


def get_version():
    branch_name = get_app_branch("erpnext")
    if "12" in branch_name:
        return 12
    elif "13" in branch_name:
        return 13
    else:
        return 13


def get_app_branch(app):
    """Returns branch of an app"""
    import subprocess

    try:
        branch = subprocess.check_output(
            "cd ../apps/{0} && git rev-parse --abbrev-ref HEAD".format(app), shell=True
        )
        branch = branch.decode("utf-8")
        branch = branch.strip()
        return branch
    except Exception:
        return ""


@frappe.whitelist()
def get_offers(profile):
    pos_profile = frappe.get_doc("POS Profile", profile)
    company = pos_profile.company
    warehouse = pos_profile.warehouse
    date = nowdate()

    values = {
        "company": company,
        "pos_profile": profile,
        "warehouse": warehouse,
        "valid_from": date,
        "valid_upto": date,
    }
    data = frappe.db.sql(
        """
        SELECT *
        FROM `tabPOS Offer`
        WHERE
        disable = 0 AND
        company = %(company)s AND
        (pos_profile is NULL OR pos_profile  = '' OR  pos_profile = %(pos_profile)s) AND
        (warehouse is NULL OR warehouse  = '' OR  warehouse = %(warehouse)s) AND
        (valid_from is NULL OR valid_from  = '' OR  valid_from <= %(valid_from)s) AND
        (valid_upto is NULL OR valid_from  = '' OR  valid_upto >= %(valid_upto)s)
    """,
        values=values,
        as_dict=1,
    )
    return data


@frappe.whitelist()
def get_customer_addresses(customer):
    return frappe.db.sql(
        """
        SELECT
            address.name,
            address.address_line1,
            address.address_line2,
            address.address_title,
            address.city,
            address.state,
            address.country,
            address.address_type
        FROM `tabAddress` as address
        INNER JOIN `tabDynamic Link` AS link
				ON address.name = link.parent
        WHERE link.link_doctype = 'Customer'
            AND link.link_name = '{0}'
            AND address.disabled = 0
        ORDER BY address.name
        """.format(
            customer
        ),
        as_dict=1,
    )


@frappe.whitelist()
def make_address(args):
    args = json.loads(args)
    address = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": args.get("name"),
            "address_line1": args.get("address_line1"),
            "address_line2": args.get("address_line2"),
            "city": args.get("city"),
            "state": args.get("state"),
            "pincode": args.get("pincode"),
            "country": args.get("country"),
            "address_type": "Shipping",
            "links": [
                {"link_doctype": args.get("doctype"), "link_name": args.get("customer")}
            ],
        }
    ).insert()

    return address


def build_item_cache(item_code):
    parent_item_code = item_code

    attributes = [
        a.attribute
        for a in frappe.db.get_all(
            "Item Variant Attribute",
            {"parent": parent_item_code},
            ["attribute"],
            order_by="idx asc",
        )
    ]

    item_variants_data = frappe.db.get_all(
        "Item Variant Attribute",
        {"variant_of": parent_item_code},
        ["parent", "attribute", "attribute_value"],
        order_by="name",
        as_list=1,
    )

    disabled_items = set([i.name for i in frappe.db.get_all("Item", {"disabled": 1})])

    attribute_value_item_map = frappe._dict({})
    item_attribute_value_map = frappe._dict({})

    item_variants_data = [r for r in item_variants_data if r[0] not in disabled_items]
    for row in item_variants_data:
        item_code, attribute, attribute_value = row
        # (attr, value) => [item1, item2]
        attribute_value_item_map.setdefault((attribute, attribute_value), []).append(
            item_code
        )
        # item => {attr1: value1, attr2: value2}
        item_attribute_value_map.setdefault(item_code, {})[attribute] = attribute_value

    optional_attributes = set()
    for item_code, attr_dict in item_attribute_value_map.items():
        for attribute in attributes:
            if attribute not in attr_dict:
                optional_attributes.add(attribute)

    frappe.cache().hset(
        "attribute_value_item_map", parent_item_code, attribute_value_item_map
    )
    frappe.cache().hset(
        "item_attribute_value_map", parent_item_code, item_attribute_value_map
    )
    frappe.cache().hset("item_variants_data", parent_item_code, item_variants_data)
    frappe.cache().hset("optional_attributes", parent_item_code, optional_attributes)


def get_item_optional_attributes(item_code):
    val = frappe.cache().hget("optional_attributes", item_code)

    if not val:
        build_item_cache(item_code)

    return frappe.cache().hget("optional_attributes", item_code)


@frappe.whitelist()
def get_item_attributes(item_code):
    attributes = frappe.db.get_all(
        "Item Variant Attribute",
        fields=["attribute"],
        filters={"parenttype": "Item", "parent": item_code},
        order_by="idx asc",
    )

    optional_attributes = get_item_optional_attributes(item_code)

    for a in attributes:
        values = frappe.db.get_all(
            "Item Attribute Value",
            fields=["attribute_value", "abbr"],
            filters={"parenttype": "Item Attribute", "parent": a.attribute},
            order_by="idx asc",
        )
        a.values = values
        if a.attribute in optional_attributes:
            a.optional = True

    return attributes


@frappe.whitelist()
def create_payment_request(doc):
    doc = json.loads(doc)
    for pay in doc.get("payments"):
        if pay.get("type") == "Phone":
            if pay.get("amount") <= 0:
                frappe.throw(_("Payment amount cannot be less than or equal to 0"))

            if not doc.get("contact_mobile"):
                frappe.throw(_("Please enter the phone number first"))

            pay_req = get_existing_payment_request(doc, pay)
            if not pay_req:
                pay_req = get_new_payment_request(doc, pay)
                pay_req.submit()
            else:
                pay_req.request_phone_payment()

            return pay_req


def get_new_payment_request(doc, mop):
    payment_gateway_account = frappe.db.get_value(
        "Payment Gateway Account",
        {
            "payment_account": mop.get("account"),
        },
        ["name"],
    )

    args = {
        "dt": "Sales Invoice",
        "dn": doc.get("name"),
        "recipient_id": doc.get("contact_mobile"),
        "mode_of_payment": mop.get("mode_of_payment"),
        "payment_gateway_account": payment_gateway_account,
        "payment_request_type": "Inward",
        "party_type": "Customer",
        "party": doc.get("customer"),
        "return_doc": True,
    }
    return make_payment_request(**args)


def get_payment_gateway_account(args):
    return frappe.db.get_value(
        "Payment Gateway Account",
        args,
        ["name", "payment_gateway", "payment_account", "message"],
        as_dict=1,
    )


def get_existing_payment_request(doc, pay):
    payment_gateway_account = frappe.db.get_value(
        "Payment Gateway Account",
        {
            "payment_account": pay.get("account"),
        },
        ["name"],
    )

    args = {
        "doctype": "Payment Request",
        "reference_doctype": "Sales Invoice",
        "reference_name": doc.get("name"),
        "payment_gateway_account": payment_gateway_account,
        "email_to": doc.get("contact_mobile"),
    }
    pr = frappe.db.exists(args)
    if pr:
        return frappe.get_doc("Payment Request", pr)


def make_payment_request(**args):
    """Make payment request"""

    args = frappe._dict(args)

    ref_doc = frappe.get_doc(args.dt, args.dn)
    gateway_account = get_payment_gateway_account(args.get("payment_gateway_account"))
    if not gateway_account:
        frappe.throw(_("Payment Gateway Account not found"))

    grand_total = get_amount(ref_doc, gateway_account.get("payment_account"))
    if args.loyalty_points and args.dt == "Sales Order":
        from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
            validate_loyalty_points,
        )

        loyalty_amount = validate_loyalty_points(ref_doc, int(args.loyalty_points))
        frappe.db.set_value(
            "Sales Order",
            args.dn,
            "loyalty_points",
            int(args.loyalty_points),
            update_modified=False,
        )
        frappe.db.set_value(
            "Sales Order",
            args.dn,
            "loyalty_amount",
            loyalty_amount,
            update_modified=False,
        )
        grand_total = grand_total - loyalty_amount

    bank_account = (
        get_party_bank_account(args.get("party_type"), args.get("party"))
        if args.get("party_type")
        else ""
    )

    existing_payment_request = None
    if args.order_type == "Shopping Cart":
        existing_payment_request = frappe.db.get_value(
            "Payment Request",
            {
                "reference_doctype": args.dt,
                "reference_name": args.dn,
                "docstatus": ("!=", 2),
            },
        )

    if existing_payment_request:
        frappe.db.set_value(
            "Payment Request",
            existing_payment_request,
            "grand_total",
            grand_total,
            update_modified=False,
        )
        pr = frappe.get_doc("Payment Request", existing_payment_request)
    else:
        if args.order_type != "Shopping Cart":
            existing_payment_request_amount = get_existing_payment_request_amount(
                args.dt, args.dn
            )

            if existing_payment_request_amount:
                grand_total -= existing_payment_request_amount

        pr = frappe.new_doc("Payment Request")
        pr.update(
            {
                "payment_gateway_account": gateway_account.get("name"),
                "payment_gateway": gateway_account.get("payment_gateway"),
                "payment_account": gateway_account.get("payment_account"),
                "payment_channel": gateway_account.get("payment_channel"),
                "payment_request_type": args.get("payment_request_type"),
                "currency": ref_doc.currency,
                "grand_total": grand_total,
                "mode_of_payment": args.mode_of_payment,
                "email_to": args.recipient_id or ref_doc.owner,
                "subject": _("Payment Request for {0}").format(args.dn),
                "message": gateway_account.get("message") or get_dummy_message(ref_doc),
                "reference_doctype": args.dt,
                "reference_name": args.dn,
                "party_type": args.get("party_type") or "Customer",
                "party": args.get("party") or ref_doc.get("customer"),
                "bank_account": bank_account,
            }
        )

        if args.order_type == "Shopping Cart" or args.mute_email:
            pr.flags.mute_email = True

        pr.insert(ignore_permissions=True)
        if args.submit_doc:
            pr.submit()

    if args.order_type == "Shopping Cart":
        frappe.db.commit()
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = pr.get_payment_url()

    if args.return_doc:
        return pr

    return pr.as_dict()


def get_amount(ref_doc, payment_account=None):
    """get amount based on doctype"""
    grand_total = 0
    for pay in ref_doc.payments:
        if pay.type == "Phone" and pay.account == payment_account:
            grand_total = pay.amount
            break

    if grand_total > 0:
        return grand_total

    else:
        frappe.throw(
            _("Payment Entry is already created or payment account is not matched")
        )

@frappe.whitelist()
def search_bundle_sku(bundle_sku, company):
    bundles = []
    bundle_items = frappe.get_all(
        "Product Bundle Item",
        filters={"parent": bundle_sku},
        fields=["item_code as bundle_sku","description","qty"])
    if len(bundle_items):
        bundles = [i for i in bundle_items]
    # frappe.log_error(message=bundles, title="Bundle Items")
    return bundles

@frappe.whitelist()
def get_pos_coupon(coupon, customer, company):
    res = check_coupon_code(coupon, customer, company)
    return res


@frappe.whitelist()
def get_active_gift_coupons(customer, company):
    coupons = []
    coupons_data = frappe.get_all(
        "POS Coupon",
        filters={
            "company": company,
            "coupon_type": "Gift Card",
            "customer": customer,
            "used": 0,
        },
        fields=["coupon_code"],
    )
    if len(coupons_data):
        coupons = [i.coupon_code for i in coupons_data]
    return coupons


@frappe.whitelist()
def get_customer_info(customer):
    customer = frappe.get_doc("Customer", customer)

    res = {"loyalty_points": None, "conversion_factor": None}
    # res["custom_b2c"] = customer.custom_b2c
    # res["custom_buyer_id_type"] = customer.custom_buyer_id_type
    res["email_id"] = customer.email_id
    res["mobile_no"] = customer.mobile_no
    res["image"] = customer.image
    res["loyalty_program"] = customer.loyalty_program
    res["customer_price_list"] = customer.default_price_list
    res["customer_group"] = customer.customer_group
    res["customer_type"] = customer.customer_type
    res["territory"] = customer.territory
    res["birthday"] = customer.posa_birthday
    res["gender"] = customer.gender
    res["tax_id"] = customer.tax_id
    res["posa_discount"] = customer.posa_discount
    res["name"] = customer.name
    res["customer_name"] = customer.customer_name
    res["customer_group_price_list"] = frappe.get_value(
        "Customer Group", customer.customer_group, "default_price_list"
    )

    if customer.loyalty_program:
        lp_details = get_loyalty_program_details_with_points(
            customer.name,
            customer.loyalty_program,
            silent=True,
            include_expired_entry=False,
        )
        res["loyalty_points"] = lp_details.get("loyalty_points")
        res["conversion_factor"] = lp_details.get("conversion_factor")

    return res


def get_company_domain(company):
    return frappe.get_cached_value("Company", cstr(company), "domain")


@frappe.whitelist()
def get_applicable_delivery_charges(
    company, pos_profile, customer, shipping_address_name=None
):
    return _get_applicable_delivery_charges(
        company, pos_profile, customer, shipping_address_name
    )


def auto_create_items():
    # create 20000 items
    for i in range(20000):
        item_code = "AUTO-ITEM-{}".format(i)
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_code,
                "description": item_code,
                "item_group": "Auto Items",
                "is_stock_item": 0,
                "stock_uom": "Nos",
                "is_sales_item": 1,
                "is_purchase_item": 0,
                "is_fixed_asset": 0,
                "is_sub_contracted_item": 0,
                "is_pro_applicable": 0,
                "is_manufactured_item": 0,
                "is_service_item": 0,
                "is_non_stock_item": 0,
                "is_batch_item": 0,
                "is_table_item": 0,
                "is_variant_item": 0,
                "is_stock_item": 1,
                "opening_stock": 1000,
                "valuation_rate": 50 + i,
                "standard_rate": 100 + i,
            }
        )
        print("Creating Item: {}".format(item_code))
        item.insert(ignore_permissions=True)
        frappe.db.commit()


@frappe.whitelist()
def search_serial_or_batch_or_barcode_number(search_value, search_serial_no):
    # search barcode no
    barcode_data = frappe.db.get_value(
        "Item Barcode",
        {"barcode": search_value},
        ["barcode", "parent as item_code"],
        as_dict=True,
    )
    if barcode_data:
        return barcode_data
    # search serial no
    if search_serial_no:
        serial_no_data = frappe.db.get_value(
            "Serial No", search_value, ["name as serial_no", "item_code"], as_dict=True
        )
        if serial_no_data:
            return serial_no_data
    # search batch no
    batch_no_data = frappe.db.get_value(
        "Batch", search_value, ["name as batch_no", "item as item_code"], as_dict=True
    )
    if batch_no_data:
        return batch_no_data
    return {}


def get_seearch_items_conditions(item_code, serial_no, batch_no, barcode):
    if serial_no or batch_no or barcode:
        return " and name = {0}".format(frappe.db.escape(item_code))

    escaped = frappe.db.escape("%" + item_code + "%")
    return """ and (
        name like {escaped}
        or item_name like {escaped}
    )""".format(escaped=escaped)



@frappe.whitelist()
def create_sales_invoice_from_order(sales_order):
    sales_invoice = make_sales_invoice(sales_order, ignore_permissions=True)
    sales_invoice.save()
    return sales_invoice


@frappe.whitelist()
def delete_sales_invoice(sales_invoice):
    frappe.delete_doc("Sales Invoice", sales_invoice)


@frappe.whitelist()
def get_sales_invoice_child_table(sales_invoice, sales_invoice_item):
    parent_doc = frappe.get_doc("Sales Invoice", sales_invoice)
    child_doc = frappe.get_doc(
        "Sales Invoice Item", {"parent": parent_doc.name, "name": sales_invoice_item}
    )
    return child_doc

# def _add_payments_to_return_invoice(invoice_doc):
#     invoice_doc.payments = []  # Reset existing payments
#     pos_profile = frappe.get_doc("POS Profile", invoice_doc.pos_profile)

#     full_amount = abs(invoice_doc.grand_total or invoice_doc.total or 0)

#     first_payment_set = False

#     for payment_method in pos_profile.payments:
#         if payment_method.allow_in_returns:

#             amount = full_amount if not first_payment_set else 0
#             first_payment_set = True  # Only the first allowed method gets the full amount

#             invoice_doc.append("payments", {
#                 "mode_of_payment": payment_method.mode_of_payment,
#                 "account": payment_method.account,
#                 "amount": amount,
#                 "default": payment_method.default,
#                 "allow_in_returns": payment_method.allow_in_returns
#             })
 # Use only the first allowed payment mode by default

def _add_payments_to_return_invoice(invoice_doc):
    invoice_doc.payments = [] # reset payments
    pos_profile = frappe.get_doc("POS Profile", invoice_doc.pos_profile)
    
    # frappe.log_error("amount 1", invoice_doc.rounded_total)
    # frappe.log_error("amount 2", invoice_doc.payments)

    for payment_method in pos_profile.payments:
        if  payment_method.allow_in_returns:
            invoice_doc.append("payments", {
                # "amount": invoice_doc.rounded_total or invoice_doc.grand_total,
                "mode_of_payment": payment_method.mode_of_payment,
                "allow_in_returns": payment_method.allow_in_returns,
        })
    # frappe.log_error("amount 1", invoice_doc.rounded_total)
    frappe.log_error("amount 2", invoice_doc.payments[0].amount)


# @frappe.whitelist()
# def get_item_location(item_code, warehouse):
# 	item_location = frappe.db.sql("""select item_location from `tabItem Location`
# 			where item_code=%s and warehouse=%s""", (item_code, warehouse), as_dict=1)
# 	return item_location[0].item_location if item_location else ""




# @frappe.whitelist()
# def get_wholesale_rates(pos_profile, item_code):
#     wholesale_profiles = [
#         "Wholesale POS",
#         "Wholesale - Western",
#         "Wholesale - Eastern",
#         "Wholesale - Central",
#         "Orange Station POS",
#         "Wholesale Central 2 POS",
#     ]

#     if pos_profile in wholesale_profiles:
#         wholesale_price_list = frappe.get_value("POS Profile", pos_profile, "selling_price_list")
#         # rate_field  = pos_profile.get("custom_wholesale_rate") or "wholesale_rate"
#         wholesale_rate = frappe.get_value(
#             "Item Price",
#             {
#                 "item_code": item_code,
#                 "price_list": wholesale_price_list,
#             },
#             "wholesale_rate",
#         ) or 0
#         return wholesale_rate

#     return None

@frappe.whitelist()
def get_wholesale_rates(pos_profile, item_code):
    wholesale_profiles = [
        "Wholesale POS",
        "Wholesale - Western",
        "Wholesale - Eastern",
        "Wholesale - Central",
        "Orange Station POS",
        "Wholesale Central 2 POS",
    ]

    if pos_profile in wholesale_profiles:
        pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
        wholesale_price_list = pos_profile_doc.selling_price_list
        rate_field = pos_profile_doc.get("custom_wholesale_rate") or "wholesale_rate"

        wholesale_rate = frappe.get_value(
            "Item Price",
            {
                "item_code": item_code,
                "price_list": wholesale_price_list,
            },
            rate_field,
        ) or 0

        return wholesale_rate

    return     