// 变更记录: 20261126-0922 新增：应用入口，挂载根组件并注册路由
import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './style.css'

createApp(App).use(router).mount('#app')
