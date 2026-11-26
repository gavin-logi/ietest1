// 变更记录: 20261126-0922 新增：登录态。启动时读取 /api/auth/me/；登录与登出都走后端 SSO 端点，前端不接触任何 token
import { reactive } from 'vue'
import { apiFetch } from './api'

export interface CurrentUser {
  id: number
  username: string
  employee_number: string | null
  email: string
  first_name: string
  last_name: string
  is_staff: boolean
}

interface MeResponse {
  authenticated: boolean
  sso_enabled: boolean
  login_url: string
  user?: CurrentUser
}

export const auth = reactive({
  loaded: false,
  user: null as CurrentUser | null,
  ssoEnabled: false,
  loginUrl: '/api/auth/login/',
})

export async function loadMe(): Promise<void> {
  try {
    const me = await apiFetch<MeResponse>('/api/auth/me/')
    auth.user = me.authenticated && me.user ? me.user : null
    auth.ssoEnabled = me.sso_enabled
    auth.loginUrl = me.login_url
  } catch {
    // 网络或后端异常时视为未登录；页面会显示对应提示，不阻断渲染
    auth.user = null
  } finally {
    auth.loaded = true
  }
}

export function loginRedirect(next: string): void {
  window.location.href = `${auth.loginUrl}?next=${encodeURIComponent(next)}`
}

export async function logout(): Promise<void> {
  const result = await apiFetch<{ redirect_url: string }>('/api/auth/logout/', {
    method: 'POST',
  })
  auth.user = null
  // 后端返回的地址可能是 IdP 登出页（已结束 Okta 会话），因此必须整页跳转
  window.location.href = result.redirect_url
}
