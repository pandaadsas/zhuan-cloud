<template>
  <div class="page-shell">
    <div class="page-intro">
      <div class="page-title">现场安全智询</div>
      <div class="page-sub">查进度、筛工单、看统计、查规范、调周报，也可以直接对话上报隐患。</div>
    </div>

    <div class="chat-layout">
      <aside class="card sessions-panel">
        <el-button class="new-btn" type="primary" plain @click="newChat"><el-icon><Plus /></el-icon>新对话</el-button>
        <div class="session-list">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="session-item"
            :class="{ active: s.id === sessionId }"
            @click="openSession(s.id)"
          >
            <div class="s-main">
              <span class="s-title">{{ s.title }}</span>
              <span class="s-time">{{ s.updated_at }}</span>
            </div>
            <el-icon class="s-del" title="删除会话" @click.stop="removeSession(s.id)"><Delete /></el-icon>
          </div>
          <div v-if="!sessions.length" class="s-empty">暂无历史会话</div>
        </div>
      </aside>

      <div class="card chat-card">
        <div class="assistant-head">
          <div class="assistant-avatar"><el-icon><Service /></el-icon></div>
          <div><strong>筑安云 AI 助手</strong><small><i></i>在线服务</small></div>
        </div>
        <div class="chat-box" ref="boxEl">
          <div v-for="(m, i) in messages" :key="i" class="msg" :class="{ me: m.me }">
            <div class="bubble">
              <template v-if="m.me">{{ m.text }}</template>
              <template v-else>
                <div v-if="m.toolLabel" class="tool-status"><i class="spinner"></i>{{ m.toolLabel }}</div>
                <div v-if="m.text" class="md-body" v-html="render(m.text)"></div>
                <div v-if="!m.text && !m.toolLabel" class="typing" aria-label="AI 正在思考"><i></i><i></i><i></i></div>
                <div v-if="m.refs && m.refs.length" class="refs">
                  <div class="refs-title">依据条款</div>
                  <div v-for="r in m.refs" :key="r.doc_name + r.clause_no" class="ref-item">
                    《{{ r.doc_name }}》{{ r.clause_no }}｜{{ r.title }}
                  </div>
                </div>
                <div v-if="m.weeklyId" class="weekly-tip">
                  周报已保存，<a href="#/weekly">前往周报页查看 →</a>
                </div>
              </template>
            </div>
          </div>
        </div>

        <div class="quick">
          <span>快捷提问</span>
          <el-button v-for="q in quick" :key="q" size="small" round plain @click="send(q)">{{ q }}</el-button>
        </div>

        <div class="input-row">
          <el-input v-model="input" aria-label="向 AI 安全助手提问" placeholder="输入问题，例如：3号楼12层的隐患整改到哪一步了？" size="large" @keydown.enter.exact.prevent="send()">
            <template #append>
              <el-button type="primary" :disabled="!input.trim() || sending" aria-label="发送问题" @click="send()"><el-icon><Position /></el-icon><span>发送</span></el-button>
            </template>
          </el-input>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { Delete } from '@element-plus/icons-vue'
import http from '../api'
import { projectStore, userStore, useUserStore } from '../store'

const GREETING = [
  '您好，我是筑安云 AI 安全助手。',
  '',
  '我可以帮你：',
  '- 查询工单处置进度，按状态/风险筛选工单',
  '- 汇总整改统计、超期与近8周趋势',
  '- 检索现场安全规范条款',
  '- 查看或生成项目安全周报',
  '- 查询责任区域、分包单位与负责人',
  '- 对话式上报隐患，AI 自动匹配责任人',
].join('\n')

const input = ref('')
const sending = ref(false)
const boxEl = ref()
const sessions = ref([])
const sessionId = ref(null)
const messages = ref([{ me: false, text: GREETING, refs: [], weeklyId: null }])

const quick = ['3号楼12层的隐患进度', '本周整改情况统计', '临边防护有哪些规范要求', '有哪些分包单位', '生成安全周报']

