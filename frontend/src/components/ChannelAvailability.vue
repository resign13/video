<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const providers = ref([])
const selectedProvider = ref('kyy')
const keyword = ref('')
const loading = ref(false)
const error = ref('')
let timer
const dateText = value => value ? new Date(value * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '尚未获取'
const statusText = row => ({ available: '可用', unavailable: '维护中', listed: '官方在列', unknown: '未知' })[row.status] || '未知'
const statusTitle = value => ({ SUCCESS: '成功', SUCCEEDED: '成功', FAILED: '失败', FAILURE: '失败' })[value] || value
const visibleProviders = computed(() => providers.value.filter(p => !selectedProvider.value || p.id === selectedProvider.value))
const rows = computed(() => visibleProviders.value.flatMap(provider => provider.records.map(row => ({ ...row, provider }))).filter(row => {
  const query = keyword.value.trim().toLowerCase()
  return !query || [row.model, row.group, row.variant, row.description].join(' ').toLowerCase().includes(query)
}))

async function load(force = false) {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(`/api/channel-availability${force ? '?refresh=1' : ''}`, { cache: 'no-store' })
    if (!response.ok) throw new Error('渠道可用性加载失败')
    providers.value = (await response.json()).providers
  } catch (e) {
    error.value = e.message || '渠道可用性加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => { load(); timer = setInterval(() => load(), 300000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section class="data-panel availability-panel">
    <div class="availability-heading">
      <div><h2>官方渠道状态</h2><p>客易云仅展示视频模型；按官方规格分别展示，每 5 分钟更新。</p></div>
      <button class="ghost small" :disabled="loading" @click="load(true)">{{ loading ? '更新中…' : '刷新状态' }}</button>
    </div>
    <search class="availability-filters">
      <label for="availability-provider">渠道<select id="availability-provider" v-model="selectedProvider" name="provider"><option value="kyy">客易云 · 视频</option><option value="meaicc">MEAICC</option><option value="">全部</option></select></label>
      <label for="availability-keyword" class="availability-search">搜索模型 / 规格<input id="availability-keyword" v-model="keyword" name="keyword" type="search" autocorrect="off" autocapitalize="none" :spellcheck="false" placeholder="例如 sd_2.5_special、720p、有参考视频" /></label>
      <span>共 {{ rows.length }} 个规格</span>
    </search>
    <div class="availability-sources">
      <div v-for="provider in visibleProviders" :key="provider.id" :class="{ stale: provider.stale }">
        <a :href="provider.source_url" target="_blank" rel="noopener noreferrer">{{ provider.name }}官方页面 ↗</a>
        <span v-if="provider.tier_name"> · {{ provider.tier_name }}视图</span>
        <span> · 数据更新 {{ dateText(provider.last_success_at) }}</span>
        <strong v-if="provider.stale"> · {{ provider.error }}{{ provider.records.length ? '，以下为上次数据' : '，当前状态未知' }}</strong>
      </div>
    </div>
    <p class="availability-note">成功率仅显示官方接口返回值，缺失时标为“未提供”。MEAICC“官方在列”表示目录收录；历史成功率供参考。</p>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="availability-table-wrap">
      <table>
        <thead><tr><th scope="col">渠道 / 模型</th><th scope="col">规格 / 说明</th><th scope="col">官方状态</th><th scope="col">成功率</th><th scope="col">平均耗时</th><th scope="col">最近生成结果</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="`${row.provider.id}:${row.id}`">
            <td><strong>{{ row.model }}</strong><small>{{ row.provider.name }} · {{ row.group }}</small></td>
            <td><span>{{ row.variant || '—' }}</span><small>{{ row.description }}</small></td>
            <td><span class="availability-badge" :class="row.provider.stale ? 'unknown' : row.status">{{ row.provider.stale ? '上次：' : '' }}{{ statusText(row) }}</span></td>
            <td><strong :class="row.success_rate != null && row.success_rate < 60 ? 'low-rate' : ''">{{ row.success_rate == null ? '未提供' : `${row.success_rate}%` }}</strong><small v-if="row.success_rate != null">{{ row.window }}{{ row.sample_count != null ? ` · ${row.sample_count} 个样本` : '' }}</small></td>
            <td>{{ row.avg_duration_seconds == null ? '未提供' : `${Math.round(row.avg_duration_seconds)} 秒` }}</td>
            <td><div v-if="row.recent_statuses.length" class="recent-results" :aria-label="row.recent_statuses.map(statusTitle).join('、')"><span v-for="(status, index) in row.recent_statuses" :key="index" :title="statusTitle(status)" :class="['SUCCESS', 'SUCCEEDED'].includes(status) ? 'success' : ['FAILED', 'FAILURE'].includes(status) ? 'failed' : 'unknown'"></span></div><span v-else>未提供</span></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="6" class="empty">{{ loading ? '正在获取官方渠道数据…' : '暂无符合条件的数据' }}</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.availability-panel { }
.availability-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
h2 { margin: 0; font-size: 20px; }
p, small, .availability-filters > span, .availability-sources { color: var(--muted); }
.availability-heading p { margin: 8px 0 18px; }
.availability-filters { display: flex; flex-wrap: wrap; gap: 14px; align-items: end; }
label { display: grid; gap: 6px; font-size: 12px; min-width: 170px; }
.availability-search { flex: 1; }
input, select { min-height: 48px; border: 1px solid #8994a8; background: var(--surface); border-radius: 9px; color: var(--text); padding: 8px 10px; width: 100%; }
.availability-filters > span { padding-bottom: 11px; font-size: 12px; }
.availability-sources { margin-top: 18px; font-size: 12px; display: grid; gap: 8px; }
a { color: var(--accent); }
.stale strong { color: #98681d; }
.availability-note { font-size: 12px; line-height: 1.6; }
.availability-table-wrap { overflow: auto; border: 1px solid var(--border); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; min-width: 950px; font-size: 12px; }
th { color: var(--muted); background: var(--soft); text-align: left; white-space: nowrap; }
th, td { padding: 14px 12px; border-bottom: 1px solid var(--border); }
td { vertical-align: top; }
td:first-child { min-width: 230px; }
td:nth-child(2) { max-width: 440px; line-height: 1.7; }
td:nth-child(n+3) { white-space: nowrap; }
small { display: block; margin-top: 5px; font-size: 11px; }
.availability-badge { display: inline-block; padding: 4px 8px; border-radius: 6px; background: #eef0f4; color: var(--muted); }
.available, .listed { color: #167d59; background: #eaf6ef; }
.unavailable { color: #b5404c; background: #fcecef; }
.low-rate { color: #b5404c; }
.recent-results { display: flex; gap: 3px; margin-top: 4px; }
.recent-results span { height: 15px; width: 6px; border-radius: 2px; background: #777b89; }
.recent-results .success { background: #45cf98; }
.recent-results .failed { background: #f67b85; }
.empty { padding: 50px 20px; text-align: center; color: var(--muted); }
@media (max-width: 700px) { .availability-panel { padding: 12px; } .availability-heading { align-items: start; } label { min-width: 130px; } .availability-search { min-width: 200px; } }
</style>
