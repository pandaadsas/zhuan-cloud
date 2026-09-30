<template>
  <section class="auth-scene">
    <div class="scene-art" aria-hidden="true">
      <svg viewBox="0 0 760 680" preserveAspectRatio="xMidYMid meet">
        <g class="blueprint blueprint-back">
          <path d="M62 594H704M118 594V332H276V594M276 594V238H432V594M432 594V304H612V594" />
          <path d="M142 370H248M142 416H248M142 462H248M142 508H248M302 282H406M302 336H406M302 390H406M302 444H406M302 498H406M462 350H582M462 404H582M462 458H582M462 512H582" />
          <path d="M276 238L354 180L432 238M432 304L522 250L612 304M118 332L197 286L276 332" />
        </g>
        <g class="blueprint blueprint-front">
          <path d="M86 594L86 312L268 312L268 594M268 594V210L456 210V594M456 594V284L648 284V594" />
          <path d="M86 312L177 258L268 312M268 210L362 142L456 210M456 284L552 222L648 284" />
          <path d="M362 142V94M338 118H386" />
        </g>
        <path class="signal-path" d="M80 520C176 470 205 528 280 438S420 328 498 382S622 380 692 276" />
        <g class="measure-lines">
          <path d="M54 616H696M54 606V626M696 606V626" />
          <path d="M680 144V594M670 144H690M670 594H690" />
        </g>
      </svg>
      <div class="scan-line"></div>
      <span class="data-node node-1"></span>
      <span class="data-node node-2"></span>
      <span class="data-node node-3"></span>
      <span class="data-node node-4"></span>
      <span class="data-node node-5"></span>
    </div>

    <div class="scene-content">
      <div class="scene-brand">
        <BrandMark />
        <div><strong>筑安云</strong><span>工地安全 · 智安协同平台</span></div>
      </div>
      <div class="scene-copy">
        <span class="scene-kicker">SMART SAFETY COLLABORATION</span>
        <h1>让每一次隐患，<br><em>都有清晰的闭环。</em></h1>
        <p>把案头交给 AI，把安全留给现场。从发现问题到整改复查，让现场处置更快一步。</p>
        <div class="scene-flow" aria-label="隐患处置流程">
          <template v-for="(item, index) in flow" :key="item">
            <span><i>{{ index + 1 }}</i>{{ item }}</span>
            <b v-if="index < flow.length - 1"></b>
          </template>
        </div>
      </div>
      <div class="scene-foot"><span></span>AI 引擎与项目数据协同在线</div>
    </div>
  </section>
</template>

<script setup>
import BrandMark from './BrandMark.vue'

const flow = ['上报', '分析', '派单', '闭环']
</script>

