(() => {
  const C = window.CONFIG;
  const $ = (id) => document.getElementById(id);
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
  };

  /* ---------- Вход ---------- */
  const len = C.password.length;
  const pin = $("pin"), input = $("pinInput");
  $("hint").textContent = "подсказка: " + C.passwordHint;
  for (let i = 0; i < len; i++) pin.appendChild(document.createElement("span"));
  const drawPin = () => {
    [...pin.children].forEach((s, i) => {
      s.textContent = input.value[i] ? "•" : "";
      s.classList.toggle("cur", i === Math.min(input.value.length, len - 1));
    });
  };
  pin.onclick = () => input.focus();
  input.addEventListener("input", () => {
    input.value = input.value.replace(/\D/g, "").slice(0, len);
    $("gateErr").hidden = true;
    drawPin();
    if (input.value.length === len) check();
  });
  $("gateForm").addEventListener("submit", (e) => { e.preventDefault(); check(); });
  function check() {
    if (input.value === C.password) { store.set("karamelka-ok", "1"); open(); hearts(80); }
    else {
      $("gateErr").hidden = false;
      const box = $("gateForm"); box.classList.remove("shake"); void box.offsetWidth; box.classList.add("shake");
      input.value = ""; drawPin();
    }
  }
  function open() { $("gate").hidden = true; $("site").hidden = false; }
  if (store.get("karamelka-ok") === "1") open(); else { drawPin(); setTimeout(() => input.focus(), 300); }

  /* ---------- Счётчик ---------- */
  const since = new Date(C.togetherSince).getTime();
  const pad = (n) => String(n).padStart(2, "0");
  function tick() {
    const t = Math.max(0, Math.floor((Date.now() - since) / 1000));
    $("cD").textContent = Math.floor(t / 86400);
    $("cH").textContent = pad(Math.floor((t % 86400) / 3600));
    $("cM").textContent = pad(Math.floor((t % 3600) / 60));
    $("cS").textContent = pad(t % 60);
  }
  tick(); setInterval(tick, 1000);

  /* ---------- Плеер ---------- */
  const audio = $("audio"), list = $("tracks"), vinyl = $("vinyl"), playBtn = $("play"), seek = $("seek");
  let songs = [], cur = -1;
  const AUDIO = /\.(mp3|m4a|aac|ogg|opus|wav|flac)$/i;
  const prettify = (file) => decodeURIComponent(file).replace(AUDIO, "").replace(/^\d+[\s._-]+/, "").replace(/_/g, " ").trim();
  const fmt = (s) => !isFinite(s) ? "0:00" : Math.floor(s / 60) + ":" + pad(Math.floor(s % 60));

  async function loadSongs() {
    let files = [];
    try {
      const r = await fetch("music/", { headers: { Accept: "application/json" } });
      const txt = await r.text();
      try { files = JSON.parse(txt).filter((f) => f.type === "file").map((f) => f.name); } // nginx autoindex json
      catch { files = [...txt.matchAll(/href="([^"?]+)"/g)].map((m) => decodeURIComponent(m[1])); } // обычный html-листинг
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

    songs = files.map((f) => {
      const base = f.replace(AUDIO, "");
      return { src: "music/" + encodeURIComponent(f), title: prettify(f),
        why: captions[base.toLowerCase()] || captions[prettify(f).toLowerCase()] || "" };
    });
    renderList();
  }
  function renderList() {
    list.innerHTML = "";
    if (!songs.length) { list.innerHTML = '<li class="empty">Песни скоро появятся 🎶</li>'; return; }
    songs.forEach((s, i) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="n">${pad(i + 1)}</span><span class="name"></span><span class="why"></span>`;
      li.querySelector(".name").textContent = s.title;
      li.querySelector(".why").textContent = s.why;
      li.onclick = () => (i === cur ? toggle() : play(i));
      list.appendChild(li);
    });
  }
  function play(i) {
    if (!songs.length) return;
    cur = (i + songs.length) % songs.length;
    const s = songs[cur];
    audio.src = s.src; audio.play().catch(() => {});
    $("nowTitle").textContent = s.title; $("nowWhy").textContent = s.why;
    [...list.children].forEach((li, j) => li.classList.toggle("active", j === cur));
  }
  function toggle() { if (cur < 0) return play(0); audio.paused ? audio.play() : audio.pause(); }
  playBtn.onclick = toggle;
  $("next").onclick = () => play(cur + 1);
  $("prev").onclick = () => (audio.currentTime > 3 ? (audio.currentTime = 0) : play(cur - 1));
  audio.onplay = () => { vinyl.classList.add("on"); playBtn.textContent = "❚❚"; playBtn.setAttribute("aria-label", "Пауза"); };
  audio.onpause = () => { vinyl.classList.remove("on"); playBtn.textContent = "▶"; playBtn.setAttribute("aria-label", "Играть"); };
  audio.onended = () => play(cur + 1);
  audio.ontimeupdate = () => {
    $("tCur").textContent = fmt(audio.currentTime); $("tDur").textContent = fmt(audio.duration);
    if (audio.duration) seek.value = (audio.currentTime / audio.duration) * 1000;
  };
  seek.oninput = () => { if (audio.duration) audio.currentTime = (seek.value / 1000) * audio.duration; };
  loadSongs();

  /* ---------- Почему ты ---------- */
  const sweets = ["🍬", "🍭", "🧁", "🍓", "🍫", "🍯", "🍩", "🍒"];
  C.reasons.forEach((text, i) => {
    const b = document.createElement("button");
    b.className = "card"; b.type = "button";
    b.innerHTML = `<div class="in"><div class="f">${sweets[i % sweets.length]}</div><div class="b"></div></div>`;
    b.querySelector(".b").textContent = text;
    b.onclick = () => b.classList.toggle("flip");
    $("reasons").appendChild(b);
  });

  /* ---------- Письма ---------- */
  C.letters.forEach((l, i) => {
    const b = document.createElement("button");
    b.className = "env"; b.type = "button";
    b.innerHTML = `…${l.when}<small>письмо ${i + 1}</small>`;
    b.onclick = () => {
      b.classList.add("opened");
      const box = $("letter"); box.hidden = false;
      box.innerHTML = ""; const h = document.createElement("b"); h.textContent = "открой, когда " + l.when;
      box.append(h, document.createTextNode(l.text));
      box.style.animation = "none"; void box.offsetWidth; box.style.animation = "";
    };
    $("envs").appendChild(b);
  });

  /* ---------- Игра ---------- */
  const game = $("game"), score = $("score");
  let caught = 0, missed = 0, running = false, spawnT, drops = [], raf;
  const good = ["🍬", "🍭", "🍯", "🍫", "💗", "🍓"];
  const setScore = () => (score.innerHTML = `<span>🍬 ${caught} / ${C.gameGoal}</span><span>промахи: ${missed}</span>`);
  setScore();
  $("gameBtn").onclick = () => {
    caught = 0; missed = 0; setScore(); $("gameStart").hidden = true; $("prize").hidden = true;
    running = true; spawn(); loop();
  };
  function spawn() {
    if (!running) return;
    const bad = Math.random() < 0.18;
    const d = document.createElement("button");
    d.type = "button"; d.className = "drop"; d.textContent = bad ? "💔" : good[(Math.random() * good.length) | 0];
    const W = game.clientWidth;
    const o = { el: d, bad, x: Math.random() * (W - 50), y: -50, v: 1.4 + Math.random() * 1.6 + caught * 0.05 };
    d.style.left = o.x + "px";
    d.addEventListener("pointerdown", (e) => {
      e.preventDefault(); if (o.done) return; o.done = true;
      d.classList.add("got"); d.style.transform += " scale(1.8)";
      if (bad) { caught = Math.max(0, caught - 2); } else { caught++; burst(e.clientX, e.clientY); }
      setScore(); setTimeout(() => d.remove(), 250);
      if (caught >= C.gameGoal) win();
    });
    game.appendChild(d); drops.push(o);
    spawnT = setTimeout(spawn, Math.max(380, 900 - caught * 25));
  }
  function loop() {
    const H = game.clientHeight;
    drops = drops.filter((o) => {
      if (o.done) return false;
      o.y += o.v; o.el.style.transform = `translateY(${o.y}px) rotate(${o.y}deg)`;
      if (o.y > H) { o.el.remove(); if (!o.bad) { missed++; setScore(); } return false; }
      return true;
    });
    if (running) raf = requestAnimationFrame(loop);
  }
  function win() {
    running = false; clearTimeout(spawnT); cancelAnimationFrame(raf);
    drops.forEach((o) => o.el.remove()); drops = [];
    const p = $("prize"); p.hidden = false; p.textContent = "🏆 " + C.gamePrize;
    $("gameStart").hidden = false; $("gameBtn").textContent = "Ещё раз";
    hearts(120);
  }

  /* ---------- Финал ---------- */
  $("finalQ").textContent = C.finalQuestion;
  const no = $("no"), qb = $("qbtns");
  let dodges = 0;
  const dodge = (e) => {
    if (e) e.preventDefault();
    dodges++;
    const r = qb.getBoundingClientRect(), maxX = Math.min(r.width / 2 - 50, 160);
    no.style.transform = `translate(${(Math.random() * 2 - 1) * maxX}px,${(Math.random() * 2 - 1) * 40}px) scale(${Math.max(0.5, 1 - dodges * 0.06)})`;
    const msgs = ["не-а", "попробуй ещё", "кнопка сломалась", "точно?", "нажми лучше «Да»"];
    $("finalA").textContent = msgs[dodges % msgs.length];
  };
  no.addEventListener("pointerenter", dodge);
  no.addEventListener("pointerdown", dodge);
  no.addEventListener("click", dodge);
  $("yes").onclick = () => { $("finalA").textContent = C.finalAnswer; no.hidden = true; hearts(220); };

  /* ---------- Сердечки / частицы ---------- */
  const cv = $("fx"), cx = cv.getContext("2d");
  let parts = [], fxOn = false;
  const resize = () => { cv.width = innerWidth * devicePixelRatio; cv.height = innerHeight * devicePixelRatio; };
  addEventListener("resize", resize); resize();
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const icons = ["💗", "💖", "💕", "🍬", "✨"];
  function hearts(n) {
    if (reduce) return;
    for (let i = 0; i < n; i++) parts.push({ x: Math.random() * innerWidth, y: innerHeight + Math.random() * 200,
      vx: (Math.random() - 0.5) * 2, vy: -(4 + Math.random() * 6), g: 0.06, s: 16 + Math.random() * 22,
      ch: icons[(Math.random() * icons.length) | 0], life: 1 });
    runFx();
  }
  function burst(x, y) {
    if (reduce) return;
    for (let i = 0; i < 8; i++) { const a = Math.random() * Math.PI * 2;
      parts.push({ x, y, vx: Math.cos(a) * 3, vy: Math.sin(a) * 3 - 1, g: 0.12, s: 12 + Math.random() * 8, ch: "✨", life: 0.8 }); }
    runFx();
  }
  function runFx() { if (fxOn) return; fxOn = true; requestAnimationFrame(frame); }
  function frame() {
    const d = devicePixelRatio; cx.setTransform(d, 0, 0, d, 0, 0); cx.clearRect(0, 0, innerWidth, innerHeight);
    parts = parts.filter((p) => {
      p.x += p.vx; p.y += p.vy; p.vy += p.g; p.life -= 0.006;
      cx.globalAlpha = Math.max(0, Math.min(1, p.life)); cx.font = p.s + "px serif"; cx.fillText(p.ch, p.x, p.y);
      return p.life > 0 && p.y < innerHeight + 60;
    });
    if (parts.length) requestAnimationFrame(frame); else { fxOn = false; cx.clearRect(0, 0, innerWidth, innerHeight); }
  }
})();
