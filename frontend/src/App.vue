<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import UsageRecords from './components/UsageRecords.vue'
import ChannelAvailability from './components/ChannelAvailability.vue'
import StudioIcon from './components/StudioIcon.vue'

const backendBase = ''
const activeView = ref('generation')
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
const reusingTaskId = ref('')
const imageSlotsExpanded = ref(false)
const referenceMediaExpanded = ref(false)
const pageHeading = ref(null)
const formFeedback = ref(null)
const historyFilter = ref('all')
const previewUrlCache = new WeakMap()
const MAX_IMAGE_UPLOAD_BYTES = 1024 * 1024
const MAX_IMAGE_DIMENSION = 4096
const JPEG_MAX_QUALITY = 0.92
const JPEG_MIN_QUALITY = 0.35

const form = reactive({
  model_family: 'LuxVid_video',
  aspect_ratio: '16:9',
  resolution: '720p',
  seconds: '15',
  prompt: '',
  images: [],
  api_key: '',
  auto_face: false,
  reference_videos: [],
  reference_audios: [],
  first_image: [],
  last_image: [],
  model_options: { seed: '-1', generate_audio: true, omni_reference_task_type: 'auto', return_last_frame: false, tools: '[]' },
})

const selectedModel = computed(() => {
  return models.value.find(item => item.value === form.model_family) || null
})
const modelGroups = computed(() => [...new Set(models.value.map(item => item.provider_name))].map(name => ({ name, models: models.value.filter(item => item.provider_name === name) })))
const activeTasks = computed(() => tasks.value.filter(task => ['queued', 'running'].includes(task.status)).length)
const filteredTasks = computed(() => tasks.value.filter(task => historyFilter.value === 'all' || (historyFilter.value === 'active' ? ['queued', 'running'].includes(task.status) : task.status === historyFilter.value)))
const pageTitle = computed(() => ({ generation: '视频创作', usage: '用量记录', availability: '渠道可用性' })[activeView.value])

async function switchView(view) {
  activeView.value = view
  await nextTick()
  pageHeading.value?.focus()
}

async function handleSubmit() {
  await submitTask()
  if (errorText.value) {
    await nextTick()
    formFeedback.value?.focus()
  }
}

const allowedResolutions = computed(() => selectedModel.value?.resolutions || ['720p'])
const maxImages = computed(() => selectedModel.value?.max_images || 1)
const secondsOptions = computed(() => selectedModel.value?.seconds_options || ['5', '10', '15'])
const aspectRatios = computed(() => selectedModel.value?.aspect_ratios || ['16:9', '9:16'])
const visibleImageCount = computed(() => {
  const max = maxImages.value
  if (imageSlotsExpanded.value) return max
  return Math.min(max, Math.max(3, Math.ceil((form.images.length + 1) / 3) * 3))
})
const hasHiddenImageSlots = computed(() => visibleImageCount.value < maxImages.value)
const canCollapseImageSlots = computed(() => imageSlotsExpanded.value)
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
const minImages = computed(() => selectedModel.value?.min_images ?? (maxImages.value > 0 ? 1 : 0))
const supportsReferenceMedia = computed(() => Boolean(selectedModel.value?.supports_reference_media))
const supportsFrameImages = computed(() => Boolean(selectedModel.value?.supports_frame_images))
const mediaUploadFields = computed(() => [
  { key: 'reference_videos', label: '参考视频', accept: '.mp4,.mov,.webm,.m4v', limit: 10, maxMB: 128 },
  { key: 'reference_audios', label: '参考音频', accept: '.mp3,.wav,.m4a,.aac,.ogg,.flac', limit: 10, maxMB: 32 },
  ...(supportsFrameImages.value ? [
    { key: 'first_image', label: '首帧图片', accept: '.png,.jpg,.jpeg,.webp,.bmp', limit: 1, maxMB: 20 },
    { key: 'last_image', label: '尾帧图片', accept: '.png,.jpg,.jpeg,.webp,.bmp', limit: 1, maxMB: 20 },
  ] : []),
].map(field => ({
  ...field,
  limit: selectedModel.value?.media_upload_limits?.[field.key]?.limit ?? field.limit,
  maxMB: (selectedModel.value?.media_upload_limits?.[field.key]?.max_bytes ?? field.maxMB * 1024 * 1024) / 1024 / 1024,
  accept: selectedModel.value?.media_upload_limits?.[field.key]?.extensions?.join(',') || field.accept,
})).filter(field => field.limit > 0))

