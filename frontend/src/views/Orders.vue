<template>
  <div>
    <div class="page-title">整改工单</div>
    <div class="page-sub">工单状态机：待审核 → 已派发 → 整改中 → 待复查 → 已闭环（可驳回/退回/延期，超期自动预警）</div>

    <div class="card">
      <div class="filters">
        <el-select v-model="f.status" placeholder="全部状态" clearable style="width: 130px" @change="load">
          <el-option v-for="(label, key) in statusMap" :key="key" :label="label" :value="key" />
        </el-select>
        <el-select v-model="f.risk" placeholder="全部风险" clearable style="width: 110px" @change="load">
          <el-option v-for="l in ['低', '中', '高', '重大']" :key="l" :label="l + '风险'" :value="l" />
        </el-select>
        <el-input v-model="f.q" placeholder="搜索工单号/标题/描述" clearable style="width: 220px" @keyup.enter="load" @clear="load" />
        <el-button type="primary" plain @click="load">查询</el-button>
        <el-checkbox v-if="isOfficer" v-model="f.mine" label="只看我上报的" @change="load" />
        <span style="flex: 1"></span>
        <el-tag effect="plain">共 {{ orders.length }} 单</el-tag>
      </div>

      <el-table :data="orders" size="small" stripe @row-click="openDetail" highlight-current-row>
        <el-table-column prop="order_no" label="工单号" width="140" />
        <el-table-column prop="title" label="隐患标题" min-width="230" show-overflow-tooltip />
        <el-table-column prop="risk_level" label="风险" width="80">
          <template #default="{ row }"><span class="risk-tag" :class="'risk-' + row.risk_level">{{ row.risk_level }}</span></template>
        </el-table-column>
        <el-table-column prop="status_label" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="responsible_name" label="责任人" width="90" />
        <el-table-column label="期限" width="130">
          <template #default="{ row }">
            <span :class="{ 'overdue-txt': row.overdue }">{{ row.deadline || '-' }}</span>
            <el-tag v-if="row.overdue" type="danger" size="small" effect="dark" style="margin-left:4px">超期</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source_label" label="来源" width="70">
          <template #default="{ row }">{{ { text: '文字', voice: '语音', image: '图片' }[row.source_type] }}</template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer v-model="drawer" :title="detail?.order?.order_no" size="560px">
      <template v-if="detail">
        <div class="d-title">{{ detail.order.title }}</div>
        <div class="d-tags">
          <el-tag type="danger" effect="dark" size="small">{{ detail.order.risk_level }}风险</el-tag>
          <el-tag :type="statusType(detail.order.status)" size="small">{{ detail.order.status_label }}</el-tag>
          <el-tag v-if="detail.order.overdue" type="danger" size="small" effect="dark">已超期</el-tag>
          <el-tag size="small" type="info">{{ { text: '文字上报', voice: '语音上报', image: '图片上报' }[detail.order.source_type] }}</el-tag>
        </div>

        <el-descriptions :column="2" border size="small" class="mt">
          <el-descriptions-item label="位置" :span="2">{{ [detail.order.building, detail.order.floor, detail.order.spot].filter(Boolean).join(' · ') || '未识别' }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ detail.order.hazard_type }}</el-descriptions-item>
          <el-descriptions-item label="责任人">{{ detail.order.responsible_name || '未指定' }}{{ detail.order.responsible_sub ? '（' + detail.order.responsible_sub + '）' : '' }}</el-descriptions-item>
          <el-descriptions-item label="整改期限">{{ detail.order.deadline || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.order.created_at }}</el-descriptions-item>
        </el-descriptions>

        <div class="sec">隐患描述</div>
        <div class="desc">{{ detail.order.description }}</div>

        <div class="sec">AI处置建议（含规范依据）</div>
        <div class="desc pre">{{ detail.order.suggestion }}</div>
        <div v-if="(detail.order.regulation_refs || []).length" class="refs">
          <el-tag v-for="(ref, i) in detail.order.regulation_refs" :key="i" size="small" effect="plain" class="ref-tag">
            《{{ ref.doc_name }}》{{ ref.clause_no }}
          </el-tag>
        </div>

        <template v-if="detail.order.rect_note">
          <div class="sec">整改说明</div>
          <div class="desc">{{ detail.order.rect_note }}</div>
        </template>

        <div v-if="actionBarVisible" class="sec">操作</div>
        <div v-if="actionBarVisible" class="actions">
          <template v-if="detail.order.status === 'pending_review' && canReview">
            <el-select v-model="chosenResp" placeholder="指定责任人（AI已推荐）" style="width: 260px">
              <el-option v-for="u in respUsers" :key="u.id" :label="u.name + '（' + u.subcontractor + '）'" :value="u.id" />
            </el-select>
            <el-input v-model="note" placeholder="审核备注（可空）" style="width: 200px" />
            <el-button type="primary" @click="act('approve')">✅ 审核通过并派单</el-button>
            <el-button type="danger" plain @click="act('reject')">驳回</el-button>
          </template>
          <template v-else-if="detail.order.status === 'dispatched' && isMine">
            <el-button type="primary" @click="act('start')">🔧 开始整改</el-button>
          </template>
          <template v-else-if="detail.order.status === 'rectifying' && isMine">
            <el-input v-model="note" type="textarea" :rows="2" placeholder="整改说明：已完成哪些整改措施" />
            <el-button type="primary" style="margin-top: 8px" @click="act('submit')">📤 提交复查</el-button>
          </template>
          <template v-else-if="detail.order.status === 'recheck' && canReview">
            <el-input v-model="note" placeholder="复查意见（可空）" />
            <div style="margin-top: 8px; display: flex; gap: 8px">
              <el-button type="success" @click="act('pass')">✅ 复查合格·闭环</el-button>
              <el-button type="warning" plain @click="act('fail_recheck')">不合格·退回整改</el-button>
            </div>
          </template>
          <template v-if="canReview && ['dispatched', 'rectifying'].includes(detail.order.status)">
            <el-button plain type="info" @click="act('extend')">⏰ 延期2天</el-button>
          </template>
        </div>

        <div class="sec">流转记录</div>
        <el-timeline>
          <el-timeline-item v-for="e in detail.events" :key="e.id" :timestamp="e.created_at" placement="top">
            <b>{{ e.actor }}</b> · {{ e.action }}
            <div class="ev-detail" v-if="e.detail">{{ e.detail }}</div>
          </el-timeline-item>
        </el-timeline>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api'
