<template>
  <section v-if="artifact" class="artifact" :class="`artifact-${artifact.type}`">
    <template v-if="artifact.type === 'work_order_list'">
      <div class="artifact-head">
        <div><span class="artifact-kicker">整改工单</span><strong>{{ artifact.title }}</strong></div>
        <el-button link type="primary" @click="$emit('navigate', '/orders')">查看全部</el-button>
      </div>
      <div v-if="orders.length" class="order-list">
        <button v-for="order in orders" :key="order.id || order.order_no" class="order-row" @click="$emit('navigate', '/orders')">
          <span class="risk-dot" :class="`risk-${order.risk_level}`"></span>
          <span class="order-main">
            <b>{{ order.order_no }}</b><span>{{ order.title }}</span>
            <small>{{ order.location || '位置未识别' }} · {{ order.responsible_name || '未指定责任人' }}</small>
          </span>
          <span class="order-side">
            <el-tag size="small" :type="statusType(order.status)">{{ order.status_label || order.status }}</el-tag>
            <small :class="{ overdue: order.overdue }">{{ order.overdue ? '已超期' : (order.deadline || '未设期限') }}</small>
          </span>
        </button>
      </div>
      <el-empty v-else :image-size="52" description="没有找到匹配工单" />
    </template>

    <template v-else-if="artifact.type === 'stats_summary'">
      <div class="artifact-head">
        <div><span class="artifact-kicker">项目概况</span><strong>{{ artifact.title }}</strong></div>
        <el-button link type="primary" @click="$emit('navigate', '/dashboard')">打开看板</el-button>
      </div>
      <div class="stats-grid">
        <div><b>{{ data.total ?? 0 }}</b><span>累计工单</span></div>
        <div><b>{{ data.open_total ?? 0 }}</b><span>在办工单</span></div>
        <div><b>{{ data.rect_rate || '0%' }}</b><span>整改率</span></div>
        <div><b :class="{ danger: overdueCount }">{{ overdueCount }}</b><span>超期未闭环</span></div>
      </div>
    </template>

    <template v-else-if="artifact.type === 'clause_refs'">
      <button class="refs-toggle" :aria-expanded="expanded" @click="expanded = !expanded">
        <span><el-icon><DocumentChecked /></el-icon><b>{{ refs.length }} 条规范依据</b><small>{{ refs[0]?.doc_name || '未检索到条款' }}</small></span>
        <el-icon class="chevron" :class="{ expanded }"><ArrowDown /></el-icon>
      </button>
      <div v-if="expanded" class="ref-list">
        <div v-for="ref in refs" :key="`${ref.doc_name}-${ref.clause_no}`">
          <b>《{{ ref.doc_name }}》{{ ref.clause_no }}</b><span>{{ ref.title }}</span>
        </div>
      </div>
    </template>

    <template v-else-if="artifact.type === 'weekly_report'">
      <div class="artifact-head compact">
        <span class="artifact-icon orange"><el-icon><Document /></el-icon></span>
        <div><span class="artifact-kicker">安全周报</span><strong>周报内容已准备好</strong></div>
        <el-button type="primary" plain size="small" @click="$emit('navigate', '/weekly')">前往周报</el-button>
      </div>
    </template>

    <template v-else-if="artifact.type === 'hazard_submitted'">
      <div class="artifact-head">
        <div><span class="artifact-kicker success">提交成功</span><strong>{{ data.order_no }} · {{ data.title }}</strong></div>
        <el-button link type="primary" @click="$emit('navigate', '/orders')">查看工单</el-button>
      </div>
      <div class="summary-line"><span>{{ data.risk_level }}风险</span><span>{{ data.status }}</span><span>{{ data.responsible }}</span></div>
    </template>

    <template v-else-if="artifact.type === 'change_preview'">
      <div class="artifact-head">
        <div><span class="artifact-kicker" :class="{ danger: data.destructive }">待确认变更</span><strong>{{ artifact.title }}</strong></div>
        <el-tag v-if="data.status !== 'pending'" :type="actionStatusType">{{ actionStatusLabel }}</el-tag>
      </div>
      <dl class="change-fields">
        <div v-for="field in data.fields || []" :key="field.label"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div>
      </dl>
      <div v-if="data.result" class="action-result" :class="data.status">{{ resultText }}</div>
      <div v-if="data.status === 'pending'" class="confirm-bar">
        <span>核对无误后再执行，确认令牌十分钟内有效。</span>
        <div>
          <el-button size="small" :disabled="busy" @click="$emit('resolve', artifact, false)">取消</el-button>
          <el-button size="small" :type="data.destructive ? 'danger' : 'primary'" :loading="busy" @click="$emit('resolve', artifact, true)">确认执行</el-button>
        </div>
      </div>
    </template>

    <template v-else-if="artifact.type === 'directory_result'">
      <div class="artifact-head compact directory-head">
        <span class="artifact-icon"><el-icon><FolderOpened /></el-icon></span>
        <div><span class="artifact-kicker">查询完成</span><strong>{{ artifact.title }}</strong></div>
        <el-button link type="primary" @click="$emit('navigate', '/projects')">项目管理</el-button>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ArrowDown, Document, DocumentChecked, FolderOpened } from '@element-plus/icons-vue'

const props = defineProps({ artifact: { type: Object, required: true }, busy: Boolean })
defineEmits(['navigate', 'resolve'])

