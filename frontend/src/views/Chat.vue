<template>
  <div class="chat-page">
    <aside class="session-rail" :class="{ collapsed: sessionsCollapsed }">
      <div class="rail-head">
        <el-button class="new-btn" type="primary" @click="newChat"><el-icon><Plus /></el-icon><span>新对话</span></el-button>
        <el-button class="collapse-btn" text circle :aria-label="sessionsCollapsed ? '展开会话列表' : '收起会话列表'" @click="sessionsCollapsed = !sessionsCollapsed"><el-icon><component :is="sessionsCollapsed ? Expand : Fold" /></el-icon></el-button>
      </div>
      <div v-if="!sessionsCollapsed" class="rail-label">最近对话</div>
      <div v-if="!sessionsCollapsed" class="session-list">
        <button v-for="s in sessions" :key="s.id" class="session-item" :class="{ active: s.id === sessionId }" @click="openSession(s.id)">
          <el-icon><ChatLineRound /></el-icon>
          <span class="s-main"><b>{{ s.title }}</b><small>{{ s.updated_at }}</small></span>
          <el-button class="s-del" text circle aria-label="删除会话" @click.stop="removeSession(s)"><el-icon><Delete /></el-icon></el-button>
        </button>
        <div v-if="!sessions.length" class="s-empty"><el-icon><ChatLineRound /></el-icon><span>还没有历史对话</span></div>
      </div>
    </aside>

    <section class="chat-workspace">
      <header class="assistant-head">
        <div class="head-main">
          <el-button class="mobile-sessions" text circle aria-label="打开历史会话" @click="mobileSessionsOpen = true"><el-icon><Clock /></el-icon></el-button>
          <div class="assistant-avatar"><el-icon><component :is="ASSISTANT.icon" /></el-icon></div>
          <div class="assistant-copy"><strong>{{ ASSISTANT.name }}</strong><small><i></i>在线 · {{ ASSISTANT.context }}</small></div>
        </div>
        <el-button v-if="messages.length" text class="head-new" @click="newChat"><el-icon><EditPen /></el-icon>新对话</el-button>
      </header>

      <main ref="boxEl" class="message-scroll">
        <div v-if="!messages.length" class="welcome">
          <div class="welcome-mark"><el-icon><component :is="ASSISTANT.icon" /></el-icon></div>
          <h1>{{ ASSISTANT.welcomeTitle }}</h1>
          <p>{{ ASSISTANT.welcomeCopy }}</p>
          <div class="task-grid">
            <button v-for="task in ASSISTANT.tasks" :key="task.title" @click="send(task.prompt)">
              <span class="task-icon"><el-icon><component :is="task.icon" /></el-icon></span>
              <span><b>{{ task.title }}</b><small>{{ task.copy }}</small></span>
              <el-icon class="task-arrow"><ArrowRight /></el-icon>
            </button>
          </div>
          <div class="welcome-note"><el-icon><Lock /></el-icon>回答基于当前项目数据与权限生成</div>
        </div>

        <div v-else class="message-list">
          <article v-for="(m, i) in messages" :key="m.id || i" class="message" :class="{ me: m.me }">
            <div v-if="!m.me" class="message-avatar"><el-icon><component :is="ASSISTANT.icon" /></el-icon></div>
            <div class="message-column">
              <div class="bubble" :class="{ failed: m.error }">
                <template v-if="m.me">{{ m.text }}</template>
                <template v-else>
                  <div v-if="m.toolSteps?.length" class="tool-trace" :class="{ done: !m.streaming }">
                    <span v-if="m.streaming" class="spinner"></span><el-icon v-else><CircleCheck /></el-icon><span>{{ toolSummary(m) }}</span>
                  </div>
                  <div v-if="m.text" class="md-body" v-html="render(m.text)"></div>
                  <div v-if="m.streaming && !m.text && !m.toolSteps?.length" class="typing" aria-label="AI 正在思考"><i></i><i></i><i></i></div>
                  <ChatArtifact v-for="(artifact, ai) in visibleArtifacts(m)" :key="artifact.data?.token || `${artifact.type}-${ai}`" :artifact="artifact" :busy="resolvingToken === artifact.data?.token" @navigate="router.push" @resolve="resolveAction" />
                  <div v-if="m.refs?.length && !hasRefArtifact(m)" class="legacy-refs"><b>依据条款</b><span v-for="r in m.refs" :key="r.doc_name + r.clause_no">《{{ r.doc_name }}》{{ r.clause_no }} · {{ r.title }}</span></div>
                  <div v-if="m.error" class="error-inline"><el-icon><WarningFilled /></el-icon><span>{{ m.error }}</span><el-button link type="primary" @click="retry(m)">重新发送</el-button></div>
                </template>
              </div>
              <div v-if="!m.me && (m.text || m.error)" class="message-actions"><el-button v-if="m.text" text size="small" @click="copyMessage(m.text)"><el-icon><CopyDocument /></el-icon>复制</el-button></div>
            </div>
          </article>
        </div>
      </main>

      <footer class="composer-wrap">
        <div v-if="messages.length" class="quick-row"><button v-for="q in ASSISTANT.quick.slice(0, 4)" :key="q" :disabled="sending" @click="send(q)">{{ q }}</button></div>
        <div class="composer" :class="{ focused: composerFocused }">
          <el-input ref="inputEl" v-model="input" type="textarea" resize="none" :autosize="{ minRows: 1, maxRows: 5 }" :aria-label="`向${ASSISTANT.name}提问`" :placeholder="ASSISTANT.placeholder" @focus="composerFocused = true" @blur="composerFocused = false" @keydown.enter.exact.prevent="send()" />
          <el-button v-if="sending" class="send-btn stop" circle aria-label="停止生成" @click="stop"><el-icon><VideoPause /></el-icon></el-button>
          <el-button v-else class="send-btn" type="primary" circle :disabled="!input.trim()" aria-label="发送问题" @click="send()"><el-icon><Position /></el-icon></el-button>
        </div>
        <div class="composer-hint">Enter 发送 · Shift + Enter 换行 · AI 内容仅供现场管理参考</div>
      </footer>
    </section>

    <el-drawer v-model="mobileSessionsOpen" direction="ltr" size="min(86vw, 330px)" :with-header="false" class="chat-session-drawer">
      <div class="mobile-rail">
        <div class="mobile-rail-title"><strong>历史对话</strong><el-button text circle @click="mobileSessionsOpen = false"><el-icon><Close /></el-icon></el-button></div>
        <el-button class="new-btn" type="primary" @click="newChat"><el-icon><Plus /></el-icon>新对话</el-button>
        <div class="session-list">
          <button v-for="s in sessions" :key="s.id" class="session-item" :class="{ active: s.id === sessionId }" @click="openSession(s.id); mobileSessionsOpen = false">
            <el-icon><ChatLineRound /></el-icon><span class="s-main"><b>{{ s.title }}</b><small>{{ s.updated_at }}</small></span>
            <el-button class="s-del" text circle @click.stop="removeSession(s)"><el-icon><Delete /></el-icon></el-button>
          </button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, ChatDotRound, ChatLineRound, CircleCheck, Clock, Close, CopyDocument, DataAnalysis, Delete, Document, EditPen, Expand, Fold, Lock, Management, OfficeBuilding, Plus, Position, Reading, Search, Service, Tickets, VideoPause, WarningFilled } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import ChatArtifact from '../components/ChatArtifact.vue'
