<template>
  <div class="page-shell">
    <div class="page-intro">
      <div class="page-title">项目安全态势</div>
      <div class="page-sub">{{ meta.project?.name || '当前项目' }}<template v-if="meta.project?.scale_desc"> · {{ meta.project.scale_desc }}</template></div>
    </div>

    <template v-if="loading">
      <div class="stat-grid"><el-skeleton v-for="i in 4" :key="i" animated><template #template><el-skeleton-item class="stat-skeleton" variant="rect" /></template></el-skeleton></div>
      <div class="chart-grid"><div v-for="i in 3" :key="i" class="card"><el-skeleton :rows="6" animated /></div></div>
    </template>

    <div v-else-if="error" class="card error-state">
      <div><el-icon><WarningFilled /></el-icon><div class="error-title">看板数据暂时无法加载</div><div class="error-copy">请检查服务状态后重试。</div><el-button type="primary" @click="load">重新加载</el-button></div>
    </div>

    <template v-else>
      <div class="stat-grid">
        <div v-for="item in stats" :key="item.label" class="stat-card" :class="item.tone">
          <div class="stat-top"><span class="stat-kicker">{{ item.kicker }}</span><el-icon><component :is="item.icon" /></el-icon></div>
          <div class="stat-num">{{ item.value }}</div>
          <div class="stat-label">{{ item.label }}</div>
        </div>
      </div>

      <div class="chart-grid">
        <section class="card trend-card">
          <div class="card-header"><div><div class="card-title">隐患治理趋势</div><div class="card-subtitle">近 8 周上报与闭环数量</div></div></div>
          <div v-if="s.trend?.length" ref="trendEl" class="chart"></div>
          <el-empty v-else :image-size="72" description="暂无趋势数据" />
        </section>
        <section class="card">
          <div class="card-header"><div><div class="card-title">在办风险分布</div><div class="card-subtitle">按风险等级统计</div></div></div>
          <div v-if="riskTotal" ref="riskEl" class="chart"></div>
          <el-empty v-else :image-size="72" description="暂无在办工单" />
        </section>
        <section class="card">
          <div class="card-header"><div><div class="card-title">高频隐患类型</div><div class="card-subtitle">累计数量 Top 6</div></div></div>
          <div v-if="Object.keys(s.type_top || {}).length" ref="typeEl" class="chart"></div>
          <el-empty v-else :image-size="72" description="暂无分类数据" />
        </section>
      </div>

      <section class="card overdue-card">
        <div class="card-header">
          <div><div class="card-title">超期重点督办</div><div class="card-subtitle">优先跟进未在期限内闭环的工单</div></div>
          <el-tag v-if="s.overdue?.length" type="danger" effect="light">{{ s.overdue.length }} 单待处理</el-tag>
        </div>
        <div class="table-wrap">
          <el-table v-if="s.overdue?.length" :data="s.overdue" size="small">
            <el-table-column prop="order_no" label="工单号" width="150" />
            <el-table-column prop="title" label="隐患标题" min-width="240" show-overflow-tooltip />
            <el-table-column prop="risk_level" label="风险" width="80"><template #default="{ row }"><span class="risk-tag" :class="'risk-' + row.risk_level">{{ row.risk_level }}</span></template></el-table-column>
            <el-table-column prop="responsible" label="责任人" width="110" />
            <el-table-column prop="deadline" label="整改期限" width="120" />
          </el-table>
          <el-empty v-else :image-size="72" description="目前没有超期工单" />
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { CircleCheck, Clock, DataLine, Warning } from '@element-plus/icons-vue'
import http from '../api'

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
const s = ref({})
const meta = ref({})
const loading = ref(true)
const error = ref(false)
const trendEl = ref()
const riskEl = ref()
const typeEl = ref()
const charts = []
let resizeObserver

const riskTotal = computed(() => Object.values(s.value.open_risk_counts || {}).reduce((sum, n) => sum + n, 0))
const stats = computed(() => [
  { label: '累计隐患工单', kicker: 'TOTAL', value: s.value.total ?? 0, icon: DataLine, tone: 'blue' },
  { label: '当前在办工单', kicker: 'IN PROGRESS', value: s.value.open_total ?? 0, icon: Clock, tone: 'orange' },
  { label: '超期未闭环', kicker: 'OVERDUE', value: (s.value.overdue || []).length, icon: Warning, tone: 'red' },
  { label: '累计整改率', kicker: 'CLOSED RATE', value: s.value.rect_rate ?? '0%', icon: CircleCheck, tone: 'green' },
])

