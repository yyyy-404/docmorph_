<script setup lang="ts">
import { useAppStore } from '@/stores/app'

const store = useAppStore()

function onSource(event: Event) {
  store.onSourceChange((event.target as HTMLSelectElement).value)
}

function onTarget(event: Event) {
  store.targetFormat = (event.target as HTMLSelectElement).value
}
</script>

<template>
  <div class="row">
    <span class="label">源格式</span>
    <select class="grow" :value="store.sourceFormat" @change="onSource">
      <option v-for="entry in store.catalog" :key="entry.source" :value="entry.source">
        {{ entry.source }}
      </option>
    </select>
    <span class="label">→ 目标格式</span>
    <select class="grow" :value="store.targetFormat" @change="onTarget">
      <option
        v-for="option in store.targetOptions"
        :key="option.target"
        :value="option.target"
        :disabled="!option.available"
        :title="option.available ? '' : option.reason"
      >
        {{ option.target }}{{ option.available ? '' : '（引擎不可用）' }}
      </option>
    </select>
  </div>
  <div
    v-if="store.targetOptions.some((item) => !item.available)"
    class="note muted"
  >
    {{
      store.targetOptions.find((item) => item.target === store.targetFormat && !item.available)
        ?.reason || '灰显格式当前环境缺少转换引擎，可运行 doctor 查看安装建议。'
    }}
  </div>
</template>

<style scoped>
select {
  min-width: 0;
}

.note {
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.5;
}
</style>