// 会话指针只存"上次打开的会话 id"，消息正文全部以服务端为准
function pointerKey() {
  return `zhuan_chat_session:${userStore.user?.id ?? 'anon'}:${projectStore.id || 'default'}`
}

function render(md) {
  return DOMPurify.sanitize(marked.parse(md || ''))
}

async function scrollBottom() {
  await nextTick()
  if (boxEl.value) boxEl.value.scrollTop = boxEl.value.scrollHeight
}

async function loadSessions() {
  try {
    sessions.value = await http.get('/api/chat/sessions')
  } catch { /* 列表加载失败不阻塞对话 */ }
}

function greeting() {
  return [{ me: false, text: GREETING, refs: [], weeklyId: null }]
}

async function openSession(id) {
  if (sending.value) return
  sessionId.value = id
  localStorage.setItem(pointerKey(), String(id))
  try {
    const rows = await http.get(`/api/chat/sessions/${id}/messages`)
    messages.value = rows
      .filter((m) => m.role === 'user' || m.content) // 中断轮的空 assistant 行不渲染
      .map((m) => ({ me: m.role === 'user', text: m.content, refs: m.refs || [], weeklyId: m.weekly_id }))
  } catch {
    messages.value = greeting()
  }
  scrollBottom()
}

function newChat() {
  sessionId.value = null
  localStorage.removeItem(pointerKey())
  messages.value = greeting()
}

async function removeSession(id) {
  try {
    await http.delete(`/api/chat/sessions/${id}`)
  } catch { /* 删除失败保持现状 */ }
  if (id === sessionId.value) newChat()
  loadSessions()
}

watch(
  () => projectStore.id,
  async () => {
    if (sending.value) return
    await loadSessions()
    const saved = localStorage.getItem(pointerKey())
    if (saved && sessions.value.some((s) => s.id === Number(saved))) openSession(Number(saved))
    else newChat()
  }
)

onMounted(async () => {
  localStorage.removeItem('zhuan_chat_history') // 清理旧版本的本地历史
  await loadSessions()
  const saved = localStorage.getItem(pointerKey())
  if (saved && sessions.value.some((s) => s.id === Number(saved))) openSession(Number(saved))
})

async function send(preset) {
  const text = (preset || input.value).trim()
  if (!text || sending.value) return
  messages.value.push({ me: true, text })
  input.value = ''
  sending.value = true
  scrollBottom()

  // reactive 包裹：push 进 messages 后 Vue 返回的是代理对象，
  // 直接改原始对象不会触发视图更新（SSE 增量必须走代理）
  const reply = reactive({ me: false, text: '', refs: [], weeklyId: null, toolLabel: '' })
  messages.value.push(reply)
  try {
    const token = localStorage.getItem('zhuan_token')
    const projectId = localStorage.getItem('zhuan_project')
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(projectId ? { 'X-Project-Id': projectId } : {}),
      },
      body: JSON.stringify({ message: text, session_id: sessionId.value }),
    })
    if (resp.status === 401) {
      useUserStore().logout()
      if (!location.hash.includes('login')) location.hash = '#/login'
      return
    }
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = chunk.split('\n').find((l) => l.startsWith('data: '))
        if (line) handleEvent(reply, JSON.parse(line.slice(6)))
      }
    }
  } catch (e) {
    reply.text += reply.text ? `\n\n（连接中断：${e?.message || e}）` : `抱歉，处理失败，请重试。（${e?.message || e}）`
    console.error('chat send error:', e)
  } finally {
    reply.toolLabel = ''
    sending.value = false
    scrollBottom()
  }
}

