<template>
  <div>
    <div class="page-title">安全周报</div>
    <div class="page-sub">按风险等级自动汇总本周隐患治理情况，AI生成周报，支持导出Word</div>

    <div class="card" style="display:flex; gap:10px; align-items:center; margin-bottom:16px">
      <el-select v-model="offset" style="width: 140px">
        <el-option label="本周" :value="0" />
        <el-option label="上周" :value="-1" />
      </el-select>
      <el-button type="primary" :loading="generating" @click="generate">⚡ AI生成周报</el-button>
      <el-button v-if="current" @click="exportWord">📥 导出Word</el-button>
      <span style="flex:1"></span>
      <el-select v-if="history.length" v-model="historyId" placeholder="历史周报" style="width: 260px" @change="viewHistory">
        <el-option v-for="h in history" :key="h.id" :label="h.week" :value="h.id" />
      </el-select>
    </div>

    <div v-if="current" class="card md-body" v-html="rendered"></div>
    <el-empty v-else description="点击「AI生成周报」，AI将基于工单数据自动汇总本周安全情况" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { marked } from 'marked'
import http from '../api'

const offset = ref(0)
const generating = ref(false)
const current = ref(null)
const history = ref([])
const historyId = ref(null)

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
  const data = await http.get('/api/weekly')
  history.value = data.reports
}

function exportWord() {
  const token = localStorage.getItem('zhuan_token')
  fetch(`/api/weekly/${current.value.id}/export`, { headers: { Authorization: `Bearer ${token}` } })
    .then((r) => r.blob())
    .then((blob) => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `筑安云安全周报_${current.value.id}.docx`
      a.click()
    })
}

onMounted(loadHistory)
</script>
