<template>
  <div>
    <v-card
      class="selection mx-auto bg-grey-lighten-5 pa-1"
      style="max-height: 76vh; height: 76vh"
    >
      <v-progress-linear
        :active="loading"
        :indeterminate="loading"
        absolute
        :location="top"
        color="info"
      ></v-progress-linear>
      <div class="overflow-y-auto px-2 pt-2" style="max-height: 75vh">
        <v-row v-if="invoice_doc" class="px-1 py-0">
          <v-col cols="7">
            <v-text-field
              variant="outlined"
              color="primary"
              :label="$t('Paid Amount')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(total_payments)"
              readonly
              :prefix="currencySymbol(invoice_doc.currency)"
              density="compact"
            ></v-text-field>
          </v-col>
          <v-col cols="5">
            <v-text-field
              variant="outlined"
              color="primary"
              :label="$t(diff_lable)"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(computed_diff_payment)"
              readonly
              :prefix="currencySymbol(invoice_doc.currency)"
              density="compact"
            ></v-text-field>
          </v-col>

          <v-col cols="7" v-if="diff_payment < 0 && !invoice_doc.is_return">
            <v-text-field
              variant="outlined"
              color="primary"
              :label="$t('Paid Change')"
              bg-color="white"
              v-model="paid_change"
              @update:model-value="set_paid_change()"
              :prefix="currencySymbol(invoice_doc.currency)"
              :rules="paid_change_rules"
              density="compact"
              readonly
              type="number"
            ></v-text-field>
          </v-col>

          <v-col cols="5" v-if="diff_payment < 0 && !invoice_doc.is_return">
            <v-text-field
              variant="outlined"
              color="primary"
              :label="$t('Credit Change')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(credit_change)"
              readonly
              :prefix="currencySymbol(invoice_doc.currency)"
              density="compact"
            ></v-text-field>
          </v-col>
        </v-row>
        <v-divider></v-divider>

        <div v-if="is_cashback">
          <v-row
            class="pyments px-1 py-0"
            v-for="payment in invoice_doc.payments"
            :key="payment.name"
          >

            <v-col cols="6" v-if="!is_mpesa_c2b_payment(payment)">
              <v-text-field
                density="compact"
                variant="outlined"
                color="primary"
                :label="$t(payment.mode_of_payment)"
                bg-color="white"
                hide-details
                v-model="payment.amount"
                type="number"
                @input="$forceUpdate()"
                :rules="[isNumber]"
                :prefix="currencySymbol(invoice_doc.currency)"
                @focus="set_rest_amount(payment.idx)"
                :readonly="invoice_doc.is_return ? false : false"
              />
            </v-col>

            <v-col
              v-if="!is_mpesa_c2b_payment(payment)"
              :cols="
                6
                  ? (payment.type != 'Phone' ||
                      payment.amount == 0 ||
                      !request_payment_field) &&
                    !is_mpesa_c2b_payment(payment)
                  : 3
              "
            >
              <v-btn
                block
                class=""
                color="primary"
                theme="dark"
                @click="set_full_amount(payment)"
                >{{ $t(payment.mode_of_payment) }}</v-btn
              >
            </v-col>
            <v-col v-if="is_mpesa_c2b_payment(payment)" :cols="12" class="pl-3">
              <v-btn
                block
                class=""
                color="success"
                theme="dark"
                @click="mpesa_c2b_dialg(payment)"
              >
                {{ $t("Get Payments {paymentMethod}", { paymentMethod: payment.mode_of_payment }) }}
              </v-btn>
            </v-col>
            <v-col
              v-if="
                payment.type == 'Phone' &&
                payment.amount > 0 &&
                request_payment_field
              "
              :cols="3"
              class="pl-1"
            >
              <v-btn
                block
                class=""
                color="success"
                theme="dark"
                :disabled="payment.amount == 0"
                @click="
                  (phone_dialog = true),
                    (payment.amount = flt(payment.amount, 0))
                "
              >
                {{ $t("Request") }}
              </v-btn>
            </v-col>
          </v-row>
        </div>

        <v-row
          class="pyments px-1 py-0"
          v-if="
            invoice_doc &&
            available_pioints_amount > 0 &&
            !invoice_doc.is_return
          "
        >
          <v-col cols="7">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('Redeem Loyalty Points')"
              bg-color="white"
              hide-details
              v-model="loyalty_amount"
              type="number"
              :prefix="currencySymbol(invoice_doc.currency)"
            ></v-text-field>
          </v-col>
          <v-col cols="5">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('You can redeem upto')"
              bg-color="white"
              hide-details
              :model-value="formatFloat(available_pioints_amount)"
              :prefix="currencySymbol(invoice_doc.currency)"
              disabled
            ></v-text-field>
          </v-col>
        </v-row>

        <v-row
          class="pyments px-1 py-0"
          v-if="
            invoice_doc &&
            available_customer_credit > 0 &&
            !invoice_doc.is_return &&
            redeem_customer_credit
          "
        >
          <v-col cols="7">
            <v-text-field
              density="compact"
              variant="outlined"
              disabled
              color="primary"
              :label="$t('Redeemed Customer Credit')"
              bg-color="white"
              hide-details
              v-model="redeemed_customer_credit"
              type="number"
              :prefix="currencySymbol(invoice_doc.currency)"
            ></v-text-field>
          </v-col>
          <v-col cols="5">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('You can redeem credit upto')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(available_customer_credit)"
              :prefix="currencySymbol(invoice_doc.currency)"
              disabled
            ></v-text-field>
          </v-col>
        </v-row>
        <v-divider></v-divider>

        <v-row class="px-1 py-0">
          <v-col cols="6">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('Net Total')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(invoice_doc.net_total)"
              disabled
              :prefix="currencySymbol(invoice_doc.currency)"
            ></v-text-field>
          </v-col>
          <v-col cols="6">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('Tax and Charges')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(invoice_doc.total_taxes_and_charges)"
              disabled
              :prefix="currencySymbol(invoice_doc.currency)"
            ></v-text-field>
          </v-col>
          <v-col cols="6">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('Total Amount')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(invoice_doc.total)"
              disabled
              :prefix="currencySymbol(invoice_doc.currency)"
            ></v-text-field>
          </v-col>
          <v-col cols="6">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('Discount Amount')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(invoice_doc.discount_amount)"
              disabled
              :prefix="currencySymbol(invoice_doc.currency)"
            ></v-text-field>
          </v-col>
          <v-col cols="6">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('Grand Total')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(invoice_doc.grand_total)"
              disabled
              :prefix="currencySymbol(invoice_doc.currency)"
            ></v-text-field>
          </v-col>
          <v-col v-if="invoice_doc.rounded_total" cols="6">
            <v-text-field
              density="compact"
              variant="outlined"
              color="primary"
              :label="$t('Rounded Total')"
              bg-color="white"
              hide-details
              :model-value="formatCurrency(invoice_doc.base_rounded_total)"
              disabled
              :prefix="currencySymbol(invoice_doc.currency)"
            ></v-text-field>
          </v-col>
          <v-col
            cols="6"
            v-if="pos_profile.posa_allow_sales_order && invoiceType == 'Order'"
          >
            <v-menu
              ref="order_delivery_date"
              v-model="order_delivery_date"
              :close-on-content-click="false"
              transition="scale-transition"
              density="default"
            >
              <template v-slot:activator="{ props }">
                <v-text-field
                  v-model="invoice_doc.posa_delivery_date"
                  :label="$t('Delivery Date')"
                  readonly
                  variant="outlined"
                  density="compact"
                  bg-color="white"
                  clearable
                  color="primary"
                  hide-details
                  v-bind="props"
                ></v-text-field>
              </template>
              <v-date-picker
                :v-model="new Date(invoice_doc.posa_delivery_date)"
                no-title
                scrollable
                color="primary"
                :min="frappe.datetime.now_date()"
                @input="order_delivery_date = false"
              >
              </v-date-picker>
            </v-menu>
          </v-col>
          <v-col cols="12" v-if="invoice_doc.posa_delivery_date">
            <v-autocomplete
              density="compact"
              clearable
              auto-select-first
              variant="outlined"
              color="primary"
              :label="$t('Address')"
              v-model="invoice_doc.shipping_address_name"
              :items="addresses"
              item-title="address_title"
              item-value="name"
              bg-color="white"
              no-data-text="Address not found"
              hide-details
              :customFilter="addressFilter"
              append-icon="mdi-plus"
              @click:append="new_address"
            >
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props">
                  <v-list-item-title class="text-primary text-subtitle-1">
                    <div v-html="item.raw.address_title"></div>
                  </v-list-item-title>
                  <v-list-item-title>
                    <div v-html="item.raw.address_line1"></div>
                  </v-list-item-title>
                  <v-list-item-subtitle
                    v-if="item.raw.custoaddress_line2mer_name"
                  >
                    <div v-html="item.raw.address_line2"></div>
                  </v-list-item-subtitle>
                  <v-list-item-subtitle v-if="item.raw.city">
                    <div v-html="item.raw.city"></div>
                  </v-list-item-subtitle>
                  <v-list-item-subtitle v-if="item.raw.state">
                    <div v-html="item.raw.state"></div>
                  </v-list-item-subtitle>
                  <v-list-item-subtitle v-if="item.raw.country">
                    <div v-html="item.raw.mobile_no"></div>
                  </v-list-item-subtitle>
                  <v-list-item-subtitle v-if="item.raw.address_type">
                    <div v-html="item.raw.address_type"></div>
                  </v-list-item-subtitle>
                </v-list-item>
              </template>
            </v-autocomplete>
          </v-col>
          <v-col cols="12" v-if="pos_profile.posa_display_additional_notes">
            <v-textarea
              class="pa-0"
              variant="outlined"
              density="compact"
              bg-color="white"
              clearable
              color="primary"
              auto-grow
              rows="2"
              :label="$t('Additional Notes')"
              v-model="invoice_doc.posa_notes"
              :model-value="invoice_doc.posa_notes"
            ></v-textarea>
          </v-col>
        </v-row>

        <div v-if="pos_profile.posa_allow_customer_purchase_order">
          <v-divider></v-divider>
          <v-row class="px-1 py-0" justify="center" align="start">
            <v-col cols="6">
              <v-text-field
                v-model="invoice_doc.po_no"
                :label="$t('Purchase Order')"
                variant="outlined"
                density="compact"
                bg-color="white"
                clearable
                color="primary"
                hide-details
              ></v-text-field>
            </v-col>
            <v-col cols="6">
              <v-menu
                ref="po_date_menu"
                v-model="po_date_menu"
                :close-on-content-click="false"
                transition="scale-transition"
              >
                <template v-slot:activator="{ props }">
                  <v-text-field
                    v-model="invoice_doc.po_date"
                    :label="$t('Purchase Order Date')"
                    readonly
                    variant="outlined"
                    density="compact"
                    hide-details
                    v-bind="props"
                    color="primary"
                  ></v-text-field>
                </template>
                <v-date-picker
                  v-model="invoice_doc.po_date"
                  no-title
                  scrollable
                  color="primary"
                  @input="po_date_menu = false"
                >
                </v-date-picker>
              </v-menu>
            </v-col>
          </v-row>
        </div>
        <v-divider></v-divider>
        <v-row class="px-1 py-0" align="start" no-gutters>
          <v-col
            cols="6"
            v-if="
              pos_profile.posa_allow_write_off_change &&
              diff_payment > 0 &&
              !invoice_doc.is_return
            "
          >
            <v-switch
              class="my-0 py-0"
              v-model="is_write_off_change"
              flat
              :label="$t('Write Off Difference Amount')"
            ></v-switch>
          </v-col>
          <v-col
            cols="6"
            v-if="pos_profile.posa_allow_credit_sale && !invoice_doc.is_return"
          >
            <v-switch
              v-model="is_credit_sale"
              :label="$t('Credit Sale?')"
            ></v-switch>
          </v-col>
          <v-col
            cols="6"
            v-if="invoice_doc.is_return && pos_profile.use_cashback"
          >
            <v-switch
              v-model="is_cashback"
              flat
              :label="$t('Cashback?')"
              class="my-0 py-0"
            ></v-switch>
          </v-col>
          <v-col cols="6" v-if="invoice_doc.is_return">
            <v-switch
              v-model="include_payment"
              flat
              :label="$t('Use Credit Sale')"
              class="my-0 py-0"
            ></v-switch>
          </v-col>

          <v-col cols="6" v-if="is_credit_sale">
            <v-menu
              ref="date_menu"
              v-model="date_menu"
              :close-on-content-click="false"
              transition="scale-transition"
            >
              <template v-slot:activator="{ props }">
                <v-text-field
                  v-model="invoice_doc.due_date"
                  :label="$t('Due Date')"
                  readonly
                  variant="outlined"
                  density="compact"
                  hide-details
                  v-bind="props"
                  color="primary"
                ></v-text-field>
              </template>
              <v-date-picker
                v-model="credit_sales_due_date"
                no-title
                scrollable
                color="primary"
                :min="frappe.datetime.now_date()"
                @input="date_menu = false"
              >
              </v-date-picker>
            </v-menu>
          </v-col>
          <v-col
            cols="6"
            v-if="!invoice_doc.is_return && pos_profile.use_customer_credit"
          >
            <v-switch
              v-model="redeem_customer_credit"
              flat
              :label="$t('Use Customer Credit')"
              class="my-0 py-0"
              @update:model-value="get_available_credit($event)"
            ></v-switch>
          </v-col>
        </v-row>
        <div
          v-if="
            invoice_doc &&
            available_customer_credit > 0 &&
            !invoice_doc.is_return &&
            redeem_customer_credit
          "
        >
          <v-row v-for="(row, idx) in customer_credit_dict" :key="idx">
            <v-col cols="4">
              <div class="pa-2 py-3">{{ row.credit_origin }}</div>
            </v-col>
            <v-col cols="4">
              <v-text-field
                density="compact"
                variant="outlined"
                color="primary"
                :label="$t('Available Credit')"
                bg-color="white"
                hide-details
                :model-value="formatCurrency(row.total_credit)"
                disabled
                :prefix="currencySymbol(invoice_doc.currency)"
              ></v-text-field>
            </v-col>
            <v-col cols="4">
              <v-text-field
                density="compact"
                variant="outlined"
                color="primary"
                :label="$t('Redeem Credit')"
                bg-color="white"
                hide-details
                type="number"
                v-model="row.credit_to_redeem"
                :prefix="currencySymbol(invoice_doc.currency)"
              ></v-text-field>
            </v-col>
          </v-row>
        </div>
        <v-divider></v-divider>
        <v-row class="pb-0 mb-2" align="start">
          <v-col cols="12">
            <v-autocomplete
              density="compact"
              clearable
              variant="outlined"
              color="primary"
              :label="$t('Sales Person') + ' *'"
              v-model="sales_person"
              :items="sales_persons"
              item-title="sales_person_name"
              item-value="name"
              bg-color="white"
              :no-data-text="$t('Sales Person not found')"
              hide-details
              :customFilter="salesPersonFilter"
              :disabled="readonly"
            >
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props">
                  <v-list-item-title class="text-primary text-subtitle-1">
                    <div v-html="item.raw.sales_person_name"></div>
                  </v-list-item-title>
                  <v-list-item-subtitle
                    v-if="item.raw.sales_person_name != item.raw.name"
                  >
                    <div v-html="`ID: ${item.raw.name}`"></div>
                  </v-list-item-subtitle>
                </v-list-item>
              </template>
            </v-autocomplete>
          </v-col>
        </v-row>
      </div>
    </v-card>


    <v-card flat class="cards mb-0 mt-3 py-0">
      <v-row align="start" no-gutters>
        <v-col cols="6">
          <v-btn
            block
            size="large"
            color="primary"
            theme="dark"
            @click="submit"
            :disabled="vaildatPayment"
            >{{ $t("Submit") }}</v-btn
          >
        </v-col>
        <v-col cols="6" class="pl-1">
          <v-btn
            block
            size="large"
            color="success"
            theme="dark"
            @click="submit(undefined, false, true)"
            :disabled="vaildatPayment"
            >{{ $t("Submit & Print") }}</v-btn
          >
        </v-col>
        <v-col cols="12">
          <v-btn
            block
            class="mt-2 pa-1"
            size="large"
            color="error"
            theme="dark"
            @click="back_to_invoice"
            >{{ $t("Cancel Payment") }}</v-btn
          >
        </v-col>
      </v-row>
    </v-card>
    <div>
      <v-dialog v-model="phone_dialog" max-width="400px">
        <v-card>
          <v-card-title>
            <span class="text-h5 text-primary">{{
              $t("Confirm Mobile Number")
            }}</span>
          </v-card-title>
          <v-card-text class="pa-0">
            <v-container>
              <v-text-field
                density="compact"
                variant="outlined"
                color="primary"
                :label="$t('Mobile Number')"
                bg-color="white"
                hide-details
                v-model="invoice_doc.contact_mobile"
                type="number"
              ></v-text-field>
            </v-container>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn color="error" theme="dark" @click="phone_dialog = false">{{
              $t("Close")
            }}</v-btn>
            <v-btn color="primary" theme="dark" @click="request_payment">{{
              $t("Request")
            }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>
  </div>
</template>

<script>
import { th } from "vuetify/locale";
import format from "../../format";
export default {
  mixins: [format],
  data: () => ({
    bank_draft_approved: false,
    custom_discount_level: null,
    include_payment: false,
    loading: false,
    pos_profile: "",
    invoice_doc: "",
    loyalty_amount: 0,
    credit_sales_due_date: new Date(frappe.datetime.now_date()),
    is_credit_sale: 0,
    is_write_off_change: 0,
    date_menu: false,
    po_date_menu: false,
    addresses: [],
    sales_persons: [],
    sales_person: "",
    paid_change: 0,
    order_delivery_date: false,
    paid_change_rules: [],
    is_return: false,
    is_cashback: true,
    redeem_customer_credit: false,
    customer_credit_dict: [],
    phone_dialog: false,
    invoiceType: "Invoice",
    pos_settings: "",
    customer_info: "",
    mpesa_modes: [],
  }),

  methods: {

  bank_draft_payment() {
    const vm = this;
    vm.loading = true;
    this.eventBus.emit("freeze", {
      title: this.$t("Processing Bank Draft..."),
    });

    frappe.call({
      method: "posawesome.posawesome.api.posapp.bank_draft_payment",
      args: {
        invoice_name: vm.invoice_doc.name,
        customer: vm.invoice_doc.customer,
        amount: vm.invoice_doc.rounded_total || vm.invoice_doc.grand_total,
      },
    callback(r) {
      vm.loading = false;
      vm.eventBus.emit("unfreeze");
      const data = r.message?.message || r.message;

      if (data && data.final_Status === 1) {
        vm.bank_draft_approved = true;
        vm.bank_draft_transaction_id = data.transaction_id;  // ✅ store temporarily in frontend

        vm.eventBus.emit("show_message", {
          text: vm.$t("Bank Draft Payment Approved"),
          color: "success",
        });
      } else {
        vm.bank_draft_approved = false;
        vm.bank_draft_transaction_id = null;
        vm.eventBus.emit("show_message", {
          text: vm.$t("Bank Draft Denied. Please try again."),
          color: "error",
        });
      }
    },

      error() {
        vm.loading = false;
        vm.bank_draft_approved = false;
        vm.eventBus.emit("unfreeze");
        vm.eventBus.emit("show_message", {
          text: vm.$t("Bank Draft API Request Error"),
          color: "error",
        });
      },
    });
  },


    recalculate_totals() {
      let net_total = 0;
      let total = 0;

      if (this.invoice_doc.items && this.invoice_doc.items.length) {
        this.invoice_doc.items.forEach((item) => {
          net_total += item.amount || 0;
          total += item.amount || 0;
        });
      }

      this.invoice_doc.net_total = this.flt(
        net_total - this.invoice_doc.discount_amount,
        this.currency_precision
      );
      this.invoice_doc.total = this.flt(total, this.currency_precision);

      const taxes = this.invoice_doc.total_taxes_and_charges || 0;
      this.invoice_doc.grand_total = this.flt(
        net_total + taxes - this.invoice_doc.discount_amount,
        this.currency_precision
      );
      this.invoice_doc.rounded_total = this.invoice_doc.grand_total;

      if (this.invoice_doc && this.invoice_doc.payments) {
        this.invoice_doc.payments.forEach((payment, idx) => {
          payment.amount = idx === 0 ? this.invoice_doc.rounded_total : 0;
        });
      }
    },

    update_item_rate(item) {
      if (localStorage.items_storage) {
        try {
          const items = JSON.parse(localStorage.getItem("items_storage"));
          localItem = items.find((i) => i.item_code === item.item_code);
        } catch (e) {
          console.error("Error reading items from localStorage", e);
        }
      }

      if (localItem) {
        item.original_rate = parseFloat(localItem.rate || 0); // add fallback
      }

      const customerGroup = this.customer_group || "";
      const vm = this;
      let rate = item.original_rate || item.rate;

      item.rate = rate;

      item.price_list_rate = item.rate;
      item.amount = item.rate * item.qty;
      item.base_rate = item.rate;
      item.base_price_list_rate = item.rate;
      item.base_amount = item.amount;

      this.recalculate_totals();
    },

    back_to_invoice() {
      this.eventBus.emit("show_payment", "false");
      this.eventBus.emit("set_customer_readonly", false);
    },
    submit(event, payment_received = false, print = false) {
      const hasBankDraft = this.invoice_doc.payments.some(
        (p) =>
          p.mode_of_payment &&
          p.mode_of_payment.toLowerCase() === "bank draft" &&
          p.amount > 0 // ensure it's actually being used
      );

      if (hasBankDraft && !this.bank_draft_approved) {
        this.eventBus.emit("show_message", {
          text: this.$t("❌ Bank Draft not approved. Cannot submit invoice."),
          color: "error",
        });
        frappe.utils.play_sound("error");
        return;
      }
        if (this.loading) {
          this.eventBus.emit("show_message", {
            text: this.$t("Bank Draft in progress. Please wait..."),
            color: "warning",
          });
          return;
        }
      if (!this.is_credit_sale) {
        if (
          this.is_cashback &&
          this.total_payments !==
            (this.invoice_doc.rounded_total || this.invoice_doc.grand_total)
        ) {
          this.eventBus.emit("show_message", {
            text: `The amount paid is not correct`,
            color: "error",
          });
          frappe.utils.play_sound("error");
          return;
        }
      }
      if (this.is_credit_sale) {
        if (this.total_payments !== 0) {
          this.eventBus.emit("show_message", {
            text: `The amount paid is not correct`,
            color: "error",
          });
          frappe.utils.play_sound("error");
          return;
        }
      }

      if (!this.sales_person) {
        this.eventBus.emit("show_message", {
          text: this.$t("Please select a Sales Person before submitting."),
          color: "error",
        });
        frappe.utils.play_sound("error");
        return;
      }
      if (!this.invoice_doc.is_return && this.total_payments < 0) {
        this.eventBus.emit("show_message", {
          text: `Payments not correct`,
          color: "error",
        });
        frappe.utils.play_sound("error");
        return;
      }
      let phone_payment_is_valid = true;
      if (!payment_received) {
        this.invoice_doc.payments.forEach((payment) => {
          if (
            payment.type == "Phone" &&
            ![0, "0", "", null, undefined].includes(payment.amount)
          ) {
            phone_payment_is_valid = false;
          }
        });
        if (!phone_payment_is_valid) {
          this.eventBus.emit("show_message", {
            text: this.$t(
              "Please request phone payment or use other payment method"
            ),
            color: "error",
          });
          frappe.utils.play_sound("error");
          console.error("phone payment not requested");
          return;
        }
      }

      if (
        !this.is_credit_sale &&
        this.is_cashback &&
        !this.pos_profile.posa_allow_partial_payment &&
        this.total_payments <
          (this.invoice_doc.rounded_total || this.invoice_doc.grand_total)
      ) {
        this.eventBus.emit("show_message", {
          text: `The amount paid is not correct`,
          color: "error",
        });
        frappe.utils.play_sound("error");
        return;
      }

      if (
        this.pos_profile.posa_allow_partial_payment &&
        !this.pos_profile.posa_allow_credit_sale &&
        this.total_payments == 0
      ) {
        this.eventBus.emit("show_message", {
          text: `Please enter the amount paid`,
          color: "error",
        });
        frappe.utils.play_sound("error");
        return;
      }

      if (!this.paid_change) this.paid_change = 0;

      if (!(this.invoice_doc.is_return && !this.is_cashback)) {
        if (this.paid_change > -this.diff_payment) {
          this.eventBus.emit("show_message", {
            text: `Paid change can not be greater than total change!`,
            color: "error",
          });
          frappe.utils.play_sound("error");
          return;
        }
      }

      let total_change = this.flt(
        this.flt(this.paid_change) + this.flt(-this.credit_change)
      );

      if (this.is_cashback && total_change != -this.diff_payment) {
        this.eventBus.emit("show_message", {
          text: `Error in change calculations!`,
          color: "error",
        });
        frappe.utils.play_sound("error");
        return;
      }

      let credit_calc_check = this.customer_credit_dict.filter((row) => {
        if (flt(row.credit_to_redeem))
          return flt(row.credit_to_redeem) > flt(row.total_credit);
        else return false;
      });

      if (credit_calc_check.length > 0) {
        this.eventBus.emit("show_message", {
          text: `redeamed credit can not greater than its total.`,
          color: "error",
        });
        frappe.utils.play_sound("error");
        return;
      }

      if (
        !this.invoice_doc.is_return &&
        this.redeemed_customer_credit >
          (this.invoice_doc.rounded_total || this.invoice_doc.grand_total)
      ) {
        this.eventBus.emit("show_message", {
          text: `can not redeam customer credit more than invoice total`,
          color: "error",
        });
        frappe.utils.play_sound("error");
        return;
      }

      this.is_sucessful_invoice = this.submit_invoice(print);
    },
    submit_invoice(print) {
      if (this.bank_draft_transaction_id) {
        this.invoice_doc.payments.forEach(p => {
          if (p.mode_of_payment && p.mode_of_payment.toLowerCase() === "bank draft") {
            p.custom_transaction_id = this.bank_draft_transaction_id;
          }
        });
      }
      let totalPayedAmount = 0;
      this.invoice_doc.payments.forEach((payment) => {
        payment.amount = flt(payment.amount);
        totalPayedAmount += payment.amount;
      });
      if (this.invoice_doc.is_return && this.include_payment) {
        this.invoice_doc.is_pos = 0;
      }
      if (this.invoice_doc.is_return && totalPayedAmount == 0) {
        this.invoice_doc.is_pos = 0;
      }

      if (this.customer_credit_dict.length) {
        this.customer_credit_dict.forEach((row) => {
          row.credit_to_redeem = flt(row.credit_to_redeem);
        });
      }
      let data = {};
      data["total_change"] = !this.invoice_doc.is_return
        ? -this.diff_payment
        : 0;
      data["paid_change"] = !this.invoice_doc.is_return ? this.paid_change : 0;
      data["credit_change"] = -this.credit_change;
      data["redeemed_customer_credit"] = this.redeemed_customer_credit;
      data["customer_credit_dict"] = this.customer_credit_dict;
      data["is_cashback"] = this.is_cashback;

      const vm = this;
      frappe.call({
        method: "posawesome.posawesome.api.posapp.submit_invoice",
        args: {
          data: data,
          invoice: this.invoice_doc,
        },
        async: false,
        callback: function (r) {
          if (!r?.message) {
            vm.eventBus.emit("show_message", {
              text: `Error submitting invoice`,
              color: "error",
            });
            return;
          }
          if (print) {
            vm.load_print_page();
          }
          vm.customer_credit_dict = [];
          vm.redeem_customer_credit = false;
          vm.is_cashback = true;
          vm.sales_person = "";

          vm.eventBus.emit("set_last_invoice", vm.invoice_doc.name);
          vm.eventBus.emit("show_message", {
            text: `Invoice ${r.message.name} is Submited`,
            color: "success",
          });
          //s
          frappe.utils.play_sound("submit");
          vm.addresses = [];
          vm.eventBus.emit("clear_invoice");
          vm.back_to_invoice();
          return;
        },
      });
    },
    set_full_amount(payment) {

      // normal payments → set full amount
      this.invoice_doc.payments.forEach((p) => {
        p.amount =
          p.idx === payment.idx
            ? this.invoice_doc.rounded_total || this.invoice_doc.grand_total
            : 0;
      });

      // if Bank Draft → call API
      if (payment.mode_of_payment?.toLowerCase() === "bank draft") {
        this.bank_draft_payment(payment);
        return; // stop here so it doesn’t overwrite amounts
      }

    },

    set_rest_amount(idx) {
      this.invoice_doc.payments.forEach((payment) => {
        if (
          payment.idx == idx &&
          payment.amount == 0 &&
          this.diff_payment > 0
        ) {
          payment.amount = this.diff_payment;
        }
      });
    },
    clear_all_amounts() {
      this.invoice_doc.payments.forEach((payment) => {
        payment.amount = 0;
      });
    },
    load_print_page() {
      const print_format =
        this.pos_profile.print_format_for_online ||
        this.pos_profile.print_format;
      const letter_head = this.pos_profile.letter_head || 0;
      const url =
        frappe.urllib.get_base_url() +
        "/printview?doctype=Sales%20Invoice&name=" +
        this.invoice_doc.name +
        "&trigger_print=1" +
        "&format=" +
        print_format +
        "&no_letterhead=" +
        letter_head;
      const printWindow = window.open(url, "Print");
      printWindow.addEventListener(
        "load",
        function () {
          printWindow.print();
        },
        true
      );
    },
    validate_due_date() {
      const today = frappe.datetime.now_date();
      const parse_today = Date.parse(today);
      const new_date = Date.parse(this.invoice_doc.due_date);
      if (new_date < parse_today) {
        setTimeout(() => {
          this.invoice_doc.due_date = today;
        }, 0);
      }
    },
    shortPay(e) {
      if (e.key === "x" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        this.submit();
      }
    },
    set_paid_change() {
      if (!this.paid_change) this.paid_change = 0;

      this.paid_change_rules = [];
      let change = -this.diff_payment;
      if (this.paid_change > change) {
        this.paid_change_rules = [
          "Paid change can not be greater than total change!",
        ];
        this.credit_change = 0;
      }
    },
    get_available_credit(e) {
      this.clear_all_amounts();
      if (e) {
        frappe
          .call("posawesome.posawesome.api.posapp.get_available_credit", {
            customer: this.invoice_doc.customer,
            company: this.pos_profile.company,
          })
          .then((r) => {
            const data = r.message;
            if (data.length) {
              const amount =
                this.invoice_doc.rounded_total || this.invoice_doc.grand_total;
              let remainAmount = amount;

              data.forEach((row) => {
                if (remainAmount > 0) {
                  if (remainAmount >= row.total_credit) {
                    row.credit_to_redeem = row.total_credit;
                    remainAmount = remainAmount - row.total_credit;
                  } else {
                    row.credit_to_redeem = remainAmount;
                    remainAmount = 0;
                  }
                } else {
                  row.credit_to_redeem = 0;
                }
              });

              this.customer_credit_dict = data;
            } else {
              this.customer_credit_dict = [];
            }
          });
      } else {
        this.customer_credit_dict = [];
      }
    },
    get_addresses() {
      const vm = this;
      if (!vm.invoice_doc) {
        return;
      }
      frappe.call({
        method: "posawesome.posawesome.api.posapp.get_customer_addresses",
        args: { customer: vm.invoice_doc.customer },
        async: true,
        callback: function (r) {
          if (!r.exc) {
            vm.addresses = r.message;
          } else {
            vm.addresses = [];
          }
        },
      });
    },
    addressFilter(item, queryText, itemText) {
      const textOne = item.address_title
        ? item.address_title.toLowerCase()
        : "";
      const textTwo = item.address_line1
        ? item.address_line1.toLowerCase()
        : "";
      const textThree = item.address_line2
        ? item.address_line2.toLowerCase()
        : "";
      const textFour = item.city ? item.city.toLowerCase() : "";
      const textFifth = item.name.toLowerCase();
      const searchText = queryText.toLowerCase();
      return (
        textOne.indexOf(searchText) > -1 ||
        textTwo.indexOf(searchText) > -1 ||
        textThree.indexOf(searchText) > -1 ||
        textFour.indexOf(searchText) > -1 ||
        textFifth.indexOf(searchText) > -1
      );
    },
    new_address() {
      this.eventBus.emit("open_new_address", this.invoice_doc.customer);
    },

    get_sales_person_names() {
      const vm = this;

      frappe.call({
        method: "posawesome.posawesome.api.posapp.get_sales_person_names",
        callback: function (r) {
          if (r.message) {
            vm.sales_persons = r.message.sales_persons;
            if (!vm.sales_person) {
              vm.sales_person = r.message.default_sales_person || "";
            }
            if (vm.pos_profile.posa_local_storage) {
              localStorage.setItem(
                "sales_persons_storage",
                JSON.stringify(r.message)
              );
            }
          }
        },
      });
    },

    salesPersonFilter(itemText, queryText, itemRow) {
      const item = itemRow.raw;
      const textOne = item.sales_person_name
        ? item.sales_person_name.toLowerCase()
        : "";
      const textTwo = item.name.toLowerCase();
      const searchText = queryText.toLowerCase();

      return (
        textOne.indexOf(searchText) > -1 || textTwo.indexOf(searchText) > -1
      );
    },
    request_payment() {
      this.phone_dialog = false;
      const vm = this;
      if (!this.invoice_doc.contact_mobile) {
        this.eventBus.emit("show_message", {
          text: this.$t(`Please Set Customer Mobile Number`),
          color: "error",
        });
        this.eventBus.emit("open_edit_customer");
        this.back_to_invoice();
        return;
      }
      this.eventBus.emit("freeze", {
        title: this.$t('waiting_for_payment'),
      });

      this.invoice_doc.payments.forEach((payment) => {
        payment.amount = flt(payment.amount);
      });
      let formData = { ...this.invoice_doc };
      formData["total_change"] = -this.diff_payment;
      formData["paid_change"] = this.paid_change;
      formData["credit_change"] = -this.credit_change;
      formData["redeemed_customer_credit"] = this.redeemed_customer_credit;
      formData["customer_credit_dict"] = this.customer_credit_dict;
      formData["is_cashback"] = this.is_cashback;

      frappe
        .call({
          method: "posawesome.posawesome.api.posapp.update_invoice",
          args: {
            data: formData,
          },
          async: false,
          callback: function (r) {
            if (r.message) {
              vm.invoice_doc = r.message;
            }
          },
        })
        .then(() => {
          frappe
            .call({
              method: "posawesome.posawesome.api.posapp.create_payment_request",
              args: {
                doc: vm.invoice_doc,
              },
            })
            .fail(() => {
              this.eventBus.emit("unfreeze");
              this.eventBus.emit("show_message", {
                text: this.$t(`Payment request failed`),
                color: "error",
              });
            })
            .then(({ message }) => {
              const payment_request_name = message.name;
              setTimeout(() => {
                frappe.db
                  .get_value("Payment Request", payment_request_name, [
                    "status",
                    "grand_total",
                  ])
                  .then(({ message }) => {
                    if (message.status != "Paid") {
                      this.eventBus.emit("unfreeze");
                      this.eventBus.emit("show_message", {
                        text: this.$t('payment_request_timeout'),
                        color: "error",
                      });
                    } else {
                      this.eventBus.emit("unfreeze");
                      this.eventBus.emit("show_message", {
                        text: this.$t("Payment of {0} received successfully.", [
                          vm.formatCurrency(
                            message.grand_total,
                            vm.invoice_doc.currency,
                            0
                          ),
                        ]),
                        color: "success",
                      });
                      frappe.db
                        .get_doc("Sales Invoice", vm.invoice_doc.name)
                        .then((doc) => {
                          vm.invoice_doc = doc;
                          vm.submit(null, true);
                        });
                    }
                  });
              }, 30000);
            });
        });
    },
    get_mpesa_modes() {
      const vm = this;
      frappe.call({
        method: "posawesome.posawesome.api.m_pesa.get_mpesa_mode_of_payment",
        args: { company: vm.pos_profile.company },
        async: true,
        callback: function (r) {
          if (!r.exc) {
            vm.mpesa_modes = r.message;
          } else {
            vm.mpesa_modes = [];
          }
        },
      });
    },
    is_mpesa_c2b_payment(payment) {
      if (
        this.mpesa_modes.includes(payment.mode_of_payment) &&
        payment.type == "Bank"
      ) {
        payment.amount = 0;
        return true;
      } else {
        return false;
      }
    },
    mpesa_c2b_dialg(payment) {
      const data = {
        company: this.pos_profile.company,
        mode_of_payment: payment.mode_of_payment,
        customer: this.invoice_doc.customer,
      };
      this.eventBus.emit("open_mpesa_payments", data);
    },
    set_mpesa_payment(payment) {
      this.pos_profile.use_customer_credit = 1;
      this.redeem_customer_credit = true;
      const invoiceAmount =
        this.invoice_doc.rounded_total || this.invoice_doc.grand_total;
      let amount =
        payment.unallocated_amount > invoiceAmount
          ? invoiceAmount
          : payment.unallocated_amount;
      if (amount < 0 || !amount) amount = 0;
      const advance = {
        type: "Advance",
        credit_origin: payment.name,
        total_credit: flt(payment.unallocated_amount),
        credit_to_redeem: flt(amount),
      };
      this.clear_all_amounts();
      this.customer_credit_dict.push(advance);
    },
  },

  computed: {
    computed_diff_payment() {
      return this.diff_payment;
    },
    total_payments() {
      let total = 0;

      const wholesaleProfiles = [
        "Wholesale POS",
        "Wholesale - Western",
        "Wholesale - Eastern",
        "Wholesale - Central",
        "Orange Station POS",
        "Wholesale Central 2 POS",
      ];

      const isWholesale = wholesaleProfiles.includes(this.pos_profile?.name);

      if (isWholesale) {
        if (this.invoice_doc && this.invoice_doc.payments) {
          this.invoice_doc.payments.forEach((payment) => {
            total += this.flt(payment.amount);
          });
        }
      } else {
        total = parseFloat(this.invoice_doc.loyalty_amount);

        if (this.invoice_doc && this.invoice_doc.payments) {
          this.invoice_doc.payments.forEach((payment) => {
            total += this.flt(payment.amount);
          });
        }

        total += this.flt(this.redeemed_customer_credit);

        if (!this.is_cashback) total = 0;
      }

      return this.flt(total, this.currency_precision);
    },

    diff_payment() {
      let diff_payment = this.flt(
        (this.invoice_doc.rounded_total || this.invoice_doc.grand_total) -
          this.total_payments,
        this.currency_precision
      );
      this.paid_change = -diff_payment;
      if (this.invoice_doc.is_return && !this.is_cashback) {
        diff_payment = 0;
      }
      return diff_payment;
    },
    credit_change() {
      let change = -this.diff_payment;
      if (this.paid_change > change) return 0;
      return this.flt(this.paid_change - change, this.currency_precision);
    },
    diff_lable() {
      // let label = this.diff_payment < 0 ? "Change" : "To Be Paid";
      let label = this.diff_payment < 0 ? this.$t("Change") : this.$t("To Be Paid");

      return label;
    },
    available_pioints_amount() {
      let amount = 0;
      if (this.customer_info.loyalty_points) {
        amount =
          this.customer_info.loyalty_points *
          this.customer_info.conversion_factor;
      }
      return amount;
    },
    available_customer_credit() {
      let total = 0;
      this.customer_credit_dict.map((row) => {
        total += row.total_credit;
      });

      return total;
    },
    redeemed_customer_credit() {
      let total = 0;
      this.customer_credit_dict.map((row) => {
        if (flt(row.credit_to_redeem)) total += flt(row.credit_to_redeem);
        else row.credit_to_redeem = 0;
      });

      return total;
    },
    vaildatPayment() {
      if (this.pos_profile.posa_allow_sales_order) {
        if (
          this.invoiceType == "Order" &&
          !this.invoice_doc.posa_delivery_date
        ) {
          return true;
        } else {
          return false;
        }
      } else {
        return false;
      }
    },
    request_payment_field() {
      let res = false;
      if (!this.pos_settings || this.pos_settings.invoice_fields.length == 0) {
        res = false;
      } else {
        this.pos_settings.invoice_fields.forEach((el) => {
          if (
            el.fieldtype == "Button" &&
            el.fieldname == "request_for_payment"
          ) {
            res = true;
          }
        });
      }
      return res;
    },
  },

  mounted: function () {
    this.$nextTick(function () {
      this.eventBus.on("send_invoice_doc_payment", (invoice_doc) => {
        this.invoice_doc = invoice_doc;

        console.log("invoice", this.invoice_doc);

        this.is_credit_sale = 0;
        this.is_write_off_change = 0;

        this.invoice_doc.payments.forEach((p) => {
          p.amount = 0;
          p.base_amount = 0;
        });

        if (invoice_doc.is_return) {
          this.is_return = true;

          const returnAmount = this.flt(
            invoice_doc.rounded_total || invoice_doc.grand_total,
            this.currency_precision
          );

          // const cashPayment = this.invoice_doc.payments.find(
          //   (p) =>
          //     p.type === "Cash" &&
          //     p.mode_of_payment.toLowerCase().includes("cash")
          // );


          const translatedCash = this.$t("Cash").toLowerCase();
          const cashPayment = this.invoice_doc.payments.find(
            (p) =>
              p.type.toLowerCase() === translatedCash ||
              p.mode_of_payment.toLowerCase().includes(translatedCash)
          );

          if (cashPayment) {
            cashPayment.amount = returnAmount;
          }
        } else {
          const totalAmount = this.flt(
            invoice_doc.rounded_total || invoice_doc.grand_total,
            this.currency_precision
          );

          const defaultPayment = this.invoice_doc.payments.find(
            (p) => p.default === 1
          );

          if (defaultPayment) {
            defaultPayment.amount = totalAmount;
          }
        }

        this.loyalty_amount = 0;
        this.get_addresses();
        this.get_sales_person_names();
        frappe.call({
          method: "posawesome.posawesome.api.posapp.get_default_sales_person",
          callback: (r) => {
            if (r.message) {
              this.sales_person = r.message.name;
            }
          },
        });
      });

      this.eventBus.on("register_pos_profile", (data) => {
        this.pos_profile = data.pos_profile;
        this.get_mpesa_modes();
      });
      this.eventBus.on("add_the_new_address", (data) => {
        this.addresses.push(data);
        this.$forceUpdate();
      });
      this.eventBus.on("update_invoice_type", (data) => {
        this.invoiceType = data;
        if (this.invoice_doc && data != "Order") {
          this.invoice_doc.posa_delivery_date = null;
          this.invoice_doc.posa_notes = null;
          this.invoice_doc.shipping_address_name = null;
        }
      });
    });
    this.eventBus.on("update_customer", (customer) => {
      if (this.customer != customer) {
        this.customer_credit_dict = [];
        this.redeem_customer_credit = false;
        this.is_cashback = true;
      }
    });
    this.eventBus.on("set_pos_settings", (data) => {
      this.pos_settings = data;
    });
    this.eventBus.on("set_customer_info_to_edit", (data) => {
      this.customer_info = data;
      this.custom_discount_level = data.custom_discount_level || null;
      this.$nextTick(() => {
        if (this.invoice_doc?.items?.length) {
          this.invoice_doc.items.forEach((item) => this.update_item_rate(item));
        }
      });
    });
    this.eventBus.on("set_mpesa_payment", (data) => {
      this.set_mpesa_payment(data);
    });
  },
  created() {
    this.eventBus.on("update_customer_discount_level", (level) => {
      this.custom_discount_level = level;
    });
    this.eventBus.on("update_customer_group", (group) => {
      this.customer_group = group;
    });
    document.addEventListener("keydown", this.shortPay.bind(this));
  },
  beforeUnmount() {
    evntBus.$off("send_invoice_doc_payment");
    evntBus.$off("register_pos_profile");
    evntBus.$off("add_the_new_address");
    evntBus.$off("update_invoice_type");
    evntBus.$off("update_customer");
    evntBus.$off("set_pos_settings");
    evntBus.$off("set_customer_info_to_edit");
    evntBus.$off("update_invoice_coupons");
    evntBus.$off("set_mpesa_ment");
  },

  unmounted() {
    document.removeEventListener("keydown", this.shortPay);
  },

  watch: {
    custom_discount_level: {
      handler(newVal) {
        if (this.invoice_doc && Array.isArray(this.invoice_doc.items)) {
          this.invoice_doc.items.forEach((item) => {
            this.update_item_rate(item);
          });
        }
      },
      immediate: false,
    },

    "invoice_doc.items": {
      async handler(newVal) {
        if (!newVal || !Array.isArray(newVal)) return;

        await Promise.all(newVal.map((item) => this.update_item_rate(item)));
        this.recalculate_totals();
      },
      deep: true,
      immediate: true,
    },

    loyalty_amount(value) {
      if (value > this.available_pioints_amount) {
        this.invoice_doc.loyalty_amount = 0;
        this.invoice_doc.redeem_loyalty_points = 0;
        this.invoice_doc.loyalty_points = 0;
        this.eventBus.emit("show_message", {
          text: `Loyalty Amount can not be more then ${this.available_pioints_amount}`,
          color: "error",
        });
      } else {
        this.invoice_doc.loyalty_amount = this.flt(this.loyalty_amount);
        this.invoice_doc.redeem_loyalty_points = 1;
        this.invoice_doc.loyalty_points =
          this.flt(this.loyalty_amount) / this.customer_info.conversion_factor;
      }
    },
    is_credit_sale(value) {
      if (value) {
        this.invoice_doc.payments.forEach((payment) => {
          payment.amount = 0;
          payment.base_amount = 0;
        });
      }
    },
    credit_sales_due_date(value) {
      this.invoice_doc.due_date = frappe.datetime.get_datetime_as_string(value);
    },
    is_write_off_change(value) {
      if (value == 1) {
        this.invoice_doc.write_off_amount = this.diff_payment;
        this.invoice_doc.write_off_outstanding_amount_automatically = 1;
      } else {
        this.invoice_doc.write_off_amount = 0;
        this.invoice_doc.write_off_outstanding_amount_automatically = 0;
      }
    },
    redeemed_customer_credit(value) {
      if (value > this.available_customer_credit) {
        this.eventBus.emit("show_message", {
          text: `You can redeem customer credit upto ${this.available_customer_credit}`,
          color: "error",
        });
      }
    },
    sales_person() {
      if (this.sales_person) {
        this.invoice_doc.sales_team = [
          {
            sales_person: this.sales_person,
            allocated_percentage: 100,
          },
        ];
      } else {
        this.invoice_doc.sales_team = [];
      }
    },
  },
};
</script>
