<script setup lang="ts">
import { displayTheme, displayDensity, reducedMotion, saveDisplay } from '../design/preferences'
</script>
<template>
  <div class="view"><div class="page-heading"><div><h1>显示偏好</h1><p class="page-intro">调整当前浏览器的工作空间。</p></div></div>
    <section class="content-card" aria-label="显示设置">
      <div class="preference-row"><div><label for="display-theme"><strong>外观</strong></label><p>主题只影响界面，不改变 CT 灰阶和响应图颜色。</p></div><select id="display-theme" v-model="displayTheme" @change="saveDisplay"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></div>
      <div class="preference-row"><div><label for="display-density"><strong>信息密度</strong></label><p>调整病例和任务列表的行高。</p></div><select id="display-density" v-model="displayDensity" @change="saveDisplay"><option value="compact">紧凑</option><option value="standard">标准</option><option value="comfortable">舒适</option></select></div>
      <div class="preference-row"><div><label for="display-motion"><strong>减少动态效果</strong></label><p>系统已开启减少动态时，始终尊重系统设置。</p></div><input id="display-motion" v-model="reducedMotion" type="checkbox" @change="saveDisplay" /></div>
    </section>
    <p class="board-note">仅保存外观、密度和动态偏好。病例、影像、账号信息与任务记录不会存入这些设置。</p>
  </div>
</template>