async function load() {
  loading.value = true
  error.value = false
  disposeCharts()
  try {
    const [overview, info] = await Promise.all([http.get('/api/stats/overview'), http.get('/api/meta/info')])
    s.value = overview
    meta.value = info
    loading.value = false
    await nextTick()
    drawCharts()
  } catch {
    error.value = true
    loading.value = false
  }
}

function init(el, option) {
  if (!el) return
  const chart = echarts.init(el)
  chart.setOption(option)
  charts.push(chart)
}
function drawCharts() {
  const axisColor = '#718096'
  if (s.value.trend?.length) init(trendEl.value, {
    tooltip: { trigger: 'axis' }, legend: { data: ['新增隐患', '闭环数'], top: 0, textStyle: { color: axisColor } },
    grid: { left: 42, right: 16, top: 34, bottom: 24 },
    xAxis: { type: 'category', data: s.value.trend.map((t) => t.label), axisLine: { lineStyle: { color: '#dfe6f0' } }, axisLabel: { color: axisColor } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf1f6' } }, axisLabel: { color: axisColor } },
    series: [
      { name: '新增隐患', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, data: s.value.trend.map((t) => t.new), itemStyle: { color: '#2459d3' }, areaStyle: { color: 'rgba(36,89,211,.1)' }, lineStyle: { width: 3 } },
      { name: '闭环数', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, data: s.value.trend.map((t) => t.closed), itemStyle: { color: '#35a873' }, lineStyle: { width: 3 } },
    ],
  })
  const order = ['重大', '高', '中', '低']
  const colors = { 重大: '#a51d2d', 高: '#dc554c', 中: '#f59e0b', 低: '#35a873' }
  const riskData = order.filter((k) => s.value.open_risk_counts?.[k]).map((k) => ({ name: k, value: s.value.open_risk_counts[k], itemStyle: { color: colors[k] } }))
  if (riskData.length) init(riskEl.value, {
    tooltip: { trigger: 'item' }, legend: { bottom: 0, icon: 'circle', textStyle: { color: axisColor } },
    series: [{ type: 'pie', radius: ['50%', '72%'], center: ['50%', '44%'], data: riskData, label: { formatter: '{b} {c}', color: axisColor }, itemStyle: { borderColor: '#fff', borderWidth: 3 } }],
  })
  const entries = Object.entries(s.value.type_top || {})
  if (entries.length) init(typeEl.value, {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 116, right: 18, top: 8, bottom: 24 },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf1f6' } }, axisLabel: { color: axisColor } },
    yAxis: { type: 'category', data: entries.map((e) => e[0]).reverse(), axisLabel: { width: 104, overflow: 'truncate', color: axisColor }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', data: entries.map((e) => e[1]).reverse(), itemStyle: { color: '#4b76da', borderRadius: [0, 5, 5, 0] }, barWidth: 13 }],
  })
  resizeObserver = new ResizeObserver(() => charts.forEach((chart) => chart.resize()))
  ;[trendEl.value, riskEl.value, typeEl.value].filter(Boolean).forEach((el) => resizeObserver.observe(el))
}
function disposeCharts() {
  resizeObserver?.disconnect()
  resizeObserver = undefined
  while (charts.length) charts.pop().dispose()
}
onMounted(load)
onBeforeUnmount(disposeCharts)
</script>

<style scoped>
.stat-skeleton { width: 100%; height: 126px; border-radius: 14px; }
.stat-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 13px; color: inherit; }
.stat-top .el-icon { font-size: 20px; opacity: .72; }
.stat-kicker { font-size: 10px; font-weight: 750; letter-spacing: .08em; opacity: .65; }
.stat-card.blue { color: var(--zhuan-blue); } .stat-card.orange { color: #bf7108; } .stat-card.red { color: #d04d46; } .stat-card.green { color: #2d9463; }
.stat-card .stat-num { color: inherit; }
.chart-grid { display: grid; grid-template-columns: 1.65fr 1fr 1.25fr; gap: 14px; }
.chart { height: 260px; }
.overdue-card { margin-top: 16px; }
.risk-tag { font-weight: 700; }
.table-wrap { overflow-x: auto; }
@media (max-width: 1200px) { .chart-grid { grid-template-columns: 1fr 1fr; } .trend-card { grid-column: 1 / -1; } }
@media (max-width: 760px) { .chart-grid { grid-template-columns: 1fr; } .trend-card { grid-column: auto; } .chart { height: 240px; } }
</style>
