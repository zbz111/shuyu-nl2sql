<template>
  <div class="query-page">
    <div class="ask card">
      <el-input
        v-model="question"
        type="textarea"
        :rows="2"
        resize="none"
        placeholder="用一句话提问，例如：每天的销售额走势如何？1 号为什么比 5 号卖得多？"
        @keydown.enter.exact.prevent="ask"
      />
      <div class="ask-bar">
        <div class="chips">
          <span v-for="q in samples" :key="q" class="chip" @click="quick(q)">{{ q }}</span>
        </div>
        <el-button type="primary" :loading="loading" :disabled="!canAsk" @click="ask">分析</el-button>
      </div>
    </div>

    <div v-if="!items.length" class="empty card">
      <el-icon :size="28"><TrendCharts /></el-icon>
      <div class="empty-title">问一句，自动生成 SQL、出图，并给出分析</div>
      <div class="page-sub">数字由系统计算，结论可追溯到具体行</div>
    </div>

    <div v-for="(item, idx) in items" :key="idx" class="result card">
      <div class="q-line">
        <div class="q-text">{{ item.question }}</div>
        <div class="q-meta">
          <el-tag size="small" :type="statusType(item)" effect="light">{{ statusText(item) }}</el-tag>
          <span>{{ item.latency_ms }}ms</span>
          <span v-if="item.retries">自动修正 {{ item.retries }} 次</span>
        </div>
      </div>

      <div class="sql-box">
        <div class="sql-head">
          <span class="sql-title">SQL</span>
          <div class="sql-actions">
            <el-button text size="small" @click="item.editing = !item.editing">{{ item.editing ? '收起' : '编辑' }}</el-button>
            <el-button text size="small" @click="copySql(item.sql)">复制</el-button>
            <el-button text size="small" type="primary" :loading="item.running" @click="runSql(item)">执行</el-button>
          </div>
        </div>
        <el-input v-if="item.editing" v-model="item.sql" type="textarea" :rows="4" class="mono" />
        <pre v-else class="sql-code mono">{{ item.sql }}</pre>
      </div>

      <el-alert v-if="item.error" :title="item.error" type="error" :closable="false" show-icon class="err" />

      <div v-if="item.status === 'ok'">
        <div v-if="item.insight_summary" class="insight-hero">
          <el-icon><MagicStick /></el-icon>
          <span>{{ item.insight_summary }}</span>
        </div>

        <el-tabs v-model="item.tab" @tab-change="() => renderChart(item)">
          <el-tab-pane label="图表" name="chart">
            <div :ref="(el) => setChartRef(el, idx)" class="chart"></div>
            <div v-if="!item.chart" class="page-sub center">这个结果不适合画图（需要至少一列类别/时间 + 一列数值）</div>
          </el-tab-pane>

          <el-tab-pane label="分析" name="insight">
            <div v-if="item.insights?.length" class="fact-list">
              <div v-for="(f, i) in item.insights" :key="i" class="fact">
                <el-tag size="small" effect="plain" class="fact-tag">{{ f.title }}</el-tag>
                <span class="fact-text">{{ f.text }}</span>
              </div>
            </div>
            <div v-if="item.hypotheses?.length" class="hypo">
              <div class="hypo-title">可能的影响因素（推测，需业务确认）</div>
              <ul>
                <li v-for="(h, i) in item.hypotheses" :key="i">{{ h }}</li>
              </ul>
            </div>
            <div v-if="!item.insights?.length && !item.hypotheses?.length" class="page-sub">
              暂无结构化结论，可看表格或图表。
            </div>
          </el-tab-pane>

          <el-tab-pane label="表格" name="table">
            <el-table :data="item.tableData" size="small" max-height="420" border>
              <el-table-column v-for="c in item.columns" :key="c" :prop="c" :label="c" min-width="120" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>
        </el-tabs>

        <div class="foot-meta">共 {{ item.row_count }} 行<span v-if="item.row_count >= 200">（已截断展示）</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import api, { errorMessage } from '../api'

const props = defineProps({
  datasources: { type: Array, default: () => [] },
  currentDs: { type: Number, default: null }
})

const question = ref('')
const loading = ref(false)
const items = ref([])
const charts = {}

const samples = ['每天的销售额走势如何？', '1 号为什么比 5 号卖得多？', '每个品类的销售额是多少？', '8 月比 7 月卖得好吗？']

const canAsk = computed(() => question.value.trim() && props.currentDs)
const dsId = computed(() => props.currentDs)

function quick(q) {
  question.value = q
  ask()
}

function blank(questionText) {
  return {
    question: questionText,
    sql: '',
    status: 'pending',
    columns: [],
    rows: [],
    row_count: 0,
    latency_ms: 0,
    error: '',
    retries: 0,
    narration: '',
    insight_summary: '',
    insights: [],
    hypotheses: [],
    chart: null,
    tab: 'chart',
    editing: false,
    running: false
  }
}

function toTable(data) {
  return (data.rows || []).map((r) => Object.fromEntries(data.columns.map((c, i) => [c, r[i]])))
}

function applyResult(item, data) {
  Object.assign(item, data)
  item.tableData = toTable(data)
  if (!data.chart) item.tab = data.insights?.length ? 'insight' : 'table'
  nextTick(() => renderChart(item))
}

