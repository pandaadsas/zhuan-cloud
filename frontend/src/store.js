import { reactive, computed } from 'vue'

const stored = JSON.parse(localStorage.getItem('zhuan_user') || 'null')

export const userStore = reactive({
  token: localStorage.getItem('zhuan_token') || '',
  user: stored,
})

// 当前项目上下文：经 X-Project-Id 请求头跟随所有 API 请求
// id 统一为数字，保证与选项 value 严格相等（否则刷新后 el-select 显示原始 id）
export const projectStore = reactive({
  id: Number(localStorage.getItem('zhuan_project')) || '',
  list: [],
})

export const currentProject = computed(
  () => projectStore.list.find((p) => p.id === projectStore.id) || null,
)

export function setProject(id) {
  projectStore.id = id
  localStorage.setItem('zhuan_project', id)
}

export function setProjectList(list) {
  projectStore.list = list
  // 未选择或所选项目已不存在时，落到第一个项目
  if (!list.some((p) => p.id === projectStore.id)) {
    setProject(list[0]?.id ?? '')
  }
}

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