import http from '../api'
import { projectStore, userStore, useUserStore } from '../store'

const PROFILES = {
  safety: {
    key: 'safety', name: '筑安云 AI 安全助手', icon: Service, context: '当前项目安全智询', placeholder: '询问工单进度、整改统计或安全规范…',
    welcomeTitle: '今天想了解什么？', welcomeCopy: '直接描述你的问题，我会结合当前项目数据查询、分析并给出下一步建议。',
    quick: ['3号楼12层的隐患进度', '本周整改情况统计', '临边防护有哪些规范要求', '生成安全周报'],
    tasks: [
      { title: '查工单', copy: '查询整改状态、责任人与期限', prompt: '3号楼12层的隐患进度', icon: Tickets },
      { title: '看统计', copy: '掌握在办、闭环和超期情况', prompt: '本周整改情况统计', icon: DataAnalysis },
      { title: '问规范', copy: '检索安全条款与处置依据', prompt: '临边防护有哪些规范要求', icon: Reading },
      { title: '生成周报', copy: '自动汇总本周治理成效', prompt: '生成本周安全周报', icon: Document },
      { title: '上报隐患', copy: '用自然语言创建待审核工单', prompt: '我要上报一条现场隐患', icon: ChatDotRound },
    ],
  },
  pm: {
    key: 'pm', name: '筑安云 项目管理助手', icon: OfficeBuilding, context: '项目、区域与分包管理', placeholder: '输入管理指令，例如：新增一个项目…',
    welcomeTitle: '准备管理哪个项目？', welcomeCopy: '我可以查询或整理变更内容；所有写操作都会先生成预览，确认后才执行。',
    quick: ['列出所有项目', '新增一个项目', '查看当前项目的责任区域', '新增一家分包单位'],
    tasks: [
      { title: '项目目录', copy: '查看项目与当前施工阶段', prompt: '列出所有项目', icon: Search },
      { title: '新增项目', copy: '整理项目信息并生成确认单', prompt: '我要新增一个项目', icon: Plus },
      { title: '责任区域', copy: '查询或维护区域与负责人', prompt: '查看当前项目的责任区域', icon: Management },
      { title: '分包单位', copy: '查看或维护分包与负责人', prompt: '查看当前项目的分包单位', icon: OfficeBuilding },
    ],
  },
}

