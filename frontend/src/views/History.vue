<template>
  <div>
    <div class="head-row">
      <div>
        <div class="page-title">查询历史</div>
        <div class="page-sub">每一次提问、生成的 SQL、耗时都记录在案</div>
      </div>
      <el-switch v-model="onlyFavorite" active-text="只看收藏" @change="load" />
    </div>

    <div class="card panel">
      <el-table :data="rows" size="default" @row-click="copySql">
        <el-table-column prop="question" label="问题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="sql" label="SQL" min-width="260" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'ok' ? 'success' : row.status === 'blocked' ? 'warning' : 'danger'" effect="light">
              {{ row.status === 'ok' ? '成功' : row.status === 'blocked' ? '拦截' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="row_count" label="行数" width="80" />
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ row.latency_ms }}ms</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN', { hour12: false }) }}</template>
        </el-table-column>
        <el-table-column label="收藏" width="80" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click.stop="toggle(row)">
              <el-icon :color="row.favorite ? '#f59e0b' : ''"><StarFilled v-if="row.favorite" /><Star v-else /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api, { errorMessage } from '../api'

defineProps({ datasources: { type: Array, default: () => [] }, currentDs: { type: Number, default: null } })

const rows = ref([])
const onlyFavorite = ref(false)

async function load() {
  try {
    const params = { favorite: onlyFavorite.value, limit: 100 }
    const { data } = await api.get('/queries', { params })
    rows.value = data
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function toggle(row) {
  try {
    const { data } = await api.post(`/queries/${row.id}/favorite`)
    row.favorite = data.favorite
    if (onlyFavorite.value && !data.favorite) rows.value = rows.value.filter((r) => r.id !== row.id)
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function copySql(row) {
  if (!row.sql) return
  try {
    await navigator.clipboard.writeText(row.sql)
    ElMessage.success('SQL 已复制')
  } catch {
    /* ignore */
  }
}

onMounted(load)
</script>

<style scoped>
.head-row { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.panel { padding: 10px 12px; }
</style>
