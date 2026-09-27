<template>
  <div>
    <div class="page-title">系统设置</div>
    <div class="page-sub">AI 引擎与模型配置，保存后立即生效（无需重启）；API Key 保存在服务器数据库，不会泄露到浏览器</div>

    <div class="card" style="max-width: 720px">
      <el-form label-width="130px" label-position="left">
        <el-form-item label="AI 模式">
          <el-radio-group v-model="form.mock_mode">
            <el-radio-button :value="false">真实 AI（通义千问）</el-radio-button>
            <el-radio-button :value="true">内置模拟引擎（演示兜底）</el-radio-button>
          </el-radio-group>
          <div class="hint">模拟引擎不消耗 API 额度、断网可用；正式演示请选真实 AI</div>
        </el-form-item>

        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password
            :placeholder="s.has_key ? `留空则继续使用服务器当前 Key（${s.api_key_masked}）` : '粘贴阿里云百炼 DashScope 的 Key（sk-开头）'" />
          <div class="hint">组员各自测试时，填自己的 Key 保存即可，随时可换；当前服务器 Key：{{ s.api_key_masked || '未配置' }}</div>
        </el-form-item>

        <el-form-item label="文本模型">
          <el-select v-model="form.text_model" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="m in ['qwen-flash', 'qwen-turbo', 'qwen-plus', 'qwen-max']" :key="m" :label="m" :value="m" />
          </el-select>
          <div class="hint">隐患抽取、处置建议、周报撰写、AI问答（推荐 qwen-flash，便宜且快）</div>
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
          <el-button @click="testConn" :loading="testing">🔍 测试连接</el-button>
          <el-button type="primary" @click="save" :loading="saving">保存设置</el-button>
          <el-tag v-if="testResult === 'ok'" type="success" style="margin-left:10px">连接成功</el-tag>
          <el-tag v-else-if="testResult === 'fail'" type="danger" style="margin-left:10px">连接失败</el-tag>
        </el-form-item>
      </el-form>

      <el-alert v-if="testError" type="error" :title="testError" :closable="false" style="margin-top: 8px" />
      <el-alert type="info" :closable="false"
        :title="'提示：切换 Key 后首次上报会重新校验；向量缓存按内容自动失效重算' + (savedAt ? '｜最后一次保存：' + savedAt : '')" />
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
const testError = ref('')
const savedAt = ref('')

onMounted(load)

async function load() {
  const data = await http.get('/api/settings')
  s.value = data
  form.mock_mode = data.mock_mode
  form.text_model = data.text_model
  form.vl_model = data.vl_model
  form.embed_model = data.embed_model
  form.asr_model = data.asr_model
  savedAt.value = data.updated_at || ''
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
  testError.value = ''
  try {
    const r = await http.post('/api/settings/test', { api_key: form.api_key, model: form.text_model })
    if (r.ok) {
      testResult.value = 'ok'
      ElMessage.success(`连接成功（${r.model} 回复：${r.reply}）`)
    } else {
      testResult.value = 'fail'
      testError.value = r.error
    }
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.hint { color: #98a3b8; font-size: 12px; line-height: 1.6; width: 100%; margin-top: 2px; }
</style>
