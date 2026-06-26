<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'

const backendBase = ''
const models = ref([])
const tasks = ref([])
const submitting = ref(false)
const errorText = ref('')
const filesInput = ref(null)
const activeImageSlot = ref(null)
const selectedTaskId = ref('')
const taskPollTimer = ref(null)
const workMode = ref('standard')
const batchCount = ref(3)
const rerunningTaskId = ref('')
const previewUrlCache = new WeakMap()

const form = reactive({
  model_family: 'LuxVid_video',
  aspect_ratio: '16:9',
  resolution: '720p',
  seconds: '15',
  prompt: '',
  images: [],
  api_key: '',
  auto_face: false,
})

const selectedModel = computed(() => {
  return models.value.find(item => item.value === form.model_family) || null
})

const allowedResolutions = computed(() => selectedModel.value?.resolutions || ['720p'])
const maxImages = computed(() => selectedModel.value?.max_images || 1)
const secondsOptions = computed(() => selectedModel.value?.seconds_options || ['5', '10', '15'])
const aspectRatios = computed(() => selectedModel.value?.aspect_ratios || ['16:9', '9:16'])
const batchPromptList = computed(() => {
  const lines = form.prompt
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
  if (workMode.value === 'batch' && lines.length > 1) {
    return lines
  }
  return Array.from({ length: Math.max(1, Number(batchCount.value) || 1) }, () => form.prompt.trim())
})

const selectedTask = computed(() => {
  return tasks.value.find(item => item.id === selectedTaskId.value) || null
})

const supportsAutoFace = computed(() => form.model_family === 'videos')

watch(selectedModel, (model) => {
  if (!model) return
  if (!model.resolutions.includes(form.resolution)) {
    form.resolution = model.resolutions[0]
  }
  if (!model.seconds_options.includes(form.seconds)) {
    form.seconds = model.seconds_options[0]
  }
  if (!model.aspect_ratios.includes(form.aspect_ratio)) {
    form.aspect_ratio = model.aspect_ratios[0]
  }
  if (form.images.length > model.max_images) {
    form.images = form.images.slice(0, model.max_images)
  }
  form.auto_face = form.model_family === 'videos'
}, { immediate: true })

watch(tasks, (list) => {
  if (!selectedTaskId.value && list.length) {
    selectedTaskId.value = list[0].id
    return
  }
  if (selectedTaskId.value && !list.some(item => item.id === selectedTaskId.value)) {
    selectedTaskId.value = list[0]?.id || ''
  }
})

function formatStatus(status) {
  const map = {
    queued: '等待中',
    running: '生成中',
    completed: '完成',
    failed: '失败',
  }
  return map[status] || status
}

function taskStatusClass(status) {
  return status || 'queued'
}

function setWorkMode(mode) {
  workMode.value = mode
  errorText.value = ''
}

function onFilesChange(event) {
  const list = Array.from(event.target.files || [])
  if (!list.length) return

  appendImageFiles(list, activeImageSlot.value)
  activeImageSlot.value = null
  if (filesInput.value) {
    filesInput.value.value = ''
  }
}

function isImageFile(file) {
  return Boolean(file)
    && (file.type?.startsWith('image/') || /\.(png|jpe?g|webp|bmp)$/i.test(file.name || ''))
}

function appendImageFiles(files, replaceIndex = null) {
  const imageFiles = Array.from(files || []).filter(isImageFile)
  if (!imageFiles.length) {
    errorText.value = '未找到可上传的图片'
    return
  }

  if (replaceIndex !== null && replaceIndex !== undefined) {
    const index = replaceIndex
    const nextImages = [...form.images]
    nextImages[index] = imageFiles[0]
    form.images = nextImages.slice(0, maxImages.value)
  } else {
    const nextImages = [...form.images]
    const availableCount = Math.max(0, maxImages.value - nextImages.length)
    for (const file of imageFiles) {
      if (nextImages.length >= maxImages.value) break
      nextImages.push(file)
    }
    form.images = nextImages
    if (imageFiles.length > availableCount) {
      errorText.value = `当前模型最多允许 ${maxImages.value} 张参考图`
    } else {
      errorText.value = ''
    }
  }
}

function isDirectoryItem(item) {
  const entry = item?.webkitGetAsEntry?.()
  return Boolean(entry?.isDirectory)
}

function readFileEntry(entry) {
  return new Promise(resolve => {
    entry.file(file => resolve(file), () => resolve(null))
  })
}

