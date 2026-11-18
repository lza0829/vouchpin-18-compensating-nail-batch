import { createRouter, createWebHistory } from 'vue-router'
import Home from './pages/Home.vue'
import Events from './pages/Events.vue'
import Redeem from './pages/Redeem.vue'
import Returns from './pages/Returns.vue'
import Batches from './pages/Batches.vue'
import Reconciliation from './pages/Reconciliation.vue'
import Settings from './pages/Settings.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/events', component: Events },
    { path: '/redeem', component: Redeem },
    { path: '/returns', component: Returns },
    { path: '/batches', component: Batches },
    { path: '/reconciliation', component: Reconciliation },
    { path: '/settings', component: Settings },
  ],
})
