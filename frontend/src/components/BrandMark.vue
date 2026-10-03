<template>
  <div class="brand-mark" :class="{ compact }" aria-hidden="true">
    <span>筑</span><i></i>
  </div>
</template>

<script setup>
defineProps({ compact: Boolean })
</script>

<style scoped>
.brand-mark { position: relative; display: grid; place-items: center; flex: 0 0 auto; width: 52px; height: 52px; overflow: hidden; border-radius: 15px; color: white; background: linear-gradient(145deg, #326be4, #1a48b8); box-shadow: 0 10px 24px rgba(18, 62, 163, .28); }
.brand-mark::before { content: ""; position: absolute; inset: 7px; border: 1px solid rgba(255,255,255,.2); border-radius: 10px; }
.brand-mark span { z-index: 1; font-size: 25px; line-height: 1; font-weight: 850; letter-spacing: -.08em; transform: translateX(-1px); }
.brand-mark i { position: absolute; right: -7px; bottom: -9px; width: 29px; height: 29px; border: 7px solid #f5a817; border-radius: 50%; opacity: .95; }
.brand-mark.compact { width: 42px; height: 42px; border-radius: 12px; box-shadow: 0 8px 18px rgba(5, 17, 42, .24); }
.brand-mark.compact span { font-size: 21px; }
.brand-mark.compact i { width: 24px; height: 24px; border-width: 6px; }
</style>