import { userStore } from '../store'

const statusMap = {
  pending_review: '待审核', dispatched: '已派发', rectifying: '整改中',
  recheck: '待复查', closed: '已闭环', rejected: '已驳回',
}
const orders = ref([])
const detail = ref(null)
const drawer = ref(false)
const respUsers = ref([])
const chosenResp = ref(null)
const note = ref('')
const f = reactive({ status: '', risk: '', q: '', mine: false })

const role = computed(() => userStore.user?.role)
const isOfficer = computed(() => ['safety_officer', 'safety_supervisor'].includes(role.value))
const canReview = computed(() => ['safety_officer', 'safety_supervisor'].includes(role.value))
const isMine = computed(() => detail.value?.order?.responsible_user_id === userStore.user?.id)
const actionBarVisible = computed(() => {
  const o = detail.value?.order
  if (!o) return false
  if (['pending_review'].includes(o.status)) return canReview.value
  if (['dispatched', 'rectifying'].includes(o.status)) return canReview.value || isMine.value
  if (o.status === 'recheck') return canReview.value
  return false
})

function statusType(s) {
  return { pending_review: 'warning', dispatched: 'primary', rectifying: '', recheck: 'warning', closed: 'success', rejected: 'info' }[s]
}

async function load() {
  const params = {}
  if (f.status) params.status = f.status
  if (f.risk) params.risk = f.risk
  if (f.q) params.q = f.q
  if (f.mine) params.mine = 1
  const data = await http.get('/api/orders', { params })
  orders.value = data.orders
}

async function openDetail(row) {
  note.value = ''
  const data = await http.get(`/api/orders/${row.id}`)
  detail.value = data
  chosenResp.value = data.order.responsible_user_id || null
  drawer.value = true
}

async function act(action) {
  await http.post(`/api/orders/${detail.value.order.id}/action`, {
    action,
    note: note.value,
    responsible_user_id: action === 'approve' ? chosenResp.value : undefined,
  })
  ElMessage.success('操作成功')
  const fresh = await http.get(`/api/orders/${detail.value.order.id}`)
  detail.value = fresh
  await load()
}

onMounted(async () => {
  await load()
  try {
    const opt = await http.get('/api/meta/options')
    respUsers.value = opt.responsible_users
  } catch {}
})
</script>

<style scoped>
.filters { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.overdue-txt { color: #f56c6c; font-weight: 700; }
.d-title { font-size: 17px; font-weight: 700; }
.d-tags { display: flex; gap: 6px; margin: 10px 0; flex-wrap: wrap; }
.mt { margin-top: 10px; }
.sec { font-weight: 700; font-size: 13px; margin: 16px 0 6px; color: #1d2b4f; }
.desc { font-size: 13px; color: #44506a; line-height: 1.7; }
.pre { white-space: pre-wrap; background: #f7f9fc; padding: 10px; border-radius: 8px; }
.refs { margin-top: 8px; }
.ref-tag { margin: 0 6px 6px 0; }
.actions { display: flex; flex-direction: column; gap: 8px; }
.ev-detail { color: #7a869c; font-size: 12px; margin-top: 2px; }
:deep(.el-table__row) { cursor: pointer; }
</style>
