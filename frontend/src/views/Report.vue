<template>
  <div>
    <div class="page-title">隐患上报</div>
    <div class="page-sub">上报后AI自动完成：信息抽取 → 知识库检索 → 风险定级 → 责任人匹配 → 生成待审核工单</div>

    <div class="card">
      <el-tabs v-model="tab">
        <el-tab-pane label="⌨️ 文字上报" name="text">
          <el-input v-model="form.text" type="textarea" :rows="5" maxlength="200" show-word-limit
            placeholder="描述发现的隐患，例：3号楼12层东侧临边防护栏杆缺失，旁边有工人在作业" />
          <div class="examples">
            <el-button v-for="(e, i) in examples" :key="i" size="small" round @click="form.text = e">{{ e.slice(0, 18) }}…</el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="🎙️ 语音上报" name="voice">
          <div class="voice-box">
            <el-button :type="recording ? 'danger' : 'primary'" size="large" circle @click="toggleRec">
              <el-icon :size="26"><Microphone /></el-icon>
            </el-button>
            <div class="voice-tip">
              <template v-if="recording">录音中…再次点击结束</template>
              <template v-else>点击麦克风开始语音上报</template>
              <div v-if="asrEngine" class="engine-note">转写引擎：{{ asrEngine }}</div>
            </div>
          </div>
          <div class="examples">
            <span class="demo-label">无法录音？点演示语音：</span>
            <el-button v-for="(e, i) in demoVoice" :key="i" size="small" round @click="form.text = e">演示{{ i + 1 }}</el-button>
          </div>
          <el-input v-model="form.text" type="textarea" :rows="4" placeholder="语音转写结果（可修改）" />
        </el-tab-pane>

        <el-tab-pane label="📷 图片上报" name="image">
          <el-upload drag :show-file-list="false" accept="image/*" :http-request="uploadImage">
            <el-icon :size="40" color="#8fa3d0"><UploadFilled /></el-icon>
            <div class="el-upload__text">拍摄或上传隐患照片，AI自动识别隐患</div>
          </el-upload>
          <div v-if="imageEngine" class="engine-note">识别引擎：{{ imageEngine }}</div>
          <el-input v-model="form.text" type="textarea" :rows="4" placeholder="AI识别结果（可修改补充后提交）" />
        </el-tab-pane>
      </el-tabs>

      <div class="submit-row">
        <el-button type="primary" size="large" :loading="submitting" :disabled="!form.text.trim()" @click="submit">
          ⚡ 上报并生成整改工单
        </el-button>
      </div>
    </div>

    <el-dialog v-model="showResult" title="AI处理完成 · 工单草稿已生成" width="760px" :close-on-click-modal="false">
      <template v-if="r">
        <el-steps :active="4" align-center class="steps">
          <el-step title="信息抽取" :description="r.extracted?.engine || ''" />
          <el-step title="知识检索" :description="`匹配${(r.order?.regulation_refs || []).length}条条款`" />
          <el-step title="风险定级" />
          <el-step title="责任匹配" />
        </el-steps>

        <el-descriptions :column="2" border size="small" class="mt">
          <el-descriptions-item label="工单编号">{{ r.order?.order_no }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <span class="risk-tag" :class="'risk-' + r.order?.risk_level">{{ r.order?.risk_level }}风险</span>
          </el-descriptions-item>
          <el-descriptions-item label="隐患位置">{{ [r.order?.building, r.order?.floor, r.order?.spot].filter(Boolean).join(' · ') || '未识别到' }}</el-descriptions-item>
          <el-descriptions-item label="隐患类型">{{ r.order?.hazard_type }}</el-descriptions-item>
          <el-descriptions-item label="整改期限" :span="2">{{ r.order?.deadline }}</el-descriptions-item>
        </el-descriptions>

        <el-alert type="success" :closable="false" class="mt" :title="'AI推荐责任人：' + (r.order?.responsible_name || '待人工指定')"
          :description="r.match_reason" show-icon />

        <div class="mt regs">
          <div class="regs-title">📖 检索到的规范条款</div>
          <div v-for="(ref, i) in r.order?.regulation_refs || []" :key="i" class="reg-item">
            《{{ ref.doc_name }}》{{ ref.clause_no }} {{ ref.title }}
          </div>
        </div>

        <div class="mt suggestion">{{ r.order?.suggestion }}</div>

        <el-alert type="warning" :closable="false" class="mt" title="工单当前状态：待审核"
          description="您可以在「整改工单」页面审核该草稿，确认后AI将自动派发至责任人。" />
      </template>
      <template #footer>
        <el-button @click="showResult = false">继续上报</el-button>
        <el-button type="primary" @click="$router.push('/orders'); showResult = false">前往审核 →</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api'

const tab = ref('text')
const form = reactive({ text: '' })
const submitting = ref(false)
const showResult = ref(false)
const r = ref(null)
const recording = ref(false)
const asrEngine = ref('')
const imageEngine = ref('')

const examples = [
  '3号楼12层东侧临边防护栏杆缺失，旁边有工人在进行二次结构作业',
  '5号楼一层大门口消防通道被钢管模板占用，无法通行',
  '地下室区域配电房旁配电箱门未关闭，电缆私拉乱接',
  '6号楼15层北侧电梯井洞口没有防护盖板',
]
const demoVoice = [
  '3号楼12层东侧临边防护栏杆缺失，旁边有工人在作业',
  '5号楼一层门口消防通道被钢管模板占用',
  '2号楼6层有工人未戴安全帽搬运材料',
]

let mediaRecorder = null
let chunks = []

async function toggleRec() {
  if (!recording.value) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaRecorder = new MediaRecorder(stream)
      chunks = []
      mediaRecorder.ondataavailable = (e) => chunks.push(e.data)
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' })
        const fd = new FormData()
        fd.append('file', blob, 'report.webm')
        const data = await http.post('/api/asr', fd)
        form.text = data.transcript
        asrEngine.value = data.engine
        ElMessage.success('语音转写完成')
      }
      mediaRecorder.start()
      recording.value = true
    } catch {
      ElMessage.warning('无法访问麦克风，请使用演示语音或文字上报')
    }
  } else {
    recording.value = false
    mediaRecorder.stop()
  }
}

