(() => {
  const C = window.CONFIG;
  const $ = (id) => document.getElementById(id);
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
  };
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pad = (n) => String(n).padStart(2, "0");
  const rand = (a, b) => a + Math.random() * (b - a);
  const pick = (arr) => arr[(Math.random() * arr.length) | 0];
  const PALETTE = ["#ff4f9a", "#ffe14d", "#5fe3c0", "#7cc4ff", "#c6a8ff"];
  const jelly = (el) => { el.classList.remove("jelly"); void el.offsetWidth; el.classList.add("jelly"); };

  /* ================= Частицы (canvas) ================= */
  const cv = $("fx"), cx = cv.getContext("2d");
  let parts = [], fxOn = false;
  const resize = () => { cv.width = innerWidth * devicePixelRatio; cv.height = innerHeight * devicePixelRatio; };
  addEventListener("resize", resize); resize();

  function emit(p) { if (reduce) return; parts.push(p); if (!fxOn) { fxOn = true; requestAnimationFrame(frame); } }
  function burst(x, y, n = 14, emojis = ["💗", "✨", "🍬", "⭐"]) {
    for (let i = 0; i < n; i++) {
      const a = rand(0, Math.PI * 2), sp = rand(3, 9);
      const confetti = Math.random() < 0.55;
      emit({ x, y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 3, g: 0.28, drag: 0.96, life: 1, decay: rand(0.012, 0.022),
        rot: rand(0, 6), vr: rand(-0.3, 0.3), s: confetti ? rand(7, 13) : rand(16, 26),
        kind: confetti ? "rect" : "emoji", col: pick(PALETTE), ch: pick(emojis) });
    }
  }
  function rain(n = 120, emojis = ["💗", "💖", "💕", "🍬", "✨", "💋"]) {
    for (let i = 0; i < n; i++) {
      const confetti = Math.random() < 0.5;
      emit({ x: rand(0, innerWidth), y: innerHeight + rand(0, 300), vx: rand(-2, 2), vy: -rand(9, 17), g: 0.22, drag: 0.99, life: 1, decay: 0.005,
        rot: rand(0, 6), vr: rand(-0.2, 0.2), s: confetti ? rand(8, 14) : rand(18, 34), kind: confetti ? "rect" : "emoji", col: pick(PALETTE), ch: pick(emojis) });
    }
  }
  function frame() {
    const d = devicePixelRatio; cx.setTransform(d, 0, 0, d, 0, 0); cx.clearRect(0, 0, innerWidth, innerHeight);
    cx.textAlign = "center"; cx.textBaseline = "middle";
    parts = parts.filter((p) => {
      p.vx *= p.drag; p.vy = p.vy * p.drag + p.g; p.x += p.vx; p.y += p.vy; p.rot += p.vr; p.life -= p.decay;
      cx.save(); cx.globalAlpha = Math.max(0, Math.min(1, p.life * 1.5)); cx.translate(p.x, p.y); cx.rotate(p.rot);
      if (p.kind === "rect") { cx.fillStyle = p.col; cx.strokeStyle = "#1e1233"; cx.lineWidth = 2; cx.fillRect(-p.s / 2, -p.s / 3, p.s, p.s / 1.5); cx.strokeRect(-p.s / 2, -p.s / 3, p.s, p.s / 1.5); }
      else if (p.kind === "dot") { cx.fillStyle = p.col; cx.beginPath(); cx.arc(0, 0, Math.max(0, p.s * p.life), 0, 7); cx.fill(); }
      else { cx.font = p.s + "px serif"; cx.fillText(p.ch, 0, 0); }
      cx.restore();
      return p.life > 0 && p.y < innerHeight + 80;
    });
    if (parts.length) requestAnimationFrame(frame); else { fxOn = false; cx.clearRect(0, 0, innerWidth, innerHeight); }
  }

  /* ===== Клик где угодно: кольцо + конфетти + иногда штамп ===== */
  const STAMPS = ["муа!", "люблю", "скучаю", "ты лучшая", "карамелька", "💗💗💗", "моя", "скоро!"];
  document.addEventListener("pointerdown", (e) => {
    if (reduce || e.target.closest("input, .drop, .sticker")) return;
    const r = document.createElement("div"); r.className = "ring"; r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px";
    r.style.borderColor = pick(PALETTE); document.body.appendChild(r); setTimeout(() => r.remove(), 500);
    burst(e.clientX, e.clientY, 10);
    if (Math.random() < 0.28) stamp(e.clientX, e.clientY - 30, pick(STAMPS));
  });
  function stamp(x, y, text) {
    if (reduce) return;
    const s = document.createElement("div"); s.className = "stamp"; s.textContent = text;
    s.style.left = x + "px"; s.style.top = y + "px"; s.style.setProperty("--r", rand(-15, 15) + "deg");
    document.body.appendChild(s); setTimeout(() => s.remove(), 1000);
  }
  // Шлейф за мышкой
  let lastTrail = 0;
  document.addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse" || reduce) return;
    const now = performance.now(); if (now - lastTrail < 35) return; lastTrail = now;
    emit({ x: e.clientX, y: e.clientY, vx: rand(-0.5, 0.5), vy: rand(-1.5, -0.3), g: 0, drag: 1, life: 1, decay: 0.035, rot: 0, vr: 0,
      s: rand(4, 7), kind: "dot", col: pick(PALETTE) });
  });
  // Желе на всех кнопках
  document.addEventListener("click", (e) => { const b = e.target.closest(".btn"); if (b) jelly(b); });

  /* ================= Вход ================= */
  const norm = (s) => s.toLowerCase().replace(/ё/g, "е").replace(/[^a-zа-я0-9]/g, "");
  const answers = C.gateAnswers.map(norm);
  const WRONG = ["неа 🙂", "холодно…", "подумай ещё", "это точно ты?", C.gateHint, "почти! нет 😅"];
  let wrongN = 0;
  $("gateQ").textContent = C.gateQuestion;
  $("gateForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const box = $("gateForm"), val = norm($("gateInput").value);
    if (val && answers.includes(val)) {
      store.set("karamelka-ok", "1");
      box.classList.add("fly-away"); rain(160);
      setTimeout(open, 600);
    } else {
      $("gateMsg").textContent = WRONG[wrongN++ % WRONG.length];
      box.classList.remove("shake"); void box.offsetWidth; box.classList.add("shake");
      $("gateInput").select();
    }
  });
  function open() {
    $("gate").hidden = true; $("site").hidden = false;
    setupReveal(); placeKm();
  }
  if (store.get("karamelka-ok") === "1") open(); else setTimeout(() => $("gateInput").focus(), 400);

  /* ===== Листы «приклеиваются» при прокрутке ===== */
  function setupReveal() {
    if (reduce || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver((es) => es.forEach((en) => {
      if (!en.isIntersecting) return;
      en.target.classList.remove("pre"); en.target.classList.add("in"); io.unobserve(en.target);
    }), { threshold: 0.12 });
    document.querySelectorAll(".sheet").forEach((s) => {
      const r = s.getBoundingClientRect();
      if (r.top > innerHeight * 0.9) { s.classList.add("pre"); io.observe(s); }
      else s.classList.add("in");
    });
  }

  /* ================= Hero: прыгающие буквы ================= */
  const title = $("title");
  [..."Карамелька"].forEach((ch, i) => {
    const s = document.createElement("span"); s.textContent = ch; s.setAttribute("aria-hidden", "true");
    s.style.setProperty("--i", i); s.style.setProperty("--c", PALETTE[i % PALETTE.length]); s.style.setProperty("--w", (i % 2 ? -4 : 4) + "deg");
    s.addEventListener("click", (e) => {
      s.style.setProperty("--c", pick(PALETTE));
      s.classList.remove("hop"); void s.offsetWidth; s.classList.add("hop");
      setTimeout(() => s.classList.remove("hop"), 600);
      burst(e.clientX, e.clientY, 18, ["💗", "🍬", "✨"]);
    });
    title.appendChild(s);
  });

  // Перетаскиваемые стикеры
  document.querySelectorAll(".sticker").forEach((st) => {
    st.addEventListener("pointerdown", (e) => {
      e.preventDefault(); st.setPointerCapture(e.pointerId); st.classList.add("drag");
      const host = $("hero").getBoundingClientRect(), r = st.getBoundingClientRect();
      const ox = e.clientX - r.left, oy = e.clientY - r.top;
      const move = (ev) => {
        st.style.right = st.style.bottom = "auto";
        st.style.left = Math.max(-20, Math.min(host.width - 30, ev.clientX - host.left - ox)) + "px";
        st.style.top = Math.max(-20, Math.min(host.height - 30, ev.clientY - host.top - oy)) + "px";
      };
      const up = (ev) => { st.classList.remove("drag"); st.style.setProperty("--r", rand(-18, 18) + "deg");
        burst(ev.clientX, ev.clientY, 8); st.removeEventListener("pointermove", move); st.removeEventListener("pointerup", up); };
      st.addEventListener("pointermove", move); st.addEventListener("pointerup", up);
    });
  });

  /* ================= До встречи ================= */
  const meet = new Date(C.meetDate).getTime(), talk = new Date(C.talkingSince).getTime();
  const units = { uD: "", uH: "", uM: "", uS: "" };
  function setUnit(id, v) {
    if (units[id] === v) return; units[id] = v;
    const el = $(id); el.textContent = v;
    el.classList.remove("tick"); void el.offsetWidth; el.classList.add("tick");
  }
  function tick() {
    const now = Date.now(), before = now < meet;
    $("meetTitle").textContent = before ? "До нашей встречи" : "Мы вместе уже";
    const t = Math.floor(Math.abs(meet - now) / 1000);
    setUnit("uD", String(Math.floor(t / 86400))); setUnit("uH", pad(Math.floor((t % 86400) / 3600)));
    setUnit("uM", pad(Math.floor((t % 3600) / 60))); setUnit("uS", pad(t % 60));
    const days = Math.max(0, Math.floor((now - talk) / 86400000));
    $("talking").textContent = before ? `а общаемся мы уже ${days} дн. и ждём этого момента оба 💬` : `ура, дождались! а знакомы мы уже ${days} дн. 💗`;
  }
  tick(); setInterval(tick, 1000);

  /* ================= Между нами ================= */
  $("cityMe").textContent = C.myCity; $("cityHer").textContent = C.herCity;
  const route = $("route");
  function placeKm() {
    const el = $("km"), target = Date.now() >= meet ? 0 : C.distanceKm, t0 = performance.now();
    const step = (t) => { const k = Math.min(1, (t - t0) / 1400); el.textContent = Math.round(target * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  let kisses = +(store.get("karamelka-kisses") || 0);
  $("kissCount").textContent = kisses;
  function curvePoint(t) {
    const W = route.clientWidth, side = innerWidth <= 640 ? 36 : 44;
    const x = (1 - t) ** 2 * 10 + 2 * (1 - t) * t * 200 + t * t * 390;
    const y = (1 - t) ** 2 * 100 + 2 * (1 - t) * t * -20 + t * t * 100;
    return { x: side + (x / 400) * (W - side * 2), y: 20 + (y / 120) * 110 };
  }
  $("kissBtn").addEventListener("click", () => {
    const k = document.createElement("span"); k.className = "kiss"; k.textContent = "💋"; route.appendChild(k);
    const t0 = performance.now(), dur = reduce ? 1 : 1300;
    const fly = (now) => {
      const t = Math.min(1, (now - t0) / dur), e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
      const p = curvePoint(e);
      k.style.transform = `translate(${p.x - 17}px,${p.y - 17}px) rotate(${Math.sin(t * 12) * 20}deg) scale(${1 + Math.sin(t * Math.PI) * 0.6})`;
      if (t < 1) requestAnimationFrame(fly);
      else {
        k.remove(); kisses++; store.set("karamelka-kisses", kisses); $("kissCount").textContent = kisses;
        const ava = route.querySelector(".pin-her .ava"); ava.classList.remove("boom"); void ava.offsetWidth; ava.classList.add("boom");
        const r = ava.getBoundingClientRect(); burst(r.left + r.width / 2, r.top + r.height / 2, 22, ["💋", "💗", "✨"]);
        stamp(r.left + r.width / 2, r.top - 20, "доставлено!");
      }
    };
    requestAnimationFrame(fly);
  });

  /* ================= Плеер ================= */
  const audio = $("audio"), list = $("tracks"), cassette = $("cassette"), playBtn = $("play"), seek = $("seek");
  let songs = [], cur = -1;
  const AUDIO = /\.(mp3|m4a|aac|ogg|opus|wav|flac)$/i;
  const prettify = (f) => f.replace(AUDIO, "").replace(/^\d+[\s._-]+/, "").replace(/_/g, " ").trim();
  const fmt = (s) => (!isFinite(s) ? "0:00" : Math.floor(s / 60) + ":" + pad(Math.floor(s % 60)));

  async function loadSongs() {
    let files = [];
    try {
      const txt = await (await fetch("music/", { headers: { Accept: "application/json" } })).text();
      try { files = JSON.parse(txt).filter((f) => f.type === "file").map((f) => f.name); }
      catch { files = [...txt.matchAll(/href="([^"?]+)"/g)].map((m) => decodeURIComponent(m[1])); }
    } catch {}
    files = files.filter((f) => AUDIO.test(f)).sort((a, b) => a.localeCompare(b, "ru", { numeric: true }));
    const captions = {};
    try {
      const r = await fetch("music/captions.txt");
      if (r.ok) (await r.text()).split(/\r?\n/).forEach((line) => {
        const i = line.indexOf("|"); if (i < 0) return;
        captions[line.slice(0, i).trim().replace(AUDIO, "").toLowerCase()] = line.slice(i + 1).trim();
      });
    } catch {}
    songs = files.map((f) => ({ src: "music/" + encodeURIComponent(f), title: prettify(f),
      why: captions[f.replace(AUDIO, "").toLowerCase()] || captions[prettify(f).toLowerCase()] || "" }));
    renderList();
  }
  function renderList() {
    list.innerHTML = "";
    if (!songs.length) { list.innerHTML = '<li class="empty">песни скоро появятся 🎶</li>'; return; }
    songs.forEach((s, i) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="n">${pad(i + 1)}</span><span class="eq"><i></i><i></i><i></i></span><span class="name"></span><span class="why"></span>`;
      li.querySelector(".name").textContent = s.title; li.querySelector(".why").textContent = s.why;
      li.onclick = () => (i === cur ? toggle() : play(i));
      list.appendChild(li);
    });
  }
  function play(i) {
    if (!songs.length) return;
    cur = (i + songs.length) % songs.length;
    const s = songs[cur]; audio.src = s.src; startViz(); audio.play().catch(() => {});
    $("nowTitle").textContent = s.title; $("nowWhy").textContent = s.why || "💗";
    [...list.children].forEach((li, j) => li.classList.toggle("active", j === cur));
  }
  function toggle() { if (cur < 0) return play(0); startViz(); audio.paused ? audio.play() : audio.pause(); }
  playBtn.onclick = toggle;
  $("next").onclick = () => play(cur + 1);
  $("prev").onclick = () => (audio.currentTime > 3 ? (audio.currentTime = 0) : play(cur - 1));
  const setPlaying = (on) => {
    cassette.classList.toggle("on", on); playBtn.textContent = on ? "❚❚" : "▶";
    playBtn.setAttribute("aria-label", on ? "Пауза" : "Играть");
    list.querySelector(".active")?.classList.toggle("playing", on);
  };
  audio.onplay = () => setPlaying(true);
  audio.onpause = () => setPlaying(false);
  audio.onended = () => play(cur + 1);
  audio.ontimeupdate = () => {
    $("tCur").textContent = fmt(audio.currentTime); $("tDur").textContent = fmt(audio.duration);
    if (audio.duration) seek.value = (audio.currentTime / audio.duration) * 1000;
  };
  seek.oninput = () => { if (audio.duration) audio.currentTime = (seek.value / 1000) * audio.duration; };
  loadSongs();

  // Эквалайзер под кассетой
  const viz = $("viz"), vx = viz.getContext("2d");
  let actx, analyser, data;
  function startViz() {
    try {
      if (!actx) {
        actx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = actx.createAnalyser(); analyser.fftSize = 64; data = new Uint8Array(analyser.frequencyBinCount);
        actx.createMediaElementSource(audio).connect(analyser); analyser.connect(actx.destination);
        drawViz();
      }
      if (actx.state === "suspended") actx.resume();
    } catch {}
  }
  function drawViz() {
    const w = (viz.width = viz.clientWidth * devicePixelRatio), h = (viz.height = viz.clientHeight * devicePixelRatio);
    vx.clearRect(0, 0, w, h);
    if (analyser) analyser.getByteFrequencyData(data);
    const n = 20, bw = w / n;
    for (let i = 0; i < n; i++) {
      const v = data && !audio.paused ? data[i + 2] / 255 : 0.06;
      const bh = Math.max(3, v * h);
      vx.fillStyle = "#1e1233"; vx.fillRect(i * bw + 2, h - bh, bw - 4, bh);
    }
    requestAnimationFrame(drawViz);
  }

  /* ================= Почему ты ================= */
  const sweets = ["🍬", "🍭", "🧁", "🍓", "🍫", "🍯", "🍩", "🍒"];
  C.reasons.forEach((text, i) => {
    const b = document.createElement("button");
    b.className = "card"; b.type = "button"; b.style.setProperty("--r", rand(-4, 4) + "deg");
    b.innerHTML = `<div class="in"><div class="f" data-n="${pad(i + 1)}">${sweets[i % sweets.length]}</div><div class="b"></div></div>`;
    b.querySelector(".f").style.setProperty("--bgc", PALETTE[i % PALETTE.length]);
    b.querySelector(".b").textContent = text;
    b.onclick = (e) => { b.classList.toggle("flip"); if (b.classList.contains("flip")) burst(e.clientX, e.clientY, 16, [sweets[i % sweets.length], "💗"]); };
    $("reasons").appendChild(b);
  });

  /* ================= Письма (печатаются) ================= */
  let typer;
  C.letters.forEach((l, i) => {
    const b = document.createElement("button");
    b.className = "env"; b.type = "button"; b.style.setProperty("--bgc", PALETTE[i % PALETTE.length]);
    b.innerHTML = `<span class="seal">💗</span>…${l.when}`;
    b.onclick = () => {
      b.classList.add("opened");
      const box = $("letter"), p = $("letterText");
      box.hidden = false; box.style.animation = "none"; void box.offsetWidth; box.style.animation = "";
      $("letterHead").textContent = "открой, когда " + l.when;
      clearInterval(typer); p.textContent = ""; p.classList.remove("done");
      let k = 0;
      if (reduce) { p.textContent = l.text; p.classList.add("done"); return; }
      typer = setInterval(() => { p.textContent = l.text.slice(0, ++k); if (k >= l.text.length) { clearInterval(typer); p.classList.add("done"); } }, 32);
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    $("envs").appendChild(b);
  });

  /* ================= Игра ================= */
  const game = $("game"), score = $("score");
  let caught = 0, missed = 0, running = false, spawnT, drops = [], raf;
  const good = ["🍬", "🍭", "🍯", "🍫", "💗", "🍓"];
  const setScore = () => (score.innerHTML = `<span>🍬 ${caught}/${C.gameGoal}</span><span>мимо: ${missed}</span>`);
  setScore();
  $("gameBtn").onclick = () => {
    caught = 0; missed = 0; setScore(); $("gameStart").hidden = true; $("prize").hidden = true;
    running = true; spawn(); loop();
  };
  function popText(x, y, t, col) {
    const s = document.createElement("span"); s.className = "pop-txt"; s.textContent = t; s.style.color = col;
    s.style.left = x + "px"; s.style.top = y + "px"; game.appendChild(s); setTimeout(() => s.remove(), 700);
  }
  function spawn() {
    if (!running) return;
    const bad = Math.random() < 0.18;
    const d = document.createElement("button");
    d.type = "button"; d.className = "drop"; d.textContent = bad ? "💔" : pick(good);
    const o = { el: d, bad, x: rand(0, game.clientWidth - 56), y: -56, v: rand(1.6, 3.2) + caught * 0.06, wob: rand(0, 6) };
    d.style.left = o.x + "px";
    d.addEventListener("pointerdown", (e) => {
      e.preventDefault(); if (o.done) return; o.done = true;
      d.classList.add("got"); d.style.transform += " scale(2)";
      const gr = game.getBoundingClientRect();
      if (bad) { caught = Math.max(0, caught - 2); popText(e.clientX - gr.left, e.clientY - gr.top, "-2", "#1e1233"); jelly(game); }
      else { caught++; burst(e.clientX, e.clientY, 10, [d.textContent, "✨"]); popText(e.clientX - gr.left, e.clientY - gr.top, "+1", "#ff4f9a"); }
      setScore(); setTimeout(() => d.remove(), 250);
      if (caught >= C.gameGoal) win();
    });
    game.appendChild(d); drops.push(o);
    spawnT = setTimeout(spawn, Math.max(360, 880 - caught * 25));
  }
  function loop() {
    const H = game.clientHeight;
    drops = drops.filter((o) => {
      if (o.done) return false;
      o.y += o.v; o.wob += 0.05;
      o.el.style.transform = `translate(${Math.sin(o.wob) * 12}px,${o.y}px) rotate(${Math.sin(o.wob) * 25}deg)`;
      if (o.y > H) { o.el.remove(); if (!o.bad) { missed++; setScore(); } return false; }
      return true;
    });
    if (running) raf = requestAnimationFrame(loop);
  }
  function win() {
    running = false; clearTimeout(spawnT); cancelAnimationFrame(raf);
    drops.forEach((o) => o.el.remove()); drops = [];
    $("prize").hidden = false; $("prize").textContent = "🏆 " + C.gamePrize;
    $("gameStart").hidden = false; $("gameBtn").textContent = "Ещё раз";
    rain(140, ["🏆", "🍬", "💗", "✨"]);
  }

  /* ================= Финал ================= */
  $("finalQ").textContent = C.finalQuestion;
  const no = $("no"), qb = $("qbtns"), yes = $("yes");
  const NO_MSG = ["не-а", "попробуй ещё", "кнопка сломалась", "точно?", "жми «Да»", "ну пожалуйста", "я не отстану"];
  let dodges = 0;
  const dodge = (e) => {
    if (e) e.preventDefault();
    dodges++;
    const r = qb.getBoundingClientRect(), maxX = Math.min(r.width / 2 - 50, 180);
    no.style.transform = `translate(${rand(-1, 1) * maxX}px,${rand(-1, 1) * 40}px) rotate(${rand(-30, 30)}deg) scale(${Math.max(0.45, 1 - dodges * 0.07)})`;
    yes.style.transform = `scale(${Math.min(1.8, 1 + dodges * 0.08)})`;
    $("finalA").textContent = NO_MSG[dodges % NO_MSG.length];
  };
  no.addEventListener("pointerenter", dodge);
  no.addEventListener("pointerdown", dodge);
  no.addEventListener("click", dodge);
  yes.addEventListener("click", (e) => {
    $("finalA").textContent = C.finalAnswer; no.hidden = true; yes.style.transform = "";
    const m = $("site"); m.classList.remove("quake"); void m.offsetWidth; m.classList.add("quake");
    burst(e.clientX, e.clientY, 40, ["💗", "💖", "💋"]); rain(260);
    stamp(e.clientX, e.clientY - 50, "ДА!!! 💗");
  });
})();
