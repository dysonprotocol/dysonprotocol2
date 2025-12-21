import { createApp } from "vue";
import { createPinia } from "pinia";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import "./style.css";

import Dashboard from "./views/Dashboard.vue";
import Provider from "./views/Provider.vue";
import Providers from "./views/Providers.vue";
import CreateRequest from "./views/CreateRequest.vue";
import RequestDetail from "./views/RequestDetail.vue";
import Admin from "./views/Admin.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: Dashboard },
    { path: "/provider", name: "provider", component: Provider },
    { path: "/providers", name: "providers", component: Providers },
    { path: "/request/new", name: "create-request", component: CreateRequest },
    { path: "/request/:id", name: "request-detail", component: RequestDetail },
    { path: "/admin", name: "admin", component: Admin },
  ],
});

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