async function uploadImage(opt) {
  const fd = new FormData()
  fd.append('file', opt.file)
  const data = await http.post('/api/vision', fd)
  form.text = data.analysis
  imageEngine.value = data.engine
  ElMessage.success('图片隐患识别完成，可修改后提交')
}

async function submit() {
  submitting.value = true
  try {
    const data = await http.post('/api/reports', {
      text: form.text.trim(),
      input_type: tab.value === 'text' ? 'text' : tab.value,
    })
    if (data.need_clarify) {
      ElMessage.warning(data.question)
      return
    }
    r.value = data
    showResult.value = true
    form.text = ''
    asrEngine.value = ''
    imageEngine.value = ''
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.examples { margin: 12px 0; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.demo-label { color: #7a869c; font-size: 12px; }
.voice-box { display: flex; align-items: center; gap: 16px; padding: 8px 0 16px; }
.voice-tip { color: #5a6a8a; }
.engine-note { color: #67c23a; font-size: 12px; margin: 8px 0; }
.submit-row { margin-top: 16px; text-align: right; }
.steps { margin-bottom: 8px; }
.mt { margin-top: 14px; }
.regs-title { font-weight: 700; font-size: 13px; margin-bottom: 6px; }
.reg-item { font-size: 12px; color: #4a5a7a; padding: 3px 0; border-bottom: 1px dashed #edf1f7; }
.suggestion { background: #f7f9fc; border-radius: 8px; padding: 12px; font-size: 13px; white-space: pre-wrap; line-height: 1.7; }
</style>
