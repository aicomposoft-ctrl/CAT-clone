import { InboxOutlined } from '@ant-design/icons'
import { Alert, Button, List, Modal, Typography, Upload, message } from 'antd'
import { useState } from 'react'
import { distributionApi } from '../../../api/stock'
import type { UploadResult } from '../../../api/stock'

const MAX_FILE_BYTES = 5 * 1024 * 1024

interface Props {
  onSuccess: () => void
}

export function UploadPlanButton({ onSuccess }: Props) {
  const [open, setOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  function handleClose() {
    setOpen(false)
    setResult(null)
    setError(null)
  }

  async function handleUpload(file: File) {
    if (file.size > MAX_FILE_BYTES) {
      message.error('File too large (max 5 MB)')
      return
    }
    setUploading(true)
    setError(null)
    try {
      const res = await distributionApi.uploadCSV(file)
      setResult(res)
      if (res.imported > 0) {
        onSuccess()
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })
        ?.response
      if (status?.status === 422) {
        setError(status.data?.detail ?? 'Invalid file')
      } else {
        message.error('Server error — contact support')
      }
    } finally {
      setUploading(false)
    }
  }

  return (
    <>
      <Button type="primary" onClick={() => setOpen(true)}>
        Upload Plan
      </Button>
      <Modal
        title="Upload Distribution Plan"
        open={open}
        onCancel={handleClose}
        footer={
          result ? (
            <Button type="primary" onClick={handleClose}>
              Done
            </Button>
          ) : null
        }
        width={520}
      >
        {result ? (
          <div>
            <Typography.Text strong>
              {result.imported} row{result.imported !== 1 ? 's' : ''} imported
            </Typography.Text>
            {result.errors.length > 0 && (
              <List
                style={{ marginTop: 12 }}
                header={
                  <Typography.Text type="warning">
                    {result.errors.length} row error{result.errors.length !== 1 ? 's' : ''}
                  </Typography.Text>
                }
                size="small"
                dataSource={result.errors}
                renderItem={(e) => (
                  <List.Item>
                    <Typography.Text type="secondary">
                      Row {e.row} · {e.field}: {e.message}
                    </Typography.Text>
                  </List.Item>
                )}
              />
            )}
          </div>
        ) : (
          <>
            {error && (
              <Alert type="error" message={error} style={{ marginBottom: 12 }} />
            )}
            <Upload.Dragger
              accept=".csv"
              multiple={false}
              showUploadList={false}
              disabled={uploading}
              beforeUpload={(file) => {
                handleUpload(file)
                return false
              }}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">Click or drag CSV file here</p>
              <p className="ant-upload-hint">
                Accepts .csv only · max 5 MB
              </p>
            </Upload.Dragger>
          </>
        )}
      </Modal>
    </>
  )
}