<style scoped>
.auth-scene { position: relative; z-index: 1; width: min(620px, 48vw); min-height: 600px; color: #fff; }
.scene-art { position: absolute; inset: 0 -7% 0 -5%; overflow: hidden; pointer-events: none; }
.scene-art::before { content: ""; position: absolute; inset: 12% 8% 6%; border-radius: 50%; background: radial-gradient(circle, rgba(38,96,218,.22), transparent 65%); filter: blur(12px); animation: halo-breathe 14s ease-in-out infinite alternate; }
svg { position: absolute; inset: 5% 0 0; width: 100%; height: 94%; overflow: visible; }
.blueprint { fill: none; stroke-linecap: round; stroke-linejoin: round; }
.blueprint-back { stroke: rgba(127,163,225,.13); stroke-width: 1; }
.blueprint-front { stroke: rgba(135,176,244,.28); stroke-width: 1.4; stroke-dasharray: 1180; stroke-dashoffset: 1180; animation: draw-blueprint 2.2s .25s ease-out forwards, blueprint-breathe 12s 2.5s ease-in-out infinite; }
.signal-path { fill: none; stroke: rgba(245,158,11,.58); stroke-width: 2; stroke-linecap: round; stroke-dasharray: 7 12; animation: signal-flow 12s linear infinite; }
.measure-lines { fill: none; stroke: rgba(135,176,244,.18); stroke-width: 1; stroke-dasharray: 4 8; }
.scan-line { position: absolute; left: 8%; right: 4%; top: 20%; height: 1px; background: linear-gradient(90deg, transparent, rgba(80,145,255,.75), rgba(245,158,11,.55), transparent); box-shadow: 0 0 18px rgba(62,126,235,.55); animation: scan-building 16s ease-in-out infinite; }
.data-node { position: absolute; width: 8px; height: 8px; border: 1px solid rgba(255,190,75,.9); border-radius: 50%; background: #f5a817; box-shadow: 0 0 0 0 rgba(245,168,23,.36); animation: node-pulse 3.6s ease-out infinite; }
.data-node::after { content: ""; position: absolute; inset: -5px; border: 1px solid rgba(245,168,23,.2); border-radius: inherit; }
.node-1 { left: 17%; top: 55%; animation-delay: .2s; }
.node-2 { left: 37%; top: 42%; animation-delay: 1.1s; }
.node-3 { left: 51%; top: 29%; animation-delay: 2.2s; }
.node-4 { left: 67%; top: 48%; animation-delay: 1.7s; }
.node-5 { left: 84%; top: 35%; animation-delay: 2.8s; }
.scene-content { position: relative; z-index: 2; display: flex; flex-direction: column; min-height: 600px; padding: 22px 0 20px; }
.scene-brand { display: flex; align-items: center; gap: 13px; opacity: 0; animation: scene-in .55s .05s ease-out forwards; }
.scene-brand strong, .scene-brand span { display: block; }
.scene-brand strong { font-size: 22px; letter-spacing: .06em; }
.scene-brand span { margin-top: 3px; color: #9db0d3; font-size: 11px; letter-spacing: .05em; }
.scene-copy { width: min(520px, 90%); margin: auto 0; padding-bottom: 10px; opacity: 0; animation: scene-in .6s .16s ease-out forwards; }
.scene-kicker { display: block; margin-bottom: 18px; color: #f6b83f; font-size: 10px; font-weight: 750; letter-spacing: .16em; }
h1 { margin: 0; font-size: clamp(34px, 4vw, 52px); line-height: 1.24; font-weight: 760; letter-spacing: -.035em; text-shadow: 0 12px 36px rgba(0,0,0,.2); }
h1 em { color: #b7cbf1; font-style: normal; }
p { max-width: 460px; margin: 20px 0 28px; color: #aebedd; font-size: 14px; line-height: 1.85; }
.scene-flow { display: flex; align-items: center; }
.scene-flow span { display: flex; align-items: center; gap: 7px; color: #d7e2f6; font-size: 12px; white-space: nowrap; }
.scene-flow i { display: grid; place-items: center; width: 25px; height: 25px; border: 1px solid rgba(161,190,239,.35); border-radius: 8px; color: #f4b43a; background: rgba(22,55,113,.5); font-size: 10px; font-style: normal; }
.scene-flow b { width: clamp(18px, 3vw, 38px); height: 1px; margin: 0 8px; overflow: hidden; background: rgba(139,169,220,.24); }
.scene-flow b::after { content: ""; display: block; width: 40%; height: 100%; background: #4f8af1; animation: flow-line 2.6s ease-in-out infinite; }
.scene-foot { display: flex; align-items: center; gap: 8px; color: #7188af; font-size: 10px; opacity: 0; animation: scene-in .55s .3s ease-out forwards; }
.scene-foot span { width: 6px; height: 6px; border-radius: 50%; background: #43c889; box-shadow: 0 0 0 5px rgba(67,200,137,.08); }
@keyframes scene-in { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes draw-blueprint { to { stroke-dashoffset: 0; } }
@keyframes blueprint-breathe { 0%, 100% { opacity: .72; } 50% { opacity: 1; } }
@keyframes signal-flow { to { stroke-dashoffset: -190; } }
@keyframes scan-building { 0%, 12% { transform: translateY(-90px); opacity: 0; } 25%, 70% { opacity: .65; } 88%, 100% { transform: translateY(390px); opacity: 0; } }
@keyframes node-pulse { 0% { box-shadow: 0 0 0 0 rgba(245,168,23,.42); } 55%, 100% { box-shadow: 0 0 0 14px rgba(245,168,23,0); } }
@keyframes flow-line { 0% { transform: translateX(-120%); } 100% { transform: translateX(350%); } }
@keyframes halo-breathe { to { opacity: .6; transform: scale(1.08); } }
@media (max-width: 900px) { .auth-scene { display: none; } }
@media (prefers-reduced-motion: reduce) {
  .blueprint-front { stroke-dashoffset: 0; }
  .scene-brand, .scene-copy, .scene-foot { opacity: 1; transform: none; }
}
</style>