const route = useRoute()
const router = useRouter()
const ASSISTANT = PROFILES[route.meta.assistant === 'pm' ? 'pm' : 'safety']
const input = ref('')
const inputEl = ref()
const sending = ref(false)
const composerFocused = ref(false)
const boxEl = ref()
const sessions = ref([])
const sessionId = ref(null)
const messages = ref([])
const sessionsCollapsed = ref(false)
const mobileSessionsOpen = ref(false)
const resolvingToken = ref('')
let controller = null

function pointerKey() { return `zhuan_chat_session:${ASSISTANT.key}:${userStore.user?.id ?? 'anon'}:${projectStore.id || 'default'}` }
function render(md) { return DOMPurify.sanitize(marked.parse(md || '')) }
async function scrollBottom() { await nextTick(); if (boxEl.value) boxEl.value.scrollTop = boxEl.value.scrollHeight }
async function loadSessions() { try { sessions.value = await http.get('/api/chat/sessions', { params: { assistant: ASSISTANT.key }, silent: true }) } catch { sessions.value = [] } }

async function openSession(id) {
  if (sending.value) stop()
  sessionId.value = id
  localStorage.setItem(pointerKey(), String(id))
  try {
    const rows = await http.get(`/api/chat/sessions/${id}/messages`, { silent: true })
    messages.value = rows.filter((m) => m.role === 'user' || m.content || m.artifacts?.length).map((m) => ({ id: m.id, me: m.role === 'user', text: m.content, refs: m.refs || [], weeklyId: m.weekly_id, artifacts: m.artifacts || [], toolSteps: (m.tool_trace || []).map((t) => ({ ...t, status: 'done' })), streaming: false }))
  } catch { messages.value = []; ElMessage.error('历史会话加载失败') }
  scrollBottom()
}

function newChat() {
  if (sending.value) stop()
  sessionId.value = null; messages.value = []; input.value = ''
  localStorage.removeItem(pointerKey()); mobileSessionsOpen.value = false
  nextTick(() => inputEl.value?.focus())
}

async function removeSession(session) {
  try { await ElMessageBox.confirm(`删除对话“${session.title}”？删除后无法恢复。`, '删除对话', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }) } catch { return }
  try { await http.delete(`/api/chat/sessions/${session.id}`, { silent: true }); if (session.id === sessionId.value) newChat(); await loadSessions(); ElMessage.success('对话已删除') } catch { ElMessage.error('删除失败，请重试') }
}

watch(() => projectStore.id, async () => { if (sending.value) stop(); await loadSessions(); const saved = Number(localStorage.getItem(pointerKey())); if (saved && sessions.value.some((s) => s.id === saved)) await openSession(saved); else newChat() })
onMounted(async () => { localStorage.removeItem('zhuan_chat_history'); await loadSessions(); const saved = Number(localStorage.getItem(pointerKey())); if (saved && sessions.value.some((s) => s.id === saved)) await openSession(saved) })
onBeforeUnmount(() => controller?.abort())
function stop() { controller?.abort(); controller = null }

