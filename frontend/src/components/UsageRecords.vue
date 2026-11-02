<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

const filters = reactive({ provider: 'kyy', key: '', start: '', end: '' })
const records = ref([])
const providers = ref([])
const summary = ref({})
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const pageSize = 50
let timer
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const dateText = value => new Date(value * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
const secondsText = value => value == null ? '未返回' : `${Number(value)} 秒`

function statusText(record) {
  const generated = ['completed', 'success', 'succeeded', 'done'].includes(record.provider_status)
  if (generated && record.status === 'failed') return '上游已生成，本地失败'
  return ({ queued: '等待中', running: '处理中', completed: '完成', failed: '失败' })[record.status] || record.status
}

async function load(reset = false) {
  if (loading.value) return
  if (reset) page.value = 1
  loading.value = true
  error.value = ''
  try {
    const query = new URLSearchParams({ ...filters, page: String(page.value), page_size: String(pageSize) })
    const response = await fetch(`/api/usage?${query}`, { cache: 'no-store' })
    const data = await response.json()
    if (!response.ok) throw new Error(data.error || '用量记录加载失败')
    records.value = data.records
    providers.value = data.providers
    summary.value = data.summary
    total.value = data.total
  } catch (e) {
    error.value = e.message || '用量记录加载失败'
  } finally {
    loading.value = false
  }
}

function changePage(delta) {
  page.value += delta
  load()
}

onMounted(() => { load(); timer = setInterval(() => load(), 15000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section class="usage-panel">
    <div class="usage-heading">
      <div><h2>生成用量记录</h2><p>保留 3 个月，视频文件清理后记录仍会保留。Key 默认脱敏显示。</p></div>
      <button class="ghost small" :disabled="loading" @click="load()">{{ loading ? '加载中…' : '刷新' }}</button>
    </div>
    <form class="usage-filters" @submit.prevent="load(true)">
      <label>渠道<select v-model="filters.provider"><option value="kyy">客易云</option><option value="">全部渠道</option><option v-for="p in providers.filter(p => p.provider !== 'kyy')" :key="p.provider" :value="p.provider">{{ p.provider_name }}</option></select></label>
      <label>Key<input v-model="filters.key" placeholder="搜索 Key 前缀或后缀" /></label>
      <label>开始日期<input v-model="filters.start" type="date" /></label>
      <label>结束日期<input v-model="filters.end" type="date" /></label>
      <button type="submit" class="primary" :disabled="loading">查询</button>
    </form>
    <div class="usage-summary">
      <div><span>生成记录</span><strong>{{ total }} 条</strong></div>
      <div><span>已生成视频</span><strong>{{ summary.generated_count || 0 }} 个 · {{ Number(summary.generated_seconds || 0) }} 秒</strong></div>
      <div><span>渠道已返回费用合计</span><strong v-if="summary.cost_totals?.length">{{ summary.cost_totals.map(t => `${t.amount} ${t.unit}`).join(' / ') }}</strong><strong v-else>未返回</strong><small>有费用 {{ summary.with_cost || 0 }} 条 · 未返回 {{ summary.without_cost || 0 }} 条</small></div>
    </div>
    <p class="usage-note">视频总秒数优先使用渠道返回的实际时长，未返回时按设定时长统计；费用仅记录渠道实际返回值，不同单位分别汇总。</p>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="usage-table-wrap">
      <table class="usage-table">
        <thead><tr><th>提交时间</th><th>渠道 / 模型</th><th>使用的 Key</th><th>设定秒数</th><th>实际秒数</th><th>费用消耗</th><th>状态</th><th>任务 ID</th></tr></thead>
        <tbody>
          <tr v-for="record in records" :key="record.task_id">
            <td :title="`记录保留至 ${dateText(record.expires_ts)}`">{{ dateText(record.created_ts) }}</td>
            <td>{{ record.provider_name }}<small>{{ record.model }}</small></td>
            <td><code>{{ record.key_label }}</code></td>
            <td>{{ secondsText(record.requested_seconds) }}</td>
            <td>{{ secondsText(record.actual_seconds) }}</td>
            <td>{{ record.cost_amount == null ? '未返回' : `${record.cost_amount} ${record.cost_unit}` }}</td>
            <td>{{ statusText(record) }}</td>
            <td><code :title="record.remote_task_id">{{ record.remote_task_id || record.task_id }}</code></td>
          </tr>
          <tr v-if="!records.length"><td colspan="8" class="usage-empty">{{ loading ? '正在加载记录…' : '当前筛选条件下暂无记录，新提交任务会自动记录。' }}</td></tr>
        </tbody>
      </table>
    </div>
    <div class="usage-pagination"><span>共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页</span><button class="ghost small" :disabled="loading || page <= 1" @click="changePage(-1)">上一页</button><button class="ghost small" :disabled="loading || page >= pages" @click="changePage(1)">下一页</button></div>
  </section>
</template>

<style scoped>
.usage-panel { margin-top: 10px; height: calc(100vh - 82px); overflow: auto; border: 1px solid #30313b; border-radius: 14px; background: #1a1a20; padding: 20px; }
.usage-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
h2 { margin: 0; font-size: 20px; }
p, .usage-note, small { color: #a6a7b7; }
.usage-heading p { margin: 8px 0 18px; }
.usage-filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }
.usage-filters label { display: grid; gap: 6px; font-size: 12px; min-width: 150px; }
.usage-filters input, .usage-filters select { min-height: 36px; border: 1px solid #363848; background: #101117; border-radius: 9px; color: #f4f4f7; padding: 8px 10px; }
.usage-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }
.usage-summary > div { border: 1px solid #333541; border-radius: 12px; padding: 16px; background: #23232d; display: grid; gap: 8px; }
.usage-summary span { color: #a6a7b7; font-size: 12px; }
.usage-summary strong { font-size: 19px; overflow-wrap: anywhere; }
.usage-note { font-size: 12px; margin: 14px 0; }
.usage-table-wrap { overflow: auto; border: 1px solid #333541; border-radius: 10px; }
.usage-table { border-collapse: collapse; width: 100%; min-width: 1000px; font-size: 12px; }
th { color: #b7b8c6; background: #24252e; font-weight: 600; text-align: left; white-space: nowrap; }
th, td { padding: 12px; border-bottom: 1px solid #30313d; }
td { vertical-align: top; }
td small { display: block; margin-top: 5px; }
td:last-child code { display: block; max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.usage-empty { padding: 50px 20px; text-align: center; color: #a6a7b7; }
.usage-pagination { display: flex; gap: 10px; align-items: center; justify-content: flex-end; margin-top: 16px; font-size: 12px; }
.usage-pagination span { margin-right: auto; color: #a6a7b7; }
@media (max-width: 700px) { .usage-panel { padding: 12px; } .usage-summary { grid-template-columns: 1fr; } .usage-filters label { flex: 1; min-width: 130px; } }
</style>
