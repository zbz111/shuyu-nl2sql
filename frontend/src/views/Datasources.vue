<template>
  <div>
    <div class="head-row">
      <div>
        <div class="page-title">数据源</div>
        <div class="page-sub">上传 CSV / Excel / SQLite，或连一个只读 MySQL 账号</div>
      </div>
      <div class="actions">
        <el-upload :show-file-list="false" :http-request="upload" accept=".csv,.xlsx,.db,.sqlite,.sqlite3">
          <el-button :icon="UploadFilled" :loading="uploading">上传数据文件</el-button>
        </el-upload>
        <el-button type="primary" :icon="Plus" @click="dialog = true">添加 MySQL</el-button>
      </div>
    </div>

    <div v-if="!datasources.length" class="empty card">
      <el-icon :size="28"><Coin /></el-icon>
      <div class="empty-title">还没有数据源</div>
      <div class="page-sub">上传一个 CSV / Excel 文件，或者填 MySQL 连接信息</div>
    </div>

    <div v-else class="grid ds-grid">
      <div v-for="ds in datasources" :key="ds.id" class="card ds-card">
        <div class="ds-top">
          <div class="ds-icon" :class="ds.kind"><el-icon><Coin /></el-icon></div>
          <el-tag size="small" :type="ds.status === 'ok' ? 'success' : 'danger'" effect="light">
            {{ ds.status === 'ok' ? '连接正常' : '连接异常' }}
          </el-tag>
        </div>
        <div class="ds-name">{{ ds.name }}</div>
        <div class="ds-meta">
          <span class="mono">{{ ds.kind.toUpperCase() }}</span>
          <span v-if="ds.host">· {{ ds.host }}:{{ ds.port }}</span>
          <span>· {{ ds.table_count }} 张表</span>
        </div>
        <div class="ds-actions">
          <el-button size="small" @click="openTables(ds)">表结构</el-button>
          <el-button size="small" @click="$emit('select-ds', ds)">用它分析</el-button>
          <el-button size="small" text @click="test(ds)">测试</el-button>
          <el-button size="small" text type="danger" @click="remove(ds)">删除</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialog" title="添加 MySQL 数据源" width="460px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如：生产库（只读）" />
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="16">
            <el-form-item label="主机">
              <el-input v-model="form.host" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="端口">
              <el-input-number v-model="form.port" :min="1" :max="65535" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="数据库名">
          <el-input v-model="form.database" />
        </el-form-item>
        <el-form-item label="只读账号">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <div class="tip">建议专门创建一个只有 SELECT 权限的账号；系统也会再做一次 SQL 白名单校验。</div>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="create">保存并测试</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="drawer" size="46%" :title="`表结构 · ${current?.name || ''}`">
      <el-collapse v-model="expanded">
        <el-collapse-item v-for="t in tables" :key="t.name" :name="t.name">
          <template #title>
            <span class="tbl-name mono">{{ t.name }}</span>
            <span class="tbl-meta">{{ t.columns.length }} 列 · {{ t.row_count }} 行</span>
          </template>
          <el-table :data="t.columns" size="small" border>
            <el-table-column prop="name" label="字段" />
            <el-table-column prop="type" label="类型" />
            <el-table-column label="主键" width="70">
              <template #default="{ row }">{{ row.pk ? '是' : '' }}</template>
            </el-table-column>
          </el-table>
          <div v-if="t.sample.length" class="sample">
            <div class="sample-title">示例数据</div>
            <pre class="mono">{{ JSON.stringify(t.sample.slice(0, 2), null, 2) }}</pre>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errorMessage } from '../api'

const props = defineProps({
  datasources: { type: Array, default: () => [] },
  currentDs: { type: Number, default: null }
})
const emit = defineEmits(['refresh', 'select-ds'])

const dialog = ref(false)
const drawer = ref(false)
const saving = ref(false)
const uploading = ref(false)
const tables = ref([])
const current = ref(null)
const expanded = ref([])
const form = ref({ name: '', host: '127.0.0.1', port: 3306, database: '', username: '', password: '' })

async function upload({ file }) {
  uploading.value = true
  const fd = new FormData()
  fd.append('file', file)
  try {
    await api.post('/datasources/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success('已上传并解析表结构')
    emit('refresh')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    uploading.value = false
  }
}

async function create() {
  if (!form.value.name || !form.value.database) return ElMessage.warning('请填写名称和数据库名')
  saving.value = true
  try {
    await api.post('/datasources', form.value)
    ElMessage.success('已保存')
    dialog.value = false
    form.value = { name: '', host: '127.0.0.1', port: 3306, database: '', username: '', password: '' }
    emit('refresh')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    saving.value = false
  }
}

async function openTables(ds) {
  current.value = ds
  drawer.value = true
  expanded.value = []
  try {
    const { data } = await api.get(`/datasources/${ds.id}/tables`)
    tables.value = data
    if (data.length) expanded.value = [data[0].name]
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function test(ds) {
  try {
    const { data } = await api.post(`/datasources/${ds.id}/test`)
    data.ok ? ElMessage.success(data.message) : ElMessage.error(data.message)
    emit('refresh')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function remove(ds) {
  try {
    await ElMessageBox.confirm(`删除数据源「${ds.name}」？本地上传的数据库文件也会被删除。`, '确认删除', {
      type: 'warning'
    })
    await api.delete(`/datasources/${ds.id}`)
    ElMessage.success('已删除')
    emit('refresh')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(errorMessage(e))
  }
}
</script>

<style scoped>
.head-row { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.actions { display: flex; gap: 10px; align-items: center; }
.ds-grid { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
.ds-card { padding: 18px; display: flex; flex-direction: column; gap: 8px; }
.ds-top { display: flex; align-items: center; justify-content: space-between; }
.ds-icon {
  width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center;
  background: var(--primary-soft); color: var(--primary);
}
.ds-icon.mysql { background: #fff3e0; color: #f59e0b; }
.ds-name { font-size: 15.5px; font-weight: 650; margin-top: 4px; }
.ds-meta { font-size: 12px; color: var(--muted); display: flex; gap: 6px; flex-wrap: wrap; }
.ds-actions { display: flex; gap: 2px; margin-top: 8px; border-top: 1px solid var(--border); padding-top: 10px; flex-wrap: wrap; }
.empty { padding: 56px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.empty-title { font-size: 16px; font-weight: 600; }
.tip { font-size: 12px; color: var(--muted); line-height: 1.6; }
.tbl-name { font-weight: 600; }
.tbl-meta { margin-left: 10px; font-size: 12px; color: var(--muted); }
.sample { margin-top: 10px; }
.sample-title { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.sample pre { background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px; font-size: 12px; overflow: auto; }
</style>


