// 变更记录: 20261126-0922 新增：路由与登录守卫。需要登录的页面在未登录时跳转后端登录端点，登录后回到原页面
import { createRouter, createWebHistory } from 'vue-router'
import { auth, loadMe, loginRedirect } from '../auth'
import HomeView from '../views/HomeView.vue'
import NotFoundView from '../views/NotFoundView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView, meta: { requiresAuth: true } },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView },
  ],
})

router.beforeEach(async (to) => {
  if (!auth.loaded) {
    await loadMe()
  }
  // SSO 未启用时不跳转（后端会返回 503），由页面显示提示
  if (to.meta.requiresAuth && !auth.user && auth.ssoEnabled) {
    loginRedirect(to.fullPath)
    return false
  }
  return true
})
