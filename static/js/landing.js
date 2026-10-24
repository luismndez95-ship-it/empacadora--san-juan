/* Landing Empacadora San Juan -- animacion guiada por scroll, sin librerias.
 *
 * Idea central: cada escena (`data-scene`) es una seccion alta con un
 * contenido `sticky` adentro. Medimos cuanto se ha recorrido la seccion
 * (progreso 0..1) y cada escena traduce ese numero a transformaciones.
 */
(() => {
  "use strict";

  // ───────── utilidades ─────────
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const clamp = (v, min = 0, max = 1) => Math.min(max, Math.max(min, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  /** Convierte p en 0..1 dentro de la ventana [from, to]. */
  const span = (p, from, to) => clamp((p - from) / (to - from));
  const easeOut = (t) => 1 - Math.pow(1 - t, 3);
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const thousands = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

  const root = document.documentElement;
  const reducedQuery = matchMedia("(prefers-reduced-motion: reduce)");
  const narrowQuery = matchMedia("(max-width: 800px)");

  // ───────── escenas: cada fabrica devuelve update(p) ─────────
  function makeHero(el) {
    const bg = $(".hero__bg img", el);
    const content = $(".hero__content", el);
    const fade = $(".hero__fade", el);
    const cue = $(".scroll-cue", el);
    return (p) => {
      bg.style.transform = `scale(${1.05 + p * 0.38}) translateY(${p * 7}%)`;
      const t = easeInOut(span(p, 0, 0.6));
      content.style.transform = `translateY(${-t * 14}vh) scale(${1 + t * 0.55})`;
      content.style.opacity = 1 - span(p, 0.25, 0.65);
      fade.style.opacity = span(p, 0.55, 1);
      cue.style.opacity = 1 - span(p, 0, 0.08);
    };
  }

  function makeVolcano(el) {
    const intro = $(".volcano__intro", el);
    const win = $(".volcano__window", el);
    const img = $("img", win);
    const items = $$("[data-r]", el);
    const counter = $("[data-counter]", el);
    const target = Number(counter.dataset.to);
    return (p) => {
      intro.style.opacity = 1 - span(p, 0.08, 0.3);
      intro.style.transform = `scale(${1 + p * 0.35})`;
      const radius = lerp(0, 150, easeInOut(span(p, 0.12, 0.6)));
      win.style.clipPath = `circle(${radius}% at 50% 58%)`;
      img.style.transform = `scale(${lerp(1.4, 1.02, easeOut(span(p, 0.12, 1)))})`;
      items.forEach((item, i) => {
        const t = easeOut(span(p, 0.52 + i * 0.05, 0.68 + i * 0.05));
        item.style.opacity = t;
        item.style.transform = `translateY(${(1 - t) * 36}px)`;
      });
      counter.textContent = thousands(Math.round(target * easeOut(span(p, 0.62, 0.92))));
    };
  }

  function makeGallery(el) {
    const track = $(".gallery__track", el);
    const panels = $$(".panel:not(.panel--intro)", el);
    const bar = $(".gallery__bar i", el);
    let maxShift = 0;

    const measure = () => {
      const stacked = root.classList.contains("stack-gallery");
      maxShift = stacked ? 0 : Math.max(0, track.scrollWidth - innerWidth);
      el.style.height = stacked ? "" : `${maxShift + innerHeight}px`;
    };
    measure();

    const update = (p) => {
      if (root.classList.contains("stack-gallery")) return;
      const x = -maxShift * p;
      track.style.transform = `translate3d(${x}px, 0, 0)`;
      bar.style.transform = `scaleX(${p})`;
      panels.forEach((panel) => {
        // d: distancia del panel al centro de la pantalla (-1 .. 1 aprox.)
        const d = (panel.offsetLeft + panel.offsetWidth / 2 + x - innerWidth / 2) / innerWidth;
        $("img", panel).style.transform = `translate3d(${d * -8}%, 0, 0) scale(1.1)`;
        panel.classList.toggle("is-near", Math.abs(d) < 0.3);
      });
    };
    update.measure = measure;
    return update;
  }

  function makeProcess(el) {
    const steps = $$("[data-step]", el);
    const nodes = $$("[data-node]", el);
    const number = $("[data-step-number]", el);
    const fill = $(".timeline__line i", el);
    const crate = $(".crate", el);
    const glow = $(".glow", el);
    let current = -1;
    return (p) => {
      const index = Math.min(steps.length - 1, Math.floor(p * steps.length));
      if (index !== current) {
        current = index;
        steps.forEach((s, i) => s.classList.toggle("is-active", i === index));
        nodes.forEach((n, i) => n.classList.toggle("is-on", i <= index));
        number.textContent = `0${index + 1}`;
      }
      el.style.setProperty("--p", p);
      fill.style.transform = `scaleX(${p})`;
      const bob = Math.sin(p * Math.PI * 4) * 12;
      crate.style.transform =
        `translate3d(0, ${bob}px, 0) rotate(${lerp(-14, 14, p)}deg) scale(${lerp(0.78, 1.08, easeOut(p))})`;
      glow.style.transform = `scale(${lerp(0.6, 1.3, p)})`;
    };
  }

  const factories = { hero: makeHero, volcano: makeVolcano, gallery: makeGallery, process: makeProcess };
  // En modo estatico (movimiento reducido) cada escena se pinta en este progreso.
  // La portada se queda en 0: en 1 estaria cubierta por su propio fundido.
  const STILL_PROGRESS = { hero: 0 };

  const scenes = $$("[data-scene]").map((el) => ({
    el,
    name: el.dataset.scene,
    update: factories[el.dataset.scene](el),
    last: null,
  }));

  // ───────── cinta de texto ─────────
  const marqueeLines = $$(".marquee__line").map((el) => ({
    el, dir: Number(el.dataset.dir), unit: 1,
  }));
  const measureMarquee = () => marqueeLines.forEach((l) => { l.unit = $(".marquee__group", l.el).offsetWidth; });

  // ───────── bucle de render ─────────
  const progressBar = $("#progress");
  const topbar = $("#topbar");
  let ticking = false;

  const sceneProgress = (el) => {
    const rect = el.getBoundingClientRect();
    const scrollable = rect.height - innerHeight;
    return scrollable > 0 ? clamp(-rect.top / scrollable) : 0;
  };

  function render(force = false) {
    ticking = false;
    const y = scrollY;
    const reduced = root.classList.contains("reduced");
    const max = document.documentElement.scrollHeight - innerHeight;
    progressBar.style.transform = `scaleX(${max > 0 ? y / max : 0})`;
    topbar.classList.toggle("is-solid", y > 40);

    if (!reduced) {
      marqueeLines.forEach((l) => {
        const shift = (y * 0.4) % l.unit;
        l.el.style.transform = `translate3d(${l.dir < 0 ? -shift : shift - l.unit}px, 0, 0)`;
      });
    }

    scenes.forEach((scene) => {
      const p = reduced ? (STILL_PROGRESS[scene.name] ?? 1) : sceneProgress(scene.el);
      if (force || p !== scene.last) {
        scene.last = p;
        scene.update(p);
      }
    });
  }

  const requestRender = () => {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(() => render());
    }
  };

  // ───────── modo (movimiento reducido / movil) y medidas ─────────
  function layout() {
    root.classList.toggle("reduced", reducedQuery.matches);
    root.classList.toggle("stack-gallery", reducedQuery.matches || narrowQuery.matches);
    scenes.forEach((s) => s.update.measure && s.update.measure());
    measureMarquee();
    render(true);
  }

  // ───────── texto partido en letras (titulo de la portada) ─────────
  let letterIndex = 0;
  $$("[data-split]").forEach((line) => {
    const text = line.textContent.trim();
    line.textContent = "";
    [...text].forEach((char) => {
      const span = document.createElement("span");
      span.className = "ch";
      span.setAttribute("aria-hidden", "true");
      span.style.setProperty("--i", letterIndex++);
      span.textContent = char === " " ? "\u00a0" : char;
      line.appendChild(span);
    });
  });

  // ───────── aparicion al entrar en pantalla ─────────
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("in");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.2 });
  $$(".reveal").forEach((el) => observer.observe(el));

  // ───────── arranque ─────────
  addEventListener("scroll", requestRender, { passive: true });
  addEventListener("resize", layout);
  reducedQuery.addEventListener("change", layout);
  narrowQuery.addEventListener("change", layout);
  document.fonts.ready.then(layout);
  layout();
})();
