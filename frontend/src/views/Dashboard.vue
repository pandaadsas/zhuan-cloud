<template>
  <div>
    <div class="page-title">安全看板</div>
    <div class="page-sub">{{ meta.project?.name }} ｜ {{ meta.project?.scale_desc }}</div>

    <div class="stat-grid">
      <div class="stat-card"><div class="stat-num">{{ s.total }}</div><div class="stat-label">累计隐患工单</div></div>
      <div class="stat-card"><div class="stat-num">{{ s.open_total }}</div><div class="stat-label">在办工单</div></div>
      <div class="stat-card"><div class="stat-num" style="color:#f56c6c">{{ (s.overdue || []).length }}</div><div class="stat-label">超期未闭环</div></div>
      <div class="stat-card"><div class="stat-num" style="color:#67c23a">{{ s.rect_rate }}</div><div class="stat-label">累计整改率</div></div>
    </div>

    <div class="chart-grid">
      <div class="card">
        <div class="chart-title">近8周隐患上报与闭环趋势</div>
        <div ref="trendEl" class="chart"></div>
      </div>
      <div class="card">
        <div class="chart-title">在办工单风险分布</div>
        <div ref="riskEl" class="chart"></div>
      </div>
      <div class="card">
        <div class="chart-title">隐患类型Top6</div>
        <div ref="typeEl" class="chart"></div>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="chart-title">⚠️ 超期未闭环工单（重点督办）</div>
      <el-table :data="s.overdue || []" size="small" stripe>
        <el-table-column prop="order_no" label="工单号" width="150" />
        <el-table-column prop="title" label="标题" min-width="220" />
        <el-table-column prop="risk_level" label="风险" width="90">
          <template #default="{ row }"><span class="risk-tag" :class="'risk-' + row.risk_level">{{ row.risk_level }}</span></template>
        </el-table-column>
        <el-table-column prop="responsible" label="责任人" width="110" />
        <el-table-column prop="deadline" label="原期限" width="110" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, nextTick } from 'vue'
import * as echarts from 'echarts'
import http from '../api'

const s = ref({})
const meta = ref({})
const trendEl = ref()
const riskEl = ref()
const typeEl = ref()

onMounted(async () => {
  const [ov, info] = await Promise.all([http.get('/api/stats/overview'), http.get('/api/meta/info')])
  s.value = ov
  meta.value = info
  await nextTick()
  drawTrend()
  drawRisk()
  drawType()
})

function drawTrend() {
  const chart = echarts.init(trendEl.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['新增隐患', '闭环数'], top: 0 },
    grid: { left: 40, right: 16, top: 30, bottom: 24 },
    xAxis: { type: 'category', data: s.value.trend.map((t) => t.label) },
    yAxis: { type: 'value' },
    series: [
      { name: '新增隐患', type: 'line', smooth: true, data: s.value.trend.map((t) => t.new), itemStyle: { color: '#1d5bd8' }, areaStyle: { opacity: 0.12 } },
      { name: '闭环数', type: 'line', smooth: true, data: s.value.trend.map((t) => t.closed), itemStyle: { color: '#67c23a' } },
    ],
  })
}

function drawRisk() {
  const order = ['重大', '高', '中', '低']
  const colors = { 重大: '#b71c1c', 高: '#f56c6c', 中: '#e6a23c', 低: '#67c23a' }
  const data = order.filter((k) => s.value.open_risk_counts?.[k]).map((k) => ({ name: k, value: s.value.open_risk_counts[k], itemStyle: { color: colors[k] } }))
  echarts.init(riskEl.value).setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{ type: 'pie', radius: ['42%', '68%'], center: ['50%', '44%'], data, label: { formatter: '{b} {c}份' } }],
  })
}

function drawType() {
  const entries = Object.entries(s.value.type_top || {})
  echarts.init(typeEl.value).setOption({
    tooltip: {},
    grid: { left: 130, right: 20, top: 10, bottom: 24 },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: entries.map((e) => e[0]).reverse(), axisLabel: { width: 118, overflow: 'truncate' } },
    series: [{ type: 'bar', data: entries.map((e) => e[1]).reverse(), itemStyle: { color: '#3f8bfd', borderRadius: [0, 4, 4, 0] }, barWidth: 14 }],
  })
}
</script>

<style scoped>
.chart-grid { display: grid; grid-template-columns: 2fr 1fr 1.4fr; gap: 12px; }
.chart { height: 260px; }
.chart-title { font-weight: 700; font-size: 14px; margin-bottom: 6px; color: #1d2b4f; }
.risk-tag { font-weight: 700; }
@media (max-width: 1100px) { .chart-grid { grid-template-columns: 1fr; } .stat-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
