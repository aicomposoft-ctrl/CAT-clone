import apiClient from './client'

// ── Types ──────────────────────────────────────────────────────────────────

export interface Brand {
  id: string
  name: string
  type: 'client' | 'competitor'
  created_at: string
}

export interface SKU {
  id: string
  brand: Brand
  article: string | null
  rpc: string | null
  name: string
  barcode: string | null
  category: string | null
  sub_category: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Platform {
  id: string
  name: string
  type: string | null
  is_active: boolean
}

export interface SKUPlatform {
  id: string
  sku_id: string
  platform_id: string
  external_id: string | null
  url: string | null
  is_monitored: boolean
  created_at: string
}

export interface BulkUploadResult {
  imported: number
  failed: number
  errors: { row: number; field: string; reason: string }[]
}

// ── Brands ────────────────────────────────────────────────────────────────

export const brandsApi = {
  list: async (): Promise<Brand[]> => {
    const r = await apiClient.get<{ items: Brand[]; total: number }>('/brands')
    return r.data.items
  },

  create: async (name: string, type: 'client' | 'competitor'): Promise<Brand> => {
    const r = await apiClient.post<Brand>('/brands', { name, type })
    return r.data
  },
}

// ── SKUs ──────────────────────────────────────────────────────────────────

export const skusApi = {
  list: async (params?: { brand_id?: string; include_inactive?: boolean; limit?: number }): Promise<{ items: SKU[]; total: number }> => {
    const r = await apiClient.get<{ items: SKU[]; total: number; next_cursor: string | null }>('/skus', { params })
    return { items: r.data.items, total: r.data.total }
  },

  create: async (data: {
    brand_id: string
    name: string
    article?: string
    rpc?: string
    barcode?: string
    category?: string
    sub_category?: string
  }): Promise<SKU> => {
    const r = await apiClient.post<SKU>('/skus', data)
    return r.data
  },

  update: async (id: string, data: Partial<{
    name: string
    article: string
    rpc: string
    barcode: string
    category: string
    sub_category: string
    is_active: boolean
    brand_id: string
  }>): Promise<SKU> => {
    const r = await apiClient.patch<SKU>(`/skus/${id}`, data)
    return r.data
  },

  remove: async (id: string): Promise<void> => {
    await apiClient.delete(`/skus/${id}`)
  },

  bulkUpload: async (file: File): Promise<BulkUploadResult> => {
    const form = new FormData()
    form.append('file', file)
    const r = await apiClient.post<BulkUploadResult>('/skus/bulk-upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return r.data
  },
}

// ── Platforms ─────────────────────────────────────────────────────────────

export const platformsApi = {
  list: async (): Promise<Platform[]> => {
    const r = await apiClient.get<{ items: Platform[] }>('/platforms')
    return r.data.items
  },
}

// Rewrite MinIO presigned URLs to go through the Vite /s3 proxy.
// MinIO generates URLs with http://localhost:9000 which is unreachable from
// the browser when served via Codespaces or any remote dev URL.
function rewriteMinioUrl(url: string): string {
  return url.replace(/^https?:\/\/localhost:9000/, '/s3')
}

// ── SKU Reference ────────────────────────────────────────────────────────

export interface SKUReference {
  reference_image_url: string | null
  reference_description: string | null
  reference_composition: string | null
}

export const referenceApi = {
  getImageUrl: async (skuId: string): Promise<{ url: string | null }> => {
    try {
      const r = await apiClient.get<{ presigned_url: string }>(`/skus/${skuId}/reference/image-url`)
      return { url: rewriteMinioUrl(r.data.presigned_url) }
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 404) return { url: null }
      throw e
    }
  },

  uploadImage: async (skuId: string, file: File): Promise<{ url: string }> => {
    const form = new FormData()
    form.append('file', file)
    const r = await apiClient.post<{ presigned_url: string }>(`/skus/${skuId}/reference/image`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return { url: rewriteMinioUrl(r.data.presigned_url) }
  },

  updateText: async (skuId: string, data: {
    reference_description?: string | null
    reference_composition?: string | null
  }): Promise<void> => {
    await apiClient.patch(`/skus/${skuId}/reference/text`, data)
  },
}

// ── SKU-Platforms ─────────────────────────────────────────────────────────

export const skuPlatformsApi = {
  listForSku: async (skuId: string): Promise<SKUPlatform[]> => {
    const r = await apiClient.get<SKUPlatform[]>('/sku-platforms', {
      params: { sku_id: skuId },
    })
    return r.data
  },

  link: async (data: { sku_id: string; platform_id: string; external_id?: string; url?: string }): Promise<SKUPlatform> => {
    const r = await apiClient.post<SKUPlatform>('/sku-platforms', data)
    return r.data
  },

  unlink: async (id: string): Promise<void> => {
    await apiClient.delete(`/sku-platforms/${id}`)
  },
}
