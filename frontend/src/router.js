import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('./components/AppShell.vue'),
    children: [
      { path: '', redirect: '/query' },
      { path: 'query', component: () => import('./views/Query.vue'), meta: { title: '自然语言查询' } },
      { path: 'datasources', component: () => import('./views/Datasources.vue'), meta: { title: '数据源' } },
      { path: 'history', component: () => import('./views/History.vue'), meta: { title: '查询历史' } },
      { path: 'admin', component: () => import('./views/Admin.vue'), meta: { title: '管理后台' } },
      { path: 'settings', component: () => import('./views/Settings.vue'), meta: { title: '个人设置' } }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/query' }
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) return '/login'
  if (to.path === '/login' && token) return '/query'
  return true
})

export default router