function handleEvent(msg, ev) {
  if (ev.type === 'delta') {
    msg.text += ev.text
    scrollBottom()
  } else if (ev.type === 'tool') {
    msg.toolLabel = ev.label || ev.name
  } else if (ev.type === 'refs') {
    msg.refs = ev.refs || []
  } else if (ev.type === 'done') {
    msg.weeklyId = ev.weekly_id || null
    if (ev.session_id && ev.session_id !== sessionId.value) {
      sessionId.value = ev.session_id
      localStorage.setItem(pointerKey(), String(ev.session_id))
      loadSessions()
    }
  } else if (ev.type === 'error') {
    msg.text += `${msg.text ? '\n\n' : ''}⚠️ ${ev.message || 'AI 服务异常，请重试'}`
  }
}
</script>

<style scoped>
.chat-layout { display: flex; gap: 14px; align-items: stretch; }
.sessions-panel { width: 220px; flex: 0 0 auto; display: flex; flex-direction: column; gap: 8px; padding: 10px; }
.new-btn { width: 100%; }
.session-list { flex: 1; overflow-y: auto; }
.session-item { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 9px; cursor: pointer; }
.session-item:hover { background: rgba(77, 123, 226, .07); }
.session-item.active { background: rgba(77, 123, 226, .13); }
.s-main { flex: 1; min-width: 0; }
.s-title { display: block; font-size: 12.5px; color: var(--zhuan-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.s-time { display: block; margin-top: 1px; font-size: 10px; color: var(--zhuan-muted); }
.s-del { flex: 0 0 auto; color: var(--zhuan-muted); opacity: 0; transition: opacity .15s; }
.s-del:hover { color: #d9534f; }
.session-item:hover .s-del { opacity: 1; }
.s-empty { padding: 14px 0; color: var(--zhuan-muted); font-size: 11px; text-align: center; }
.chat-card { flex: 1; min-width: 0; padding: 0; overflow: hidden; }
.assistant-head { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border-bottom: 1px solid var(--zhuan-line); }
.assistant-avatar { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 11px; color: #fff; background: linear-gradient(145deg, var(--zhuan-blue), #4d7be2); }
.assistant-head strong, .assistant-head small { display: block; }
.assistant-head strong { font-size: 13px; }
.assistant-head small { margin-top: 2px; color: var(--zhuan-muted); font-size: 10px; }
.assistant-head small i { display: inline-block; width: 6px; height: 6px; margin-right: 5px; border-radius: 50%; background: #35a873; }
.chat-box { border: 0; border-radius: 0; }
.tool-status { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; color: var(--zhuan-muted); font-size: 12px; }
.spinner { width: 11px; height: 11px; border: 2px solid var(--zhuan-line); border-top-color: var(--zhuan-blue); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.refs { margin-top: 8px; padding: 8px 10px; border-radius: 8px; background: rgba(77, 123, 226, .06); }
.refs-title { margin-bottom: 4px; color: var(--zhuan-muted); font-size: 11px; }
.ref-item { padding: 2px 0; font-size: 12px; line-height: 1.6; color: var(--zhuan-blue); }
.weekly-tip { margin-top: 8px; font-size: 12px; color: var(--zhuan-muted); }
.weekly-tip a { color: var(--zhuan-blue); text-decoration: none; font-weight: 600; }
.quick { display: flex; align-items: center; gap: 8px; padding: 11px 16px 7px; flex-wrap: wrap; border-top: 1px solid var(--zhuan-line); }
.quick > span { margin-right: 2px; color: var(--zhuan-muted); font-size: 11px; }
.input-row { padding: 6px 16px 16px; }
.typing { display: flex; gap: 4px; padding: 15px 17px; }
.typing i { width: 5px; height: 5px; border-radius: 50%; background: #91a0b8; animation: typing 1s ease-in-out infinite; }
.typing i:nth-child(2) { animation-delay: .15s; } .typing i:nth-child(3) { animation-delay: .3s; }
@keyframes typing { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-4px); } }
@media (max-width: 760px) {
  .sessions-panel { display: none; }
  .quick { flex-wrap: nowrap; overflow-x: auto; }
  .quick > * { flex: 0 0 auto; }
  .input-row :deep(.el-input-group__append span) { display: none; }
}
</style>