async function send(preset) {
  const text = (typeof preset === 'string' ? preset : input.value).trim()
  if (!text || sending.value) return
  messages.value.push({ me: true, text }); input.value = ''; sending.value = true
  const reply = reactive({ me: false, text: '', refs: [], artifacts: [], toolSteps: [], streaming: true, error: '', requestText: text })
  messages.value.push(reply); controller = new AbortController(); scrollBottom()
  try {
    const token = localStorage.getItem('zhuan_token'); const projectId = localStorage.getItem('zhuan_project')
    const resp = await fetch('/api/chat', { method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(projectId ? { 'X-Project-Id': projectId } : {}) }, body: JSON.stringify({ message: text, session_id: sessionId.value, assistant: ASSISTANT.key }) })
    if (resp.status === 401) { useUserStore().logout(); router.push('/login'); return }
    if (!resp.ok || !resp.body) throw new Error(`请求失败（${resp.status}）`)
    const reader = resp.body.getReader(); const decoder = new TextDecoder(); let buf = ''
    for (;;) {
      const { done, value } = await reader.read(); if (done) break
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) { const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2); const line = chunk.split('\n').find((l) => l.startsWith('data: ')); if (line) handleEvent(reply, JSON.parse(line.slice(6))) }
    }
  } catch (error) {
    if (error?.name === 'AbortError') { if (!reply.text) reply.text = '已停止生成。' } else reply.error = error?.message || '连接中断，请重试'
  } finally {
    reply.streaming = false; reply.toolSteps.forEach((step) => { step.status = 'done' }); sending.value = false; controller = null; scrollBottom()
  }
}

function handleEvent(msg, ev) {
  if (ev.type === 'delta') msg.text += ev.text
  else if (ev.type === 'tool') msg.toolSteps.push({ name: ev.name, label: ev.label || ev.name, status: 'running' })
  else if (ev.type === 'artifact' && ev.artifact) msg.artifacts.push(ev.artifact)
  else if (ev.type === 'refs') msg.refs = ev.refs || []
  else if (ev.type === 'done') { msg.weeklyId = ev.weekly_id || null; if (ev.session_id && ev.session_id !== sessionId.value) { sessionId.value = ev.session_id; localStorage.setItem(pointerKey(), String(ev.session_id)); loadSessions() } }
  else if (ev.type === 'error') msg.error = ev.message || 'AI 服务异常，请重试'
  scrollBottom()
}

function visibleArtifacts(message) {
  const seen = new Set()
  return (message.artifacts || []).filter((artifact) => { if (artifact.type === 'clause_refs' && !(artifact.data?.refs || []).length) return false; const key = artifact.type === 'clause_refs' ? artifact.type : artifact.data?.token || `${artifact.type}:${artifact.title}`; if (seen.has(key)) return false; seen.add(key); return true })
}
function hasRefArtifact(message) { return (message.artifacts || []).some((a) => a.type === 'clause_refs' && a.data?.refs?.length) }
function toolSummary(message) { const steps = message.toolSteps || []; if (message.streaming) return steps.at(-1)?.label || '正在处理…'; return steps.length > 1 ? `已完成 ${steps.length} 个处理步骤` : (steps[0]?.label || '').replace('正在', '已完成').replace('…', '') }
async function copyMessage(text) { try { await navigator.clipboard.writeText(text); ElMessage.success('已复制回答') } catch { ElMessage.error('复制失败') } }
function retry(message) { message.error = ''; send(message.requestText) }

async function resolveAction(artifact, confirm) {
  const token = artifact.data?.token
  if (!token || resolvingToken.value) return
  resolvingToken.value = token
  try { const result = await http.post(`/api/chat/actions/${token}`, { confirm }, { silent: true }); Object.assign(artifact, result.artifact); ElMessage.success(confirm ? (result.ok ? '变更已执行' : '执行失败，请查看结果') : '操作已取消') }
  catch (error) { ElMessage.error(error.response?.data?.detail || '操作处理失败') }
  finally { resolvingToken.value = '' }
}
</script>