async function ask() {
  if (!canAsk.value) {
    if (!props.currentDs) ElMessage.warning('请先在左侧选择数据源')
    return
  }
  loading.value = true
  const item = blank(question.value.trim())
  items.value.push(item)
  question.value = ''
  try {
    const { data } = await api.post('/query', { datasource_id: dsId.value, question: item.question })
    applyResult(item, data)
  } catch (e) {
    item.status = 'error'
    item.error = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function runSql(item) {
  item.running = true
  try {
    const { data } = await api.post('/query/execute', { datasource_id: dsId.value, sql: item.sql })
    applyResult(item, data)
  } catch (e) {
    item.error = errorMessage(e)
  } finally {
    item.running = false
  }
}

function setChartRef(el, idx) {
  if (el) charts[idx] = el
}

function renderChart(item) {
  const idx = items.value.indexOf(item)
  if (item.tab !== 'chart') return
  nextTick(() => {
    const el = charts[idx]
    if (!el) return
    const inst = echarts.getInstanceByDom(el) || echarts.init(el)
    const spec = item.chart
    if (!spec) {
      inst.clear()
      return
    }

    let labels = spec.labels
    let values = spec.values
    if (!labels || !values) {
      const xIdx = item.columns.indexOf(spec.x)
      const yIdx = item.columns.indexOf(spec.y)
      if (xIdx < 0 || yIdx < 0) return
      labels = item.rows.map((r) => r[xIdx])
      values = item.rows.map((r) => r[yIdx])
    }

    // 峰值/谷值用 ECharts 内置的 max/min，自动定位，不依赖 valueIndex
    const seriesType = spec.type === 'line' ? 'line' : 'bar'
    const markPoint = {
      symbolSize: 46,
      label: { fontSize: 10, formatter: (p) => p.name },
      data: [
        { type: 'max', name: '峰值', itemStyle: { color: '#f56c6c' } },
        { type: 'min', name: '谷值', itemStyle: { color: '#909399' } }
      ]
    }

    inst.setOption(
      {
        tooltip: { trigger: 'axis', axisPointer: { type: seriesType === 'bar' ? 'shadow' : 'line' } },
        grid: { left: 70, right: 30, top: 40, bottom: 50 },
        xAxis: {
          type: 'category',
          data: labels,
          boundaryGap: seriesType === 'bar',
          axisLabel: { rotate: labels.length > 12 ? 40 : 0, fontSize: 11, interval: 0 }
        },
        yAxis: { type: 'value', axisLabel: { fontSize: 11 } },
        series: [
          {
            type: seriesType,
            data: values.map((v) => (v === null || v === undefined ? 0 : Number(v))),
            smooth: seriesType === 'line',
            symbolSize: 5,
            showSymbol: labels.length <= 40,
            lineStyle: seriesType === 'line' ? { width: 2 } : undefined,
            barMaxWidth: 48,
            itemStyle: seriesType === 'bar' ? { borderRadius: [5, 5, 0, 0], color: '#6366f1' } : { color: '#6366f1' },
            markPoint
          }
        ]
      },
      true
    )
    inst.resize()
  })
}

function statusText(item) {
  if (item.status === 'ok') return '成功'
  if (item.status === 'blocked') return '已拦截'
  if (item.status === 'error') return '失败'
  return '分析中'
}

function statusType(item) {
  if (item.status === 'ok') return 'success'
  if (item.status === 'blocked') return 'warning'
  if (item.status === 'error') return 'danger'
  return 'info'
}

async function copySql(sql) {
  try {
    await navigator.clipboard.writeText(sql)
    ElMessage.success('SQL 已复制')
  } catch {
    ElMessage.warning('浏览器不支持复制')
  }
}

watch(
  () => props.currentDs,
  () => {
    items.value = []
  }
)
</script>

<style scoped>
.query-page { display: flex; flex-direction: column; gap: 16px; max-width: 1180px; }
.ask { padding: 14px 16px; }
.ask :deep(.el-textarea__inner) { background: transparent; box-shadow: none; font-size: 14.5px; padding: 6px 4px; }
.ask-bar { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; gap: 12px; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; }
.chip {
  font-size: 12px; color: var(--muted); border: 1px solid var(--border); background: var(--surface-2);
  padding: 4px 10px; border-radius: 999px; cursor: pointer; transition: all 0.15s;
}
.chip:hover { color: var(--primary); border-color: var(--primary); }
.empty { padding: 56px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.empty-title { font-size: 16px; font-weight: 600; }
.result { padding: 16px 18px; }
.q-line { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.q-text { font-weight: 600; font-size: 14.5px; }
.q-meta { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--muted); }

.insight-hero {
  margin: 12px 0; padding: 12px 14px; border-radius: 10px;
  background: var(--primary-soft); color: var(--primary);
  display: flex; align-items: flex-start; gap: 8px; font-size: 13.5px; line-height: 1.7;
}
.sql-box { background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; margin: 10px 0; }
.sql-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.sql-title { font-size: 11px; letter-spacing: 1px; color: var(--muted); font-weight: 600; }
.sql-actions { display: flex; gap: 2px; }
.sql-code { margin: 0; font-size: 12.5px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.err { margin: 10px 0; }
.chart { height: 340px; width: 100%; }
.center { text-align: center; padding: 18px; }
.foot-meta { font-size: 11.5px; color: var(--muted); margin-top: 6px; }

.fact-list { display: flex; flex-direction: column; gap: 8px; }
.fact { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; line-height: 1.7; }
.fact-tag { flex: 0 0 auto; margin-top: 1px; }
.fact-text { color: var(--text); }
.hypo { margin-top: 14px; padding: 12px 14px; border-radius: 10px; background: var(--surface-2); border: 1px dashed var(--border); }
.hypo-title { font-size: 12.5px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
.hypo ul { margin: 0; padding-left: 18px; }
.hypo li { font-size: 12.5px; line-height: 1.8; color: var(--text); }
</style>