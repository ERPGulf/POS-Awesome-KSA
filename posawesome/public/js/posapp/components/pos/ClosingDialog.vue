<template>
  <v-row justify="center">
    <v-dialog v-model="closingDialog" max-width="900px">
      <v-card>
        <v-card-title>
          <span class="text-h5 text-primary">{{ $t("closing_pos_shift") }}</span>
        </v-card-title>
        <v-card-text class="pa-0">
          <v-container>
            <v-row>
              <v-col cols="12" class="pa-1">
                <v-data-table
                  :headers="headers"
                  :items="dialog_data.payment_reconciliation"
                  item-key="mode_of_payment"
                  class="elevation-1"
                  :items-per-page="itemsPerPage"
                  hide-default-footer
                >
                  <template v-slot:item.closing_amount="{ item }">
                    <v-text-field
                      v-model.number="item.closing_amount"
                      type="number"
                      :rules="[max25chars]"
                      :label="$t('edit')"
                      class="ma-0 pa-0"
                      hide-details
                      dense
                    />
                  </template>

                  <template v-slot:item.difference="{ item }">
                    {{ currencySymbol(pos_profile.currency) }}
                    {{
                      (item.difference = formatCurrency(
                        item.expected_amount - item.closing_amount
                      ))
                    }}
                  </template>

                  <template v-slot:item.opening_amount="{ item }">
                    {{ currencySymbol(pos_profile.currency) }}
                    {{ formatCurrency(item.opening_amount) }}
                  </template>

                  <template v-slot:item.expected_amount="{ item }">
                    {{ currencySymbol(pos_profile.currency) }}
                    {{ formatCurrency(item.expected_amount) }}
                  </template>
                </v-data-table>
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>

        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="error" theme="dark" @click="close_dialog">
            {{ $t("close") }}
          </v-btn>
          <v-btn color="success" theme="dark" @click="submit_dialog">
            {{ $t("submit") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-row>
</template>
<script>
import format from "../../format";
export default {
  mixins: [format],
  data() {
  return {
    closingDialog: false,
    itemsPerPage: 20,
    dialog_data: {},
    pos_profile: "",
    headers: [],
    pagination: {},
  };
},

  methods: {
    max25chars(v) {
    return (v?.toString()?.length <= 20) || this.$t('input_too_long');
  },

    close_dialog() {
      this.closingDialog = false;
    },
    submit_dialog() {
      this.eventBus.emit("submit_closing_pos", this.dialog_data);
      this.closingDialog = false;
    },
    generateHeaders() {
      this.headers = [
        {
          title: this.$t("mode_of_payment"),
          value: "mode_of_payment",
          align: "start",
          sortable: true,
        },
        {
          title: this.$t("opening_amount"),
          align: "end",
          sortable: true,
          value: "opening_amount",
        },
        {
          title: this.$t("closing_amount"),
          value: "closing_amount",
          align: "end",
          sortable: true,
        },
      ];
      if (!this.pos_profile?.hide_expected_amount) {
        this.headers.push({
          title: this.$t("expected_amount"),
          value: "expected_amount",
          align: "end",
          sortable: false,
        });
        this.headers.push({
          title: this.$t("difference"),
          value: "difference",
          align: "end",
          sortable: false,
        });
      }
    },
  },

  created() {
    this.eventBus.on("open_ClosingDialog", (data) => {
      this.closingDialog = true;
      if (data?.payment_reconciliation) {
        data.payment_reconciliation.forEach((row) => {
          row.closing_amount = row.expected_amount;
        });
      }
      this.dialog_data = data;
    });

    this.eventBus.on("register_pos_profile", (data) => {
      this.pos_profile = data.pos_profile;
      this.generateHeaders();
    });
  },
};
</script>