const expanded = ref(false)
const data = computed(() => props.artifact.data || {})
const orders = computed(() => data.value.orders || [])
const refs = computed(() => data.value.refs || [])
const overdueCount = computed(() => Array.isArray(data.value.overdue) ? data.value.overdue.length : (data.value.overdue || 0))
const actionStatusLabel = computed(() => ({ completed: '已执行', cancelled: '已取消', failed: '执行失败', expired: '已过期' }[data.value.status] || data.value.status))
const actionStatusType = computed(() => ({ completed: 'success', cancelled: 'info', failed: 'danger', expired: 'warning' }[data.value.status] || 'info'))
const resultText = computed(() => data.value.result?.error || data.value.result?.message || (data.value.status === 'completed' ? '变更已执行完成。' : ''))

function statusType(status) {
  return { pending_review: 'warning', dispatched: 'primary', rectifying: '', recheck: 'warning', closed: 'success', rejected: 'info' }[status] || 'info'
}
</script>

<style scoped>
.artifact { margin-top: 10px; overflow: hidden; border: 1px solid #dfe7f3; border-radius: 14px; background: #fff; }
.artifact-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 14px 10px; }
.artifact-head > div { min-width: 0; }
.artifact-head strong, .artifact-kicker { display: block; }
.artifact-head strong { overflow: hidden; color: #17233b; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.artifact-kicker { margin-bottom: 3px; color: #71809a; font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.artifact-kicker.success { color: #21865b; }
.artifact-kicker.danger { color: #d84d4d; }
.artifact-head.compact { justify-content: flex-start; padding: 13px 14px; }
.artifact-head.compact .el-button { margin-left: auto; }
.artifact-icon { display: grid; flex: 0 0 auto; place-items: center; width: 34px; height: 34px; border-radius: 10px; color: #2459d3; background: #edf3ff; }
.artifact-icon.orange { color: #b66c00; background: #fff4df; }
.order-list { border-top: 1px solid #edf1f7; }
.order-row { display: flex; align-items: center; width: 100%; gap: 10px; padding: 11px 14px; border: 0; border-bottom: 1px solid #edf1f7; color: inherit; background: transparent; text-align: left; cursor: pointer; }
.order-row:last-child { border-bottom: 0; }
.order-row:hover { background: #f7f9fd; }
.risk-dot { width: 7px; height: 30px; border-radius: 8px; background: #71a27e; }
.risk-dot.risk-中 { background: #d99a2b; }.risk-dot.risk-高 { background: #e45b52; }.risk-dot.risk-重大 { background: #a92536; }
.order-main { display: grid; flex: 1; min-width: 0; gap: 2px; }
.order-main b { color: #233250; font-size: 11px; }
.order-main span { overflow: hidden; font-size: 13px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.order-main small, .order-side small { color: #7a879d; font-size: 10px; }
.order-side { display: grid; justify-items: end; gap: 5px; }
.order-side small.overdue, .danger { color: #d84d4d; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid #edf1f7; }
.stats-grid div { display: grid; gap: 3px; padding: 13px; border-right: 1px solid #edf1f7; }
.stats-grid div:last-child { border-right: 0; }
.stats-grid b { color: #2459d3; font-size: 20px; }.stats-grid span { color: #77839a; font-size: 10px; }
.refs-toggle { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 12px 14px; border: 0; color: inherit; background: #f7f9fd; cursor: pointer; }
.refs-toggle > span { display: grid; grid-template-columns: auto auto 1fr; align-items: center; gap: 7px; min-width: 0; }
.refs-toggle b { font-size: 12px; }.refs-toggle small { overflow: hidden; color: #7a879d; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.chevron { transition: transform .18s; }.chevron.expanded { transform: rotate(180deg); }
.ref-list { display: grid; gap: 8px; padding: 10px 14px 13px; }
.ref-list div { display: grid; gap: 2px; }.ref-list b { color: #2459d3; font-size: 11px; }.ref-list span { color: #5d6b82; font-size: 11px; }
.summary-line { display: flex; gap: 12px; padding: 0 14px 13px; color: #647189; font-size: 11px; }
.change-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; margin: 0 14px 12px; overflow: hidden; border: 1px solid #e7ecf4; border-radius: 9px; background: #e7ecf4; }
.change-fields div { display: grid; grid-template-columns: 86px 1fr; gap: 8px; padding: 8px 10px; background: #fafbfe; }
.change-fields dt { color: #7a879d; font-size: 10px; }.change-fields dd { margin: 0; overflow-wrap: anywhere; font-size: 11px; }
.confirm-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; border-top: 1px solid #edf1f7; background: #fafbfe; }
.confirm-bar > span { color: #7a879d; font-size: 10px; }.confirm-bar > div { display: flex; gap: 6px; }
.action-result { margin: 0 14px 12px; padding: 8px 10px; border-radius: 8px; color: #536078; background: #f3f6fa; font-size: 11px; }
.action-result.completed { color: #237653; background: #edf8f2; }.action-result.failed { color: #b33838; background: #fff1f1; }
@media (max-width: 600px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }.stats-grid div:nth-child(2) { border-right: 0; }.stats-grid div:nth-child(-n+2) { border-bottom: 1px solid #edf1f7; }
  .change-fields { grid-template-columns: 1fr; }.confirm-bar { align-items: flex-start; flex-direction: column; }.confirm-bar > div { align-self: flex-end; }
}
</style>
