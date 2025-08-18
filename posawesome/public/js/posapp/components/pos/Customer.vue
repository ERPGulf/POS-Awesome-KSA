<template>
  <div :dir="$i18n.locale === 'ar' ? 'rtl' : 'ltr'">
    <v-autocomplete
      density="compact"
      clearable
      auto-select-first
      variant="outlined"
      color="primary"
      :label="$t('Customer')"
      v-model="customer"
      :items="filteredCustomers"
      v-model:search="searchQuery"
      item-title="customer_name"
      item-value="name"
      bg-color="white"
      :no-data-text="$t('Customers not found')"
      hide-details
      :custom-filter="customFilter"
      :disabled="readonly"
      append-icon="mdi-plus"
      @click:append="new_customer"
      prepend-inner-icon="mdi-account-edit"
      @click:prepend-inner="edit_customer"
    >
      <template v-slot:item="{ props, item }">
        <v-list-item v-bind="props">
          <v-list-item-subtitle v-if="item.raw.customer_name !== item.raw.name">
            <div v-html="`${$t('ID')}: ${item.raw.name}`"></div>
          </v-list-item-subtitle>
          <v-list-item-subtitle v-if="item.raw.tax_id">
            <div v-html="`${$t('TAX ID')}: ${item.raw.tax_id}`"></div>
          </v-list-item-subtitle>
          <v-list-item-subtitle v-if="item.raw.email_id">
            <div v-html="`${$t('Email')}: ${item.raw.email_id}`"></div>
          </v-list-item-subtitle>
          <v-list-item-subtitle v-if="item.raw.mobile_no">
            <div v-html="`${$t('Mobile No')}: ${item.raw.mobile_no}`"></div>
          </v-list-item-subtitle>
          <v-list-item-subtitle v-if="item.raw.primary_address">
            <div v-html="`${$t('Primary Address')}: ${item.raw.primary_address}`"></div>
          </v-list-item-subtitle>
        </v-list-item>
      </template>
    </v-autocomplete>

    <div class="mb-8">
      <NewCustomer />
      <EditCustomer />
    </div>
  </div>
</template>

<script>
import NewCustomer from "./NewCustomer.vue";
import EditCustomer from "./EditCustomer.vue";

export default {
  data: () => ({
    pos_profile: "",
    customers: [],
    customer: "",
    readonly: false,
    customer_info: {},
    searchQuery: "",
    last_discount_level: null, 
  }),

  components: {
    NewCustomer,
    EditCustomer,
  },

  computed: {
    filteredCustomers() {
      if (!this.searchQuery) {
        return this.customers.slice(0, 50);
      }

      const query = this.searchQuery.toLowerCase();

      const filtered = this.customers.filter((cust) => {
        return (
          
          (cust.customer_name || "").toLowerCase().includes(query) ||
          (cust.tax_id || "").toLowerCase().includes(query) ||
          (cust.email_id || "").toLowerCase().includes(query) ||
          (cust.mobile_no || "").toLowerCase().includes(query) ||
          (cust.name || "").toLowerCase().includes(query)
        );
      });

      return filtered.slice(0, 50);
    },
  },
  methods: {
    get_customer_names() {
      const vm = this;

      // Only call API if customers are not already loaded
      if (vm.customers.length > 0) return;

      frappe.call({
        method: "posawesome.posawesome.api.posapp.get_customer_names",
        args: {
          pos_profile: vm.pos_profile,
        },
        callback(r) {
          if (r.message) {
            vm.customers = r.message.customers || [];

            if (r.message.custom_profile_type) {
              vm.eventBus.emit("update_profile_type", r.message.custom_profile_type);
            }
          }
          
        },
      });
    },
    new_customer() {
      this.eventBus.emit("open_new_customer");
    },

    edit_customer() {
      this.eventBus.emit("set_customer_info_to_edit", this.customer_info);
      this.eventBus.emit("open_edit_customer");
    },

    customFilter(itemText, queryText, itemRow) {
      const item = itemRow.raw;
      const searchText = queryText.toLowerCase();

      return (
        
        (item.customer_name || "").toLowerCase().includes(searchText) ||
        (item.tax_id || "").toLowerCase().includes(searchText) ||
        (item.email_id || "").toLowerCase().includes(searchText) ||
        (item.mobile_no || "").toLowerCase().includes(searchText) ||
        (item.name || "").toLowerCase().includes(searchText)
      );
    },
  },

  mounted() {
    if (this.pos_profile) {
      this.fetchPosProfile?.();
      this.get_customer_names();
    }
  },

  created() {
    this.$nextTick(() => {
      const cached = sessionStorage.getItem("cached_pos_profile");
      if (cached) {
        this.pos_profile = JSON.parse(cached);
        this.get_customer_names();
      } else {
        // console.warn("No cached pos_profile found.");
        console.warn(this.$t("No cached POS profile found."));

      }
      // ended

      this.eventBus.on("payments_register_pos_profile", (data) => {
        this.pos_profile = data.pos_profile;
        this.get_customer_names();
      });

      this.eventBus.on("set_customer", (customer) => {
        this.customer = customer;
      });

      this.eventBus.on("add_customer_to_list", (customer) => {
        this.customers.push(customer);
      });

      this.eventBus.on("set_customer_readonly", (value) => {
        this.readonly = value;
      });

      this.eventBus.on("set_customer_info_to_edit", (data) => {
        this.customer_info = data;
      });

      this.eventBus.on("fetch_customer_details", () => {
        this.get_customer_names();
      });
    });
  },

  watch: {
    customer(newVal) {
      this.eventBus.emit("update_customer", newVal);

      if (!newVal || !Array.isArray(this.customers)) {
        this.eventBus.emit("update_customer_discount_level", null);
        this.last_discount_level = null;
        return;
      }

      // Find full customer object
      const selected = this.customers.find((c) => c.name === newVal);
      if (selected) {
        // ✅ Emit this!
        this.eventBus.emit("update_customer_group", selected.customer_group);
      }

      if (selected && selected.custom_discount_level != null) {
        // Only for wholesale customers (level 1 or 2)
        if ([1, 2].includes(Number(selected.custom_discount_level))) {
          if (this.last_discount_level !== selected.custom_discount_level) {
            this.eventBus.emit(
              "update_customer_discount_level",
              selected.custom_discount_level
            );
            this.last_discount_level = selected.custom_discount_level;
          }
        } else {
          // Not wholesale, reset discount level if changed
          if (this.last_discount_level !== null) {
            this.eventBus.emit("update_customer_discount_level", null);
            this.last_discount_level = null;
          }
        }
      } else {
        // Customer not found or no discount level
        if (this.last_discount_level !== null) {
          this.eventBus.emit("update_customer_discount_level", null);
          this.last_discount_level = null;
        }
      }
    },
  },

};
</script>
