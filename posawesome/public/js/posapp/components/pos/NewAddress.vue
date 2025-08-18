<template>
  <v-row justify="center">
    <v-dialog v-model="addressDialog" max-width="600px">
      <v-card>
        <v-card-title>
          <span class="text-h5 text-primary">
            {{ $t("Add New Address") }}
          </span>
        </v-card-title>
        <v-card-text class="pa-0">
          <v-container>
            <v-row>
              <v-col cols="12">
                <v-text-field
                  density="compact"
                  color="primary"
                  :label="$t('Address Name')"
                  bg-color="white"
                  hide-details
                  v-model="address.name"
                ></v-text-field>
              </v-col>
              <v-col cols="12">
                <v-text-field
                  density="compact"
                  color="primary"
                  :label="$t('Address Line 1')"
                  bg-color="white"
                  hide-details
                  v-model="address.address_line1"
                ></v-text-field>
              </v-col>
              <v-col cols="12">
                <v-text-field
                  density="compact"
                  color="primary"
                  :label="$t('Address Line 2')"
                  bg-color="white"
                  hide-details
                  v-model="address.address_line2"
                ></v-text-field>
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :label="$t('City')"
                  density="compact"
                  color="primary"
                  bg-color="white"
                  hide-details
                  v-model="address.city"
                ></v-text-field>
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :label="$t('State')"
                  density="compact"
                  bg-color="white"
                  hide-details
                  v-model="address.state"
                ></v-text-field>
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="error" theme="dark" @click="close_dialog">
            {{ $t("Close") }}
          </v-btn>
          <v-btn color="success" theme="dark" @click="submit_dialog">
            {{ $t("Submit") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-row>
</template>

<script>
export default {
  data: () => ({
    addressDialog: false,
    address: {},
    customer: "",
  }),

  methods: {
    close_dialog() {
      this.addressDialog = false;
    },

    submit_dialog() {
      this.address.customer = this.customer;
      this.address.doctype = "Customer";
      frappe.call({
        method: "posawesome.posawesome.api.posapp.make_address",
        args: {
          args: this.address,
        },
        callback: (r) => {
          if (!r.exc) {
            this.eventBus.emit("add_the_new_address", r.message);
            this.eventBus.emit("show_message", {
              text: this.$t("Customer Address created successfully."),
              color: "success",
            });
            this.addressDialog = false;
            this.customer = "";
            this.address = {};
          }
        },
      });
    },
  },

  created() {
    this.eventBus.on("open_new_address", (data) => {
      this.addressDialog = true;
      this.customer = data;
    });
  },
};
</script>
