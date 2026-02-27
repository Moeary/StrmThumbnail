<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

const config = reactive({
  media_path: '/media',
  threads: 2,
  generate_poster: true,
  generate_fanart: true,
  generate_nfo: false,
  poster_percent: 10,
  fanart_percent: 50,
  cron: '0 2 * * *',
  overwrite: false
})

const stats = reactive({
  status: 'idle',
  success_count: 0,
  failed_count: 0,
  skipped_count: 0,
  total_files: 0,
  duration_seconds: 0,
  progress: {
    current: 0,
    total: 0,
    status: 'idle'
  }
})

const loading = ref(false)
const saving = ref(false)
const logs = ref([])
let ws = null

const currentStatus = computed(() => {
  if (stats.progress.status === 'running') return '运行中'
  if (stats.progress.status === 'stopped') return '已停止'
  return '空闲'
})

const progressPercent = computed(() => {
  if (!stats.progress.total) return 0
  return Math.floor((stats.progress.current / stats.progress.total) * 100)
})

function logLine(message) {
  logs.value.push(`[${new Date().toLocaleTimeString()}] ${message}`)
  if (logs.value.length > 500) {
    logs.value.shift()
  }
}

async function fetchConfig() {
  const res = await fetch('/api/config')
  const data = await res.json()
  Object.assign(config, data)
}

async function fetchStats() {
  const res = await fetch('/api/stats')
  const data = await res.json()
  Object.assign(stats, data)
  if (data.progress) {
    stats.progress = data.progress
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || '保存失败')
    }
    logLine('配置保存成功')
  } catch (err) {
    logLine(`配置保存失败: ${err.message}`)
  } finally {
    saving.value = false
  }
}

async function startTask(mode = 'full') {
  loading.value = true
  try {
    const res = await fetch('/api/task/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode })
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || '启动失败')
    }
    stats.progress.status = 'running'
    logLine(`任务已启动 (${mode})`)
  } catch (err) {
    logLine(`启动失败: ${err.message}`)
  } finally {
    loading.value = false
  }
}

async function stopTask() {
  try {
    const res = await fetch('/api/task/stop', { method: 'POST' })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || '停止失败')
    }
    logLine('已发送停止指令')
  } catch (err) {
    logLine(`停止失败: ${err.message}`)
  }
}

function connectWs() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${protocol}://${location.host}/ws/stream`)

  ws.onopen = () => {
    logLine('WebSocket 已连接')
    ws.send('ping')
  }

  ws.onmessage = event => {
    const data = JSON.parse(event.data)
    if (data.type === 'log') {
      logLine(data.message)
    } else if (data.type === 'progress') {
      stats.progress = {
        current: data.current,
        total: data.total,
        status: data.status
      }
    } else if (data.type === 'stats') {
      Object.assign(stats, data)
      stats.progress = { current: 0, total: 0, status: 'idle' }
      logLine(`任务完成: 成功${data.success_count} 失败${data.failed_count} 跳过${data.skipped_count}`)
    }
  }

  ws.onclose = () => {
    logLine('WebSocket 已断开，3秒后重连')
    setTimeout(connectWs, 3000)
  }
}

onMounted(async () => {
  await fetchConfig()
  await fetchStats()
  connectWs()
})

onUnmounted(() => {
  if (ws) ws.close()
})
</script>

