import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import {
  ArrowDown, ArrowRight, Check, CircleCheck, Clock, Connection, Download,
  EditPen, Key, Lock, MagicStick, Menu, Message, Microphone, Picture, Plus,
  Position, Postcard, Promotion, Reading, Select, Service, Setting, SwitchButton,
  Tools, Upload, UploadFilled, User, WarningFilled,
} from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import './styles.css'

const app = createApp(App)
app.use(ElementPlus, { locale: zhCn })
app.use(router)
const icons = {
  ArrowDown, ArrowRight, Check, CircleCheck, Clock, Connection, Download,
  EditPen, Key, Lock, MagicStick, Menu, Message, Microphone, Picture, Plus,
  Position, Postcard, Promotion, Reading, Select, Service, Setting, SwitchButton,
  Tools, Upload, UploadFilled, User, WarningFilled,
}
for (const [name, component] of Object.entries(icons)) app.component(name, component)
app.mount('#app')
