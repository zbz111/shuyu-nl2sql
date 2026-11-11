<template>
  <div class="login-wrap">
    <div class="glow glow-a"></div>
    <div class="glow glow-b"></div>

    <div class="login-card card">
      <div class="head">
        <div class="logo">数</div>
        <div>
          <div class="name">数语</div>
          <div class="sub">自然语言数据分析 · 私有化部署</div>
        </div>
      </div>

      <el-form :model="form" @submit.prevent="submit" class="form">
        <el-form-item>
          <el-input v-model="form.username" size="large" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            size="large"
            type="password"
            show-password
            placeholder="密码"
            :prefix-icon="Lock"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit" :loading="loading" @click="submit">登录</el-button>
        <div v-if="error" class="error">{{ error }}</div>
      </el-form>

      <div class="foot">只读连接 · SQL 白名单 · 全链路审计</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import api, { errorMessage } from '../api'

const router = useRouter()
const form = ref({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

async function submit() {
  if (!form.value.username || !form.value.password) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/auth/login', form.value)
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    router.push('/query')
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100vh; display: grid; place-items: center; position: relative; overflow: hidden;
  background: radial-gradient(1200px 600px at 20% 0%, #e6f4ff 0%, var(--bg) 55%);
}
html.dark .login-wrap { background: radial-gradient(1200px 600px at 20% 0%, #10243a 0%, #0e1016 55%); }
.glow { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.45; }
.glow-a { width: 420px; height: 420px; background: #38bdf8; top: -120px; right: -80px; }
.glow-b { width: 360px; height: 360px; background: #6366f1; bottom: -140px; left: -100px; opacity: 0.3; }
.login-card { width: 380px; padding: 32px 30px 26px; position: relative; z-index: 1; }
.head { display: flex; align-items: center; gap: 12px; margin-bottom: 26px; }
.logo {
  width: 42px; height: 42px; border-radius: 12px;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: #fff; display: grid; place-items: center; font-size: 20px; font-weight: 700;
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.35);
}
.name { font-size: 18px; font-weight: 700; letter-spacing: 0.5px; }
.sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
.form :deep(.el-input__wrapper) { border-radius: 10px; }
.submit { width: 100%; margin-top: 6px; border-radius: 10px; height: 42px; font-weight: 600; }
.error { color: var(--danger); font-size: 12.5px; margin-top: 10px; text-align: center; }
.foot { margin-top: 22px; text-align: center; font-size: 11.5px; color: var(--muted); }
</style>
