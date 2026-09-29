<template>
  <div class="page-shell">
    <div class="page-intro">
      <div class="page-title">项目安全复盘</div>
      <div class="page-sub">汇总隐患治理数据，由 AI 生成结构化周报并支持 Word 导出。</div>
    </div>

    <div class="card toolbar">
      <el-select v-model="offset" style="width: 140px">
        <el-option label="本周" :value="0" />
        <el-option label="上周" :value="-1" />
      </el-select>
      <el-button type="primary" :loading="generating" @click="generate"><el-icon><MagicStick /></el-icon>AI 生成周报</el-button>
      <el-button v-if="current" :loading="exporting" @click="exportWord"><el-icon><Download /></el-icon>导出 Word</el-button>
      <span class="toolbar-spacer"></span>
      <el-select v-if="history.length" v-model="historyId" placeholder="历史周报" style="width: 260px" @change="viewHistory">
        <el-option v-for="h in history" :key="h.id" :label="h.week" :value="h.id" />
      </el-select>
    </div>

    <div v-if="loading" class="card"><el-skeleton :rows="9" animated /></div>
    <div v-else-if="error" class="card error-state">
      <div><el-icon><WarningFilled /></el-icon><div class="error-title">历史周报加载失败</div><div class="error-copy">请稍后重试。</div><el-button type="primary" @click="loadHistory">重新加载</el-button></div>
    </div>
    <article v-else-if="current" class="card report-content md-body" v-html="rendered"></article>
    <div v-else class="card empty-state"><el-empty :image-size="100" description="选择时间范围并生成第一份安全周报" /></div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import http from '../api'

const offset = ref(0)
const generating = ref(false)
const current = ref(null)
const history = ref([])
const historyId = ref(null)
const loading = ref(true)
const error = ref(false)
const exporting = ref(false)

const rendered = computed(() => (current.value ? marked.parse(current.value.content_md) : ''))

async function generate() {
  generating.value = true
  try {
    current.value = await http.post('/api/weekly/generate', { offset: offset.value })
    await loadHistory()
    historyId.value = current.value.id
  } finally {
    generating.value = false
  }
}

async function viewHistory(id) {
  const data = await http.get(`/api/weekly/${id}`)
  current.value = data
}

async function loadHistory() {
  loading.value = true
  error.value = false
  try {
    const data = await http.get('/api/weekly')
    history.value = data.reports
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function exportWord() {
  exporting.value = true
  const token = localStorage.getItem('zhuan_token')
  try {
    const response = await fetch(`/api/weekly/${current.value.id}/export`, { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw new Error('export failed')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `筑安云安全周报_${current.value.id}.docx`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('周报导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

onMounted(loadHistory)
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.toolbar-spacer { flex: 1; }
.report-content { max-width: 980px; margin: 0 auto; padding: 30px clamp(20px, 4vw, 52px); }
@media (max-width: 760px) {
  .toolbar { align-items: stretch; flex-direction: column; }
  .toolbar > .el-select { width: 100% !important; }
  .toolbar-spacer { display: none; }
}
</style>
