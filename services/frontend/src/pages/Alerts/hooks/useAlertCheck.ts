import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { message } from 'antd'
import { AxiosError } from 'axios'
import { alertConfigsApi } from '../../../api/alerts'

export function useAlertCheck() {
  const [cooldownUntil, setCooldownUntil] = useState<number>(0)
  const [remaining, setRemaining] = useState<number>(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (cooldownUntil > Date.now()) {
      intervalRef.current = setInterval(() => {
        const diff = Math.ceil((cooldownUntil - Date.now()) / 1000)
        if (diff > 0) {
          setRemaining(diff)
        } else {
          if (intervalRef.current !== null) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
          setRemaining(0)
        }
      }, 1000)
    } else {
      setRemaining(0)
    }

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [cooldownUntil])

  const mutation = useMutation({
    mutationFn: () => alertConfigsApi.check(),
    onSuccess: (data) => {
      setCooldownUntil(Date.now() + 60_000)
      message.success(
        `Создано событий: ${data.events_created}, отправлено писем: ${data.emails_sent}`
      )
    },
    onError: (err) => {
      const status = (err as AxiosError).response?.status
      if (status === 429) {
        // Server-side rate limit hit — start cooldown to match server window
        setCooldownUntil(Date.now() + 60_000)
        message.warning('Слишком много запросов, подождите 1 минуту')
      } else {
        message.error('Ошибка при запуске проверки')
      }
    },
  })

  const isCooling = remaining > 0

  return {
    run: mutation.mutate,
    isLoading: mutation.isPending,
    isCooling,
    remaining,
  }
}
