<!-- 变更记录: 20261126-0922 新增：首页。显示当前用户（工号、邮箱）与退出按钮；未登录时显示登录入口 -->
<script setup lang="ts">
import { ref } from 'vue'
import { auth, loginRedirect, logout } from '../auth'

const errorMessage = ref('')

async function onLogout() {
  errorMessage.value = ''
  try {
    await logout()
  } catch {
    errorMessage.value = '退出失败，请稍后重试。'
  }
}
</script>

<template>
  <main class="page">
    <template v-if="auth.user">
      <h1>{{ auth.user.first_name || auth.user.username }}，您好</h1>
      <dl class="profile">
        <dt>工号</dt>
        <dd>{{ auth.user.employee_number ?? '—' }}</dd>
        <dt>邮箱</dt>
        <dd>{{ auth.user.email || '—' }}</dd>
      </dl>
      <button type="button" @click="onLogout">退出登录</button>
      <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
    </template>
    <template v-else>
      <h1>未登录</h1>
      <p v-if="auth.ssoEnabled">请使用 Okta 账号登录。</p>
      <p v-else>单点登录未启用，请联系系统管理员检查配置。</p>
      <button v-if="auth.ssoEnabled" type="button" @click="loginRedirect('/')">登录</button>
    </template>
  </main>
</template>