function readDirectoryBatch(reader) {
  return new Promise((resolve, reject) => {
    reader.readEntries(resolve, reject)
  })
}

async function collectFilesFromEntry(entry) {
  if (!entry) return []
  if (entry.isFile) {
    const file = await readFileEntry(entry)
    return file ? [file] : []
  }
  if (!entry.isDirectory) return []

  const reader = entry.createReader()
  const files = []
  while (true) {
    const entries = await readDirectoryBatch(reader)
    if (!entries.length) break
    const nestedFiles = await Promise.all(entries.map(item => collectFilesFromEntry(item)))
    files.push(...nestedFiles.flat())
  }
  return files
}

async function getDroppedFiles(dataTransfer) {
  const items = Array.from(dataTransfer?.items || [])
  const directFiles = Array.from(dataTransfer?.files || [])
  const hasDirectory = items.some(isDirectoryItem)
  const fileItemCount = items.filter(item => item.kind === 'file').length

  if (!hasDirectory && directFiles.length && directFiles.length >= fileItemCount) {
    return directFiles
  }
  if (!items.length) {
    return directFiles
  }

  const files = []
  for (const item of items) {
    if (item.kind !== 'file') continue
    const entry = item.webkitGetAsEntry?.()
    if (entry) {
      files.push(...await collectFilesFromEntry(entry))
    } else {
      const file = item.getAsFile?.()
      if (file) files.push(file)
    }
  }
  const seen = new Set()
  return files
    .filter(file => {
      const key = `${file.name}_${file.size}_${file.lastModified}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name, 'zh-CN', { numeric: true }))
}

async function onImageDrop(event) {
  activeImageSlot.value = null
  const files = await getDroppedFiles(event.dataTransfer)
  appendImageFiles(files)
}

function openImagePicker(index = null) {
  activeImageSlot.value = index
  filesInput.value?.click()
}

function removeImage(index) {
  form.images = form.images.filter((_, itemIndex) => itemIndex !== index)
  if (filesInput.value) {
    filesInput.value.value = ''
  }
}

function clearForm() {
  form.prompt = ''
  form.images = []
  if (filesInput.value) {
    filesInput.value.value = ''
  }
}

function clearHistory() {
  tasks.value = []
  selectedTaskId.value = ''
}

async function loadModels() {
  const res = await fetch(`${backendBase}/api/models`)
  const data = await res.json()
  models.value = data.models || []
  if (models.value.length && !models.value.some(item => item.value === form.model_family)) {
    form.model_family = models.value[0].value
  }
}

async function loadTasks() {
  const res = await fetch(`${backendBase}/api/tasks`)
  const data = await res.json()
  tasks.value = data.tasks || []
}

async function createRemoteTask(promptText) {
  const payload = new FormData()
  payload.append('model_family', form.model_family)
  payload.append('aspect_ratio', form.aspect_ratio)
  payload.append('resolution', form.resolution)
  payload.append('seconds', form.seconds)
  payload.append('prompt', promptText)
  if (supportsAutoFace.value) {
    payload.append('auto_face', form.auto_face ? 'true' : 'false')
  }
  if (form.api_key.trim()) {
    payload.append('api_key', form.api_key.trim())
  }
  form.images.forEach(file => payload.append('images', file, file.name))
  const res = await fetch(`${backendBase}/api/tasks`, {
    method: 'POST',
    body: payload,
  })
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || '提交失败')
  }
  return data
}

async function submitTask() {
  errorText.value = ''
  if (!form.prompt.trim()) {
    errorText.value = '请输入提示词'
    return
  }
  if (!form.images.length) {
    errorText.value = '请至少上传 1 张参考图'
    return
  }
  if (selectedModel.value?.needs_api_key && !form.api_key.trim()) {
    errorText.value = '当前模型需要填写 API Key'
    return
  }

  const prompts = workMode.value === 'batch' ? batchPromptList.value : [form.prompt.trim()]
  if (workMode.value === 'batch' && prompts.length < 2) {
    errorText.value = '批量生成至少需要 2 个任务；可设置批量数量，或在提示词框按行输入多个提示词'
    return
  }

  submitting.value = true
  try {
    let lastTask = null
    for (let index = 0; index < prompts.length; index += 1) {
      const promptText = prompts[index]
      if (!promptText) continue
      errorText.value = workMode.value === 'batch'
        ? `正在提交批量任务 ${index + 1}/${prompts.length}...`
        : ''
      lastTask = await createRemoteTask(promptText)
    }
    clearForm()
    await loadTasks()
    if (lastTask?.id) {
      selectedTaskId.value = lastTask.id
    }
    errorText.value = ''
  } catch (error) {
    errorText.value = error.message || '提交失败'
  } finally {
    submitting.value = false
  }
}


async function rerunTask(task) {
  if (!task?.id || rerunningTaskId.value) return
  rerunningTaskId.value = task.id
  errorText.value = ''
  try {
    const res = await fetch(`${backendBase}/api/tasks/${task.id}/rerun`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.error || '重新提交失败')
    }
    await loadTasks()
    if (data?.id) {
      selectedTaskId.value = data.id
    }
  } catch (error) {
    errorText.value = error.message || '重新提交失败'
  } finally {
    rerunningTaskId.value = ''
  }
}

function openDownload(task) {
  if (!task?.download_url) return
  window.open(task.download_url, '_blank')
}

function openPreview(task) {
  if (!task?.download_url) return
  window.open(task.download_url, '_blank')
}

function previewFileUrl(file) {
  if (!previewUrlCache.has(file)) {
    previewUrlCache.set(file, URL.createObjectURL(file))
  }
  return previewUrlCache.get(file)
}

onMounted(async () => {
  await loadModels()
  await loadTasks()
  taskPollTimer.value = window.setInterval(loadTasks, 5000)
})

onUnmounted(() => {
  if (taskPollTimer.value) {
    window.clearInterval(taskPollTimer.value)
  }
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-left">
        <button class="back-btn">←</button>
        <div>
          <h1>视频生成</h1>
          <p>多参考图工作台</p>
        </div>
      </div>
      <div class="topbar-right"></div>
    </header>

    <div class="workspace">
      <aside class="left-panel">
        <div class="brand-card">
          <div class="brand-icon">◆</div>
          <div class="brand-title">Veo Generator</div>
        </div>

        <div class="field">
          <select v-model="form.model_family">
            <option v-for="item in models" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </div>

        <div v-if="selectedModel?.needs_api_key" class="field">
          <input
            v-model="form.api_key"
            type="password"
            placeholder="填写 API Key"
          />
        </div>

        <label v-if="supportsAutoFace" class="face-option">
          <input v-model="form.auto_face" type="checkbox" />
          <span>自动人脸处理</span>
        </label>

        <div class="mode-row">
          <button
            class="mode-btn"
            :class="{ active: workMode === 'standard' }"
            @click="setWorkMode('standard')"
          >标准模式</button>
          <button
            class="mode-btn"
            :class="{ active: workMode === 'batch' }"
            @click="setWorkMode('batch')"
          >批量生成</button>
        </div>

        <div v-if="workMode === 'batch'" class="batch-row">
          <span>批量数量</span>
          <select v-model="batchCount" class="mini-select">
            <option v-for="num in [2,3,4,5,6,8,10]" :key="num" :value="num">{{ num }} 个</option>
          </select>
          <span class="batch-note">提示词多行时按行生成</span>
        </div>

        <p class="hint">左侧任务卡支持滚动查看；批量模式会把当前参考图按多个单任务提交。</p>

        <div class="editor-card">
          <div class="task-head-row">
            <div class="task-chip">{{ workMode === 'batch' ? `批量任务 × ${batchPromptList.length}` : '标准任务' }}</div>
            <select v-model="form.aspect_ratio" class="mini-select">
              <option v-for="ratio in aspectRatios" :key="ratio" :value="ratio">{{ ratio }}</option>
            </select>
            <select v-model="form.resolution" class="mini-select">
              <option v-for="item in allowedResolutions" :key="item" :value="item">{{ item }}</option>
            </select>
            <select v-model="form.seconds" class="mini-select">
              <option v-for="item in secondsOptions" :key="item" :value="item">{{ item }}</option>
            </select>
          </div>

          <div
            class="image-grid"
            @dragenter.prevent.stop
            @dragover.prevent.stop
            @drop.prevent.stop="onImageDrop"
          >
            <div
              v-for="index in maxImages"
              :key="index"
              class="image-slot"
              :class="{ filled: form.images[index - 1] }"
              role="button"
              tabindex="0"
              @click="openImagePicker(index - 1)"
              @keydown.enter.prevent="openImagePicker(index - 1)"
            >
              <template v-if="form.images[index - 1]">
                <img :src="previewFileUrl(form.images[index - 1])" alt="" />
                <button class="remove-image" title="移除图片" @click.stop="removeImage(index - 1)">×</button>
                <span class="slot-file">{{ form.images[index - 1].name }}</span>
              </template>
              <template v-else>
                <span class="slot-icon">⇪</span>
                <span class="slot-title">图片 {{ index }}</span>
                <span class="slot-hint">点击上传</span>
              </template>
            </div>
          </div>

          <input
            ref="filesInput"
            class="hidden-input"
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.bmp"
            :multiple="activeImageSlot === null"
            @change="onFilesChange"
          />
          <button class="ghost upload-btn" @click="openImagePicker()">追加参考图</button>

          <textarea
            v-model="form.prompt"
            class="prompt-box"
            rows="10"
            :placeholder="workMode === 'batch' ? '输入批量提示词：单行会按批量数量重复提交；多行则每行生成一个任务...' : '输入标准模式下的提示词...'"
          ></textarea>
        </div>

        <p v-if="errorText" class="error">{{ errorText }}</p>

        <div class="footer-actions">
          <button class="ghost" @click="clearForm">重置</button>
          <button class="primary" :disabled="submitting" @click="submitTask">
            {{ submitting ? '提交中...' : (workMode === 'batch' ? `批量生成 ${batchPromptList.length} 个` : '生成视频') }}
          </button>
        </div>
      </aside>

      <section class="right-panel">
        <div class="preview-card">
          <div class="preview-surface">
            <template v-if="selectedTask?.download_url">
              <video :src="selectedTask.download_url" controls preload="metadata"></video>
            </template>
            <template v-else-if="selectedTask?.image_preview_urls?.[0]">
              <img :src="selectedTask.image_preview_urls[0]" alt="" />
            </template>
            <template v-else>
              <div class="preview-placeholder">
                <p>生成完成后会在这里显示视频</p>
                <p>可先点击右侧历史查看任务详情</p>
              </div>
            </template>
          </div>

          <div class="detail-panel">
            <div class="badge" :class="taskStatusClass(selectedTask?.status)">
              {{ formatStatus(selectedTask?.status || 'queued') }}
            </div>

            <h3>{{ selectedTask?.display_id || '未选择任务' }}</h3>
            <div class="meta-card">{{ selectedTask ? `${selectedTask.model_family} / ${selectedTask.resolution} / ${selectedTask.seconds}s` : '模型 / 分辨率 / 时长' }}</div>

            <div class="detail-label">提示词</div>
            <div class="detail-box prompt-view">{{ selectedTask?.prompt || '' }}</div>

            <div class="detail-label">RAW ID</div>
            <div class="detail-box single-line">{{ selectedTask?.remote_task_id || selectedTask?.id || '' }}</div>

            <div class="detail-label">日志</div>
            <div class="detail-box log-box">{{ (selectedTask?.logs || []).join('\n') }}</div>

            <div class="preview-actions single-action">
              <button class="ghost small" :disabled="!selectedTask?.download_url" @click="openDownload(selectedTask)">下载</button>
            </div>
          </div>
        </div>

        <div class="history-card">
          <div class="history-head">
            <div class="history-title">任务历史（{{ tasks.length }}）</div>
            <div class="history-right">
              <span class="history-note">视频会自动保存到本地目录，可随时回看或下载</span>
              <button class="ghost small" @click="clearHistory">清空历史</button>
            </div>
          </div>

          <div class="history-list">
            <div
              v-for="task in tasks"
              :key="task.id"
              class="history-item"
              :class="{ selected: task.id === selectedTaskId }"
              @click="selectedTaskId = task.id"
            >
              <div class="history-top">
                <div>
                  <div class="history-item-title">{{ task.display_id }}</div>
                  <div class="history-item-meta">
                    {{ formatStatus(task.status) }} · {{ task.aspect_ratio }} / {{ task.resolution }} · {{ task.seconds }}s
                  </div>
                </div>
                <span class="dot" :class="taskStatusClass(task.status)"></span>
              </div>

              <div v-if="task.image_preview_urls?.length" class="history-images">
                <img
                  v-for="(url, idx) in task.image_preview_urls.slice(0, 6)"
                  :key="idx"
                  :src="url"
                  alt=""
                />
              </div>

              <div class="history-bottom">
                <div class="mini-progress">
                  <div class="mini-progress-bar" :style="{ width: `${task.progress || 0}%` }"></div>
                </div>
                <button class="ghost tiny" :disabled="rerunningTaskId === task.id" @click.stop="rerunTask(task)">
                  {{ rerunningTaskId === task.id ? '提交中' : '重新提交' }}
                </button>
                <button class="ghost tiny" :disabled="!task.download_url" @click.stop="openDownload(task)">下载</button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