watch(() => form.model_options.omni_reference_task_type, mode => {
  if (selectedModel.value?.supports_special_options && mode === 'extend') form.aspect_ratio = 'adaptive'
})

watch(selectedModel, (model) => {
  if (!model) return
  imageSlotsExpanded.value = false
  referenceMediaExpanded.value = false
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
  if (!model.supports_reference_media) {
    form.reference_videos = []
    form.reference_audios = []
  }
  if (model.media_upload_limits?.reference_videos?.limit === 0) {
    form.reference_videos = []
  }
  if (!model.supports_frame_images) {
    form.first_image = []
    form.last_image = []
  }
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

async function onFilesChange(event) {
  const list = Array.from(event.target.files || [])
  if (!list.length) return

  try {
    await appendImageFiles(list, activeImageSlot.value)
  } catch (error) {
    errorText.value = error.message || '图片压缩失败'
  } finally {
    activeImageSlot.value = null
    if (filesInput.value) {
      filesInput.value.value = ''
    }
  }
}

function isImageFile(file) {
  return Boolean(file)
    && (file.type?.startsWith('image/') || /\.(png|jpe?g|webp|bmp)$/i.test(file.name || ''))
}

function loadImageForCompression(file) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(objectUrl)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      reject(new Error(`无法读取图片：${file.name || '未命名图片'}`))
    }
    image.src = objectUrl
  })
}

function canvasToJpegBlob(canvas, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(blob => {
      if (blob) {
        resolve(blob)
      } else {
        reject(new Error('浏览器不支持图片压缩'))
      }
    }, 'image/jpeg', quality)
  })
}

async function compressImageFile(file) {
  const image = await loadImageForCompression(file)
  const sourceWidth = image.naturalWidth || image.width
  const sourceHeight = image.naturalHeight || image.height
  if (!sourceWidth || !sourceHeight) {
    throw new Error(`图片尺寸无效：${file.name || '未命名图片'}`)
  }

  let scale = Math.min(1, MAX_IMAGE_DIMENSION / Math.max(sourceWidth, sourceHeight))
  try {
    for (let pass = 0; pass < 8; pass += 1) {
      const width = Math.max(1, Math.round(sourceWidth * scale))
      const height = Math.max(1, Math.round(sourceHeight * scale))
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const context = canvas.getContext('2d', { alpha: false })
      if (!context) throw new Error('浏览器无法创建图片压缩画布')

      context.fillStyle = '#ffffff'
      context.fillRect(0, 0, width, height)
      context.drawImage(image, 0, 0, width, height)

      const highestQualityBlob = await canvasToJpegBlob(canvas, JPEG_MAX_QUALITY)
      if (highestQualityBlob.size <= MAX_IMAGE_UPLOAD_BYTES) {
        return new File(
          [highestQualityBlob],
          `${(file.name || 'image').replace(/\.[^.]+$/, '')}.jpg`,
          { type: 'image/jpeg', lastModified: file.lastModified },
        )
      }

      const lowestQualityBlob = await canvasToJpegBlob(canvas, JPEG_MIN_QUALITY)
      if (lowestQualityBlob.size <= MAX_IMAGE_UPLOAD_BYTES) {
        let low = JPEG_MIN_QUALITY
        let high = JPEG_MAX_QUALITY
        let bestBlob = lowestQualityBlob
        for (let attempt = 0; attempt < 7; attempt += 1) {
          const quality = (low + high) / 2
          const candidate = await canvasToJpegBlob(canvas, quality)
          if (candidate.size <= MAX_IMAGE_UPLOAD_BYTES) {
            bestBlob = candidate
            low = quality
          } else {
            high = quality
          }
        }
        return new File(
          [bestBlob],
          `${(file.name || 'image').replace(/\.[^.]+$/, '')}.jpg`,
          { type: 'image/jpeg', lastModified: file.lastModified },
        )
      }

      scale *= 0.75
    }
  } finally {
    image.src = ''
  }

  throw new Error(`图片压缩后仍超过 1 MB：${file.name || '未命名图片'}`)
}

