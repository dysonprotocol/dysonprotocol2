import { createRouter, createWebHistory } from "vue-router";
import GameView from "@/views/GameView.vue";
import DeployView from "@/views/DeployView.vue";
import AutopilotView from "@/views/AutopilotView.vue";

const routes = [
  { path: "/", name: "game", component: GameView },
  { path: "/deploy", name: "deploy", component: DeployView },
  { path: "/autopilot", name: "autopilot", component: AutopilotView },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
