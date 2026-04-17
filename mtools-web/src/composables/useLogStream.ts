import { onUnmounted, ref } from 'vue'

export function useLogStream(url: string) {
  const logs = ref('')
  const status = ref<'stopped' | 'running' | 'error' | 'connecting'>('connecting')
  const pid = ref<number | null>(null)
  let ws: WebSocket | null = null

  function connect() {
    ws = new WebSocket(url)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'log' || data.type === 'status') {
        if (data.logs !== undefined) logs.value = data.logs
        if (data.status) status.value = data.status
        if (data.pid !== undefined) pid.value = data.pid
      }
    }
    ws.onclose = () => { status.value = 'stopped' }
    ws.onerror = () => { status.value = 'error' }
  }

  function disconnect() {
    ws?.close()
    ws = null
  }

  onUnmounted(disconnect)

  return { logs, status, pid, connect, disconnect }
}