async function appendImageFiles(files, replaceIndex = null) {
  const imageFiles = Array.from(files || []).filter(isImageFile)
  if (!imageFiles.length) {
    errorText.value = '未找到可上传的图片'
    return
  }

  const limit = replaceIndex !== null && replaceIndex !== undefined
    ? 1
    : Math.max(0, maxImages.value - form.images.length)
  const filesToCompress = imageFiles.slice(0, limit)
  if (!filesToCompress.length) {
    errorText.value = `当前模型最多允许 ${maxImages.value} 张参考图`
    return
  }

  const compressedFiles = []
  for (let index = 0; index < filesToCompress.length; index += 1) {
    errorText.value = `正在压缩图片 ${index + 1}/${filesToCompress.length}...`
    compressedFiles.push(await compressImageFile(filesToCompress[index]))
  }

  if (replaceIndex !== null && replaceIndex !== undefined) {
    const index = replaceIndex
    const nextImages = [...form.images]
    nextImages[index] = compressedFiles[0]
    form.images = nextImages.slice(0, maxImages.value)
  } else {
    const nextImages = [...form.images]
    for (const file of compressedFiles) {
      if (nextImages.length >= maxImages.value) break
      nextImages.push(file)
    }
    form.images = nextImages
    if (imageFiles.length > filesToCompress.length) {
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
  try {
    const files = await getDroppedFiles(event.dataTransfer)
    await appendImageFiles(files)
  } catch (error) {
    errorText.value = error.message || '图片压缩失败'
  }
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

async function onMediaFilesChange(event, field) {
  const input = event.target
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  errorText.value = ''
  if ((field.limit > 1 && form[field.key].length + files.length > field.limit) || files.length > field.limit) {
    errorText.value = `${field.label}最多上传 ${field.limit} 个文件，请先移除部分文件`
    return
  }
  const extensions = field.accept.split(',')
  if (files.some(file => !extensions.includes(`.${file.name.split('.').pop().toLowerCase()}`))) {
    errorText.value = `${field.label}文件格式不支持`
    return
  }
  if (files.some(file => !file.size || file.size > field.maxMB * 1024 * 1024)) {
    errorText.value = `${field.label}单个文件需大于 0 且不超过 ${field.maxMB} MB`
    return
  }
  try {
    const prepared = ['first_image', 'last_image'].includes(field.key)
      ? await Promise.all(files.map(compressImageFile))
      : files
    form[field.key] = field.limit === 1 ? prepared : [...form[field.key], ...prepared]
  } catch (error) {
    errorText.value = error.message || '参考文件处理失败'
  }
}

function clearForm() {
  form.prompt = ''
  form.images = []
  form.reference_videos = []
  form.reference_audios = []
  form.first_image = []
  form.last_image = []
  form.model_options = { seed: '-1', generate_audio: true, omni_reference_task_type: 'auto', return_last_frame: false, tools: '[]' }
  referenceMediaExpanded.value = false
  imageSlotsExpanded.value = false
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
  const data = await readJsonResponse(res, '加载模型失败')
  models.value = data.models || []
  if (models.value.length && !models.value.some(item => item.value === form.model_family)) {
    form.model_family = models.value[0].value
  }
}

async function loadTasks() {
  const res = await fetch(`${backendBase}/api/tasks`)
  const data = await readJsonResponse(res, '加载任务失败')
  tasks.value = data.tasks || []
}

function expandImageSlots() {
  imageSlotsExpanded.value = true
}

function collapseImageSlots() {
  if (form.images.length <= 12) {
    imageSlotsExpanded.value = false
  }
}

async function readJsonResponse(response, defaultMessage = '请求失败') {
  const text = await response.text()
  let data = {}
  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    if (response.status === 413) {
      throw new Error('上传文件总大小超过服务器限制，请减少文件数量或压缩后重试')
    }
    throw new Error(`${defaultMessage}（服务器返回 HTTP ${response.status}）`)
  }
  if (!response.ok) {
    throw new Error(data.error || data.message || `${defaultMessage}（HTTP ${response.status}）`)
  }
  return data
}

async function createRemoteTask(promptText) {
  const payload = new FormData()
  payload.append('model_family', form.model_family)
  payload.append('aspect_ratio', form.aspect_ratio)
  payload.append('resolution', form.resolution)
  payload.append('seconds', form.seconds)
  payload.append('prompt', promptText)
  if (selectedModel.value?.supports_special_options) {
    let tools
    try { tools = JSON.parse(form.model_options.tools || '[]') } catch { throw new Error('工具配置必须为有效 JSON 数组') }
    payload.append('model_options', JSON.stringify({ ...form.model_options, tools }))
  }
  if (supportsAutoFace.value) {
    payload.append('auto_face', form.auto_face ? 'true' : 'false')
  }
  if (form.api_key.trim()) {
    payload.append('api_key', form.api_key.trim())
  }
  form.images.forEach(file => payload.append('images', file, file.name))
  if (supportsReferenceMedia.value) {
    mediaUploadFields.value.forEach(field => {
      form[field.key].forEach(file => payload.append(field.key, file, file.name))
    })
  }
  const res = await fetch(`${backendBase}/api/tasks`, {
    method: 'POST',
    body: payload,
  })
  return readJsonResponse(res, '提交失败')
}

async function submitTask() {
  errorText.value = ''
  if (!form.prompt.trim()) {
    errorText.value = '请输入提示词'
    return
  }
  if (minImages.value > 0 && !form.images.length) {
    errorText.value = '请至少上传 1 张参考图'
    return
  }
  if (selectedModel.value?.needs_api_key && !form.api_key.trim()) {
    errorText.value = '当前模型需要填写 API Key'
    return
  }
  const uploadBytes = [...form.images, ...mediaUploadFields.value.flatMap(field => form[field.key])]
    .reduce((total, file) => total + file.size, 0)
  if (uploadBytes > 510 * 1024 * 1024) {
    errorText.value = '上传文件总大小不能超过 510 MB，请减少文件数量或压缩后重试'
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
    const data = await readJsonResponse(res, '重新提交失败')
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

function fileExtensionFromBlob(blob) {
  const mime = blob?.type || ''
  if (mime.includes('png')) return 'png'
  if (mime.includes('webp')) return 'webp'
  if (mime.includes('bmp')) return 'bmp'
  return 'jpg'
}

async function imageUrlToFile(url, index) {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`\u53c2\u8003\u56fe ${index + 1} \u8bfb\u53d6\u5931\u8d25`)
  }
  const blob = await res.blob()
  const ext = fileExtensionFromBlob(blob)
  return new File([blob], `reuse_ref_${index + 1}.${ext}`, { type: blob.type || 'image/jpeg' })
}

async function reuseTaskConfig(task) {
  if (!task?.id || reusingTaskId.value) return
  reusingTaskId.value = task.id
  errorText.value = ''
  try {
    const model = models.value.find(item => item.value === task.model_family)
    if (!model) {
      throw new Error('\u5f53\u524d\u4efb\u52a1\u6a21\u578b\u5df2\u4e0d\u5728\u4e0b\u62c9\u5217\u8868\u4e2d')
    }

    form.model_family = task.model_family
    await nextTick()
    form.aspect_ratio = model.aspect_ratios.includes(task.aspect_ratio) ? task.aspect_ratio : model.aspect_ratios[0]
    form.resolution = model.resolutions.includes(task.resolution) ? task.resolution : model.resolutions[0]
    const taskSeconds = String(task.seconds || '')
    form.seconds = model.seconds_options.includes(taskSeconds) ? taskSeconds : model.seconds_options[0]
    form.prompt = task.prompt || ''
    form.auto_face = Boolean(task.auto_face) && task.model_family === 'videos'
    form.model_options = { seed: '-1', generate_audio: true, omni_reference_task_type: 'auto', return_last_frame: false,
      ...task.model_options, tools: JSON.stringify(task.model_options?.tools || []) }
    for (const field of mediaUploadFields.value) {
      form[field.key] = await Promise.all((task.media_files?.[field.key] || []).map(async (media) => {
        const response = await fetch(`${backendBase}${media.url}`)
        if (!response.ok) throw new Error(`${field.label}文件已过期或无法读取，请重新上传`)
        const blob = await response.blob()
        return new File([blob], media.name, { type: blob.type })
      }))
    }
    referenceMediaExpanded.value = false

    const imageUrls = (task.image_preview_urls || []).slice(0, model.max_images || 0)
    form.images = imageUrls.length
      ? await Promise.all(imageUrls.map(async (url, index) => {
        const sourceFile = await imageUrlToFile(url, index)
        return compressImageFile(sourceFile)
      }))
      : []

    workMode.value = 'standard'
    selectedTaskId.value = task.id
    errorText.value = '\u5df2\u590d\u7528\u5230\u5de6\u4fa7\uff0c\u53ef\u76f4\u63a5\u4fee\u6539\u540e\u751f\u6210'
  } catch (error) {
    errorText.value = error.message || '\u590d\u7528\u4efb\u52a1\u5931\u8d25'
  } finally {
    reusingTaskId.value = ''
  }
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
    <a class="skip-link" href="#workspace-main">跳到工作区</a>
    <aside class="app-nav">
      <div class="studio-brand"><span class="brand-mark"><StudioIcon name="video" /></span><div><strong>视频创作工坊</strong><span>VIDEO STUDIO</span></div></div>
      <p class="nav-caption">工作空间</p>
      <nav aria-label="主要导航">
        <button v-for="item in [{ id: 'generation', label: '视频创作', icon: 'video' }, { id: 'usage', label: '用量记录', icon: 'chart' }, { id: 'availability', label: '渠道可用性', icon: 'activity' }]" :key="item.id" type="button" :aria-current="activeView === item.id ? 'page' : undefined" :class="{ active: activeView === item.id }" @click="switchView(item.id)"><StudioIcon :name="item.icon" /><span>{{ item.label }}</span></button>
      </nav>
      <div class="nav-footer"><span class="nav-footer-dot"></span><div>多渠道视频工作台<small>{{ models.length }} 个已接入模型</small></div></div>
    </aside>

    <main id="workspace-main" class="main-content">
      <header class="page-header">
        <div><p class="eyebrow">工作空间 <span>/</span> {{ pageTitle }}</p><h1 ref="pageHeading" tabindex="-1">{{ pageTitle }}</h1></div>
        <div class="header-status"><span class="status-dot" :class="{ busy: activeTasks }"></span>{{ activeTasks ? `${activeTasks} 个任务处理中` : '准备开始创作' }}</div>
      </header>
      <UsageRecords v-if="activeView === 'usage'" />
      <ChannelAvailability v-if="activeView === 'availability'" />

      <div v-show="activeView === 'generation'" class="workspace">
        <form class="composer" action="/api/tasks" method="post" aria-labelledby="composer-title" @submit.prevent="handleSubmit">
          <div class="composer-heading"><div><h2 id="composer-title">创建视频</h2><p>从一个想法，开始一段画面</p></div><span class="subtle-chip">{{ workMode === 'batch' ? '批量' : '标准' }}</span></div>
          <div class="composer-scroll">
            <fieldset class="form-section">
              <legend><span class="step-number">01</span>模型与参数</legend>
              <div class="field"><label for="model-family">生成模型</label><select id="model-family" v-model="form.model_family" name="model_family"><optgroup v-for="group in modelGroups" :key="group.name" :label="group.name"><option v-for="item in group.models" :key="item.value" :value="item.value">{{ item.label }}</option></optgroup></select><span class="field-help">{{ selectedModel?.provider_name }}渠道</span></div>
              <div class="parameter-grid">
                <div class="field"><label for="aspect-ratio">画面比例</label><select id="aspect-ratio" v-model="form.aspect_ratio" name="aspect_ratio"><option v-for="ratio in aspectRatios" :key="ratio" :value="ratio">{{ ratio }}</option></select></div>
                <div class="field"><label for="resolution">分辨率</label><select id="resolution" v-model="form.resolution" name="resolution"><option v-for="item in allowedResolutions" :key="item" :value="item">{{ item }}</option></select></div>
                <div class="field"><label for="seconds">视频时长</label><select id="seconds" v-model="form.seconds" name="seconds"><option v-for="item in secondsOptions" :key="item" :value="item">{{ item }} 秒</option></select></div>
              </div>
              <div v-if="selectedModel?.needs_api_key" class="field"><label for="api-key">渠道 Key</label><input id="api-key" v-model="form.api_key" name="api_key" type="password" autocomplete="current-password" placeholder="填写当前渠道的 Key" /></div>
              <label v-if="supportsAutoFace" class="check-row"><input v-model="form.auto_face" name="auto_face" type="checkbox" />自动人脸处理</label>
            </fieldset>

            <fieldset class="form-section">
              <legend><span class="step-number">02</span>画面描述</legend>
              <div class="mode-row" aria-label="生成模式"><button type="button" :aria-pressed="workMode === 'standard'" :class="{ active: workMode === 'standard' }" @click="setWorkMode('standard')">单个视频</button><button type="button" :aria-pressed="workMode === 'batch'" :class="{ active: workMode === 'batch' }" @click="setWorkMode('batch')">批量生成</button></div>
              <div v-if="workMode === 'batch'" class="batch-row"><label for="batch-count">批量数量</label><select id="batch-count" v-model="batchCount" name="batch_count"><option v-for="num in [2,3,4,5,6,8,10]" :key="num" :value="num">{{ num }} 个</option></select></div>
              <label class="prompt-label" for="prompt">提示词 <span>必填</span></label>
              <textarea id="prompt" v-model="form.prompt" name="prompt" class="prompt-box" rows="5" required :placeholder="workMode === 'batch' ? '输入一条提示词重复生成，或每行一条提示词分别生成…' : '描述主体、动作、场景和镜头运动，例如：模特穿着深蓝牛仔裤缓步走向镜头，自然光，镜头平稳跟随…'" aria-describedby="prompt-help"></textarea>
              <p id="prompt-help" class="field-help">{{ workMode === 'batch' ? '多行提示词将按行创建任务。' : '描述越具体，画面越接近你的想法。' }}</p>
            </fieldset>

            <fieldset class="form-section">
              <legend><span class="step-number">03</span>参考素材 <span class="legend-note">{{ minImages ? '需上传图片' : '可选' }}</span></legend>
              <div class="section-caption"><span>参考图片</span><span>{{ form.images.length }} / {{ maxImages }}</span></div>
              <div v-if="maxImages > 0" class="image-grid" @dragenter.prevent.stop @dragover.prevent.stop @drop.prevent.stop="onImageDrop">
                <div v-for="index in visibleImageCount" :key="index" class="image-slot" :class="{ filled: form.images[index - 1] }">
                  <button type="button" class="image-pick" :aria-label="form.images[index - 1] ? `替换图片 ${index}：${form.images[index - 1].name}` : `上传参考图片 ${index}`" @click="openImagePicker(index - 1)"><img v-if="form.images[index - 1]" :src="previewFileUrl(form.images[index - 1])" :alt="form.images[index - 1].name" width="100" height="100" /><template v-else><StudioIcon name="plus" /><span>图片 {{ index }}</span></template></button>
                  <button v-if="form.images[index - 1]" type="button" class="remove-image" :aria-label="`移除图片 ${index}`" @click="removeImage(index - 1)">×</button>
                </div>
              </div>
              <input ref="filesInput" class="visually-hidden" type="file" name="images" aria-label="参考图片文件" tabindex="-1" accept=".png,.jpg,.jpeg,.webp,.bmp" :multiple="activeImageSlot === null" @change="onFilesChange" />
              <div class="image-grid-actions"><button v-if="maxImages > 0" type="button" class="text-button" @click="openImagePicker()"><StudioIcon name="upload" />选择多张图片</button><button v-if="hasHiddenImageSlots" type="button" class="text-button muted" @click="expandImageSlots">展开其余 {{ maxImages - visibleImageCount }} 个位置</button><button v-if="canCollapseImageSlots" type="button" class="text-button muted" @click="collapseImageSlots">收起空位</button></div>
              <p v-if="supportsReferenceMedia" class="field-help">可直接生成文字视频，也可上传图片作为人物或风格参考。</p>
              <details v-if="supportsReferenceMedia" class="disclosure" :open="referenceMediaExpanded" @toggle="referenceMediaExpanded = $event.target.open"><summary>音频{{ mediaUploadFields.some(f => f.key === 'reference_videos') ? '、视频' : '' }}{{ supportsFrameImages ? '与首尾帧' : '' }}参考<span>可选</span></summary><div class="disclosure-body"><p class="field-help">{{ selectedModel?.reference_media_hint || '选择本地文件，提交时自动上传。' }}</p><div v-for="field in mediaUploadFields" :key="field.key" class="media-field"><label :for="`media-${field.key}`">{{ field.label }} <span>{{ form[field.key].length }}/{{ field.limit }}</span></label><input :id="`media-${field.key}`" :name="field.key" type="file" :accept="field.accept" :multiple="field.limit > 1" @change="onMediaFilesChange($event, field)" /><span class="field-help">单个文件最多 {{ field.maxMB }} MB</span><div v-for="(file, index) in form[field.key]" :key="`${file.name}-${index}`" class="media-file-row"><span :title="file.name">{{ file.name }}</span><button type="button" class="text-button" :aria-label="`移除${field.label} ${file.name}`" @click="form[field.key].splice(index, 1)">移除</button></div></div></div></details>
              <details v-if="selectedModel?.supports_special_options" class="disclosure"><summary>高级生成参数<span>可选</span></summary><div class="disclosure-body"><div class="field"><label for="seed">随机种子（-1 为随机）</label><input id="seed" v-model="form.model_options.seed" name="seed" type="text" inputmode="numeric" /></div><div class="field"><label for="task-type">任务类型</label><select id="task-type" v-model="form.model_options.omni_reference_task_type" name="task_type"><option value="auto">自动判断</option><option value="reference">参考生成</option><option value="extend">视频延长</option></select></div><label class="check-row"><input v-model="form.model_options.generate_audio" type="checkbox" name="generate_audio" />生成音轨</label><label class="check-row"><input v-model="form.model_options.return_last_frame" type="checkbox" name="return_last_frame" />返回尾帧图片</label><div class="field"><label for="tools">工具配置（JSON 数组）</label><textarea id="tools" v-model="form.model_options.tools" name="tools" rows="2" placeholder="[]"></textarea></div></div></details>
            </fieldset>
          </div>
          <div class="composer-footer"><p v-if="errorText" ref="formFeedback" class="form-feedback" tabindex="-1" role="status">{{ errorText }}</p><div class="footer-actions"><button type="button" class="ghost" @click="clearForm">重置</button><button type="submit" class="primary" :disabled="submitting"><StudioIcon :name="submitting ? 'refresh' : 'video'" />{{ submitting ? '提交中…' : workMode === 'batch' ? `生成 ${batchPromptList.length} 个视频` : '生成视频' }}<StudioIcon name="arrow" /></button></div></div>
        </form>

        <section class="result-pane" aria-label="视频结果和任务历史">
          <div class="preview-card">
            <div class="result-heading"><div><h2>预览与结果</h2><p>{{ selectedTask ? selectedTask.model_family : '你的下一段作品，从这里开始' }}</p></div><button type="button" class="ghost small" :disabled="!selectedTask?.download_url" @click="openDownload(selectedTask)"><StudioIcon name="download" />下载视频</button></div>
            <div class="preview-surface"><video v-if="selectedTask?.download_url" :src="selectedTask.download_url" controls preload="metadata"></video><img v-else-if="selectedTask?.image_preview_urls?.[0]" :src="selectedTask.image_preview_urls[0]" alt="任务参考图片" /><div v-else class="preview-placeholder"><div class="empty-film"><StudioIcon name="play" /></div><h3>{{ selectedTask ? formatStatus(selectedTask.status) : '让灵感成为画面' }}</h3><p>{{ selectedTask ? '任务进度与结果会自动更新' : '选择模型，描述画面，开始创作你的第一个视频' }}</p><span v-if="!selectedTask" class="preview-empty-label">AI VIDEO WORKSPACE</span></div></div>
            <div v-if="selectedTask" class="preview-caption"><div class="caption-main"><span class="badge" :class="taskStatusClass(selectedTask.status)">{{ formatStatus(selectedTask.status) }}</span><span>{{ selectedTask.aspect_ratio }} <i>·</i> {{ selectedTask.resolution }} <i>·</i> {{ selectedTask.seconds }} 秒</span><code>{{ selectedTask.display_id }}</code></div><details class="task-details" :open="selectedTask.status === 'failed'"><summary>提示词与运行详情</summary><div class="task-detail-content"><label>提示词</label><p>{{ selectedTask.prompt }}</p><label>任务 ID</label><code>{{ selectedTask.remote_task_id || selectedTask.id }}</code><label>运行日志</label><pre>{{ (selectedTask.logs || []).join('\n') }}</pre><a v-if="selectedTask.last_frame_url" :href="selectedTask.last_frame_url" target="_blank" rel="noopener noreferrer">查看尾帧图片 ↗</a></div></details></div>
          </div>

          <section class="history-card" aria-labelledby="history-heading">
            <div class="history-head"><h2 id="history-heading">任务历史 <span>{{ tasks.length }}</span></h2><button type="button" class="text-button muted" :disabled="!tasks.length" @click="clearHistory">清空历史</button></div>
            <div class="history-filters" aria-label="筛选任务"><button v-for="filter in [{ value: 'all', label: '全部任务' }, { value: 'active', label: '进行中' }, { value: 'completed', label: '已完成' }, { value: 'failed', label: '失败' }]" :key="filter.value" type="button" :aria-pressed="historyFilter === filter.value" :class="{ active: historyFilter === filter.value }" @click="historyFilter = filter.value">{{ filter.label }}</button></div>
            <div class="history-list"><article v-for="task in filteredTasks" :key="task.id" class="history-item" :class="{ selected: task.id === selectedTaskId }"><button type="button" class="history-select" :aria-pressed="task.id === selectedTaskId" @click="selectedTaskId = task.id"><div class="history-thumbnail"><img v-if="task.image_preview_urls?.length" :src="task.image_preview_urls[0]" alt="" width="52" height="52" /><StudioIcon v-else name="video" /></div><div class="history-copy"><h3>{{ task.prompt || task.display_id }}</h3><p>{{ task.model_family }} <i>·</i> {{ task.resolution }} <i>·</i> {{ task.seconds }} 秒</p><div v-if="['queued', 'running'].includes(task.status)" class="mini-progress" role="progressbar" :aria-valuenow="task.progress || 0" aria-valuemin="0" aria-valuemax="100" :aria-label="`${task.display_id} 生成进度`"><div :style="{ width: `${task.progress || 0}%` }"></div></div></div><span class="badge" :class="taskStatusClass(task.status)">{{ formatStatus(task.status) }}</span></button><div class="history-actions"><button type="button" class="text-button" :disabled="reusingTaskId === task.id" @click="reuseTaskConfig(task)">{{ reusingTaskId === task.id ? '复用中…' : '复用' }}</button><button type="button" class="text-button" :disabled="rerunningTaskId === task.id" @click="rerunTask(task)">{{ rerunningTaskId === task.id ? '提交中…' : '重试' }}</button><button type="button" class="icon-button" aria-label="下载该视频" :disabled="!task.download_url" @click="openDownload(task)"><StudioIcon name="download" /></button></div></article><div v-if="!filteredTasks.length" class="history-empty"><StudioIcon name="clock" /><strong>{{ tasks.length ? '暂无此类任务' : '还没有生成记录' }}</strong><span>{{ tasks.length ? '切换筛选查看其他任务' : '提交后可以在这里查看进度、复用和下载' }}</span></div></div>
          </section>
        </section>
      </div>
    </main>
  </div>
</template>