<style scoped>
.chat-page { display:flex;height:calc(100dvh - 124px);min-height:620px;overflow:hidden;border:1px solid rgba(214,224,237,.9);border-radius:16px;background:#fff;box-shadow:var(--zhuan-shadow) }
.session-rail { display:flex;flex:0 0 238px;flex-direction:column;width:238px;padding:12px 10px;border-right:1px solid #e7ecf3;background:#f7f9fc;transition:flex-basis .2s,width .2s }.session-rail.collapsed { flex-basis:64px;width:64px }
.rail-head { display:flex;gap:6px }.new-btn { flex:1;border-radius:10px }.collapse-btn { flex:0 0 auto }.session-rail.collapsed .rail-head { align-items:center;flex-direction:column }.session-rail.collapsed .new-btn { width:40px;flex:0 0 40px;padding:0 }.session-rail.collapsed .new-btn span { display:none }
.rail-label { padding:18px 9px 7px;color:#8a96a9;font-size:10px;font-weight:700;letter-spacing:.08em }.session-list { min-height:0;overflow-y:auto }
.session-item { display:flex;align-items:center;width:100%;gap:9px;padding:9px;border:0;border-radius:10px;color:#536078;background:transparent;text-align:left;cursor:pointer }.session-item:hover { background:#edf2fa }.session-item.active { color:#1e4fb9;background:#e7eefc }
.s-main { display:grid;flex:1;min-width:0;gap:2px }.s-main b { overflow:hidden;font-size:12px;font-weight:650;text-overflow:ellipsis;white-space:nowrap }.s-main small { color:#8a96a9;font-size:9px }.s-del { flex:0 0 auto;opacity:0 }.session-item:hover .s-del,.session-item:focus-within .s-del { opacity:1 }.s-del:hover { color:#d94b4b }
.s-empty { display:grid;justify-items:center;gap:8px;padding:48px 8px;color:#9aa5b7;font-size:11px }.s-empty .el-icon { font-size:24px }
.chat-workspace { display:flex;flex:1;min-width:0;flex-direction:column;background:#fff }.assistant-head { display:flex;flex:0 0 66px;align-items:center;justify-content:space-between;padding:0 20px;border-bottom:1px solid #e8edf4 }
.head-main { display:flex;align-items:center;min-width:0;gap:10px }.assistant-avatar { display:grid;flex:0 0 auto;place-items:center;width:36px;height:36px;border-radius:12px;color:#fff;background:linear-gradient(145deg,#2459d3,#4d7be2);box-shadow:0 7px 16px rgba(36,89,211,.22) }.assistant-copy { min-width:0 }.assistant-copy strong,.assistant-copy small { display:block }.assistant-copy strong { font-size:13px }.assistant-copy small { margin-top:2px;color:#7c899e;font-size:10px }.assistant-copy small i { display:inline-block;width:6px;height:6px;margin-right:5px;border-radius:50%;background:#36ad78 }.mobile-sessions { display:none }.head-new { color:#647189 }
.message-scroll { flex:1;min-height:0;overflow-y:auto;background:linear-gradient(180deg,#fbfcfe 0%,#f7f9fc 100%);scroll-behavior:smooth }.welcome { display:grid;align-content:center;width:min(760px,calc(100% - 36px));min-height:100%;margin:auto;padding:34px 0;text-align:center }
.welcome-mark { display:grid;place-items:center;width:56px;height:56px;margin:0 auto 15px;border-radius:18px;color:#fff;background:linear-gradient(145deg,#183e9a,#3670ea);box-shadow:0 12px 28px rgba(36,89,211,.24);font-size:25px }.welcome h1 { margin:0;font-size:24px;letter-spacing:-.03em }.welcome>p { margin:8px auto 22px;color:#718098;font-size:13px;line-height:1.7 }
.task-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;text-align:left }.task-grid button { display:flex;align-items:center;gap:11px;min-height:72px;padding:12px;border:1px solid #e1e8f2;border-radius:13px;color:inherit;background:rgba(255,255,255,.88);cursor:pointer;transition:border-color .18s,transform .18s,box-shadow .18s }.task-grid button:hover { border-color:#aebfe9;transform:translateY(-1px);box-shadow:0 8px 20px rgba(29,55,99,.08) }.task-icon { display:grid;flex:0 0 auto;place-items:center;width:38px;height:38px;border-radius:11px;color:#2459d3;background:#edf3ff;font-size:17px }.task-grid button>span:nth-child(2) { display:grid;flex:1;gap:3px }.task-grid b { font-size:13px }.task-grid small { color:#7b879b;font-size:10px }.task-arrow { color:#a3adbd }.welcome-note { display:flex;align-items:center;justify-content:center;gap:5px;margin-top:18px;color:#9aa5b5;font-size:10px }
.message-list { width:min(900px,calc(100% - 36px));margin:0 auto;padding:24px 0 32px }.message { display:flex;align-items:flex-start;gap:10px;margin-bottom:20px }.message.me { justify-content:flex-end }.message-avatar { display:grid;flex:0 0 auto;place-items:center;width:30px;height:30px;border-radius:10px;color:#2459d3;background:#e9f0ff }.message-column { max-width:min(78%,760px);min-width:0 }.message.me .message-column { max-width:min(72%,680px) }
.bubble { padding:12px 15px;border:1px solid #e1e7f0;border-radius:5px 16px 16px;background:#fff;box-shadow:0 3px 12px rgba(18,44,86,.045);font-size:13px;line-height:1.7;overflow-wrap:anywhere }.message.me .bubble { color:#fff;border-color:transparent;border-radius:16px 5px 16px 16px;background:#2459d3;box-shadow:0 7px 18px rgba(36,89,211,.16);white-space:pre-wrap }.bubble.failed { border-color:#f0caca }
.tool-trace { display:flex;align-items:center;gap:7px;margin-bottom:8px;color:#68768e;font-size:10px }.tool-trace.done { color:#6c987e }.spinner { width:11px;height:11px;border:2px solid #dbe3ef;border-top-color:#2459d3;border-radius:50%;animation:spin .8s linear infinite }.typing { display:flex;gap:4px;padding:5px 1px }.typing i { width:5px;height:5px;border-radius:50%;background:#91a0b8;animation:typing 1s ease-in-out infinite }.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}
.message-actions { min-height:24px;margin-top:2px;opacity:0;transition:opacity .15s }.message:hover .message-actions { opacity:1 }.message-actions .el-button { color:#8490a4;font-size:10px }.legacy-refs { display:grid;gap:4px;margin-top:10px;padding:9px 10px;border-radius:9px;background:#f3f6fb }.legacy-refs b { color:#6c7890;font-size:10px }.legacy-refs span { color:#2459d3;font-size:11px }.error-inline { display:flex;align-items:center;gap:7px;margin-top:8px;padding:8px 10px;border-radius:9px;color:#b34242;background:#fff1f1;font-size:11px }.error-inline span { flex:1 }
.composer-wrap { flex:0 0 auto;padding:8px 18px 11px;border-top:1px solid #e8edf4;background:#fff }.quick-row { display:flex;gap:7px;max-width:900px;margin:0 auto 7px;overflow-x:auto }.quick-row button { flex:0 0 auto;padding:5px 10px;border:1px solid #e2e8f1;border-radius:99px;color:#647189;background:#fafbfe;font-size:10px;cursor:pointer }.quick-row button:hover { color:#2459d3;border-color:#b8c8eb;background:#f3f7ff }
.composer { display:flex;align-items:flex-end;gap:9px;max-width:900px;margin:0 auto;padding:8px 8px 8px 13px;border:1px solid #d9e1ec;border-radius:15px;background:#fff;box-shadow:0 6px 18px rgba(25,50,92,.07);transition:border-color .18s,box-shadow .18s }.composer.focused { border-color:#9eb3e5;box-shadow:0 8px 22px rgba(36,89,211,.11) }.composer :deep(.el-textarea__inner) { min-height:28px!important;padding:4px 0;border:0;background:transparent;box-shadow:none;line-height:20px }.send-btn { flex:0 0 auto;width:34px;height:34px }.send-btn.stop { color:#fff;background:#263550 }.composer-hint { margin-top:5px;color:#a0a9b8;font-size:9px;text-align:center }
.mobile-rail { display:flex;height:100%;flex-direction:column;gap:12px;padding:14px;background:#f7f9fc }.mobile-rail-title { display:flex;align-items:center;justify-content:space-between }.mobile-rail>.new-btn { width:100%;height:40px;flex:0 0 40px }.mobile-rail .session-list { flex:1 }
@keyframes spin { to { transform:rotate(360deg) } } @keyframes typing { 0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-4px)} }
@media (max-width:900px) { .chat-page { height:calc(100dvh - 108px);min-height:520px }.session-rail { display:none }.mobile-sessions { display:inline-flex }.message-column { max-width:min(86%,720px) } }
@media (max-width:600px) { .chat-page { height:calc(100dvh - 100px);min-height:460px;border-radius:13px }.assistant-head { flex-basis:58px;padding:0 10px }.assistant-avatar { width:32px;height:32px }.assistant-copy small { max-width:210px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap }.head-new { font-size:0 }.head-new .el-icon { margin:0;font-size:16px }.welcome { width:calc(100% - 24px);padding:24px 0 }.welcome h1 { font-size:21px }.task-grid { grid-template-columns:1fr }.task-grid button { min-height:62px }.message-list { width:calc(100% - 20px);padding-top:16px }.message { gap:6px;margin-bottom:15px }.message-avatar { width:26px;height:26px }.message-column,.message.me .message-column { max-width:89% }.bubble { padding:10px 12px }.composer-wrap { padding:7px 9px 8px }.quick-row { margin-bottom:6px }.composer-hint { display:none }.message-actions { opacity:1 } }
</style>
