import { reactive, computed } from 'vue'

const stored = JSON.parse(localStorage.getItem('zhuan_user') || 'null')

export const userStore = reactive({
  token: localStorage.getItem('zhuan_token') || '',
  user: stored,
})

export const isLoggedIn = computed(() => !!userStore.token)

export function setAuth(token, user) {
  userStore.token = token
  userStore.user = user
  localStorage.setItem('zhuan_token', token)
  localStorage.setItem('zhuan_user', JSON.stringify(user))
}

export function useUserStore() {
  return {
    logout() {
      userStore.token = ''
      userStore.user = null
      localStorage.removeItem('zhuan_token')
      localStorage.removeItem('zhuan_user')
    },
  }
}

export const ROLE_HOME = {
  safety_officer: '/report',
  safety_supervisor: '/dashboard',
  project_manager: '/dashboard',
  responsible: '/orders',
}
