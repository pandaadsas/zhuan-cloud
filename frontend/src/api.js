import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from './store'

const http = axios.create({ baseURL: '', timeout: 120000 })

http.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('zhuan_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

http.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    const detail = err.response?.data?.detail || err.message || '请求失败'
    if (err.response?.status === 401) {
      useUserStore().logout()
      if (!location.hash.includes('login')) location.hash = '#/login'
    }
    ElMessage.error(String(detail))
    return Promise.reject(err)
  }
)

export default http
