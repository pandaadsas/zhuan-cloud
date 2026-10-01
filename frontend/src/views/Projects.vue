<template>
  <div class="page-shell">
    <div class="page-intro">
      <div class="page-title">项目管理</div>
      <div class="page-sub">维护项目基本信息、责任区域与分包单位。切换右上角项目可查看对应数据。</div>
    </div>

    <div class="card" v-loading="loading">
      <div class="card-header">
        <div>
          <div class="card-title">项目列表</div>
          <div class="card-subtitle">点击行选中项目，可在下方维护其区域与分包</div>
        </div>
        <el-button v-if="canManage" type="primary" @click="openProjectDialog()"><el-icon><Plus /></el-icon>新建项目</el-button>
      </div>

      <el-table :data="projects" highlight-current-row @current-change="selectProject" empty-text="暂无项目">
        <el-table-column prop="name" label="项目名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="location" label="所在地" min-width="120" show-overflow-tooltip />
        <el-table-column prop="scale_desc" label="规模" min-width="200" show-overflow-tooltip />
        <el-table-column prop="current_stage" label="当前阶段" min-width="130" show-overflow-tooltip />
        <el-table-column prop="zone_count" label="区域数" width="80" align="center" />
        <el-table-column v-if="canManage" label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openProjectDialog(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <template v-if="selected">
      <div class="card" v-loading="zonesLoading">
        <div class="card-header">
          <div>
            <div class="card-title">责任区域 · {{ selected.name }}</div>
            <div class="card-subtitle">隐患上报时按区域名称匹配责任人</div>
          </div>
          <el-button v-if="canManage" type="primary" plain @click="openZoneDialog()"><el-icon><Plus /></el-icon>新增区域</el-button>
        </div>
        <el-table :data="zones" empty-text="该项目还没有区域">
          <el-table-column prop="name" label="区域名称" min-width="140" />
          <el-table-column prop="zone_type" label="类型" min-width="110" />
          <el-table-column prop="floor_count" label="层数" width="70" align="center" />
          <el-table-column prop="current_stage" label="当前阶段" min-width="130" show-overflow-tooltip />
          <el-table-column prop="subcontractor" label="分包单位" min-width="150" show-overflow-tooltip />
          <el-table-column prop="responsible_name" label="责任人" min-width="100" />
          <el-table-column v-if="canManage" label="操作" width="130" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="openZoneDialog(row)">编辑</el-button>
              <el-button link type="danger" @click="removeZone(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="card" v-loading="subsLoading">
        <div class="card-header">
          <div>
            <div class="card-title">分包单位 · {{ selected.name }}</div>
            <div class="card-subtitle">按承包范围自动匹配隐患整改责任人</div>
          </div>
          <el-button v-if="canManage" type="primary" plain @click="openSubDialog()"><el-icon><Plus /></el-icon>新增分包</el-button>
        </div>
        <el-table :data="subs" empty-text="该项目还没有分包单位">
          <el-table-column prop="name" label="单位名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="scope" label="承包范围" min-width="260" show-overflow-tooltip />
          <el-table-column prop="leader_name" label="负责人" min-width="100" />
          <el-table-column prop="leader_phone" label="联系电话" min-width="130" />
          <el-table-column v-if="canManage" label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="openSubDialog(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
    <div v-else class="empty-hint">在上方选中一个项目后，可在此维护它的责任区域与分包单位。</div>

    <!-- 项目表单 -->
    <el-dialog v-model="projectDialog.visible" :title="projectDialog.editing ? '编辑项目' : '新建项目'" width="520px">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="项目名称" required><el-input v-model="projectForm.name" placeholder="如：三河市保障性租赁住房项目" /></el-form-item>
        <el-form-item label="所在地"><el-input v-model="projectForm.location" /></el-form-item>
        <el-form-item label="总面积"><el-input v-model="projectForm.total_area" placeholder="如：147,536.8㎡" /></el-form-item>
        <el-form-item label="规模描述"><el-input v-model="projectForm.scale_desc" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="当前阶段"><el-input v-model="projectForm.current_stage" placeholder="如：主体结构 + 二次结构" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="projectForm.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projectDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="projectDialog.saving" @click="saveProject">保存</el-button>
      </template>
    </el-dialog>

    <!-- 区域表单 -->
    <el-dialog v-model="zoneDialog.visible" :title="zoneDialog.editing ? '编辑区域' : `新增区域 · ${selected?.name || ''}`" width="520px">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="区域名称" required><el-input v-model="zoneForm.name" placeholder="如：3号楼 / 地下室区域" /></el-form-item>
        <el-form-item label="类型"><el-input v-model="zoneForm.zone_type" placeholder="如：高层住宅 / 公共区域" /></el-form-item>
        <el-form-item label="层数"><el-input-number v-model="zoneForm.floor_count" :min="0" :max="200" /></el-form-item>
        <el-form-item label="当前阶段"><el-input v-model="zoneForm.current_stage" /></el-form-item>
        <el-form-item label="分包单位">
          <el-select v-model="zoneForm.subcontractor_id" clearable style="width: 100%">
            <el-option v-for="s in subs" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="责任人">
          <el-select v-model="zoneForm.responsible_user_id" clearable filterable style="width: 100%">
            <el-option v-for="u in respUsers" :key="u.id" :label="`${u.name}（${u.subcontractor || '未挂分包'}）`" :value="u.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="zoneDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="zoneDialog.saving" @click="saveZone">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分包表单 -->
    <el-dialog v-model="subDialog.visible" :title="subDialog.editing ? '编辑分包' : `新增分包 · ${selected?.name || ''}`" width="520px">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="单位名称" required><el-input v-model="subForm.name" /></el-form-item>
        <el-form-item label="承包范围"><el-input v-model="subForm.scope" type="textarea" :rows="2" placeholder="隐患类型按范围关键词匹配责任人" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="subForm.leader_name" /></el-form-item>
        <el-form-item label="联系电话"><el-input v-model="subForm.leader_phone" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="subDialog.saving" @click="saveSub">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api'
import { userStore, setProjectList, projectStore, setProject } from '../store'

const user = computed(() => userStore.user || {})
const canManage = computed(() => ['project_manager', 'safety_supervisor'].includes(user.value.role))

const loading = ref(true)
const projects = ref([])
const selected = ref(null)
const zones = ref([])
const subs = ref([])
const zonesLoading = ref(false)
const subsLoading = ref(false)
const respUsers = ref([])

const projectDialog = reactive({ visible: false, editing: null, saving: false })
const zoneDialog = reactive({ visible: false, editing: null, saving: false })
const subDialog = reactive({ visible: false, editing: null, saving: false })

const blankProject = { name: '', location: '', total_area: '', scale_desc: '', current_stage: '', note: '' }
const blankZone = { name: '', zone_type: '', floor_count: 0, current_stage: '', subcontractor_id: null, responsible_user_id: null }
const blankSub = { name: '', scope: '', leader_name: '', leader_phone: '' }
const projectForm = reactive({ ...blankProject })
const zoneForm = reactive({ ...blankZone })
const subForm = reactive({ ...blankSub })

onMounted(load)

async function load() {
  loading.value = true
  try {
    const data = await http.get('/api/projects')
    projects.value = data.projects || []
    setProjectList(projects.value)
    // 保持当前项目选中态
    const cur = projects.value.find((p) => p.id === Number(projectStore.id))
    selected.value = cur || projects.value[0] || null
    if (selected.value) await Promise.all([loadZones(), loadSubs(), loadRespUsers()])
  } finally {
    loading.value = false
  }
}

async function selectProject(row) {
  if (!row || row.id === selected.value?.id) return
  selected.value = row
  zones.value = []
  subs.value = []
  await Promise.all([loadZones(), loadSubs()])
}

async function loadZones() {
  if (!selected.value) return
  zonesLoading.value = true
  try {
    const data = await http.get(`/api/projects/${selected.value.id}/zones`)
    zones.value = data.zones || []
  } finally { zonesLoading.value = false }
}

async function loadSubs() {
  if (!selected.value) return
  subsLoading.value = true
  try {
    const data = await http.get(`/api/projects/${selected.value.id}/subcontractors`)
    subs.value = data.subcontractors || []
  } finally { subsLoading.value = false }
}

async function loadRespUsers() {
  try {
    const data = await http.get('/api/meta/options')
    respUsers.value = data.responsible_users || []
  } catch {}
}

/* ---- 项目 ---- */
function openProjectDialog(row) {
  projectDialog.editing = row || null
  Object.assign(projectForm, blankProject, row || {})
  projectDialog.visible = true
}

async function saveProject() {
  if (!projectForm.name.trim()) return ElMessage.warning('请填写项目名称')
  projectDialog.saving = true
  try {
    if (projectDialog.editing) {
      const updated = await http.put(`/api/projects/${projectDialog.editing.id}`, projectForm)
      Object.assign(projectDialog.editing, updated)
      ElMessage.success('项目已更新')
    } else {
      const created = await http.post('/api/projects', projectForm)
      setProject(created.id)
      await load() // load() 会按当前项目选中并加载其区域/分包
      ElMessage.success('项目已创建，已切换到新项目')
      projectDialog.visible = false
      return
    }
    projectDialog.visible = false
  } finally { projectDialog.saving = false }
}

/* ---- 区域 ---- */
function openZoneDialog(row) {
  zoneDialog.editing = row || null
  Object.assign(zoneForm, blankZone, row ? { ...row, subcontractor: undefined, responsible_name: undefined } : {})
  zoneDialog.visible = true
}

async function saveZone() {
  if (!zoneForm.name.trim()) return ElMessage.warning('请填写区域名称')
  zoneDialog.saving = true
  try {
    const payload = { ...zoneForm }
    if (zoneDialog.editing) {
      const updated = await http.put(`/api/projects/zones/${zoneDialog.editing.id}`, payload)
      Object.assign(zoneDialog.editing, updated)
      ElMessage.success('区域已更新')
    } else {
      const created = await http.post(`/api/projects/${selected.value.id}/zones`, payload)
      zones.value.push(created)
      selected.value.zone_count += 1
      ElMessage.success('区域已新增')
    }
    zoneDialog.visible = false
  } finally { zoneDialog.saving = false }
}

async function removeZone(row) {
  try {
    await ElMessageBox.confirm(`确定删除区域「${row.name}」吗？`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch {
    return
  }
  try {
    await http.delete(`/api/projects/zones/${row.id}`)
    zones.value = zones.value.filter((z) => z.id !== row.id)
    selected.value.zone_count -= 1
    ElMessage.success('区域已删除')
  } catch {}
}

/* ---- 分包 ---- */
function openSubDialog(row) {
  subDialog.editing = row || null
  Object.assign(subForm, blankSub, row || {})
  subDialog.visible = true
}

async function saveSub() {
  if (!subForm.name.trim()) return ElMessage.warning('请填写分包单位名称')
  subDialog.saving = true
  try {
    if (subDialog.editing) {
      const updated = await http.put(`/api/projects/subcontractors/${subDialog.editing.id}`, subForm)
      Object.assign(subDialog.editing, updated)
      ElMessage.success('分包已更新')
    } else {
      const created = await http.post(`/api/projects/${selected.value.id}/subcontractors`, subForm)
      subs.value.push(created)
      ElMessage.success('分包已新增')
    }
    subDialog.visible = false
  } finally { subDialog.saving = false }
}
</script>

<style scoped>
.empty-hint { margin-top: 16px; padding: 26px; border: 1px dashed var(--zhuan-line); border-radius: var(--zhuan-radius); color: var(--zhuan-muted); font-size: 13px; text-align: center; }
.card + .card, .card + .empty-hint { margin-top: 16px; }
</style>
