<template>
  <div fluid class="mt-2">
    <ClosingDialog />
    <Drafts />
    <SalesOrders />
    <Returns />
    <NewAddress />
    <MpesaPayments />
    <Variants />
    <OpeningDialog v-if="dialog" :dialog="dialog" />
    <v-row v-show="!dialog">
      <v-col
        v-show="!payment && !offers && !coupons"
        xl="5" lg="5" md="5" sm="5" cols="12"
        class="pos pr-0"
      >
        <ItemsSelector />
      </v-col>

      <v-col v-show="bundles" xl="5" lg="5" md="5" sm="5" cols="12" class="pos pr-0">
        <PosBundles />
      </v-col>

      <v-col v-show="offers" xl="5" lg="5" md="5" sm="5" cols="12" class="pos pr-0">
        <PosOffers />
      </v-col>

      <v-col v-show="coupons" xl="5" lg="5" md="5" sm="5" cols="12" class="pos pr-0">
        <PosCoupons />
      </v-col>

      <v-col v-show="payment" xl="5" lg="5" md="5" sm="5" cols="12" class="pos pr-0">
        <Payments />
      </v-col>

      <v-col xl="7" lg="7" md="7" sm="7" cols="12" class="pos">
        <Invoice />
      </v-col>
    </v-row>
  </div>
</template>

<script>
import ItemsSelector from "./ItemsSelector.vue";
import Invoice from "./Invoice.vue";
import OpeningDialog from "./OpeningDialog.vue";
import Payments from "./Payments.vue";
import PosOffers from "./PosOffers.vue";
import PosCoupons from "./PosCoupons.vue";
import Drafts from "./Drafts.vue";
import SalesOrders from "./SalesOrders.vue";
import ClosingDialog from "./ClosingDialog.vue";
import NewAddress from "./NewAddress.vue";
import Variants from "./Variants.vue";
import Returns from "./Returns.vue";
import MpesaPayments from "./Mpesa-Payments.vue";
import PosBundles from "./PosBundles.vue";

export default {
  data() {
    return {
      dialog: false,
      pos_profile: "",
      pos_opening_shift: "",
      payment: false,
      offers: false,
      coupons: false,
      bundles: false,
    };
  },

  components: {
    ItemsSelector,
    Invoice,
    OpeningDialog,
    Payments,
    Drafts,
    ClosingDialog,
    PosBundles,
    Returns,
    PosOffers,
    PosCoupons,
    NewAddress,
    Variants,
    MpesaPayments,
    SalesOrders,
  },

  methods: {
    check_opening_entry() {
      return frappe
        .call("posawesome.posawesome.api.posapp.check_opening_shift", {
          user: frappe.session.user,
        })
        .then((r) => {
          if (r.message) {
            this.pos_profile = r.message.pos_profile;
            sessionStorage.setItem("cached_pos_profile", JSON.stringify(this.pos_profile));
            this.pos_opening_shift = r.message.pos_opening_shift;
            this.get_offers(this.pos_profile.name);
            this.eventBus.emit("register_pos_profile", r.message);
            this.eventBus.emit("set_company", r.message.company);
            console.info("LoadPosProfile");
          } else {
            this.create_opening_voucher();
          }
        });
    },

    create_opening_voucher() {
      this.dialog = true;
    },

    get_closing_data() {
      return frappe
        .call("posawesome.posawesome.doctype.pos_closing_shift.pos_closing_shift.make_closing_shift_from_opening", {
          opening_shift: this.pos_opening_shift,
        })
        .then((r) => {
          if (r.message) {
            this.eventBus.emit("open_ClosingDialog", r.message);
          }
        });
    },

    submit_closing_pos(data) {
      frappe
        .call("posawesome.posawesome.doctype.pos_closing_shift.pos_closing_shift.submit_closing_shift", {
          closing_shift: data,
        })
        .then((r) => {
          if (r.message) {
            this.eventBus.emit("show_message", {
              text: `POS Shift Closed`,
              color: "success",
            });
            this.check_opening_entry();
          } else {
            console.error(r);
          }
        });
    },

    get_offers(pos_profile) {
      return frappe
        .call("posawesome.posawesome.api.posapp.get_offers", {
          profile: pos_profile,
        })
        .then((r) => {
          if (r.message) {
            console.info("LoadOffers");
            this.eventBus.emit("set_offers", r.message);
          }
        });
    },

    get_pos_setting() {
      frappe.db.get_doc("POS Settings", undefined).then((doc) => {
        this.eventBus.emit("set_pos_settings", doc);
      });
    },

    setupEventListeners() {
      this.eventBus.on("close_opening_dialog", () => (this.dialog = false));

      this.eventBus.on("register_pos_data", (data) => {
        this.pos_profile = data.pos_profile;
        this.get_offers(this.pos_profile.name);
        this.pos_opening_shift = data.pos_opening_shift;
        this.eventBus.emit("register_pos_profile", data);
        console.info("LoadPosProfile");
      });

      this.eventBus.on("show_payment", (data) => {
        this.payment = data === "true";
        this.offers = this.coupons = false;
      });

      this.eventBus.on("show_offers", (data) => {
        this.offers = data === "true";
        this.payment = this.coupons = false;
      });

      this.eventBus.on("show_coupons", (data) => {
        this.coupons = data === "true";
        this.offers = this.payment = false;
      });

      this.eventBus.on("show_bundles", (data) => {
        this.bundles = data === "true";
        this.coupons = this.offers = this.payment = false;
      });

      this.eventBus.on("open_closing_dialog", this.get_closing_data);
      this.eventBus.on("submit_closing_pos", this.submit_closing_pos);
    },

    removeEventListeners() {
      this.eventBus.off("close_opening_dialog");
      this.eventBus.off("register_pos_data");
      this.eventBus.off("show_payment");
      this.eventBus.off("show_offers");
      this.eventBus.off("show_coupons");
      this.eventBus.off("show_bundles");
      this.eventBus.off("open_closing_dialog");
      this.eventBus.off("submit_closing_pos");
    },
  },

  mounted() {
    this.check_opening_entry();
    this.get_pos_setting();
    this.setupEventListeners();
  },

  beforeUnmount() {
    this.removeEventListeners();
  },
};
</script>

<style scoped></style>
