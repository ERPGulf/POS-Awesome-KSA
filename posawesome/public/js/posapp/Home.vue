<template>
  <v-app class="container1">
    <v-main>
      <transition name="fade-lang" mode="out-in">
        <div :key="$i18n.locale">
          <Navbar @changePage="setPage($event)" />
          <component :is="page" class="mx-4 md-4" />
        </div>
      </transition>
    </v-main>
  </v-app>
</template>

<script>
import Navbar from "./components/Navbar.vue";
import POS from "./components/pos/Pos.vue";
import Payments from "./components/payments/Pay.vue";
import { useI18n } from "vue-i18n";
export default {
  data: function () {
    return {
      page: "POS",
    };
  },
  components: {
    Navbar,
    POS,
    Payments,
  },
  methods: {
    setPage(page) {
      this.page = page;
    },
    remove_frappe_nav() {
      this.$nextTick(function () {
        $(".page-head").remove();
        $(".navbar.navbar-default.navbar-fixed-top").remove();
      });
    },
  },
  mounted() {
    this.remove_frappe_nav();
  },
  updated() {},
 
  created() {
  setTimeout(() => {
    this.remove_frappe_nav();
    const lang = localStorage.getItem("lang") || "en";
    document.dir = lang === "ar" ? "rtl" : "ltr";
  }, 1000);
}

};
</script>

<style scoped>
.container1 {
  margin-top: 0px;
}

.fade-lang-enter-active,
.fade-lang-leave-active {
  transition: opacity 0.4s ease;
}
.fade-lang-enter-from,
.fade-lang-leave-to {
  opacity: 0;
}
</style>
