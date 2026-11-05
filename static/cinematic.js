'use strict';
// 纯视觉渐进增强：不读取材料、不保存输入、不改变业务节点坐标。
(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  let observer;
  const reveal = root => {
    const elements = root.querySelectorAll('[data-entrance]');
    if (reduced.matches || !('IntersectionObserver' in window)) return;
    if (!observer) observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.remove('waiting-entrance');
        entry.target.classList.add('has-entered');
        observer.unobserve(entry.target);
      });
    }, {threshold: 0.08});
    document.documentElement.classList.add('motion-ready');
    elements.forEach(el => {
      if (el.dataset.motionBound) return;
      el.dataset.motionBound = 'true';
      el.classList.add('waiting-entrance');
      observer.observe(el);
    });
  };
  const resetMotion = () => {
    if (!reduced.matches) return;
    observer?.disconnect();
    document.querySelectorAll('.waiting-entrance').forEach(el => el.classList.remove('waiting-entrance'));
    document.querySelectorAll('[data-tilt]').forEach(el => {el.style.transform = '';});
  };
  reduced.addEventListener('change', resetMotion);
  // 轻量首屏视差，只移动装饰图；触摸、键盘与减少动态下保持静态。
  const bindTilt = root => root.querySelectorAll('[data-tilt]').forEach(art => {
    if (art.dataset.tiltBound) return;
    art.dataset.tiltBound = 'true';
    const host = art.closest('.cinema-hero,.overview-hero');
    if (!host) return;
    let frame = 0, latest;
    host.addEventListener('pointermove', event => {
      if (reduced.matches || !finePointer.matches || document.hidden || window.CareerEffects?.mode==='off' || event.pointerType !== 'mouse') return;
      latest = {x: event.clientX, y: event.clientY};
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (!latest || reduced.matches || document.hidden || window.CareerEffects?.mode==='off') return;
        const rect = host.getBoundingClientRect();
        const x = Math.max(-1, Math.min(1, (latest.x - rect.left) / rect.width * 2 - 1));
        const y = Math.max(-1, Math.min(1, (latest.y - rect.top) / rect.height * 2 - 1));
        art.style.transform = `perspective(1000px) rotateY(${x * 3}deg) rotateX(${-y * 2}deg) translate3d(${x * 5}px,${y * 3}px,0)`;
      });
    });
    const reset = () => {cancelAnimationFrame(frame); frame = 0; latest = null; art.style.transform = '';};
    host.addEventListener('pointerleave', reset);
    window.addEventListener('pagehide', reset);
    document.addEventListener('visibilitychange', () => {if (document.hidden) reset();});
    window.addEventListener('viewchange', reset);
    document.addEventListener('keydown', reset, {passive: true});
  });
  const init = () => {reveal(document);bindTilt(document);};
  init();
  window.addEventListener('platform-ready', init);
  // 首页面向已登录账号的具体入口；只在平台就绪后进入白名单前台视图。
  let platformReady = window.careerPlatformReady === true;
  const linkedViews = new Set(['overview','materials','risk','privacy','career','tree','exam','interview','jobs','profile']);
  const openLinkedView = () => {
    const view = location.hash.slice(1);
    if (platformReady && linkedViews.has(view) && typeof show === 'function') show(view);
  };
  window.addEventListener('platform-loaded', () => {platformReady = true;openLinkedView();});
  window.addEventListener('hashchange', openLinkedView);
  openLinkedView();
  document.addEventListener('keydown', () => document.body.classList.add('motion-keyboard'), {passive: true});
  document.addEventListener('pointerdown', () => document.body.classList.remove('motion-keyboard'), {passive: true});
})();
