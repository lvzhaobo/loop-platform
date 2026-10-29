import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import Antd from 'ant-design-vue'
import './styles/shell.css'
import './styles.css'

createApp(App).use(router).use(Antd).mount('#app')
