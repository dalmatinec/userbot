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
  const COLORS = ["#e8a0b4", "#f6d6dc", "#e6c08a", "#c0465f"];

  /* ================= Звёздное небо (фон) ================= */
  const sky = $("sky"), sx = sky.getContext("2d");
  let stars = [], bokeh = [];
  function sizeSky() {
    sky.width = innerWidth * devicePixelRatio; sky.height = innerHeight * devicePixelRatio;
    stars = Array.from({ length: Math.round((innerWidth * innerHeight) / 9000) }, () => ({ x: rand(0, innerWidth), y: rand(0, innerHeight), r: rand(0.3, 1.2), p: rand(0, 6), s: rand(0.005, 0.02) }));
    bokeh = Array.from({ length: 14 }, () => ({ x: rand(0, innerWidth), y: rand(0, innerHeight), r: rand(20, 70), v: rand(0.1, 0.35), a: rand(0.03, 0.08), c: pick(["232,160,180", "230,192,138"]) }));
  }
  sizeSky(); addEventListener("resize", sizeSky);
  function drawSky() {
    const d = devicePixelRatio; sx.setTransform(d, 0, 0, d, 0, 0); sx.clearRect(0, 0, innerWidth, innerHeight);
    for (const b of bokeh) {
      b.y -= b.v; if (b.y < -b.r) { b.y = innerHeight + b.r; b.x = rand(0, innerWidth); }
      const g = sx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r);
      g.addColorStop(0, `rgba(${b.c},${b.a})`); g.addColorStop(1, `rgba(${b.c},0)`);
      sx.fillStyle = g; sx.beginPath(); sx.arc(b.x, b.y, b.r, 0, 7); sx.fill();
    }
    for (const s of stars) {
      s.p += s.s; sx.globalAlpha = 0.25 + Math.abs(Math.sin(s.p)) * 0.75;
      sx.fillStyle = "#f6e6d0"; sx.beginPath(); sx.arc(s.x, s.y, s.r, 0, 7); sx.fill();
    }
    sx.globalAlpha = 1;
    if (!reduce) requestAnimationFrame(drawSky);
  }
  drawSky();

  /* ================= Частицы: лепестки, искры, сердца ================= */
  const cv = $("fx"), cx = cv.getContext("2d");
  let parts = [], fxOn = false;
  const resize = () => { cv.width = innerWidth * devicePixelRatio; cv.height = innerHeight * devicePixelRatio; };
  addEventListener("resize", resize); resize();
  function emit(p) { if (reduce) return; parts.push(p); if (!fxOn) { fxOn = true; requestAnimationFrame(frame); } }
  function bloom(x, y, n = 12) {
    for (let i = 0; i < n; i++) {
      const a = rand(0, Math.PI * 2), sp = rand(1, 4.5), k = Math.random();
      emit({ x, y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 1, g: k < 0.4 ? 0.03 : -0.02, drag: 0.97, life: 1, decay: rand(0.01, 0.02),
        rot: rand(0, 6), vr: rand(-0.08, 0.08), s: k < 0.4 ? rand(5, 9) : k < 0.75 ? rand(1.5, 3) : rand(12, 20),
        kind: k < 0.4 ? "petal" : k < 0.75 ? "spark" : "heart", col: pick(COLORS) });
    }
  }
  function petalRain(n = 140) {
    for (let i = 0; i < n; i++) {
      const heart = Math.random() < 0.3;
      emit({ x: rand(0, innerWidth), y: rand(-innerHeight, -10), vx: rand(-0.6, 0.6), vy: rand(1, 2.6), g: 0, drag: 1, life: 1.6, decay: 0.003,
        rot: rand(0, 6), vr: rand(-0.04, 0.04), sway: rand(0, 6), s: heart ? rand(12, 22) : rand(6, 11), kind: heart ? "heart" : "petal", col: pick(COLORS) });
    }
  }
  function frame() {
    const d = devicePixelRatio; cx.setTransform(d, 0, 0, d, 0, 0); cx.clearRect(0, 0, innerWidth, innerHeight);
    cx.textAlign = "center"; cx.textBaseline = "middle";
    parts = parts.filter((p) => {
      p.vx *= p.drag; p.vy = p.vy * p.drag + p.g;
      if (p.sway !== undefined) { p.sway += 0.03; p.x += Math.sin(p.sway) * 0.8; }
      p.x += p.vx; p.y += p.vy; p.rot += p.vr; p.life -= p.decay;
      cx.save(); cx.globalAlpha = Math.max(0, Math.min(1, p.life)); cx.translate(p.x, p.y); cx.rotate(p.rot);
      if (p.kind === "petal") { cx.fillStyle = p.col; cx.beginPath(); cx.ellipse(0, 0, p.s, p.s * 0.55, 0, 0, 7); cx.fill(); }
      else if (p.kind === "spark") { cx.shadowColor = p.col; cx.shadowBlur = 10; cx.fillStyle = "#fff4e0"; cx.beginPath(); cx.arc(0, 0, Math.max(0, p.s), 0, 7); cx.fill(); }
      else { cx.shadowColor = p.col; cx.shadowBlur = 12; cx.fillStyle = p.col; cx.font = p.s + "px serif"; cx.fillText("♥", 0, 0); }
      cx.restore();
      return p.life > 0 && p.y < innerHeight + 40;
    });
    if (parts.length) requestAnimationFrame(frame); else { fxOn = false; cx.clearRect(0, 0, innerWidth, innerHeight); }
  }

  /* ===== Касание: кольцо света, лепестки, иногда шёпот ===== */
  const WHISPERS = ["люблю", "моя", "скучаю", "ты лучшая", "Карамелька", "скоро", "думаю о тебе"];
  document.addEventListener("pointerdown", (e) => {
    if (reduce || e.target.closest("input, .drop, .heart-btn")) return;
    const r = document.createElement("div"); r.className = "ring"; r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px";
    document.body.appendChild(r); setTimeout(() => r.remove(), 1000);
    bloom(e.clientX, e.clientY, 9);
    if (Math.random() < 0.22) whisper(e.clientX, e.clientY - 30, pick(WHISPERS));
  });
  function whisper(x, y, text) {
    if (reduce) return;
    const s = document.createElement("div"); s.className = "whisper"; s.textContent = text;
    s.style.left = x + "px"; s.style.top = y + "px"; document.body.appendChild(s); setTimeout(() => s.remove(), 2000);
  }
  let lastTrail = 0;
  document.addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse" || reduce) return;
    const now = performance.now(); if (now - lastTrail < 40) return; lastTrail = now;
    emit({ x: e.clientX, y: e.clientY, vx: rand(-0.3, 0.3), vy: rand(-0.8, -0.2), g: 0, drag: 1, life: 0.9, decay: 0.03, rot: 0, vr: 0, s: rand(1, 2.2), kind: "spark", col: "#e6c08a" });
  });
  // Волна света на кнопках
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".btn"); if (!b || reduce) return;
    const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height), rp = document.createElement("span");
    rp.className = "ripple"; rp.style.width = rp.style.height = s + "px";
    rp.style.left = e.clientX - r.left - s / 2 + "px"; rp.style.top = e.clientY - r.top - s / 2 + "px";
    b.appendChild(rp); setTimeout(() => rp.remove(), 700);
  });

  /* ================= Вход: удерживай сердце ================= */
  const heart = $("heartBtn"), fill = $("heartFill"), gateText = $("gateText");
  gateText.textContent = C.gateText;
  let level = 0, holding = false, last = 0, beatT = 0, opened = false;
  const HOLD_MS = 2400;
  function hold(e) { e.preventDefault(); if (opened) return; holding = true; heart.classList.add("holding"); last = performance.now(); requestAnimationFrame(step); }
  function release() { holding = false; heart.classList.remove("holding"); }
  function step(now) {
    const dt = now - last; last = now;
    level = Math.max(0, Math.min(1, level + (holding ? dt / HOLD_MS : -dt / 900)));
    fill.setAttribute("y", 92 - 92 * level);
    if (holding && now - beatT > 550) { beatT = now; try { navigator.vibrate && navigator.vibrate(30); } catch {}
      const r = heart.getBoundingClientRect(); bloom(r.left + r.width / 2, r.top + r.height / 2, 3); }
    if (level >= 1 && !opened) { opened = true; unlock(); return; }
    if (holding || level > 0) requestAnimationFrame(step);
  }
  heart.addEventListener("pointerdown", hold);
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => heart.addEventListener(ev, release));
  heart.addEventListener("contextmenu", (e) => e.preventDefault());
  heart.addEventListener("keydown", (e) => { if ((e.key === " " || e.key === "Enter") && !holding) hold(e); });
  heart.addEventListener("keyup", release);
  function unlock() {
    release(); gateText.textContent = C.gateDone;
    const r = heart.getBoundingClientRect(); bloom(r.left + r.width / 2, r.top + r.height / 2, 40);
    try { navigator.vibrate && navigator.vibrate([60, 80, 120]); } catch {}
    store.set("karamelka-ok", "1");
    setTimeout(() => { $("gate").classList.add("leave"); petalRain(120); }, 900);
    setTimeout(open, 1900);
  }
  function open() { $("gate").hidden = true; $("site").hidden = false; setupReveal(); animateKm(); }
  if (store.get("karamelka-ok") === "1") open();

  /* ===== Разделы проявляются при прокрутке ===== */
  function setupReveal() {
    if (reduce || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver((es) => es.forEach((en) => {
      if (!en.isIntersecting) return;
      en.target.classList.remove("pre"); en.target.classList.add("in"); io.unobserve(en.target);
    }), { threshold: 0.15 });
    document.querySelectorAll(".sec:not(.hero)").forEach((s) => {
      if (s.getBoundingClientRect().top > innerHeight * 0.9) { s.classList.add("pre"); io.observe(s); }
    });
  }

  /* ================= Заголовок ================= */
  const title = $("title");
  [..."Карамелька"].forEach((ch, i) => {
    const s = document.createElement("span"); s.textContent = ch; s.setAttribute("aria-hidden", "true"); s.style.setProperty("--i", i);
    s.addEventListener("click", (e) => { s.classList.add("glow"); setTimeout(() => s.classList.remove("glow"), 1200); bloom(e.clientX, e.clientY, 14); });
    title.appendChild(s);
  });

  /* ================= До встречи ================= */
  const meet = new Date(C.meetDate).getTime(), talk = new Date(C.talkingSince).getTime();
  const units = {};
  function setUnit(id, v) {
    if (units[id] === v) return; units[id] = v;
    const el = $(id); el.textContent = v; el.classList.remove("tick"); void el.offsetWidth; el.classList.add("tick");
  }
  const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 10 || h >= 20) ? b : c; };
  function tick() {
    const now = Date.now(), before = now < meet;
    $("meetTitle").textContent = before ? "До нашей встречи" : "Мы вместе уже";
    const t = Math.floor(Math.abs(meet - now) / 1000);
    setUnit("uD", String(Math.floor(t / 86400))); setUnit("uH", pad(Math.floor((t % 86400) / 3600)));
    setUnit("uM", pad(Math.floor((t % 3600) / 60))); setUnit("uS", pad(t % 60));
    const days = Math.max(0, Math.floor((now - talk) / 86400000));
    $("talking").textContent = before
      ? `а мы общаемся уже ${days} ${plural(days, "день", "дня", "дней")}, и оба ждём этого момента`
      : `дождались. а знакомы мы уже ${days} ${plural(days, "день", "дня", "дней")}`;
  }
  tick(); setInterval(tick, 1000);

  /* ================= Между нами ================= */
  $("city").textContent = C.city; $("distanceNote").textContent = C.distanceNote;
  const route = $("route");
  function animateKm() {
    const el = $("km"), target = C.distanceKm, t0 = performance.now();
    const step = (t) => { const k = Math.min(1, (t - t0) / 1800); el.textContent = Math.round(target * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  let kisses = +(store.get("karamelka-kisses") || 0);
  $("kissCount").textContent = kisses;
  function curvePoint(t) {
    const W = route.clientWidth, side = innerWidth <= 640 ? 30 : 40;
    const x = (1 - t) ** 2 * 10 + 2 * (1 - t) * t * 200 + t * t * 390;
    const y = (1 - t) ** 2 * 100 + 2 * (1 - t) * t * -20 + t * t * 100;
    return { x: side + (x / 400) * (W - side * 2), y: 20 + (y / 120) * 110 };
  }
  $("kissBtn").addEventListener("click", () => {
    const k = document.createElement("span"); k.className = "kiss"; k.textContent = "♥"; route.appendChild(k);
    const t0 = performance.now(), dur = reduce ? 1 : 1800;
    let lastSpark = 0;
    const fly = (now) => {
      const t = Math.min(1, (now - t0) / dur), e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2, p = curvePoint(e);
      k.style.transform = `translate(${p.x - 8}px,${p.y - 14}px) scale(${1 + Math.sin(t * Math.PI) * 0.5})`;
      if (now - lastSpark > 50) { lastSpark = now; const r = route.getBoundingClientRect();
        emit({ x: r.left + p.x, y: r.top + p.y, vx: rand(-0.3, 0.3), vy: rand(-0.3, 0.3), g: 0, drag: 1, life: 0.8, decay: 0.025, rot: 0, vr: 0, s: rand(1, 2), kind: "spark", col: "#e8a0b4" }); }
      if (t < 1) return requestAnimationFrame(fly);
      k.remove(); kisses++; store.set("karamelka-kisses", kisses); $("kissCount").textContent = kisses;
      const dot = route.querySelector(".pt-her .dot"); dot.classList.remove("boom"); void dot.offsetWidth; dot.classList.add("boom");
      const r = dot.getBoundingClientRect(); bloom(r.left + 7, r.top + 7, 24); whisper(r.left + 7, r.top - 30, "получила");
    };
    requestAnimationFrame(fly);
  });

  /* ================= Плеер ================= */
  const audio = $("audio"), list = $("tracks"), vinyl = $("cassette"), playBtn = $("play"), seek = $("seek");
  let songs = [], cur = -1;
  const AUDIO = /\.(mp3|m4a|aac|ogg|opus|wav|flac)$/i;
  const prettify = (f) => f.replace(AUDIO, "").replace(/^\d+[\s._-]+/, "").replace(/_/g, " ").replace(/\s+/g, " ").trim();
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
    if (!songs.length) { list.innerHTML = '<li class="empty">песни скоро появятся</li>'; return; }
    songs.forEach((s, i) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="n">${pad(i + 1)}</span><span class="name"></span><span class="eq"><i></i><i></i><i></i></span><span class="why"></span>`;
      li.querySelector(".name").textContent = s.title; li.querySelector(".why").textContent = s.why;
      li.onclick = () => (i === cur ? toggle() : play(i));
      list.appendChild(li);
    });
  }
  function play(i) {
    if (!songs.length) return;
    cur = (i + songs.length) % songs.length;
    const s = songs[cur]; audio.src = s.src; startViz(); audio.play().catch(() => {});
    $("nowTitle").textContent = s.title; $("nowWhy").textContent = s.why;
    [...list.children].forEach((li, j) => li.classList.toggle("active", j === cur));
  }
  function toggle() { if (cur < 0) return play(0); startViz(); audio.paused ? audio.play() : audio.pause(); }
  playBtn.onclick = toggle;
  $("next").onclick = () => play(cur + 1);
  $("prev").onclick = () => (audio.currentTime > 3 ? (audio.currentTime = 0) : play(cur - 1));
  const setPlaying = (on) => {
    vinyl.classList.toggle("on", on); playBtn.textContent = on ? "❚❚" : "▶";
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

  const viz = $("viz"), vx = viz.getContext("2d");
  let actx, analyser, data;
  function startViz() {
    try {
      if (!actx) {
        actx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = actx.createAnalyser(); analyser.fftSize = 128; analyser.smoothingTimeConstant = 0.85;
        data = new Uint8Array(analyser.frequencyBinCount);
        actx.createMediaElementSource(audio).connect(analyser); analyser.connect(actx.destination);
      }
      if (actx.state === "suspended") actx.resume();
    } catch {}
  }
  (function drawViz() {
    const w = (viz.width = viz.clientWidth * devicePixelRatio), h = (viz.height = viz.clientHeight * devicePixelRatio);
    vx.clearRect(0, 0, w, h);
    if (analyser) analyser.getByteFrequencyData(data);
    const n = 40, bw = w / n, g = vx.createLinearGradient(0, h, 0, 0);
    g.addColorStop(0, "#c0465f"); g.addColorStop(1, "#e6c08a"); vx.fillStyle = g;
    for (let i = 0; i < n; i++) {
      const v = data && !audio.paused ? data[i + 1] / 255 : 0.04;
      const bh = Math.max(2, v * h);
      vx.fillRect(i * bw + bw * 0.3, (h - bh) / 2, bw * 0.4, bh);
    }
    requestAnimationFrame(drawViz);
  })();

  /* ================= Почему ты ================= */
  const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
  C.reasons.forEach((text, i) => {
    const b = document.createElement("button");
    b.className = "card"; b.type = "button";
    b.innerHTML = `<div class="in"><div class="f"><b>${ROMAN[i] || i + 1}</b><small>открыть</small></div><div class="b"></div></div>`;
    b.querySelector(".b").textContent = text;
    b.onclick = (e) => { b.classList.toggle("flip"); if (b.classList.contains("flip")) bloom(e.clientX, e.clientY, 14); };
    $("reasons").appendChild(b);
  });

  /* ================= Письма ================= */
  let typer;
  C.letters.forEach((l) => {
    const b = document.createElement("button");
    b.className = "env"; b.type = "button";
    b.innerHTML = `<span class="seal">♥</span>…${l.when}`;
    b.onclick = () => {
      b.classList.add("opened");
      const box = $("letter"), p = $("letterText");
      box.hidden = false; box.style.animation = "none"; void box.offsetWidth; box.style.animation = "";
      $("letterHead").textContent = "открой, когда " + l.when;
      clearInterval(typer); p.textContent = ""; p.classList.remove("done");
      if (reduce) { p.textContent = l.text; p.classList.add("done"); return; }
      let k = 0;
      typer = setInterval(() => { p.textContent = l.text.slice(0, ++k); if (k >= l.text.length) { clearInterval(typer); p.classList.add("done"); } }, 38);
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    $("envs").appendChild(b);
  });

  /* ================= Игра ================= */
  const game = $("game"), score = $("score");
  let caught = 0, missed = 0, running = false, spawnT, drops = [], raf;
  const setScore = () => (score.innerHTML = `<span>поймано ${caught} из ${C.gameGoal}</span><span>мимо ${missed}</span>`);
  setScore();
  $("gameBtn").onclick = () => {
    caught = 0; missed = 0; setScore(); $("gameStart").hidden = true; $("prize").hidden = true;
    running = true; spawn(); loop();
  };
  function popText(x, y, t, col) {
    const s = document.createElement("span"); s.className = "pop-txt"; s.textContent = t; s.style.color = col;
    s.style.left = x + "px"; s.style.top = y + "px"; game.appendChild(s); setTimeout(() => s.remove(), 800);
  }
  function spawn() {
    if (!running) return;
    const r = Math.random(), type = r < 0.18 ? "cloud" : r < 0.6 ? "star" : "heart";
    const d = document.createElement("button");
    d.type = "button"; d.className = "drop " + type; d.textContent = type === "cloud" ? "☁" : type === "star" ? "✦" : "♥";
    const o = { el: d, bad: type === "cloud", x: rand(0, game.clientWidth - 56), y: -56, v: rand(1.4, 2.8) + caught * 0.06, wob: rand(0, 6) };
    d.style.left = o.x + "px";
    d.addEventListener("pointerdown", (e) => {
      e.preventDefault(); if (o.done) return; o.done = true;
      d.classList.add("got"); d.style.transform += " scale(2.2)";
      const gr = game.getBoundingClientRect();
      if (o.bad) { caught = Math.max(0, caught - 2); popText(e.clientX - gr.left, e.clientY - gr.top, "−2", "#b5949f"); }
      else { caught++; bloom(e.clientX, e.clientY, 8); popText(e.clientX - gr.left, e.clientY - gr.top, "+1", "#e6c08a"); }
      setScore(); setTimeout(() => d.remove(), 300);
      if (caught >= C.gameGoal) win();
    });
    game.appendChild(d); drops.push(o);
    spawnT = setTimeout(spawn, Math.max(380, 900 - caught * 25));
  }
  function loop() {
    const H = game.clientHeight;
    drops = drops.filter((o) => {
      if (o.done) return false;
      o.y += o.v; o.wob += 0.04;
      o.el.style.transform = `translate(${Math.sin(o.wob) * 14}px,${o.y}px)`;
      if (o.y > H) { o.el.remove(); if (!o.bad) { missed++; setScore(); } return false; }
      return true;
    });
    if (running) raf = requestAnimationFrame(loop);
  }
  function win() {
    running = false; clearTimeout(spawnT); cancelAnimationFrame(raf);
    drops.forEach((o) => o.el.remove()); drops = [];
    $("prize").hidden = false; $("prize").textContent = C.gamePrize;
    $("gameStart").hidden = false; $("gameBtn").textContent = "Ещё раз";
    petalRain(120);
  }

  /* ================= Финал ================= */
  $("finalQ").textContent = C.finalQuestion;
  const no = $("no"), qb = $("qbtns"), yes = $("yes");
  const NO_MSG = ["не получится", "попробуй ещё", "эта кнопка не работает", "точно?", "лучше «Да»", "я подожду"];
  let dodges = 0;
  // «Нет» отпрыгивает внутри блока, всегда видна и никогда не заезжает на «Да»
  let nx = 0, ny = 0, lastDodge = 0;
  const dodge = (e) => {
    if (e) e.preventDefault();
    const now = performance.now(); if (now - lastDodge < 200) return; lastDodge = now;
    dodges++;
    const box = qb.getBoundingClientRect(), yr = yes.getBoundingClientRect();
    const w = no.offsetWidth, h = no.offsetHeight, gap = 14;
    const baseL = box.left + no.offsetLeft, baseT = box.top + no.offsetTop;
    const nr = { left: baseL + nx, top: baseT + ny };
    for (let i = 0; i < 40; i++) {
      const L = rand(box.left, box.right - w), T = rand(box.top, box.bottom - h);
      const hitsYes = L < yr.right + gap && L + w > yr.left - gap && T < yr.bottom + gap && T + h > yr.top - gap;
      const tooClose = Math.hypot(L - nr.left, T - nr.top) < w * 0.8;
      if (!hitsYes && !tooClose) { nx = L - baseL; ny = T - baseT; break; }
    }
    no.style.transform = `translate(${nx}px,${ny}px)`;
    yes.style.boxShadow = `0 0 ${Math.min(36, 14 + dodges * 3)}px rgba(230,192,138,.55)`;
    $("finalA").textContent = NO_MSG[dodges % NO_MSG.length];
  };
  no.addEventListener("pointerenter", dodge);
  no.addEventListener("pointerdown", dodge);
  no.addEventListener("click", dodge);
  yes.addEventListener("click", (e) => {
    $("finalA").textContent = C.finalAnswer; no.hidden = true;
    bloom(e.clientX, e.clientY, 50); petalRain(260);
    whisper(e.clientX, e.clientY - 60, "навсегда");
  });
})();