<template>
  <div class="container mx-auto max-w-7xl p-4 space-y-4">
    <h1 class="text-2xl font-bold">StrmThumbnail 控制台</h1>

    <div class="grid gap-4 md:grid-cols-3">
      <section class="card bg-base-100 shadow">
        <div class="card-body">
          <h2 class="card-title">Dashboard</h2>
          <div class="text-sm opacity-70">状态：{{ currentStatus }}</div>

          <progress class="progress progress-primary w-full" :value="progressPercent" max="100"></progress>
          <div class="text-sm">{{ stats.progress.current }} / {{ stats.progress.total }} ({{ progressPercent }}%)</div>

          <div class="stats stats-vertical lg:stats-horizontal shadow bg-base-200">
            <div class="stat py-2">
              <div class="stat-title">成功</div>
              <div class="stat-value text-success text-2xl">{{ stats.success_count }}</div>
            </div>
            <div class="stat py-2">
              <div class="stat-title">失败</div>
              <div class="stat-value text-error text-2xl">{{ stats.failed_count }}</div>
            </div>
            <div class="stat py-2">
              <div class="stat-title">跳过</div>
              <div class="stat-value text-warning text-2xl">{{ stats.skipped_count }}</div>
            </div>
          </div>

          <div class="text-sm">总耗时：{{ Number(stats.duration_seconds || 0).toFixed(2) }}s</div>

          <div class="card-actions justify-end">
            <button class="btn btn-primary" :disabled="loading" @click="startTask('full')">立即运行</button>
            <button class="btn btn-secondary" :disabled="loading" @click="startTask('incremental')">增量运行</button>
            <button class="btn btn-error btn-outline" @click="stopTask">停止</button>
          </div>
        </div>
      </section>

      <section class="card bg-base-100 shadow md:col-span-2">
        <div class="card-body">
          <h2 class="card-title">Terminal View</h2>
          <div class="rounded-lg bg-neutral text-neutral-content p-3 h-80 overflow-y-auto font-mono text-xs leading-5">
            <div v-for="(line, i) in logs" :key="i">{{ line }}</div>
          </div>
        </div>
      </section>
    </div>

    <section class="card bg-base-100 shadow">
      <div class="card-body">
        <h2 class="card-title">Settings</h2>
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <label class="form-control">
            <div class="label"><span class="label-text">目录映射</span></div>
            <input v-model="config.media_path" class="input input-bordered" placeholder="/media" />
          </label>

          <label class="form-control">
            <div class="label"><span class="label-text">线程数</span></div>
            <input v-model.number="config.threads" type="number" min="1" max="32" class="input input-bordered" />
          </label>

          <label class="form-control">
            <div class="label"><span class="label-text">Cron 表达式</span></div>
            <input v-model="config.cron" class="input input-bordered" placeholder="0 2 * * *" />
            <div class="label"><span class="label-text-alt">示例：每天凌晨2点 = 0 2 * * *</span></div>
          </label>

          <label class="label cursor-pointer justify-start gap-3">
            <input v-model="config.generate_poster" type="checkbox" class="toggle toggle-primary" />
            <span class="label-text">生成 Poster (10%)</span>
          </label>

          <label class="label cursor-pointer justify-start gap-3">
            <input v-model="config.generate_fanart" type="checkbox" class="toggle toggle-primary" />
            <span class="label-text">生成 Fanart (50%)</span>
          </label>

          <label class="label cursor-pointer justify-start gap-3">
            <input v-model="config.generate_nfo" type="checkbox" class="toggle toggle-primary" />
            <span class="label-text">生成 NFO</span>
          </label>

          <label class="form-control">
            <div class="label"><span class="label-text">Poster 抽帧百分比</span></div>
            <input v-model.number="config.poster_percent" type="number" min="1" max="99" class="input input-bordered" />
          </label>

          <label class="form-control">
            <div class="label"><span class="label-text">Fanart 抽帧百分比</span></div>
            <input v-model.number="config.fanart_percent" type="number" min="1" max="99" class="input input-bordered" />
          </label>

          <label class="label cursor-pointer justify-start gap-3">
            <input v-model="config.overwrite" type="checkbox" class="toggle toggle-secondary" />
            <span class="label-text">覆盖已存在文件</span>
          </label>
        </div>

        <div class="card-actions justify-end">
          <button class="btn btn-accent" :class="{ loading: saving }" @click="saveConfig">保存配置</button>
        </div>
      </div>
    </section>
  </div>
</template>
