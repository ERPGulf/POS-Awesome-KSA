<template>
  <v-row justify="center">
    <v-dialog v-model="customerDialog" max-width="600px">
      <v-card>
        <v-card-title>
          <span class="headline indigo--text">{{ $t("New Customer") }}</span>
        </v-card-title>
        <v-card-text class="pa-0">
          <v-container>
            <v-row>
              <v-col cols="12">
                <v-text-field
                  dense
                  color="indigo"
                  :label="$t('Customer Name')+ ' *'"
                  background-color="white"
                  hide-details
                  v-model="customer_name"
                  :rules="[(v) => !!v || $t('Customer Name is required')]"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  dense
                  color="indigo"
                  :label="$t('Mobile No')+ ' *'"
                  background-color="white"
                  hide-details
                  v-model="mobile_no"
                  placeholder="9665XXXXXXXX"
                  @input="validateInput"
                  :error="!isValid"
                  :maxlength="12"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  dense
                  color="indigo"
                  :label="$t('Email Id')"
                  background-color="white"
                  hide-details
                  v-model="email_id"
                />
              </v-col>
              <v-col cols="6">
                <v-menu
                  ref="birthday_menu"
                  v-model="birthday_menu"
                  :close-on-content-click="false"
                  transition="scale-transition"
                  density="default"
                >
                  <template v-slot:activator="{ props }">
                    <v-text-field
                      v-model="formattedBirthday"
                      @click="birthday_menu = true"
                      :label="$t('Birthday')"
                      readonly
                      density="compact"
                      clearable
                      hide-details
                      v-bind="props"
                      color="primary"
                    />
                  </template>
                  <v-date-picker
                    v-model="birthday"
                    color="primary"
                    no-title
                    scrollable
                    :max="frappe.datetime.now_date()"
                  >
                    <template v-slot:actions>
                      <v-btn
                        text
                        color="primary"
                        @click="birthday_menu = false"
                      >
                        {{ $t("Set") }}
                      </v-btn>
                    </template>
                  </v-date-picker>
                </v-menu>
              </v-col>

            </v-row>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="error" dark @click="close_dialog">{{
            $t("Close")
          }}</v-btn>
          <v-btn color="primary" dark @click="submit_dialog">{{
            $t("Submit")
          }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-row>
</template>
<script>
export default {
  data: () => ({
    customerDialog: false,
    pos_profile: "",
    customer_name: "",
    tax_id: "",
    email_id: "",
    referral_code: "",
    company: "",
    companies: [],
    refcodes: [],
    birthday: new Date(),
    formattedBirthday: "",
    birthday_menu: false,
    group: "",
    groups: [],
    territory: "",
    territorys: [],

    address_line1: "",
    address_line2: "",
    custom_building_number: "",
    pincode: "",

    city: "",
    fixedText: "9665",
    mobile_no: "9665",
    isValid: true,
    isValidPincode: true,
    isValidBuildingNumber: true,
  }),

  computed: {
    isValid() {
      const userInput = this.mobile_no.slice(this.fixedText.length);
      return userInput.length === 8 && /^\d+$/.test(userInput);
    },
  },

  watch: {
    birthday(val) {
      if (val) {
        const date = new Date(val);
        this.formattedBirthday = date.toISOString().slice(0, 10);
      } else {
        this.formattedBirthday = "";
      }
    },
  },

  methods: {
    validatePincode() {
      const isValid = /^\d{5}$/.test(this.pincode);
      this.isValidPincode = isValid;
      if (!isValid) {
        this.eventBus.emit("show_mesage", {
          text: this.$t("Pincode must be exactly 5 digits!"),
          color: "error",
        });
      }
    },

    validateBuildingNumber() {
      const isValid = /^\d{4}$/.test(this.custom_building_number);
      this.isValidBuildingNumber = isValid;
      if (!isValid) {
        this.eventBus.emit("show_mesage", {
          text: this.$t("Building number must be exactly 4 digits!"),
          color: "error",
        });
      }
    },

    close_dialog() {
      this.customerDialog = false;
    },

    validateInput(value) {
      if (!value.startsWith(this.fixedText)) {
        value = this.fixedText;
      }

      let userInput = value
        .slice(this.fixedText.length)
        .replace(/\D/g, "")
        .slice(0, 8);
      this.mobile_no = this.fixedText + userInput;

      this.isValid = /^9665\d{8}$/.test(this.mobile_no);

      if (!this.isValid) {
        this.eventBus.emit("show_mesage", {
          text: this.$t(
            "Mobile number must start with 9665 and be exactly 12 digits."
          ),
          color: "error",
        });
      }

      return this.isValid;
    },

    getCustomerGroups() {
      const vm = this;
      frappe.call({
        method: "posawesome.posawesome.api.posapp.get_customers_groups",
        args: {
          posProfile: JSON.parse(sessionStorage.getItem("cached_pos_profile"))
            .name,
        },
        callback(r) {
          if (r.message) {
            vm.groups = r.message;
          }
        },
      });

      vm.refcodes = [
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
      ];
    },

    getCustomerTerritorys() {
      if (this.territorys.length > 0) return;
      const vm = this;
      frappe.db
        .get_list("Territory", {
          fields: ["name"],
          page_length: 1000,
        })
        .then((data) => {
          data.forEach((el) => {
            vm.territorys.push(el.name);
          });
        });
    },

    getCompanies() {
      if (this.companies.length > 0) return;
      const vm = this;
      frappe.db
        .get_list("Company", {
          fields: ["name"],
          page_length: 1000,
        })
        .then((data) => {
          data.forEach((el) => {
            vm.companies.push(el.name);
          });
        });
    },

    submit_dialog() {
      if (this.customer_name) {
        var vm = this;
        const args = {
          customer_name: this.customer_name,
          company: this.company,
          tax_id: this.tax_id,
          mobile_no: this.mobile_no,
          email_id: this.email_id,
          city: this.city,
          referral_code: this.referral_code,
          birthday: this.birthday.toISOString().slice(0, 10),
          customer_group: this.group,
          territory: this.territory,

          address_line1: this.address_line1,
          address_line2: this.address_line2,
          custom_building_number: this.custom_building_number,
          pincode: this.pincode,
        };

        if (!/^9665\d{8}$/.test(this.mobile_no)) {
          this.eventBus.emit("show_message", {
            text: __(
              "Cannot create customer: Mobile number must be 9665XXXXXXXX (12 digits)."
            ),
            color: "error",
          });
          return;
        }
   


        frappe.call({
          method: "posawesome.posawesome.api.posapp.create_customer",
          args,
          callback(r) {
            if (!r.exc && r.message.name) {
              vm.eventBus.emit("show_mesage", {
                text: __("Customer contact created successfully."),
                color: "success",
              });

              args.name = r.message.name;
              frappe.utils.play_sound("submit");
              vm.eventBus.emit("add_customer_to_list", args);
              vm.eventBus.emit("set_customer", r.message.name);

              Object.assign(vm, {
                customer_name: "",
                tax_id: "",
                mobile_no: "9665",
                city: "",
                email_id: "",
                referral_code: "",
                company: "",
                birthday: new Date(),
                formattedBirthday: "",
                group: "",
                customerDialog: false,

                address_line1: "",
                address_line2: "",
                custom_building_number: "",
                pincode: "",
              });
            }
          },
        });

        this.customerDialog = false;
      }
    },
  },

  created() {
    this.eventBus.on("open_new_customer", () => {
      this.customerDialog = true;
      this.getCustomerGroups();
    });

    this.eventBus.on("register_pos_profile", (data) => {
      this.pos_profile = data.pos_profile;
    });

    this.getCustomerTerritorys();
    this.getCompanies();
  },
};
</script>
