<template>
  <div class="page-shell">
    <div class="page-intro">
      <div class="page-title">AI 服务配置</div>
      <div class="page-sub">管理模型与访问凭证。保存后立即生效，无需重启服务。</div>
    </div>

    <div class="settings-grid">
    <div class="card settings-card" v-loading="loading">
      <div v-if="error && !loading" class="error-state">
        <div><el-icon><WarningFilled /></el-icon><div class="error-title">设置加载失败</div><div class="error-copy">请检查服务状态后重试。</div><el-button type="primary" @click="load">重新加载</el-button></div>
      </div>
      <el-form v-else label-width="130px" label-position="left">
        <el-form-item label="AI 模式">
          <el-radio-group v-model="form.mock_mode">
            <el-radio-button :value="false">真实 AI（通义千问）</el-radio-button>
            <el-radio-button :value="true">内置模拟引擎</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password
            :placeholder="s.has_key ? `留空则继续使用当前 Key（${s.api_key_masked}）` : '粘贴阿里云百炼 DashScope 的 Key（sk-开头）'" />
        </el-form-item>

        <el-form-item label="文本模型">
          <el-select v-model="form.text_model" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="m in ['qwen-flash', 'qwen-turbo', 'qwen-plus', 'qwen-max']" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>

        <el-form-item label="图片识别模型">
          <el-select v-model="form.vl_model" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="m in ['qwen-vl-plus', 'qwen-vl-max']" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>

        <el-form-item label="向量模型">
          <el-select v-model="form.embed_model" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="m in ['text-embedding-v4', 'text-embedding-v3']" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>

        <el-form-item label="语音识别模型">
          <el-select v-model="form.asr_model" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="m in ['qwen3-asr-flash', 'paraformer-v2']" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button @click="testConn" :loading="testing"><el-icon><Connection /></el-icon>测试连接</el-button>
          <el-button type="primary" @click="save" :loading="saving"><el-icon><Check /></el-icon>保存设置</el-button>
          <el-tag v-if="testResult === 'ok'" type="success" style="margin-left:10px">连接成功</el-tag>
          <el-tag v-else-if="testResult === 'fail'" type="danger" style="margin-left:10px">连接失败</el-tag>
        </el-form-item>
      </el-form>
    </div>
    <aside class="card security-note">
      <div class="note-icon"><el-icon><Lock /></el-icon></div>
      <strong>凭证安全</strong>
      <p>API Key 仅保存在服务器数据库中，不会返回或暴露给浏览器。</p>
      <div class="note-line"><span>当前模式</span><b>{{ form.mock_mode ? '模拟引擎' : '真实 AI' }}</b></div>
      <div class="note-line"><span>凭证状态</span><b>{{ s.has_key ? '已配置' : '未配置' }}</b></div>
      <div v-if="savedAt" class="saved-at">最近更新：{{ savedAt }}</div>
    </aside>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api'

const s = ref({})
const form = reactive({ mock_mode: false, api_key: '', text_model: '', vl_model: '', embed_model: '', asr_model: '' })
const saving = ref(false)
const testing = ref(false)
const testResult = ref('')
const savedAt = ref('')
const loading = ref(true)
const error = ref(false)

onMounted(load)

async function load() {
  loading.value = true
  error.value = false
  try {
    const data = await http.get('/api/settings')
    s.value = data
    form.mock_mode = data.mock_mode
    form.text_model = data.text_model
    form.vl_model = data.vl_model
    form.embed_model = data.embed_model
    form.asr_model = data.asr_model
    savedAt.value = data.updated_at || ''
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await http.put('/api/settings', form)
    ElMessage.success('已保存，立即生效')
    await load()
  } finally {
    saving.value = false
  }
}

async function testConn() {
  testing.value = true
  testResult.value = ''
  try {
    const r = await http.post('/api/settings/test', { api_key: form.api_key, model: form.text_model })
    if (r.ok) {
      testResult.value = 'ok'
      ElMessage.success(`连接成功（${r.model} 回复：${r.reply}）`)
    } else {
      testResult.value = 'fail'
    }
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.hint { color: #98a3b8; font-size: 12px; line-height: 1.6; width: 100%; margin-top: 2px; }
.settings-grid { display: grid; grid-template-columns: minmax(0, 760px) minmax(220px, 300px); gap: 16px; align-items: start; }
.settings-card { min-height: 380px; }
.security-note { position: sticky; top: 94px; }
.note-icon { display: grid; place-items: center; width: 42px; height: 42px; margin-bottom: 14px; border-radius: 12px; color: var(--zhuan-blue); background: #edf2fd; font-size: 20px; }
.security-note strong { font-size: 15px; }
.security-note p { margin: 7px 0 18px; color: var(--zhuan-muted); font-size: 12px; line-height: 1.7; }
.note-line { display: flex; justify-content: space-between; padding: 10px 0; border-top: 1px solid var(--zhuan-line); color: var(--zhuan-muted); font-size: 12px; }
.note-line b { color: var(--zhuan-text); font-weight: 650; }
.saved-at { margin-top: 13px; color: #929db0; font-size: 10px; }
@media (max-width: 980px) { .settings-grid { grid-template-columns: 1fr; } .security-note { position: static; } }
@media (max-width: 600px) {
  :deep(.el-form-item) { display: block; }
  :deep(.el-form-item__label) { width: auto !important; margin-bottom: 6px; line-height: 1.4; }
  :deep(.el-form-item__content) { margin-left: 0 !important; }
  :deep(.el-radio-group) { display: grid; width: 100%; }
}
</style>
