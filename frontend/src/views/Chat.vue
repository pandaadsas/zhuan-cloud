<template>
  <div>
    <div class="page-title">AI安全助手</div>
    <div class="page-sub">自然语言查进度、查统计、问规范条款、一键生成周报</div>

    <div class="card">
      <div class="chat-box" ref="boxEl">
        <div v-for="(m, i) in messages" :key="i" class="msg" :class="{ me: m.me }">
          <div class="bubble">
            <div v-if="m.me">{{ m.text }}</div>
            <div v-else class="md-body" v-html="m.html"></div>
          </div>
        </div>
      </div>

      <div class="quick">
        <el-button v-for="q in quick" :key="q" size="small" round plain @click="send(q)">{{ q }}</el-button>
      </div>

      <div class="input-row">
        <el-input v-model="input" placeholder="试试：3号楼12层的隐患整改到哪一步了？" size="large" @keyup.enter="send()">
          <template #append>
            <el-button type="primary" :loading="sending" @click="send()">发送</el-button>
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
      '您好，我是筑安云AI安全助手 🤖\n\n可以帮我：\n- 查工单进度（如：3号楼12层的隐患进度）\n- 查统计（如：本周整改情况）\n- 答规范问题（如：临边防护有什么要求）\n- 生成安全周报（安全员/总监/项目经理）'
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
.quick { display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
.input-row { margin-top: 4px; }
</style>
