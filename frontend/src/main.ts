import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { Button, Tag } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import './style.css'
import './workspace.css'
import App from './App.vue'
import router from './router'

createApp(App).use(createPinia()).use(router).use(Button).use(Tag).mount('#app')
