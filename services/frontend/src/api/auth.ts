import axios from 'axios'
import { AuthUser, useAuthStore } from '../store/authStore'

interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: AuthUser
}

export const authApi = {
  login: async (email: string, password: string): Promise<AuthUser> => {
    const response = await axios.post<LoginResponse>('/api/v1/auth/login', { email, password })
    const { access_token, refresh_token, user } = response.data
    sessionStorage.setItem('refresh_token', refresh_token)
    useAuthStore.getState().setAuth(user, access_token)
    return user
  },

  logout: () => {
    useAuthStore.getState().clearAuth()
    window.location.href = '/login'
  },
}
