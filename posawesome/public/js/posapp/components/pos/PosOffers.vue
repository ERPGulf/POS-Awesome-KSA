<template>
  <div>
    <v-card
      class="selection mx-auto bg-grey-lighten-5"
      style="max-height: 80vh; height: 80vh"
    >
      <v-card-title>
        <span class="text-h6 text-primary">{{ $t('Offers') }}</span>
      </v-card-title>
      <div
        class="my-0 py-0 overflow-y-auto"
        style="max-height: 75vh"
        @mouseover="style = 'cursor: pointer'"
      >
        <v-data-table
          :headers="items_headers"
          :items="pos_offers"
          :single-expand="singleExpand"
          v-model:expanded="expanded"
          show-expand
          item-key="row_id"
          class="elevation-1"
          :items-per-page="itemsPerPage"
          hide-default-footer
        >
          <template v-slot:item.offer_applied="{ item }">
            <v-checkbox-btn
              @click="forceUpdateItem"
              :v-model="item.offer_applied"
              :disabled="
                (item.offer == 'Give Product' &&
                  !item.give_item &&
                  (!item.replace_cheapest_item || !item.replace_item)) ||
                (item.offer == 'Grand Total' &&
                  discount_percentage_offer_name &&
                  discount_percentage_offer_name != item.name)
              "
            ></v-checkbox-btn>
          </template>
          <template v-slot:expanded-item="{ headers, item }">
            <td :colspan="headers.length">
              <v-row class="mt-2">
                <v-col v-if="item.description">
                  <div
                    class="text-primary"
                    v-html="handleNewLine(item.description)"
                  ></div>
                </v-col>
                <v-col v-if="item.offer == 'Give Product'">
                  <v-autocomplete
                    v-model="item.give_item"
                    :items="get_give_items(item)"
                    item-title="item_code"
                    variant="outlined"
                    density="compact"
                    color="primary"
                    :label="$t('Give Item')"
                    :disabled="
                      item.apply_type != 'Item Group' ||
                      item.replace_item ||
                      item.replace_cheapest_item
                    "
                  ></v-autocomplete>
                </v-col>
              </v-row>
            </td>
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
            >{{ $t('Back') }}</v-btn
          >
        </v-col>
      </v-row>
    </v-card>
  </div>
</template>

<script>
import format from "../../format";
export default {
  mixins: [format],
  data: () => ({
    loading: false,
    pos_profile: "",
    pos_offers: [],
    allItems: [],
    discount_percentage_offer_name: null,
    itemsPerPage: 1000,
    expanded: [],
    singleExpand: true,
    items_headers: [],
  }),
  computed: {
    offersCount() {
      return this.pos_offers.length;
    },
    appliedOffersCount() {
      return this.pos_offers.filter((el) => !!el.offer_applied).length;
    },
  },
  methods: {
    back_to_invoice() {
      this.eventBus.emit("show_offers", "false");
    },
    forceUpdateItem() {
      this.pos_offers = [...this.pos_offers];
    },
    makeid(length) {
      let result = "";
      const characters = "abcdefghijklmnopqrstuvwxyz0123456789";
      for (let i = 0; i < length; i++) {
        result += characters.charAt(Math.floor(Math.random() * characters.length));
      }
      return result;
    },
    updatePosOffers(offers) {
      const toRemove = this.pos_offers.filter(
        (pos_offer) => !offers.some((offer) => offer.name === pos_offer.name)
      ).map((o) => o.row_id);
      this.removeOffers(toRemove);

      offers.forEach((offer) => {
        const pos_offer = this.pos_offers.find((o) => o.name === offer.name);
        if (pos_offer) {
          Object.assign(pos_offer, offer);
          if (pos_offer.offer === "Grand Total" && !this.discount_percentage_offer_name) {
            pos_offer.offer_applied = !!pos_offer.auto;
          }
        } else {
          const newOffer = {
            ...offer,
            row_id: offer.row_id || this.makeid(20),
            give_item:
              offer.apply_type === "Item Code"
                ? offer.apply_item_code || "Nothing"
                : offer.give_item,
            offer_applied: this.determineAppliedStatus(offer),
          };
          if (newOffer.offer === "Give Product" && !newOffer.give_item) {
            newOffer.give_item = this.get_give_items(newOffer)[0]?.item_code;
          }
          this.pos_offers.push(newOffer);
          this.eventBus.emit("show_message", {
            text: this.$t("New Offer Available"),
            color: "warning",
          });
        }
      });
    },
    determineAppliedStatus(offer) {
      if (offer.offer_applied) return true;
      if (
        offer.apply_type === "Item Group" &&
        offer.offer === "Give Product" &&
        !offer.replace_cheapest_item &&
        !offer.replace_item
      ) return false;
      if (offer.offer === "Grand Total" && this.discount_percentage_offer_name) return false;
      return !!offer.auto;
    },
    removeOffers(ids) {
      this.pos_offers = this.pos_offers.filter((o) => !ids.includes(o.row_id));
    },
    handelOffers() {
      this.eventBus.emit("update_invoice_offers", this.pos_offers.filter(o => o.offer_applied));
    },
    handleNewLine(str) {
      return str ? str.replace(/(?:\r\n|\r|\n)/g, "<br />") : "";
    },
    get_give_items(offer) {
      if (offer.apply_type === "Item Code") return [offer.apply_item_code];
      if (offer.apply_type === "Item Group") {
        let filtered = this.allItems.filter((item) => item.item_group === offer.apply_item_group);
        return offer.less_then > 0 ? filtered.filter((item) => item.rate < offer.less_then) : filtered;
      }
      return [];
    },
    updateCounters() {
      this.eventBus.emit("update_offers_counters", {
        offersCount: this.offersCount,
        appliedOffersCount: this.appliedOffersCount,
      });
    },
    updatePosCoupuns() {
      this.eventBus.emit("update_pos_coupons", this.pos_offers.filter(o => o.offer_applied && o.coupon_based));
    },
  },
  watch: {
    pos_offers: {
      deep: true,
      handler() {
        this.handelOffers();
        this.updateCounters();
        this.updatePosCoupuns();
      },
    },
  },
  created() {
    this.items_headers = [
        { title: this.$t('Name'), value: "name", align: "start" },
        { title: this.$t('Apply On'), value: "apply_on", align: "start" },
        { title: this.$t('Offer'), value: "offer", align: "start" },
        { title: this.$t('Applied'), value: "offer_applied", align: "start" },
      ];

    this.$nextTick(() => {
      this.eventBus.on("register_pos_profile", (data) => {
        this.pos_profile = data.pos_profile;
      });
      this.eventBus.on("update_customer", (customer) => {
        if (this.customer !== customer) this.offers = [];
      });
      this.eventBus.on("update_pos_offers", (data) => this.updatePosOffers(data));
      this.eventBus.on("update_discount_percentage_offer_name", (data) => {
        this.discount_percentage_offer_name = data.value;
      });
      this.eventBus.on("set_all_items", (data) => {
        this.allItems = data;
      });
    });
  },
};
</script>