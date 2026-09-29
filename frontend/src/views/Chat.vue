<template>
  <div class="page-shell">
    <div class="page-intro">
      <div class="page-title">现场安全智询</div>
      <div class="page-sub">查询工单进度、治理统计和规范条款，也可以直接生成安全周报。</div>
    </div>

    <div class="card chat-card">
      <div class="assistant-head">
        <div class="assistant-avatar"><el-icon><Service /></el-icon></div>
        <div><strong>筑安云 AI 助手</strong><small><i></i>在线服务</small></div>
      </div>
      <div class="chat-box" ref="boxEl">
        <div v-for="(m, i) in messages" :key="i" class="msg" :class="{ me: m.me }">
          <div class="bubble">
            <div v-if="m.me">{{ m.text }}</div>
            <div v-else class="md-body" v-html="m.html"></div>
          </div>
        </div>
        <div v-if="sending" class="msg"><div class="bubble typing" aria-label="AI 正在思考"><i></i><i></i><i></i></div></div>
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
</template>

<script setup>
import { nextTick, ref } from 'vue'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import http from '../api'

const input = ref('')
const sending = ref(false)
const boxEl = ref()
const messages = ref([
  {
    me: false,
    html: marked.parse(
      '您好，我是筑安云 AI 安全助手。\n\n我可以帮你：\n- 查询工单处置进度\n- 汇总本周整改情况\n- 检索现场安全规范\n- 生成项目安全周报'
    ),
  },
])
const quick = ['3号楼12层的隐患进度', '本周整改情况统计', '临边防护有哪些规范要求', '生成安全周报']

async function scrollBottom() {
  await nextTick()
  if (boxEl.value) boxEl.value.scrollTop = boxEl.value.scrollHeight
}

async function send(preset) {
  const text = (preset || input.value).trim()
  if (!text || sending.value) return
  messages.value.push({ me: true, text })
  input.value = ''
  sending.value = true
  scrollBottom()
  try {
    const data = await http.post('/api/chat', { message: text })
    messages.value.push({ me: false, html: marked.parse(data.reply || ''), weeklyId: data.weekly_id })
  } catch {
    messages.value.push({ me: false, html: marked.parse('抱歉，处理失败，请重试。') })
  } finally {
    sending.value = false
    scrollBottom()
  }
}
</script>

<style scoped>
.chat-card { padding: 0; overflow: hidden; }
.assistant-head { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border-bottom: 1px solid var(--zhuan-line); }
.assistant-avatar { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 11px; color: #fff; background: linear-gradient(145deg, var(--zhuan-blue), #4d7be2); }
.assistant-head strong, .assistant-head small { display: block; }
.assistant-head strong { font-size: 13px; }
.assistant-head small { margin-top: 2px; color: var(--zhuan-muted); font-size: 10px; }
.assistant-head small i { display: inline-block; width: 6px; height: 6px; margin-right: 5px; border-radius: 50%; background: #35a873; }
.chat-box { border: 0; border-radius: 0; }
.quick { display: flex; align-items: center; gap: 8px; padding: 11px 16px 7px; flex-wrap: wrap; border-top: 1px solid var(--zhuan-line); }
.quick > span { margin-right: 2px; color: var(--zhuan-muted); font-size: 11px; }
.input-row { padding: 6px 16px 16px; }
.typing { display: flex; gap: 4px; padding: 15px 17px; }
.typing i { width: 5px; height: 5px; border-radius: 50%; background: #91a0b8; animation: typing 1s ease-in-out infinite; }
.typing i:nth-child(2) { animation-delay: .15s; } .typing i:nth-child(3) { animation-delay: .3s; }
@keyframes typing { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-4px); } }
@media (max-width: 600px) {
  .quick { flex-wrap: nowrap; overflow-x: auto; }
  .quick > * { flex: 0 0 auto; }
  .input-row :deep(.el-input-group__append span) { display: none; }
}
</style>
