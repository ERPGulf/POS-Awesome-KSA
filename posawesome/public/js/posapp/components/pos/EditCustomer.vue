<template>
  <v-row justify="center">
    <v-dialog v-model="customerDialog" max-width="600px" :dir="$i18n.locale === 'ar' ? 'rtl' : 'ltr'">
      <v-card>
        <v-card-title>
          <span class="headline indigo--text">{{ $t("Customer Info") }}</span>
        </v-card-title>
        <v-card-text class="pa-0">
          <v-container>
            <v-row>
              <v-col cols="12">
                <v-text-field
                  dense
                  color="indigo"
                  :label="$t('Customer Name')"
                  background-color="white"
                  hide-details
                  readonly
                  v-model="customer_info.customer_name"
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  dense
                  color="indigo"
                  :label="$t('Email')"
                  background-color="white"
                  hide-details
                  v-model="customer_info.email_id"
                  @change="set_customer_info('email_id', $event)"
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  dense
                  color="indigo"
                  :label="$t('Mobile No')"
                  background-color="white"
                  hide-details
                  v-model="customer_info.mobile_no"
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  v-model="customer_info.loyalty_program"
                  :label="$t('Loyalty Program')"
                  dense
                  readonly
                  hide-details
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  v-model="customer_info.loyalty_points"
                  :label="$t('Loyalty Points')"
                  dense
                  readonly
                  hide-details
                />
              </v-col>

              <v-col cols="6">
                <v-select
                  dense
                  color="indigo"
                  :label="$t('Referral Code') + ' *'"
                  background-color="white"
                  hide-details
                  v-model="referral_code"
                  :items="refcodes"
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  dense
                  color="indigo"
                  :label="$t('Tax ID')"
                  background-color="white"
                  hide-details
                  v-model="customer_info.tax_id"
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  v-model="customer_info.address_line1"
                  :label="$t('Address Line 1')"
                  dense
                  hide-details
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  v-model="customer_info.address_line2"
                  :label="$t('Address Line 2')"
                  dense
                  hide-details
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  v-model="customer_info.pincode"
                  :maxlength="5"
                  :label="$t('Pincode')"
                  dense
                  hide-details
                />
              </v-col>

              <v-col cols="6">
                <v-text-field
                  v-model="customer_info.city"
                  :label="$t('City')"
                  dense
                  hide-details
                />
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" dark @click="save_customer_info">{{ $t("Save") }}</v-btn>
          <v-btn color="error" dark @click="close_dialog">{{ $t("Close") }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-row>
</template>

<script>
export default {
  data: () => ({
    referral_code: "",
    refcodes: [
      "Haraj - حراج",
      "Snap - سناب",
      "Instagram - انستاجرام",
      "Twitter - تويتر",
      "Youtube - يوتيوب",
      "Facebook - فيسبوك",
      "Tik Tok تيك توك",
      "Google - جوجل",
      "Friend - صديق او زميل",
      "Customer - عميل قديم",
      "Wholesale Customer - عميل شركات وجملة",
      "Visitor - زائر محل",
    ],
    original_customer_info: null,
    customerDialog: false,
    customer_info: {
      customer: "",
      customer_name: "",
      email_id: "",
      mobile_no: "",
      loyalty_program: "",
      loyalty_points: 0,
      address_line1: "",
      address_line2: "",
      //custom_building_number: "",
      pincode: "",
      city: "",
      //custom_b2c: false,
      //custom_buyer_id: "",
      tax_id: "",
    },
  }),

  methods: {
    close_dialog() {
      this.customerDialog = false;
    },

    async save_customer_info() {
      const vm = this;

      if (!/^9665\d{8}$/.test(vm.customer_info.mobile_no)) {
        vm.eventBus.emit("show_message", {
          text: vm.$t("Cannot create customer: Mobile number must be 9665XXXXXXXX (12 digits)."),
          color: "error",
        });
        return;
      }




      if (vm.customer_info.address_line1 && !vm.customer_info.city) {
        vm.eventBus.emit("show_message", {
          text: vm.$t("City is mandatory when address is provided!"),
          color: "error",
        });
        return;
      }

      if (vm.customer_info.pincode && !/^\d{5}$/.test(vm.customer_info.pincode)) {
        vm.eventBus.emit("show_message", {
          text: vm.$t("Pincode must be exactly 5 digits!"),
          color: "error",
        });
        return;
      }

      if (!vm.referral_code) {
        vm.eventBus.emit("show_message", {
          text: vm.$t("Referral code is mandatory for customers!"),
          color: "error",
        });
        return;
      }

      const fields_to_update = [
        "mobile_no", "tax_id", "referral_code", "address_line1",
        "address_line2", "pincode", "city",
      ];

      vm.customer_info.referral_code = vm.referral_code;

      for (const field of fields_to_update) {
        await new Promise((resolve) => {
          frappe.call({
            method: "posawesome.posawesome.api.posapp.set_customer_info",
            args: {
              fieldname: field,
              customer: vm.customer_info.customer,
              value: vm.customer_info[field],
            },
            callback: (r) => {
              if (!r.exc) {
                vm.eventBus.emit("show_message", {
                  text: vm.$t("Updated customer"),
                  color: "success",
                });
              }
              resolve();
            },
            error: () => resolve(),
          });
        });
      }

      vm.customerDialog = false;
    },

    set_customer_info(field, value) {
      frappe.call({
        method: "posawesome.posawesome.api.posapp.set_customer_info",
        args: {
          fieldname: field,
          customer: this.customer_info.customer,
          value: value,
        },
        callback: (r) => {
          if (!r.exc) {
            this.customer_info[field] = value;
            this.eventBus.emit("show_message", {
              text: this.$t("Customer contact updated successfully."),
              color: "success",
            });
            frappe.utils.play_sound("submit");
          }
        },
      });
    },
  },

  created() {
    this.eventBus.on("open_edit_customer", () => {
      this.customerDialog = true;
    });

    this.eventBus.on("set_customer_info_to_edit", (data) => {
      this.customer_info = {
        ...data,
        customer: data.name,
      };
      this.referral_code = data.posa_referral_code || "";
      this.original_customer_info = JSON.parse(JSON.stringify(this.customer_info));
      frappe.call({
        method: "posawesome.posawesome.api.posapp.get_customer_address",
        args: { customer_name: data.name },
        callback: (r) => {
          if (r.message) {
            const addr = r.message;
            this.customer_info.address_line1 = addr.address_line1;
            this.customer_info.address_line2 = addr.address_line2;
            this.customer_info.city = addr.city;
            this.customer_info.pincode = addr.pincode;
          }
        },
      });
    });
  },
};
</script>
