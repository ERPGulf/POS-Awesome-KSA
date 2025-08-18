<template>
  <div>
    <v-card
      class="selection mx-auto bg-grey-lighten-5"
      style="max-height: 80vh; height: 80vh"
    >
      <v-card-title>
        <v-row no-gutters align="center" justify="center">
          <v-col cols="6">
            <span class="text-h6 text-warning">{{ $t("Bundles") }}</span>
          </v-col>
          <v-col cols="4">
            <v-text-field
              density="compact"
              variant="outlined"
              color="indigo"
              :label="$t('Bundle')"
              bg-color="white"
              hide-details
              v-model="new_bundle"
              class="mr-4"
            />
          </v-col>
          <v-col cols="2">
            <v-btn
              class="pa-1"
              color="primary"
              theme="dark"
              @click="search_bundle(new_bundle)"
            >
              {{ $t("Search") }}
            </v-btn>
          </v-col>
        </v-row>
      </v-card-title>

      <div
        class="my-0 py-0 overflow-y-auto"
        style="max-height: 75vh"
        @mouseover="style = 'cursor: pointer'"
      >
        <v-data-table
          :headers="items_headers"
          :items="posa_bundles"
          :single-expand="singleExpand"
          v-model:expanded="expanded"
          item-key="bundle"
          class="elevation-1"
          :items-per-page="itemsPerPage"
          hide-default-footer
        >
          <template #item.description="{ item }">
            {{ stripHTML(item.description) }}
          </template>
        </v-data-table>
      </div>
    </v-card>

    <v-card flat style="max-height: 11vh; height: 11vh" class="cards mb-0 mt-3 py-0">
      <v-row align="start" no-gutters>
        <v-col cols="12">
          <v-btn
            block
            class="pa-1"
            size="large"
            color="warning"
            theme="dark"
            @click="back_to_invoice"
          >
            {{ $t("Back") }}
          </v-btn>
        </v-col>
      </v-row>
    </v-card>
  </div>
</template>

<script>
export default {
  data: () => ({
    loading: false,
    pos_profile: "",
    customer: "",
    posa_bundles: [],
    new_bundle: null,
    itemsPerPage: 1000,
    singleExpand: true,
    expanded: [],
    items_headers: [],
  }),

  methods: {
    stripHTML(html) {
      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = html;
      return tempDiv.textContent || tempDiv.innerText || "";
    },

    back_to_invoice() {
      this.eventBus.emit("show_bundles", "false");
    },

    search_bundle(new_bundle) {
      if (!new_bundle) return;
      const vm = this;
      frappe.call({
        method: "posawesome.posawesome.api.posapp.search_bundle_sku",
        args: {
          bundle_sku: new_bundle,
          company: vm.pos_profile.company,
        },
        callback: function (r) {
          if (r.message) {
            vm.posa_bundles = [];
            r.message.forEach((bundle) => {
              vm.add_bundle(bundle);
            });
          }
        },
      });
    },

    add_bundle(bundle_item) {
      if (!bundle_item) return;
      this.posa_bundles.push({
        description: this.stripHTML(bundle_item.description),
        item_code: bundle_item.bundle_sku,
        qty: bundle_item.qty,
      });
    },

    removeBundle(remove_list) {
      this.posa_bundles = this.posa_bundles.filter(
        (bundle) => !remove_list.includes(bundle.item_code)
      );
    },

    updateInvoice() {
      this.eventBus.emit("update_invoice_bundles", this.posa_bundles);
    },
  },

  watch: {
    posa_bundles: {
      deep: true,
      handler() {
        this.updateInvoice();
      },
    },
  },

  created() {
    this.items_headers = [
    { title: this.$t("Name"), align: "start", sortable: true, value: "description" },
    { title: this.$t("Item Code"), value: "item_code", align: "start" },
    { title: this.$t("Qty"), value: "qty", align: "start" }
  ];
    this.$nextTick(() => {
      this.eventBus.on("register_pos_profile", (data) => {
        this.pos_profile = data.pos_profile;
      });
    });
  },
};
</script>
