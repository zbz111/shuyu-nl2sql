<template>
  <div>
    <div class="grid stats">
      <div class="card stat-card">
        <div class="label">今日查询</div>
        <div class="value">{{ stats.queries_today }}</div>
        <div class="hint">累计 {{ stats.queries }} 次</div>
      </div>
      <div class="card stat-card">
        <div class="label">平均延迟</div>
        <div class="value">{{ (stats.avg_latency_ms / 1000).toFixed(1) }}s</div>
        <div class="hint">含模型生成时间</div>
      </div>
      <div class="card stat-card">
        <div class="label">失败/拦截率</div>
        <div class="value">{{ (stats.error_rate * 100).toFixed(1) }}%</div>
        <div class="hint">越低越好</div>
      </div>
      <div class="card stat-card">
        <div class="label">用户 / 数据源</div>
        <div class="value">{{ stats.users }} / {{ stats.datasources }}</div>
        <div class="hint">账号与接入</div>
      </div>
    </div>

    <div class="card panel">
      <el-tabs v-model="tab">
        <el-tab-pane label="用户" name="users">
          <el-table :data="users" size="default">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="username" label="用户名" min-width="140" />
            <el-table-column prop="display_name" label="姓名" min-width="140" />
            <el-table-column label="角色" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.role === 'admin' ? 'warning' : 'info'" effect="plain">
                  {{ row.role === 'admin' ? '管理员' : '成员' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_active ? 'success' : 'danger'" effect="light">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button text size="small" @click="toggle(row)">{{ row.is_active ? '禁用' : '启用' }}</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="审计日志" name="logs">
          <el-table :data="logs" size="small" max-height="520">
            <el-table-column prop="id" label="#" width="70" />
            <el-table-column prop="action" label="动作" width="160" />
            <el-table-column prop="target" label="对象" width="180" show-overflow-tooltip />
            <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip />
            <el-table-column prop="ip" label="IP" width="130" />
            <el-table-column label="时间" width="170">
              <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN', { hour12: false }) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="系统" name="system">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="模型">{{ system.llm?.model }}</el-descriptions-item>
            <el-descriptions-item label="模型状态">
              <el-tag :type="system.llm?.ok ? 'success' : 'danger'" size="small">{{ system.llm?.ok ? '正常' : '不可用' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="行数上限">{{ system.max_rows }}</el-descriptions-item>
            <el-descriptions-item label="查询超时">{{ system.timeout }}s</el-descriptions-item>
            <el-descriptions-item label="重试次数">{{ system.max_retry }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ system.version }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api, { errorMessage } from '../api'

defineProps({ datasources: { type: Array, default: () => [] }, currentDs: { type: Number, default: null } })

const tab = ref('users')
const stats = ref({ users: 0, datasources: 0, queries: 0, queries_today: 0, error_rate: 0, avg_latency_ms: 0 })
const users = ref([])
const logs = ref([])
const system = ref({})

async function load() {
  try {
    const [s, u, l, sys] = await Promise.all([
      api.get('/admin/stats'),
      api.get('/admin/users'),
      api.get('/admin/logs', { params: { limit: 100 } }),
      api.get('/admin/system')
    ])
    stats.value = s.data
    users.value = u.data
    logs.value = l.data
    system.value = sys.data
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function toggle(row) {
  try {
    await api.patch(`/admin/users/${row.id}?is_active=${!row.is_active}`)
    row.is_active = !row.is_active
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

onMounted(load)
</script>

<style scoped>
.stats { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-bottom: 18px; }
.panel { padding: 8px 18px 18px; }
</style>
