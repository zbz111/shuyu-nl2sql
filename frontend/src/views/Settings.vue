<template>
  <div class="settings">
    <div class="card section">
      <div class="section-title">账号</div>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="用户名">{{ user.username }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ user.display_name }}</el-descriptions-item>
        <el-descriptions-item label="角色">{{ user.role === 'admin' ? '管理员' : '成员' }}</el-descriptions-item>
        <el-descriptions-item label="状态">启用</el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="card section">
      <div class="section-title">修改密码</div>
      <el-form label-position="top" style="max-width: 380px">
        <el-form-item label="原密码">
          <el-input v-model="pwd.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码（至少 6 位）">
          <el-input v-model="pwd.new_password" type="password" show-password />
        </el-form-item>
        <el-button type="primary" :loading="saving" @click="changePassword">保存</el-button>
      </el-form>
    </div>

    <div class="card section">
      <div class="section-title">外观</div>
      <el-switch v-model="dark" active-text="深色模式" @change="applyTheme" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api, { errorMessage } from '../api'

const user = JSON.parse(localStorage.getItem('user') || '{}')
const pwd = ref({ old_password: '', new_password: '' })
const saving = ref(false)
const dark = ref(document.documentElement.classList.contains('dark'))

async function changePassword() {
  if (!pwd.value.old_password || pwd.value.new_password.length < 6) {
    return ElMessage.warning('请填写原密码，新密码至少 6 位')
  }
  saving.value = true
  try {
    await api.post('/auth/change-password', pwd.value)
    ElMessage.success('密码已修改')
    pwd.value = { old_password: '', new_password: '' }
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    saving.value = false
  }
}

function applyTheme(val) {
  document.documentElement.classList.toggle('dark', val)
  localStorage.setItem('theme', val ? 'dark' : 'light')
}
</script>

<style scoped>
.settings { display: grid; gap: 16px; max-width: 860px; }
.section { padding: 18px 20px; }
.section-title { font-weight: 650; font-size: 14.5px; margin-bottom: 14px; }
</style>
