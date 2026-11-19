/**
 * main.js - CineStream Multi-Language Frontend Controller
 * Powered by GSAP 3 & ScrollTrigger
 * Features:
 *   - 6 Languages: English, Hindi, Kannada, Tamil, Telugu, Malayalam
 *   - Native script and transliterated search with auto-detection
 *   - Voice search via Web Speech API with regional accents (kn-IN, hi-IN, etc.)
 *   - Title script toggle (Native script vs English transliteration)
 *   - Dynamic Hero headline transitions per regional industry
 *   - Hybrid ML recommendations & Cross-Language Picks
 *   - Interactive Model Insights with per-language evaluation and PCA plots
 */

// ============================================================
// ============================================================
// GLOBAL STATE
// ============================================================
const state = {
  userId: "user_" + Math.random().toString(36).slice(2, 8),
  ratings: {},         // { movieId: starCount }
  currentPage: 1,
  currentGenre: "All",
  currentLang: "all",  // "all", "en", "hi", "kn", "ta", "te", "ml"
  titleMode: "native", // "native" or "en"
  epicAllLangs: false,
  activeTrailerLang: "hi",
  trailerVolume: parseInt(localStorage.getItem("cinestream_volume") || "100"),
  isMuted: localStorage.getItem("cinestream_muted") === "true",
  recRefreshPending: false,
  searchDebounce: null,
  speechRecognition: null,

  // 3D Carousel & Full-Bleed Hero Banner State
  featuredMovies: [],
  activeCardIndex: 0,
  isTransitioning: false,
  hasInteracted: false,
  isTrailerMode: false,
  hoverIntentTimer: null,
  ambientPreviewTimer: null,
  watchlist: new Map(),
  toastTimer: null,
};

const LANG_DISPLAY_NAMES = {
  all: "Global",
  en: "English",
  hi: "Hindi",
  kn: "Kannada",
  ta: "Tamil",
  te: "Telugu",
  ml: "Malayalam",
  ja: "Japanese"
};

const LANG_VOICE_TAGS = {
  all: "en-IN", en: "en-IN", hi: "hi-IN", kn: "kn-IN", ta: "ta-IN", te: "te-IN", ml: "ml-IN"
};

// ============================================================
// UTILITIES
// ============================================================

// ============================================================
// WATCHLIST INTEGRATION & ANIMATIONS
// ============================================================
function showToastWithUndo(msg, onUndo) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.innerHTML = `
    <span>${escapeHtml(msg)}</span>
    <button class="toast-undo-btn" id="toastUndoBtn">Undo</button>
  `;
  toast.className = "toast show";
  clearTimeout(state.toastTimer);
  const undoBtn = document.getElementById("toastUndoBtn");
  if (undoBtn) {
    undoBtn.onclick = () => {
      toast.classList.remove("show");
      if (typeof onUndo === "function") onUndo();
    };
  }
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 4000);
}

function getBookmarkBtnHtml(id, mediaType = "movie", extraClass = "") {
  const key = `${mediaType}:${id}`;
  const isSaved = state.watchlist && state.watchlist.has(key);
  const icon = isSaved ? "&#128278;" : "+";
  const label = isSaved ? "Remove from Watchlist" : "Add to Watchlist";
  const savedClass = isSaved ? "saved" : "";
  return `<button class="card-bookmark-btn ${savedClass} ${extraClass}" data-id="${id}" data-type="${mediaType}" aria-label="${label}" title="${label}"><span class="bm-icon">${icon}</span></button>`;
}

function flyPosterToNavbar(startEl, posterSrc) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const target = document.getElementById("navWatchlistLink");
  if (!target || !startEl) return;
  const startRect = startEl.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();

  const flyer = document.createElement("div");
  flyer.className = "flying-poster";
  flyer.style.cssText = `
    position: fixed;
    left: ${startRect.left + startRect.width / 2 - 25}px;
    top: ${startRect.top + startRect.height / 2 - 35}px;
    width: 50px;
    height: 70px;
    border-radius: 6px;
    background: #111 url('${posterSrc || ""}') center/cover no-repeat;
    box-shadow: 0 8px 24px rgba(249,226,125,0.4);
    z-index: 99999;
    pointer-events: none;
  `;
  document.body.appendChild(flyer);
  gsap.to(flyer, {
    left: targetRect.left + targetRect.width / 2 - 10,
    top: targetRect.top + targetRect.height / 2 - 10,
    width: 20,
    height: 20,
    opacity: 0.1,
    duration: 0.75,
    ease: "power2.inOut",
    onComplete: () => {
      flyer.remove();
      const badge = document.getElementById("navWatchlistBadge");
      if (badge) {
        gsap.fromTo(badge, { scale: 1.5, color: "#f9e27d" }, { scale: 1, color: "#fff", duration: 0.35, ease: "back.out(2)" });
      }
    }
  });
}

function updateWatchlistUI() {
  const count = state.watchlist.size;
  const badge = document.getElementById("navWatchlistBadge");
  if (badge) {
    const prev = parseInt(badge.textContent || "0");
    badge.textContent = count;
    if (prev !== count && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      gsap.fromTo(badge, { scale: 1.4 }, { scale: 1, duration: 0.3, ease: "back.out(2)" });
    }
  }

  // Sync all bookmark buttons across cards
  document.querySelectorAll(".card-bookmark-btn").forEach(btn => {
    const key = `${btn.dataset.type}:${btn.dataset.id}`;
    const isSaved = state.watchlist.has(key);
    btn.classList.toggle("saved", isSaved);
    btn.setAttribute("aria-label", isSaved ? "Remove from Watchlist" : "Add to Watchlist");
    btn.setAttribute("title", isSaved ? "Remove from Watchlist" : "Add to Watchlist");
    const icon = btn.querySelector(".bm-icon");
    if (icon) icon.innerHTML = isSaved ? "&#128278;" : "+";
  });

  // Sync hero button if active movie is selected
  const activeMovie = state.featuredMovies[state.activeCardIndex];
  if (activeMovie) {
    updateHeroWatchlistBtn(activeMovie);
  }
}

function updateHeroWatchlistBtn(movie) {
  const heroBtn = document.getElementById("heroAddListBtn");
  if (!heroBtn || !movie) return;
  const mid = movie.tmdb_id || movie.id || movie.movieId;
  const key = `movie:${mid}`;
  const isSaved = state.watchlist.has(key);
  heroBtn.classList.toggle("saved", isSaved);
  const textSpan = document.getElementById("heroAddListText");
  if (textSpan) textSpan.textContent = isSaved ? "In Watchlist" : "Add to Watchlist";
  const iconSpan = heroBtn.querySelector(".btn-plus-icon");
  if (iconSpan) iconSpan.innerHTML = isSaved ? "&#128278;" : "+";
}

async function toggleWatchlist(itemData, triggerEl) {
  const mid = parseInt(itemData.tmdb_id || itemData.id || itemData.movieId);
  if (!mid) return;
  const mediaType = String(itemData.media_type || "movie").toLowerCase();
  const key = `${mediaType}:${mid}`;
  const displayTitle = getDisplayTitle(itemData) || itemData.title || "Movie";
  const posterSrc = itemData.poster_url || itemData.poster_large_url || "";

  if (state.watchlist.has(key)) {
    // Remove
    state.watchlist.delete(key);
    updateWatchlistUI();
    showToastWithUndo(`Removed "${displayTitle}" from Watchlist`, () => toggleWatchlist(itemData, triggerEl));
    try {
      await fetch(`/api/watchlist/${mediaType}/${mid}`, { method: "DELETE" });
    } catch (err) {
      console.error("Watchlist remove error:", err);
    }
  } else {
    // Add
    state.watchlist.set(key, {
      tmdb_id: mid,
      media_type: mediaType,
      title: displayTitle,
      poster_url: posterSrc,
      release_year: itemData.year || itemData.release_year || "",
      lang: itemData.lang || "en",
      genres: itemData.genres || "",
      cluster_name: itemData.clusterName || itemData.cluster_name || ""
    });
    updateWatchlistUI();

    // Pop & spin animation
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const icon = triggerEl?.querySelector(".bm-icon") || triggerEl?.querySelector(".btn-plus-icon");
      if (icon) {
        gsap.fromTo(icon, { rotate: -90, scale: 0.5 }, { rotate: 0, scale: 1, duration: 0.4, ease: "back.out(2)" });
      }
      flyPosterToNavbar(triggerEl, posterSrc);
    }

    showToastWithUndo(`Added "${displayTitle}" to Watchlist`, () => toggleWatchlist(itemData, triggerEl));

    try {
      await fetch("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tmdb_id: mid,
          media_type: mediaType,
          title: displayTitle,
          poster_url: posterSrc,
          release_year: itemData.year || itemData.release_year || "",
          lang: itemData.lang || "en",
          genres: itemData.genres || "",
          cluster_name: itemData.clusterName || itemData.cluster_name || ""
        })
      });
    } catch (err) {
      console.error("Watchlist add error:", err);
    }
  }
}

async function initWatchlist() {
  // Delegated bookmark button clicks
  document.body.addEventListener("click", (e) => {
    const bmBtn = e.target.closest(".card-bookmark-btn");
    if (!bmBtn) return;
    e.preventDefault();
    e.stopPropagation();
    const id = bmBtn.dataset.id;
    const mediaType = bmBtn.dataset.type || "movie";
    const card = bmBtn.closest(".poster-card, .rec-card, .carousel-slot, .search-result-item");
    const movieData = {
      tmdb_id: id,
      movieId: id,
      media_type: mediaType,
      title: bmBtn.dataset.title || card?.querySelector(".poster-title, .rec-movie-title, .rec-title, .card-movie-title")?.textContent?.trim() || "Movie",
      poster_url: bmBtn.dataset.poster || card?.querySelector("img")?.src || "",
      year: bmBtn.dataset.year || card?.querySelector(".poster-meta, .rec-movie-sub")?.textContent?.match(/\d{4}/)?.[0] || "",
      lang: bmBtn.dataset.lang || state.currentLang || "en",
      cluster_name: bmBtn.dataset.cluster || card?.querySelector(".poster-cluster-tag, .rec-cluster-tag")?.textContent?.trim() || ""
    };
    toggleWatchlist(movieData, bmBtn);
  });

  try {
    const res = await fetch("/api/watchlist");
    const data = await res.json();
    if (data.items) {
      state.watchlist.clear();
      data.items.forEach(it => {
        state.watchlist.set(`${it.media_type || "movie"}:${it.tmdb_id}`, it);
      });
      updateWatchlistUI();
    }
  } catch (err) {
    console.error("Failed to load initial watchlist:", err);
  }
}

function showToast(msg, type = "success") {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.className = `toast show ${type}`;
  setTimeout(() => toast.classList.remove("show"), 3200);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function ensureEnglish(text, fallback = "") {
  if (!text) return fallback;
  const NON_LATIN_RE = /[\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u3040-\u30FF\u4E00-\u9FFF]/;
  return NON_LATIN_RE.test(text) ? fallback : text;
}

function getDisplayTitle(movie) {
  if (!movie) return "";
  const candidate = movie.title_en || movie.title_clean || movie.title || movie.name || "";
  const clean = ensureEnglish(candidate, movie.title_en || "");
  return clean || movie.title_en || movie.title || "Movie";
}

function getScriptFontClass(lang) {
  return "";
}

function getMovieTrailerId(movie) {
  if (!movie || !movie.trailers) return "";

  // 1. Check selected audio language
  const audio = movie.selected_audio;
  if (audio && movie.trailers[audio] && typeof movie.trailers[audio] === "string" && movie.trailers[audio].trim()) {
    return movie.trailers[audio].trim();
  }

  // 2. Check movie default or original language
  if (movie.default_lang && movie.trailers[movie.default_lang] && typeof movie.trailers[movie.default_lang] === "string" && movie.trailers[movie.default_lang].trim()) {
    return movie.trailers[movie.default_lang].trim();
  }
  if (movie.original_lang && movie.trailers[movie.original_lang] && typeof movie.trailers[movie.original_lang] === "string" && movie.trailers[movie.original_lang].trim()) {
    return movie.trailers[movie.original_lang].trim();
  }

  // 3. Fallback priority: Hindi -> Kannada -> English -> Telugu -> Tamil -> Malayalam
  const priority = ["hi", "kn", "en", "te", "ta", "ml"];
  for (const l of priority) {
    if (movie.trailers[l] && typeof movie.trailers[l] === "string" && movie.trailers[l].trim()) {
      return movie.trailers[l].trim();
    }
  }

  // 4. Any valid non-empty string in trailers
  for (const k of Object.keys(movie.trailers)) {
    if (movie.trailers[k] && typeof movie.trailers[k] === "string" && movie.trailers[k].trim()) {
      return movie.trailers[k].trim();
    }
  }

  return "";
}

function handlePosterError(imgEl, title, year) {
  const parent = imgEl.parentElement;
  if (!parent) return;
  const fallback = document.createElement("div");
  fallback.className = "poster-fallback";
  fallback.innerHTML = `
    <div class="poster-fallback-title">${escapeHtml(title)}</div>
    <div class="poster-fallback-year">${year || ""}</div>
  `;
  imgEl.remove();
  parent.appendChild(fallback);
}

// ============================================================
// GSAP INTRO ANIMATIONS
// ============================================================
function runIntroAnimation() {
  if (!window.gsap) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  try {
    if (window.ScrollTrigger) gsap.registerPlugin(ScrollTrigger);
    const tl = gsap.timeline({ delay: 0.15 });

    const safeAnimate = (selector, anim) => {
      if (document.querySelector(selector)) {
        tl.from(selector, anim, "-=0.2");
      }
    };

    if (document.querySelector(".navbar")) {
      tl.from(".navbar", { y: -60, opacity: 0, duration: 0.6, ease: "power3.out" });
    }
    safeAnimate(".spotlight-badge-row", { y: 20, opacity: 0, duration: 0.45, ease: "power3.out" });
    safeAnimate(".hero-movie-title", { y: 30, opacity: 0, duration: 0.65, ease: "power4.out" });
    safeAnimate(".hero-movie-meta", { y: 20, opacity: 0, duration: 0.45, ease: "power3.out" });
    safeAnimate(".hero-movie-overview", { y: 20, opacity: 0, duration: 0.45, ease: "power3.out" });
    safeAnimate(".hero-action-group button, .hero-action-group a", { y: 20, opacity: 0, duration: 0.4, stagger: 0.1, ease: "power3.out" });
    safeAnimate(".carousel-stage-container", { scale: 0.92, opacity: 0, duration: 0.8, ease: "power3.out" });
    safeAnimate(".carousel-dots-wrapper, .sound-interaction-hint", { y: 15, opacity: 0, duration: 0.4, stagger: 0.1, ease: "power2.out" });

    if (window.ScrollTrigger) {
      if (document.querySelector(".features-grid")) {
        gsap.from(".feature-card", {
          scrollTrigger: { trigger: ".features-grid", start: "top 80%" },
          y: 50, opacity: 0, duration: 0.65, stagger: 0.14, ease: "power3.out"
        });
      }
      if (document.querySelector(".platform-split")) {
        gsap.from(".platform-text", {
          scrollTrigger: { trigger: ".platform-split", start: "top 75%" },
          x: -40, opacity: 0, duration: 0.75, ease: "power3.out"
        });
        gsap.from(".platform-visual", {
          scrollTrigger: { trigger: ".platform-split", start: "top 75%" },
          x: 40, opacity: 0, duration: 0.75, ease: "power3.out"
        });
      }
      if (document.querySelector(".newsletter")) {
        gsap.from(".newsletter-box", {
          scrollTrigger: { trigger: ".newsletter", start: "top 80%" },
          y: 35, opacity: 0, duration: 0.65, ease: "power3.out"
        });
      }
    }
  } catch (err) {
    console.warn("[runIntroAnimation error]", err);
  }
}

// ============================================================
// LANGUAGE SWITCHER
// ============================================================
function initLanguageSwitcher() {
  const pills = document.querySelectorAll(".lang-pill");
  pills.forEach(pill => {
    pill.addEventListener("click", async () => {
      pills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");

      const lang = pill.dataset.lang;
      state.currentLang = lang;
      state.currentPage = 1;

      // Update hero carousel to show featured movies for this language
      await loadFeaturedMovies(lang);

      // Refresh streaming browse grid and recommendations (keeping headings in English)
      loadMovies(state.currentGenre, 1, true);
      loadRecommendations();
      const activeMovie = state.featuredMovies[state.activeCardIndex];
      if (activeMovie) {
        loadActiveMovieRecommendations(activeMovie);
      }

      // Sync modal selector
      const modalSelect = document.getElementById("modalLangSelect");
      if (modalSelect) modalSelect.value = lang;
    });
  });

  // Script Toggle (Native vs English)
  const nativeBtn = document.getElementById("scriptNativeBtn");
  const enBtn = document.getElementById("scriptEnBtn");

  nativeBtn?.addEventListener("click", () => {
    nativeBtn.classList.add("active");
    enBtn?.classList.remove("active");
    state.titleMode = "native";
    rerenderCurrentTitles();
  });

  enBtn?.addEventListener("click", () => {
    enBtn.classList.add("active");
    nativeBtn?.classList.remove("active");
    state.titleMode = "en";
    rerenderCurrentTitles();
  });
}

function rerenderCurrentTitles() {
  document.querySelectorAll(".poster-card, .rec-card, .carousel-card").forEach(card => {
    const titleEl = card.querySelector(".poster-title, .rec-title, .carousel-card-title");
    if (!titleEl) return;
    const native = card.dataset.titleNative;
    const en = card.dataset.titleEn;
    if (state.titleMode === "en" && en) {
      titleEl.textContent = en;
    } else if (native) {
      titleEl.textContent = native;
    }
  });
}

// ============================================================
// SEARCH ENGINE & VOICE SEARCH
// ============================================================
function initSearch() {
  const input = document.getElementById("searchInput");
  const dropdown = document.getElementById("searchResultsDropdown");
  const voiceBtn = document.getElementById("voiceSearchBtn");

  if (!input || !dropdown) return;

  // Real-time search with debouncing (220ms)
  input.addEventListener("input", () => {
    clearTimeout(state.searchDebounce);
    const q = input.value.trim();
    if (!q) {
      dropdown.style.display = "none";
      dropdown.innerHTML = "";
      return;
    }

    state.searchDebounce = setTimeout(async () => {
      try {
        const langParam = state.currentLang !== "all" ? `&lang=${state.currentLang}` : "";
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}${langParam}`);
        const data = await res.json();
        renderSearchResults(data, dropdown);
      } catch (err) {
        console.error("Search error:", err);
      }
    }, 220);
  });

  // Close dropdown on outside click
  document.addEventListener("click", e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = "none";
    }
  });

  input.addEventListener("focus", () => {
    if (dropdown.children.length > 0 && input.value.trim()) {
      dropdown.style.display = "block";
    }
  });

  // Voice Search setup
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    state.speechRecognition = new SpeechRecognition();
    state.speechRecognition.continuous = false;
    state.speechRecognition.interimResults = false;

    voiceBtn?.addEventListener("click", () => {
      try {
        const langCode = LANG_VOICE_TAGS[state.currentLang] || "en-IN";
        state.speechRecognition.lang = langCode;
        voiceBtn.classList.add("listening");
        state.speechRecognition.start();
        showToast(`Listening in ${langCode}... Speak now 🎤`, "success");
      } catch (err) {
        console.warn("Speech recognition error:", err);
        voiceBtn.classList.remove("listening");
      }
    });

    state.speechRecognition.onresult = e => {
      const transcript = e.results[0][0].transcript;
      input.value = transcript;
      voiceBtn.classList.remove("listening");
      input.dispatchEvent(new Event("input"));
    };

    state.speechRecognition.onerror = () => {
      voiceBtn.classList.remove("listening");
      showToast("Voice input ended or microphone unavailable.", "error");
    };

    state.speechRecognition.onend = () => {
      voiceBtn.classList.remove("listening");
    };
  } else {
    if (voiceBtn) voiceBtn.title = "Voice search not supported in this browser";
  }
}

function renderSearchResults(data, dropdown) {
  dropdown.innerHTML = "";
  if (!data.results || data.results.length === 0) {
    dropdown.innerHTML = `<div style="padding:16px;color:#777;text-align:center;font-size:0.85rem">No movies found matching "${escapeHtml(data.query)}"</div>`;
    dropdown.style.display = "block";
    return;
  }

  // Script detection banner
  if (data.detected_script) {
    const banner = document.createElement("div");
    banner.className = "search-detected-info";
    banner.innerHTML = `&#10024; Detected Script: <strong>${escapeHtml(data.detected_script.toUpperCase())}</strong> (Auto-routing)`;
    dropdown.appendChild(banner);
  }

  data.results.forEach(m => {
    const item = document.createElement("div");
    item.className = "search-result-item";
    const posterSrc = m.poster_url || m.poster_large_url || "";
    const displayTitle = getDisplayTitle(m);
    const subTitle = (m.title_en && m.title_en !== displayTitle) ? m.title_en : (m.genres || "");

    item.innerHTML = `
      <img src="${posterSrc}" alt="${escapeHtml(displayTitle)}" class="search-result-poster"
           onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'38\\' height=\\'54\\' fill=\\'%2325252d\\'><rect width=\\'100%\\' height=\\'100%\\'/></svg>'" />
      <div class="search-result-info">
        <div class="search-result-title ${getScriptFontClass(m.lang)}">${escapeHtml(displayTitle)}</div>
        <div class="search-result-sub">${m.year || ""} &middot; ${escapeHtml(subTitle)}</div>
      </div>
      <span class="search-result-badge">${escapeHtml(m.language_name || LANG_DISPLAY_NAMES[m.lang] || "English")}</span>
    `;

    item.addEventListener("click", () => {
      dropdown.style.display = "none";
      loadSimilarMovies(m);
    });

    dropdown.appendChild(item);
  });

  dropdown.style.display = "block";
}

async function loadSimilarMovies(movie) {
  try {
    const res = await fetch(`/api/similar?movieId=${movie.movieId}&lang=${state.currentLang}`);
    const data = await res.json();
    if (data.similar && data.similar.length > 0) {
      renderRecommendations(data.similar, false);
      const recHeader = document.querySelector("#recommended .section-title");
      const engTitle = movie.title_en || movie.title_clean || movie.title || getDisplayTitle(movie);
      if (recHeader) recHeader.textContent = `More Like "${engTitle}"`;
      document.getElementById("recommended")?.scrollIntoView({ behavior: "smooth" });
      showToast(`Showing recommendations similar to "${engTitle}"`);
    }
  } catch (err) {
    console.error("Similar movies error:", err);
  }
}

// ============================================================
// CANVAS EMBER / DIYA SPARK PARTICLES
// ============================================================
function initEmberCanvas() {
  const canvas = document.getElementById("emberCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let animId = null;
  let particles = [];
  const particleCount = 42;

  function resize() {
    const parent = canvas.parentElement;
    canvas.width = parent ? parent.offsetWidth : window.innerWidth;
    canvas.height = parent ? parent.offsetHeight : 640;
  }
  resize();
  window.addEventListener("resize", resize);

  function createParticle(randomY = false) {
    return {
      x: Math.random() * canvas.width,
      y: randomY ? Math.random() * canvas.height : canvas.height + Math.random() * 20,
      radius: Math.random() * 2.2 + 0.8,
      speedY: Math.random() * 0.8 + 0.35,
      speedX: (Math.random() - 0.5) * 0.5,
      opacity: Math.random() * 0.7 + 0.25,
      hue: Math.floor(Math.random() * 25 + 35), // warm golden / amber 35-60
      wobble: Math.random() * Math.PI * 2,
      wobbleSpeed: Math.random() * 0.03 + 0.01
    };
  }

  for (let i = 0; i < particleCount; i++) {
    particles.push(createParticle(true));
  }

  function loop() {
    if (document.hidden) {
      animId = requestAnimationFrame(loop);
      return;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    particles.forEach(p => {
      p.y -= p.speedY;
      p.wobble += p.wobbleSpeed;
      p.x += p.speedX + Math.sin(p.wobble) * 0.35;

      if (p.y < -10 || p.x < -10 || p.x > canvas.width + 10) {
        Object.assign(p, createParticle(false));
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 95%, 65%, ${p.opacity})`;
      ctx.shadowColor = `hsla(${p.hue}, 100%, 70%, 0.8)`;
      ctx.shadowBlur = 8;
      ctx.fill();
    });

    animId = requestAnimationFrame(loop);
  }

  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    loop();
  }
}

// ============================================================
// FIX 1: ANIMATED OPENING SCREEN CONTROLLER
// ============================================================
let openingParticleAnimId = null;
let isOpeningScreenDismissed = false;

let introWatchdogTimer = null;

function initOpeningScreen(forceReplay = false) {
  const openingEl = document.getElementById("openingScreen");
  if (!openingEl) return;

  // Check URL param ?nointro=1 or sessionStorage
  const urlParams = new URLSearchParams(window.location.search);
  const skipParam = urlParams.get("nointro") === "1";
  const alreadySeen = sessionStorage.getItem("cinestream_intro_seen") === "true";

  if ((skipParam || alreadySeen) && !forceReplay) {
    dismissOpeningScreen(false, true); // immediate dismissal without animation
    return;
  }

  isOpeningScreenDismissed = false;
  openingEl.classList.remove("dismissed");
  openingEl.style.display = "flex";
  document.body.style.overflow = "hidden"; // Lock scrolling during intro

  // Watchdog: If intro has not finished within 7 seconds, force-dismiss it
  clearTimeout(introWatchdogTimer);
  introWatchdogTimer = setTimeout(() => {
    if (!isOpeningScreenDismissed) {
      console.warn("[Intro Watchdog] 7s elapsed. Force-dismissing intro.");
      dismissOpeningScreen(false, true);
    }
  }, 7000);

  // Check if GSAP is available
  const hasGsap = typeof window.gsap !== "undefined";
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // If GSAP is missing or error occurs, fail-safe immediately
  if (!hasGsap) {
    console.warn("[Intro] GSAP not available. Falling back to quick static intro.");
    setTimeout(() => {
      dismissOpeningScreen(false);
    }, 1800);
    attachIntroTriggers();
    return;
  }

  // GSAP is present: add js-ready class to <html> so CSS hides elements for timeline
  document.documentElement.classList.add("js-ready");

  // Particle Canvas Background (safe)
  try {
    const canvas = document.getElementById("openingParticleCanvas");
    if (canvas && !prefersReduced) {
      const ctx = canvas.getContext("2d");
      let width = (canvas.width = window.innerWidth);
      let height = (canvas.height = window.innerHeight);

      const onResize = () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
      };
      window.addEventListener("resize", onResize);

      const particles = Array.from({ length: 45 }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        r: Math.random() * 2 + 0.8,
        speedY: Math.random() * 0.4 + 0.15,
        speedX: (Math.random() - 0.5) * 0.3,
        alpha: Math.random() * 0.5 + 0.2,
        pulse: Math.random() * Math.PI
      }));

      function renderParticles() {
        if (isOpeningScreenDismissed) return;
        ctx.clearRect(0, 0, width, height);

        particles.forEach(p => {
          p.y -= p.speedY;
          p.x += p.speedX;
          p.pulse += 0.02;
          if (p.y < -10) p.y = height + 10;
          if (p.x < -10) p.x = width + 10;
          if (p.x > width + 10) p.x = -10;

          const currentAlpha = p.alpha + Math.sin(p.pulse) * 0.15;
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(249, 226, 125, ${Math.max(0.05, currentAlpha)})`;
          ctx.shadowColor = "#f9e27d";
          ctx.shadowBlur = 8;
          ctx.fill();
        });

        openingParticleAnimId = requestAnimationFrame(renderParticles);
      }

      renderParticles();
    }
  } catch (canvasErr) {
    console.warn("[Intro Canvas Error]", canvasErr);
  }

  // GSAP Timeline inside try/catch
  try {
    if (prefersReduced) {
      gsap.to("#openingEyebrow, #openingSubtitle, #openingCtaGroup", { opacity: 1, duration: 0.4 });
      gsap.to(".reveal-word", { y: "0%", duration: 0.3 });
      gsap.to(".reveal-brand", { opacity: 1, scale: 1, duration: 0.3 });
      setTimeout(() => {
        dismissOpeningScreen(false);
      }, 1500);
    } else {
      gsap.set(".reveal-word", { y: "115%" });
      gsap.set(".reveal-brand", { opacity: 0, scale: 0.82 });
      gsap.set("#openingEyebrow, #openingSubtitle, #openingCtaGroup", { opacity: 0, y: 15 });

      const tl = gsap.timeline({
        delay: 0.15,
        onComplete: () => {
          setTimeout(() => {
            if (!isOpeningScreenDismissed) dismissOpeningScreen(false);
          }, 1400);
        }
      });

      tl.to("#openingEyebrow", { opacity: 1, y: 0, duration: 0.55, ease: "power2.out" })
        .to(".opening-sparkle", { rotation: 360, duration: 0.8, ease: "power2.out" }, "<")
        .to(".reveal-word", {
          y: "0%",
          duration: 0.65,
          stagger: 0.08,
          ease: "power3.out"
        }, "-=0.2")
        .to(".reveal-brand", {
          opacity: 1,
          scale: 1,
          duration: 0.85,
          ease: "back.out(1.8)"
        }, "-=0.4")
        .to("#openingSubtitle", {
          opacity: 1,
          y: 0,
          duration: 0.55,
          ease: "power2.out"
        }, "-=0.4")
        .to("#openingCtaGroup", {
          opacity: 1,
          y: 0,
          duration: 0.5,
          ease: "back.out(1.5)"
        }, "-=0.3");
    }
  } catch (err) {
    console.error("[Intro Animation Error]", err);
    dismissOpeningScreen(false, true);
  }

  attachIntroTriggers();
}

function attachIntroTriggers() {
  const handleDismiss = (e, scrollToRecs = false) => {
    if (e) {
      try { e.preventDefault(); e.stopPropagation(); } catch (err) {}
    }
    dismissOpeningScreen(scrollToRecs);
  };

  const getStarted = document.getElementById("openingGetStarted");
  if (getStarted) getStarted.onclick = (e) => handleDismiss(e, false);

  const forYou = document.getElementById("openingForYou");
  if (forYou) forYou.onclick = (e) => handleDismiss(e, true);

  const skipBtn = document.getElementById("openingSkipBtn");
  if (skipBtn) skipBtn.onclick = (e) => handleDismiss(e, false);

  const onKeyOrScroll = (e) => {
    if (isOpeningScreenDismissed) {
      window.removeEventListener("keydown", onKeyOrScroll);
      window.removeEventListener("wheel", onKeyOrScroll);
      window.removeEventListener("touchmove", onKeyOrScroll);
      return;
    }
    if (e.type === "wheel" || e.type === "touchmove" || ["Space", "Enter", "Escape", "ArrowDown", "PageDown"].includes(e.code) || e.key === "Escape") {
      handleDismiss(e, false);
      window.removeEventListener("keydown", onKeyOrScroll);
      window.removeEventListener("wheel", onKeyOrScroll);
      window.removeEventListener("touchmove", onKeyOrScroll);
    }
  };

  window.addEventListener("keydown", onKeyOrScroll, { passive: true });
  window.addEventListener("wheel", onKeyOrScroll, { passive: true });
  window.addEventListener("touchmove", onKeyOrScroll, { passive: true });

  // Replay intro button in footer
  document.getElementById("replayIntroBtn")?.addEventListener("click", () => {
    sessionStorage.removeItem("cinestream_intro_seen");
    initOpeningScreen(true);
  });
}

function dismissOpeningScreen(scrollToRecs = false, immediate = false) {
  if (isOpeningScreenDismissed) return;
  isOpeningScreenDismissed = true;
  clearTimeout(introWatchdogTimer);
  document.documentElement.classList.remove("js-ready");

  try {
    sessionStorage.setItem("cinestream_intro_seen", "true");
  } catch (e) {}

  if (openingParticleAnimId) {
    cancelAnimationFrame(openingParticleAnimId);
    openingParticleAnimId = null;
  }

  const openingEl = document.getElementById("openingScreen");
  if (openingEl) {
    openingEl.classList.add("dismissed");
    if (immediate || !window.gsap) {
      openingEl.style.display = "none";
      try { openingEl.remove(); } catch (e) {}
    } else {
      try {
        gsap.to(openingEl, {
          y: "-100%",
          opacity: 0,
          duration: 0.6,
          ease: "power2.inOut",
          onComplete: () => {
            openingEl.style.display = "none";
            try { openingEl.remove(); } catch (e) {}
          }
        });
      } catch (e) {
        openingEl.style.display = "none";
        try { openingEl.remove(); } catch (e) {}
      }
    }
  }

  // Restore body scrolling
  document.body.style.overflow = "";

  // Reveal hero banner
  const heroContainer = document.getElementById("heroContainer");
  if (heroContainer) {
    heroContainer.style.opacity = "1";
    if (window.gsap && !immediate) {
      try {
        gsap.fromTo(heroContainer, { opacity: 0.6, scale: 0.98 }, { opacity: 1, scale: 1, duration: 0.5, ease: "power2.out" });
      } catch (e) {}
    }
  }

  if (scrollToRecs) {
    setTimeout(() => {
      document.getElementById("ramayanaSpotlightRecs")?.scrollIntoView({ behavior: "smooth" });
    }, 300);
  }

  // Initialize PromoPlayer and set active movie
  try {
    ensurePromoPlayerInit();
    if (state.featuredMovies && state.featuredMovies.length > 0) {
      setActiveMovie(state.activeCardIndex);
    }
  } catch (err) {
    console.warn("[Dismiss Post-Init Error]", err);
  }
}

// ============================================================
// FIX 2: PROMO PLAYER CONTROLLER INTEGRATION
// ============================================================
let promoPlayerInitialized = false;

function ensurePromoPlayerInit() {
  if (promoPlayerInitialized) return;
  promoPlayerInitialized = true;

  PromoPlayer.init("promo-player").then(() => {
    PromoPlayer.on("playing", (data) => {
      const activeMovie = state.featuredMovies[state.activeCardIndex];
      if (!activeMovie || data.slug !== activeMovie.slug) {
        // Ignore playing events for any other slug!
        return;
      }
      document.getElementById("heroVideoWrap")?.classList.add("active");
      updateTrailerPlayPauseUI(true);
      if (state.isTrailerMode) startProgressBar();
      updateTrailerDebugUI();
    });

    PromoPlayer.on("ended", (data) => {
      const activeMovie = state.featuredMovies[state.activeCardIndex];
      if (activeMovie && data.slug === activeMovie.slug) {
        document.getElementById("heroVideoWrap")?.classList.remove("active");
        updateTrailerPlayPauseUI(false);
        stopProgressBar();
        if (state.isTrailerMode) {
          exitFullTrailer();
        }
      }
      updateTrailerDebugUI();
    });

    PromoPlayer.on("failed", (data) => {
      const activeMovie = state.featuredMovies[state.activeCardIndex];
      if (!activeMovie || data.slug !== activeMovie.slug) return;
      document.getElementById("heroVideoWrap")?.classList.remove("active");
      const ytDirectBtn = document.getElementById("heroWatchOnYtBtn");
      if (ytDirectBtn) {
        ytDirectBtn.style.display = "inline-flex";
        const vid = (data.candidates && data.candidates[0]) || "";
        ytDirectBtn.href = vid ? `https://www.youtube.com/watch?v=${vid}` : "https://www.youtube.com";
      }
      updateTrailerDebugUI();
    });
  });
}

// (LANG_DISPLAY_NAMES defined globally at top of file)

// Audio Interaction Policy
function unlockSound() {
  if (state.hasInteracted) return;
  state.hasInteracted = true;
  const hint = document.getElementById("soundHint");
  if (hint) hint.classList.add("dismissed");
  localStorage.setItem("cinestream_sound_unlocked", "true");
}

window.addEventListener("click", unlockSound, { passive: true });
window.addEventListener("keydown", unlockSound, { passive: true });
window.addEventListener("touchstart", unlockSound, { passive: true });

document.getElementById("soundHint")?.addEventListener("click", (e) => {
  e.stopPropagation();
  unlockSound();
  toggleMute();
});

// ============================================================
// HIDDEN TRAILER DEBUG PANEL (Ctrl+Shift+D or ?debug=1)
// ============================================================
let debugPollTimer = null;

function initTrailerDebugPanel() {
  const panel = document.getElementById("trailerDebugPanel");
  const closeBtn = document.getElementById("debugCloseBtn");

  closeBtn?.addEventListener("click", () => {
    if (panel) panel.style.display = "none";
    if (debugPollTimer) {
      clearInterval(debugPollTimer);
      debugPollTimer = null;
    }
  });

  // Toggle on Ctrl+Shift+D
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.shiftKey && (e.key === "D" || e.key === "d")) {
      e.preventDefault();
      toggleDebugPanel();
    }
  });

  // Toggle if URL has ?debug=1
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("debug") === "1" && panel) {
    panel.style.display = "flex";
    updateTrailerDebugUI();
    if (!debugPollTimer) {
      debugPollTimer = setInterval(updateTrailerDebugUI, 500);
    }
  }
}

function toggleDebugPanel() {
  const panel = document.getElementById("trailerDebugPanel");
  if (!panel) return;
  const isOpening = panel.style.display === "none";
  panel.style.display = isOpening ? "flex" : "none";
  if (isOpening) {
    updateTrailerDebugUI();
    if (!debugPollTimer) {
      debugPollTimer = setInterval(updateTrailerDebugUI, 500);
    }
  } else {
    if (debugPollTimer) {
      clearInterval(debugPollTimer);
      debugPollTimer = null;
    }
  }
}

function updateTrailerDebugUI() {
  const body = document.getElementById("debugPanelBody");
  if (!body) return;

  const m = state.featuredMovies[state.activeCardIndex];
  const activeTitle = m ? m.title : "None";
  const activeSlug = m ? m.slug : "None";
  const tmdbId = m ? m.tmdb_id : "N/A";

  const promoState = (typeof PromoPlayer !== "undefined" && PromoPlayer.getState) ? PromoPlayer.getState() : {};
  const requestedId = (promoState.candidates && promoState.candidates[promoState.idx]) || "None";
  const actualId = (typeof PromoPlayer !== "undefined" && PromoPlayer.getActualVideoId) ? (PromoPlayer.getActualVideoId() || "None") : "None";
  const isMismatch = (requestedId !== "None" && actualId !== "None" && requestedId !== actualId);

  const resolved = (m && (m.valid_trailers || m.trailers)) || {};
  const sources = (m && m.sources) || {};

  let langsTable = "";
  Object.keys(resolved).forEach(k => {
    const id = resolved[k];
    const src = sources[k] || "official";
    langsTable += `<tr><td class="label">${k.toUpperCase()}</td><td><code>${id}</code></td><td><span class="debug-badge ok">${src}</span></td></tr>`;
  });

  body.innerHTML = `
    <table class="debug-table">
      <tr><td class="label">Featured:</td><td><strong>${escapeHtml(activeTitle)}</strong> (${activeSlug})</td></tr>
      <tr><td class="label">TMDB ID:</td><td>${tmdbId}</td></tr>
      <tr><td class="label">Active Slug:</td><td><code>${activeSlug}</code></td></tr>
      <tr><td class="label">Requested Video ID:</td><td><code>${requestedId}</code></td></tr>
      <tr><td class="label">Actual Player ID:</td><td>
        <code style="${isMismatch ? 'color:#ef4444;font-weight:bold;' : 'color:#10b981;'}">${actualId}</code>
        <span class="debug-badge ${isMismatch ? 'err' : 'ok'}">${isMismatch ? 'MISMATCH' : 'MATCH'}</span>
      </td></tr>
      <tr><td class="label">Controller State:</td><td>Token: ${promoState.token || 0} | Candidate ${(promoState.idx || 0) + 1} of ${promoState.candidates ? promoState.candidates.length : 0}</td></tr>
    </table>
    <div class="debug-section-title">Resolved Trailer Audio Languages</div>
    <table class="debug-table">
      <thead><tr><th style="text-align:left;color:#888;">Lang</th><th style="text-align:left;color:#888;">YouTube ID</th><th style="text-align:left;color:#888;">Source</th></tr></thead>
      <tbody>${langsTable || "<tr><td colspan='3'>No resolved trailers</td></tr>"}</tbody>
    </table>
  `;
}

function getAvailableTrailerLangs(movie) {
  if (!movie) return [];
  if (movie.available_languages && movie.available_languages.length > 0) {
    return movie.available_languages;
  }
  const trailers = movie.valid_trailers || movie.trailers || {};
  return Object.keys(trailers).filter(k => !k.startsWith("_") && trailers[k] && typeof trailers[k] === "string" && trailers[k].trim());
}

function currentAudioLang(movie) {
  if (!movie) return "hi";
  const saved = localStorage.getItem(`audio:${movie.slug}`);
  const available = getAvailableTrailerLangs(movie);
  if (saved && available.includes(saved)) {
    return saved;
  }
  if (movie.selected_audio && available.includes(movie.selected_audio)) {
    return movie.selected_audio;
  }
  if (movie.default_lang && available.includes(movie.default_lang)) {
    return movie.default_lang;
  }
  if (movie.original_lang && available.includes(movie.original_lang)) {
    return movie.original_lang;
  }
  if (available.includes("hi")) return "hi";
  if (available.includes("kn")) return "kn";
  return available[0] || "hi";
}

async function loadFeaturedMovies(lang = state.currentLang) {
  try {
    const res = await fetch(`/api/featured?lang=${encodeURIComponent(lang)}`);
    const data = await res.json();
    state.featuredMovies = data.featured || data.movies || [];
  } catch (err) {
    console.error("Failed to load featured movies from /api/featured:", err);
    state.featuredMovies = [];
  }

  if (!state.featuredMovies.length) return;

  // Determine starting active index:
  // For 'all' default to 'ramayana-part-1' if present, else 0
  let startIndex = 0;
  if (lang === "all") {
    const ramayanaIdx = state.featuredMovies.findIndex(m => m.slug === "ramayana-part-1");
    if (ramayanaIdx !== -1) startIndex = ramayanaIdx;
  }
  state.activeCardIndex = startIndex;

  renderCarouselCards();
  renderCarouselDots();
  setActiveMovie(state.activeCardIndex);
}

let activeToken = 0;
let promoTimer = null;
let slotHoverTimer = null;

function setActiveMovie(index) {
  const N = state.featuredMovies.length;
  if (!N) return;

  index = ((index % N) + N) % N;
  const token = ++activeToken;
  clearTimeout(promoTimer);
  clearTimeout(slotHoverTimer);

  const movie = state.featuredMovies[index];
  if (!movie) return;

  state.activeCardIndex = index;

  // Immediately show that movie's backdrop (hide the video layer)
  const backdropImg = document.getElementById("heroBackdropImg");
  const videoWrap = document.getElementById("heroVideoWrap");
  if (backdropImg) {
    backdropImg.src = movie.backdrop_url || movie.poster_url;
    backdropImg.style.opacity = "1";
  }
  if (videoWrap) {
    videoWrap.classList.remove("active");
  }
  const ytDirectBtn = document.getElementById("heroWatchOnYtBtn");
  if (ytDirectBtn) {
    ytDirectBtn.style.display = "none";
  }

  // Update carousel 3D visuals & dots
  updateCarouselVisuals(index, true);

  // Update Left Spotlight Overlay Info
  updateSpotlightOverlay(movie, true);
  updateHeroWatchlistBtn(movie);

  // Update Audio Dropdown Menus
  renderHeroAudioMenus(movie);

  // Update debug panel
  updateTrailerDebugUI();

  // Sync recommendation shelves
  loadActiveMovieRecommendations(movie);

  // If in trailer mode, exit it on movie switch
  if (state.isTrailerMode) {
    state.isTrailerMode = false;
    document.getElementById("hero")?.classList.remove("trailer-mode-active");
    stopProgressBar();
  }

  // Schedule trailer preview via PromoPlayer only after 1.2s delay
  if (isOpeningScreenDismissed) {
    promoTimer = setTimeout(() => {
      if (token !== activeToken) return;
      PromoPlayer.play(movie, currentAudioLang(movie));
    }, 1200);
  }
}

function goTo(targetIndex, animate = true) {
  setActiveMovie(targetIndex);
}

function renderCarouselCards() {
  const track = document.getElementById("carousel3dTrack");
  if (!track) return;
  track.innerHTML = "";

  state.featuredMovies.forEach((m, idx) => {
    const slot = document.createElement("div");
    slot.className = `carousel-slot ${idx === state.activeCardIndex ? "active" : ""}`;
    slot.dataset.index = idx;
    slot.dataset.slug = m.slug;
    slot.tabIndex = 0;
    slot.setAttribute("role", "button");
    slot.setAttribute("aria-label", `Select ${escapeHtml(m.title)}`);

    const hdBadge = `<span class="card-badge-hd">HD</span>`;
    const showingBadge = m.badge ? `<span class="card-badge-showing">${escapeHtml(m.badge)}</span>` : "";

    const availableLangs = getAvailableTrailerLangs(m);
    const savedAudio = localStorage.getItem(`audio:${m.slug}`);
    if (savedAudio && availableLangs.includes(savedAudio)) {
      m.selected_audio = savedAudio;
    } else if (!m.selected_audio) {
      if (availableLangs.includes(state.currentLang)) m.selected_audio = state.currentLang;
      else if (m.default_lang && availableLangs.includes(m.default_lang)) m.selected_audio = m.default_lang;
      else if (m.original_lang && availableLangs.includes(m.original_lang)) m.selected_audio = m.original_lang;
      else if (availableLangs.includes("hi")) m.selected_audio = "hi";
      else if (availableLangs.includes("kn")) m.selected_audio = "kn";
      else m.selected_audio = availableLangs[0] || "hi";
    }

    const audioPill = availableLangs.length > 0 ? `
      <div class="card-audio-wrap">
        <span class="card-audio-btn" title="Audio: ${LANG_DISPLAY_NAMES[m.selected_audio] || m.selected_audio}">
          <span>🔊</span>
          <span class="audio-lang-name">${escapeHtml(LANG_DISPLAY_NAMES[m.selected_audio] || (m.selected_audio || "").toUpperCase())}</span>
        </span>
      </div>
    ` : "";

    const genresFormatted = escapeHtml(m.genres_formatted || (m.genres ? m.genres.join(" • ") : "Action • Drama"));

    const inner = document.createElement("div");
    inner.className = "carousel-card-inner";
    inner.innerHTML = `
      <div class="card-poster-wrap">
        <img src="${m.poster_url}" alt="${escapeHtml(m.title)}" class="card-poster-img"
             onerror="this.src='https://image.tmdb.org/t/p/w500/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg'" />
        <div class="card-overlay-gradient"></div>
        <div class="card-badges-top">
          ${hdBadge}
          ${showingBadge}
          ${getBookmarkBtnHtml(m.tmdb_id || m.id || m.movieId || m.slug, "movie", "carousel-bm-btn")}
        </div>
        ${audioPill}
        <button class="card-play-btn" data-index="${idx}" aria-label="Play trailer with sound">
          <div class="card-play-icon"></div>
        </button>
        <div class="card-bottom-info">
          <div class="card-movie-title">${escapeHtml(m.title)}</div>
          <div class="card-genre-chips">${genresFormatted}</div>
        </div>
      </div>
    `;

    slot.appendChild(inner);

    // Hover intent debouncing
    slot.addEventListener("pointerenter", () => {
      clearTimeout(slotHoverTimer);
      slotHoverTimer = setTimeout(() => {
        if (state.activeCardIndex !== idx) {
          setActiveMovie(idx);
        }
      }, 120);
    });

    slot.addEventListener("pointerleave", () => {
      clearTimeout(slotHoverTimer);
    });

    // Card click: card play button triggers full trailer with sound, card body switches or plays
    slot.addEventListener("click", (e) => {
      unlockSound();
      clearTimeout(slotHoverTimer);
      const playBtn = e.target.closest(".card-play-btn");
      if (playBtn) {
        e.stopPropagation();
        setActiveMovie(idx);
        PromoPlayer.play(m, currentAudioLang(m), { sound: true });
        startFullTrailer(m);
        return;
      }
      if (state.activeCardIndex !== idx) {
        setActiveMovie(idx);
      } else {
        PromoPlayer.play(m, currentAudioLang(m), { sound: true });
        startFullTrailer(m);
      }
    });

    track.appendChild(slot);
  });
}

function renderCarouselDots() {
  const dotsContainer = document.getElementById("carouselDots");
  if (!dotsContainer) return;
  dotsContainer.innerHTML = "";

  state.featuredMovies.forEach((m, idx) => {
    const dot = document.createElement("button");
    dot.className = `dot-btn ${idx === state.activeCardIndex ? "active" : ""}`;
    dot.dataset.index = idx;
    dot.setAttribute("role", "tab");
    dot.setAttribute("aria-label", `Slide ${idx + 1}: ${m.title}`);
    dot.addEventListener("click", () => {
      unlockSound();
      clearTimeout(slotHoverTimer);
      setActiveMovie(idx);
    });
    dotsContainer.appendChild(dot);
  });
}

function updateCarouselVisuals(targetIndex, animate = true) {
  const N = state.featuredMovies.length;
  if (!N) return;

  const slots = document.querySelectorAll(".carousel-slot");
  slots.forEach((slot, i) => {
    let offset = i - targetIndex;
    while (offset > Math.floor(N / 2)) offset -= N;
    while (offset < -Math.floor((N - 1) / 2)) offset += N;

    let tx = 0, tz = 0, ry = 0, sc = 1, op = 1, br = 1, zIndex = 1;

    if (offset === 0) {
      tx = 0; tz = 80; ry = 0; sc = 1.08; op = 1; br = 1; zIndex = 10;
      slot.classList.add("active");
    } else if (offset === -1) {
      tx = -185; tz = -30; ry = 22; sc = 0.9; op = 0.75; br = 0.7; zIndex = 5;
      slot.classList.remove("active");
    } else if (offset === 1) {
      tx = 185; tz = -30; ry = -22; sc = 0.9; op = 0.75; br = 0.7; zIndex = 5;
      slot.classList.remove("active");
    } else if (offset === -2) {
      tx = -340; tz = -100; ry = 34; sc = 0.76; op = 0.35; br = 0.45; zIndex = 2;
      slot.classList.remove("active");
    } else if (offset === 2) {
      tx = 340; tz = -100; ry = -34; sc = 0.76; op = 0.35; br = 0.45; zIndex = 2;
      slot.classList.remove("active");
    } else {
      const sign = Math.sign(offset) || 1;
      tx = sign * 450; tz = -150; ry = -sign * 40; sc = 0.6; op = 0; br = 0.3; zIndex = 1;
      slot.classList.remove("active");
    }

    slot.style.zIndex = zIndex;
    const inner = slot.querySelector(".carousel-card-inner");
    if (inner) {
      if (animate && window.gsap) {
        gsap.to(inner, {
          x: tx,
          z: tz,
          rotateY: ry,
          scale: sc,
          opacity: op,
          filter: `brightness(${br})`,
          duration: 0.6,
          ease: "power3.out",
          overwrite: "auto"
        });
      } else {
        inner.style.transform = `translateX(${tx}px) translateZ(${tz}px) rotateY(${ry}deg) scale(${sc})`;
        inner.style.opacity = op;
        inner.style.filter = `brightness(${br})`;
      }
    }
  });

  // Update dots
  document.querySelectorAll("#carouselDots .dot-btn").forEach((dot, dIdx) => {
    dot.classList.toggle("active", dIdx === targetIndex);
  });
}

function updateSpotlightOverlay(movie, animate = true) {
  const badgeEl = document.getElementById("heroBadge");
  const titleEl = document.getElementById("heroMovieTitle");
  const yearEl = document.getElementById("heroYear");
  const genresEl = document.getElementById("heroGenres");
  const origLangEl = document.getElementById("heroOrigLang");
  const overviewEl = document.getElementById("heroOverview");
  const castNamesEl = document.getElementById("heroCastNames");

  if (badgeEl) {
    if (movie.badge) {
      badgeEl.textContent = movie.badge;
      badgeEl.style.display = "inline-block";
    } else {
      badgeEl.style.display = "none";
    }
  }

  if (titleEl) titleEl.textContent = movie.title;
  if (yearEl) yearEl.textContent = movie.year || "2026";
  if (genresEl) {
    genresEl.textContent = movie.genres_formatted || (movie.genres ? movie.genres.join(" • ") : "Action • Drama");
  }
  if (origLangEl) {
    const origCode = movie.original_language || movie.original_lang || movie.default_lang;
    const origLangName = LANG_DISPLAY_NAMES[origCode] || (origCode ? origCode.toUpperCase() : "Original");
    origLangEl.textContent = origLangName;
  }
  if (overviewEl) overviewEl.textContent = movie.overview || "";
  if (castNamesEl) {
    castNamesEl.textContent = movie.cast ? (Array.isArray(movie.cast) ? movie.cast.join(", ") : movie.cast) : "";
  }

  if (animate && window.gsap) {
    gsap.fromTo("#heroSpotlightInfo",
      { y: 14, opacity: 0.35 },
      { y: 0, opacity: 1, duration: 0.45, ease: "power3.out" }
    );
  }
}

function renderHeroAudioMenus(movie) {
  const availableLangs = getAvailableTrailerLangs(movie);
  const heroAudioWrap = document.getElementById("heroAudioWrap");
  const heroAudioLabel = document.getElementById("heroAudioLabel");
  const heroAudioMenu = document.getElementById("heroAudioMenu");

  const trailerAudioWrap = document.getElementById("trailerAudioWrap");
  const trailerAudioLabel = document.getElementById("trailerAudioLabel");
  const trailerAudioMenu = document.getElementById("trailerAudioMenu");

  const currentLang = currentAudioLang(movie);
  movie.selected_audio = currentLang;

  const selectedName = LANG_DISPLAY_NAMES[currentLang] || currentLang.toUpperCase();

  if (heroAudioLabel) heroAudioLabel.textContent = `Audio: ${selectedName}`;
  if (trailerAudioLabel) trailerAudioLabel.textContent = `Audio: ${selectedName}`;

  if (availableLangs.length <= 1) {
    if (heroAudioWrap) heroAudioWrap.style.display = "none";
    if (trailerAudioWrap) trailerAudioWrap.style.display = "none";
    return;
  }

  if (heroAudioWrap) heroAudioWrap.style.display = "inline-block";
  if (trailerAudioWrap) trailerAudioWrap.style.display = "inline-block";

  const optionsHtml = availableLangs.map(l => `
    <div class="audio-option ${l === currentLang ? "active" : ""}" data-lang="${l}">
      <span class="audio-radio-dot"></span>
      <span>${LANG_DISPLAY_NAMES[l] || l.toUpperCase()}</span>
    </div>
  `).join("");

  if (heroAudioMenu) {
    heroAudioMenu.innerHTML = optionsHtml;
    heroAudioMenu.querySelectorAll(".audio-option").forEach(opt => {
      opt.addEventListener("click", (e) => {
        e.stopPropagation();
        selectTrailerLanguage(movie, opt.dataset.lang);
        heroAudioMenu.classList.remove("open");
      });
    });
  }

  if (trailerAudioMenu) {
    trailerAudioMenu.innerHTML = optionsHtml;
    trailerAudioMenu.querySelectorAll(".audio-option").forEach(opt => {
      opt.addEventListener("click", (e) => {
        e.stopPropagation();
        selectTrailerLanguage(movie, opt.dataset.lang);
        trailerAudioMenu.classList.remove("open");
      });
    });
  }
}

function selectTrailerLanguage(movie, chosenLang) {
  if (!movie) return;
  movie.selected_audio = chosenLang;
  localStorage.setItem(`audio:${movie.slug}`, chosenLang);
  const selectedName = LANG_DISPLAY_NAMES[chosenLang] || chosenLang.toUpperCase();

  const heroAudioLabel = document.getElementById("heroAudioLabel");
  const trailerAudioLabel = document.getElementById("trailerAudioLabel");
  if (heroAudioLabel) heroAudioLabel.textContent = `Audio: ${selectedName}`;
  if (trailerAudioLabel) trailerAudioLabel.textContent = `Audio: ${selectedName}`;

  // Update card audio chip if present
  const activeCard = document.querySelector(`.carousel-slot[data-slug="${movie.slug}"]`);
  const nameSpan = activeCard?.querySelector(".audio-lang-name");
  if (nameSpan) nameSpan.textContent = chosenLang.toUpperCase();

  // Highlight active option in menu
  document.querySelectorAll(".audio-option").forEach(opt => {
    opt.classList.toggle("active", opt.dataset.lang === chosenLang);
  });

  PromoPlayer.play(movie, chosenLang, { sound: true });
  updateTrailerDebugUI();
}

function startFullTrailer(movie = null) {
  unlockSound();
  state.isTrailerMode = true;

  const hero = document.getElementById("hero");
  if (hero) hero.classList.add("trailer-mode-active");

  const m = movie || state.featuredMovies[state.activeCardIndex];
  if (m) {
    PromoPlayer.play(m, currentAudioLang(m), { sound: true });
  }

  updateMuteUI(false);
  updateTrailerPlayPauseUI(true);
  startProgressBar();
}

function exitFullTrailer() {
  state.isTrailerMode = false;

  const hero = document.getElementById("hero");
  if (hero) hero.classList.remove("trailer-mode-active");

  stopProgressBar();

  const m = state.featuredMovies[state.activeCardIndex];
  if (m) {
    // Return to muted preview
    PromoPlayer.play(m, currentAudioLang(m), { sound: false });
  }
}

function toggleTrailerPlayPause() {
  const pState = PromoPlayer.getPlayerState ? PromoPlayer.getPlayerState() : -1;
  if (pState === 1) { // PLAYING
    PromoPlayer.pause();
    updateTrailerPlayPauseUI(false);
  } else {
    PromoPlayer.resume();
    updateTrailerPlayPauseUI(true);
  }
}

function updateTrailerPlayPauseUI(isPlaying) {
  const icon = document.getElementById("trailerPlayPauseIcon");
  if (icon) icon.innerHTML = isPlaying ? "&#10074;&#10074;" : "&#9654;";
}

function toggleMute() {
  unlockSound();
  state.isMuted = !state.isMuted;
  localStorage.setItem("cinestream_muted", state.isMuted ? "true" : "false");
  PromoPlayer.setMuted(state.isMuted);
  updateMuteUI(state.isMuted);
}

function updateMuteUI(isMuted) {
  const heroMuteIcon = document.getElementById("heroMuteIcon");
  const trailerMuteIcon = document.getElementById("trailerBarMuteIcon");
  const iconHtml = isMuted ? "&#128263;" : "&#128266;";
  if (heroMuteIcon) heroMuteIcon.innerHTML = iconHtml;
  if (trailerMuteIcon) trailerMuteIcon.innerHTML = iconHtml;
}

function formatTime(seconds) {
  const s = Math.floor(seconds || 0);
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem < 10 ? "0" : ""}${rem}`;
}

let progressTimer = null;
function startProgressBar() {
  stopProgressBar();
  progressTimer = setInterval(() => {
    const cur = PromoPlayer.getCurrentTime ? PromoPlayer.getCurrentTime() : 0;
    const dur = PromoPlayer.getDuration ? PromoPlayer.getDuration() : 0;
    if (dur > 0) {
      const pct = (cur / dur) * 100;
      const bar = document.getElementById("trailerProgressBar");
      if (bar) bar.style.width = `${pct}%`;
      const timeDisplay = document.getElementById("trailerTimeDisplay");
      if (timeDisplay) timeDisplay.textContent = `${formatTime(cur)} / ${formatTime(dur)}`;
    }
  }, 350);
}

function stopProgressBar() {
  clearInterval(progressTimer);
}

function navigateCarousel(direction) {
  clearTimeout(slotHoverTimer);
  const N = state.featuredMovies.length;
  if (!N) return;
  const targetIndex = ((state.activeCardIndex + direction) % N + N) % N;
  setActiveMovie(targetIndex);
}

function initHeroCarousel() {
  // Load featured movies for default language
  loadFeaturedMovies(state.currentLang);

  // Arrow buttons
  document.getElementById("carouselPrevBtn")?.addEventListener("click", () => {
    unlockSound();
    navigateCarousel(-1);
  });
  document.getElementById("carouselNextBtn")?.addEventListener("click", () => {
    unlockSound();
    navigateCarousel(1);
  });

  // Watch Trailer Button (Left spotlight overlay)
  document.getElementById("heroWatchTrailerBtn")?.addEventListener("click", () => {
    unlockSound();
    const movie = state.featuredMovies[state.activeCardIndex];
    if (movie) {
      PromoPlayer.play(movie, currentAudioLang(movie), { sound: true });
      startFullTrailer(movie);
    }
  });

  // Add to Watchlist Button
  document.getElementById("heroAddListBtn")?.addEventListener("click", function() {
    const activeMovie = state.featuredMovies[state.activeCardIndex];
    if (activeMovie) toggleWatchlist(activeMovie, this);
  });

  // Intro strip CTAs
  document.getElementById("introGetStarted")?.addEventListener("click", () => {
    document.getElementById("streaming")?.scrollIntoView({ behavior: "smooth" });
  });
  document.getElementById("introForYou")?.addEventListener("click", () => {
    document.getElementById("ramayanaSpotlightRecs")?.scrollIntoView({ behavior: "smooth" });
  });

  // Ambient Bottom Controls
  document.getElementById("heroMuteBtn")?.addEventListener("click", toggleMute);

  const heroAudioBtn = document.getElementById("heroAudioBtn");
  const heroAudioMenu = document.getElementById("heroAudioMenu");
  heroAudioBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    heroAudioMenu?.classList.toggle("open");
  });

  // In-Trailer Control Bar
  document.getElementById("trailerBackBtn")?.addEventListener("click", exitFullTrailer);
  document.getElementById("trailerPlayPauseBtn")?.addEventListener("click", toggleTrailerPlayPause);
  document.getElementById("trailerBarMuteBtn")?.addEventListener("click", toggleMute);

  const trailerVolSlider = document.getElementById("trailerVolSlider");
  if (trailerVolSlider) {
    trailerVolSlider.value = state.trailerVolume;
    trailerVolSlider.addEventListener("input", (e) => {
      const val = parseInt(e.target.value);
      state.trailerVolume = val;
      localStorage.setItem("cinestream_volume", val);
      if (typeof PromoPlayer !== "undefined" && PromoPlayer.getPlayer && PromoPlayer.getPlayer()) {
        try {
          const p = PromoPlayer.getPlayer();
          if (p.setVolume) p.setVolume(val);
          if (val > 0 && state.isMuted) {
            PromoPlayer.setMuted(false);
            state.isMuted = false;
            localStorage.setItem("cinestream_muted", "false");
            updateMuteUI(false);
          }
        } catch (err) {}
      }
    });
  }

  const trailerAudioBtn = document.getElementById("trailerAudioBtn");
  const trailerAudioMenu = document.getElementById("trailerAudioMenu");
  trailerAudioBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    trailerAudioMenu?.classList.toggle("open");
  });

  // Progress Bar Seek
  const progressWrap = document.getElementById("trailerProgressWrap");
  progressWrap?.addEventListener("click", (e) => {
    try {
      const dur = PromoPlayer.getDuration ? PromoPlayer.getDuration() : 0;
      if (dur > 0) {
        const rect = progressWrap.getBoundingClientRect();
        const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        PromoPlayer.seekTo(pct * dur);
      }
    } catch (err) {}
  });

  // Fullscreen
  document.getElementById("trailerFullscreenBtn")?.addEventListener("click", () => {
    const hero = document.getElementById("hero");
    if (!hero) return;
    if (!document.fullscreenElement) {
      hero.requestFullscreen().catch(err => console.warn(err));
    } else {
      document.exitFullscreen().catch(err => console.warn(err));
    }
  });

  // Close menus on outside click
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".hero-audio-wrap")) {
      document.querySelectorAll(".hero-audio-menu").forEach(m => m.classList.remove("open"));
    }
  });

  // Keyboard navigation
  window.addEventListener("keydown", (e) => {
    if (state.isTrailerMode) {
      if (e.key === "Escape") {
        exitFullTrailer();
      } else if (e.key === " " && !e.target.matches("input, textarea")) {
        e.preventDefault();
        toggleTrailerPlayPause();
      }
      return;
    }

    const heroInView = isElementInViewport(document.getElementById("hero"));
    if (!heroInView) return;

    if (e.key === "ArrowLeft") {
      unlockSound();
      navigateCarousel(-1);
    } else if (e.key === "ArrowRight") {
      unlockSound();
      navigateCarousel(1);
    } else if (e.key === "Enter") {
      unlockSound();
      const activeMovie = state.featuredMovies[state.activeCardIndex];
      if (activeMovie) {
        PromoPlayer.play(activeMovie, currentAudioLang(activeMovie), { sound: true });
        startFullTrailer(activeMovie);
      }
    }
  });

  // Touch Swipe Support on Carousel Stage
  const stage = document.getElementById("carouselStageContainer");
  let touchStartX = 0;
  if (stage) {
    stage.addEventListener("touchstart", (e) => {
      touchStartX = e.touches[0].clientX;
    }, { passive: true });

    stage.addEventListener("touchend", (e) => {
      const diffX = e.changedTouches[0].clientX - touchStartX;
      if (Math.abs(diffX) > 40) {
        unlockSound();
        if (diffX > 0) navigateCarousel(-1);
        else navigateCarousel(1);
      }
    }, { passive: true });
  }

  // IntersectionObserver: pause trailer if hero scrolls out of view
  const heroEl = document.getElementById("hero");
  if (heroEl && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) {
          PromoPlayer.pause();
          updateTrailerPlayPauseUI(false);
        } else if (entry.isIntersecting && !state.isTrailerMode && isOpeningScreenDismissed) {
          const activeMovie = state.featuredMovies[state.activeCardIndex];
          if (activeMovie) {
            PromoPlayer.play(activeMovie, currentAudioLang(activeMovie));
          }
        }
      });
    }, { threshold: 0.15 });
    observer.observe(heroEl);
  }

  // Page visibility change: pause when tab hidden
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      PromoPlayer.pause();
      updateTrailerPlayPauseUI(false);
    } else if (!document.hidden && !state.isTrailerMode && isOpeningScreenDismissed) {
      const activeMovie = state.featuredMovies[state.activeCardIndex];
      if (activeMovie) {
        PromoPlayer.play(activeMovie, currentAudioLang(activeMovie));
      }
    }
  });
}

// ============================================================
// FIX 3: HORIZONTAL CAROUSEL RECOMMENDATION SHELVES
// ============================================================
async function loadActiveMovieRecommendations(activeMovie) {
  if (!activeMovie) return;

  const titleEl = document.getElementById("activeMovieTitle");
  const clusterEl = document.getElementById("activeMovieCluster");
  const shelfClusterNum = document.getElementById("shelfClusterNum");

  if (titleEl) titleEl.textContent = activeMovie.title;
  if (clusterEl) clusterEl.textContent = `${activeMovie.cluster || 1}: ${activeMovie.cluster_name || "Drama + Action"}`;
  if (shelfClusterNum) shelfClusterNum.textContent = activeMovie.cluster || 1;

  const trackCluster = document.getElementById("shelfClusterPicks");
  const trackCosine = document.getElementById("shelfCosineMatches");
  const trackTopRated = document.getElementById("shelfTopRatedPicks");

  // Show shimmer skeletons while loading
  const skeletonHtml = `<div class="rec-card-skeleton"></div><div class="rec-card-skeleton"></div><div class="rec-card-skeleton"></div><div class="rec-card-skeleton"></div>`;
  if (trackCluster) trackCluster.innerHTML = skeletonHtml;
  if (trackCosine) trackCosine.innerHTML = skeletonHtml;
  if (trackTopRated) trackTopRated.innerHTML = skeletonHtml;

  try {
    const slug = encodeURIComponent(activeMovie.slug || "ramayana-part-1");
    const mId = activeMovie.tmdb_id || "";
    const allLangsParam = state.epicAllLangs ? "1" : "0";
    const chosenModel = document.getElementById("modelSelect")?.value || "rf";
    const res = await fetch(`/api/recommend/featured?slug=${slug}&movieId=${mId}&lang=${state.currentLang}&all_langs=${allLangsParam}&model=${chosenModel}&_t=${Date.now()}`);
    const data = await res.json();

    const clusterPicks = data.cluster_picks || data.more_like_this || [];
    const closestMatches = data.closest_matches || data.epic_picks || [];
    const topRatedPicks = data.top_rated_picks || data.predicted_for_you || [];

    // Cold-start row title & subtitle update
    const predTitleEl = document.getElementById("predictedShelfTitle");
    const predSubEl = document.getElementById("predictedShelfSub");
    if (predTitleEl && data.row_title) predTitleEl.textContent = data.row_title;
    if (predSubEl && data.row_subtitle) predSubEl.textContent = data.row_subtitle;

    renderShelfRow(trackCluster, clusterPicks, "cluster", data.is_cold_start);
    renderShelfRow(trackCosine, closestMatches, "cosine", data.is_cold_start);
    renderShelfRow(trackTopRated, topRatedPicks, "rating", data.is_cold_start);

    // Init horizontal scroll listeners and arrow buttons
    setupShelfCarouselControls("shelfClusterPicks", "shelfClusterPicksPrev", "shelfClusterPicksNext", "shelfClusterFadeLeft", "shelfClusterFadeRight");
    setupShelfCarouselControls("shelfCosineMatches", "shelfCosineMatchesPrev", "shelfCosineMatchesNext", "shelfCosineFadeLeft", "shelfCosineFadeRight");
    setupShelfCarouselControls("shelfTopRatedPicks", "shelfTopRatedPicksPrev", "shelfTopRatedPicksNext", "shelfTopRatedFadeLeft", "shelfTopRatedFadeRight");

  } catch (err) {
    console.error("Failed to load featured movie recommendations:", err);
  }
}

let currentModalMovie = null;
let currentModalRating = 0;

function openRateModal(m) {
  currentModalMovie = m;
  currentModalRating = 0;
  const modal = document.getElementById("rateRamayanaModal");
  if (!modal) return;

  const displayTitle = getDisplayTitle(m);
  const posterSrc = m.poster_url || m.poster_large_url || "https://image.tmdb.org/t/p/w500/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg";
  const clusterTag = m.clusterName || m.cluster_name || "FEATURED";

  const thumb = document.getElementById("rateModalThumb");
  const badge = document.getElementById("rateModalBadge");
  const title = document.getElementById("rateModalTitle");
  const sub = document.getElementById("rateModalSub");
  const scoreText = document.getElementById("ramayanaScoreText");
  const chipsWrap = document.getElementById("modalProvidersChips");

  if (thumb) thumb.src = posterSrc;
  if (badge) badge.textContent = clusterTag.toUpperCase();
  if (title) title.textContent = displayTitle;
  if (sub) sub.textContent = m.genres_formatted || (m.genres ? m.genres.join(" • ") : "Action • Drama");
  if (scoreText) scoreText.textContent = "Select a rating from 1 to 5 stars";

  document.querySelectorAll("#ramayanaStarRating .star-lg").forEach(s => s.classList.remove("active"));

  modal.classList.add("active");
  modal.style.display = "flex";
  document.body.style.overflow = "hidden";

  const mid = m.tmdb_id || m.tmdbId || m.movieId || 1184918;
  if (chipsWrap) {
    chipsWrap.innerHTML = `<span style="color: #888; font-size: 0.8rem;">Loading streaming platforms...</span>`;
    fetch(`/api/movie/${mid}/providers`)
      .then(res => res.json())
      .then(data => {
        const providers = [...(data.flatrate || []), ...(data.rent || [])];
        if (providers.length === 0) {
          chipsWrap.innerHTML = `<span style="font-size: 0.8rem; color: #888;">Available on major Indian streaming services.</span>`;
        } else {
          chipsWrap.innerHTML = providers.slice(0, 5).map(p => `
            <span style="display: inline-flex; align-items: center; gap: 4px; background: rgba(255,255,255,0.08); padding: 4px 10px; border-radius: 6px; font-size: 0.78rem; color: #eee; font-weight: 500;">
              ${p.logo ? `<img src="${p.logo}" alt="${escapeHtml(p.name)}" style="width: 16px; height: 16px; border-radius: 3px;" />` : "📺"}
              <span>${escapeHtml(p.name)}</span>
            </span>
          `).join("");
        }
      })
      .catch(() => {
        chipsWrap.innerHTML = `<span style="font-size: 0.8rem; color: #aaa;">JioCinema &middot; Disney+ Hotstar &middot; Prime Video</span>`;
      });
  }
}

function initRateModal() {
  const modal = document.getElementById("rateRamayanaModal");
  const closer = document.getElementById("closeRateRamayana");
  const submitBtn = document.getElementById("submitRamayanaRating");
  const scoreText = document.getElementById("ramayanaScoreText");
  const stars = document.querySelectorAll("#ramayanaStarRating .star-lg");

  const close = () => {
    if (modal) {
      modal.classList.remove("active");
      modal.style.display = "none";
      document.body.style.overflow = "";
    }
  };

  closer?.addEventListener("click", close);
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) close();
  });

  stars.forEach(s => {
    s.addEventListener("click", () => {
      const val = parseInt(s.dataset.value);
      currentModalRating = val;
      stars.forEach(st => {
        st.classList.toggle("active", parseInt(st.dataset.value) <= val);
      });
      if (scoreText) scoreText.textContent = `You selected: ${val} Star${val > 1 ? "s" : ""}`;
    });
  });

  submitBtn?.addEventListener("click", async () => {
    if (!currentModalMovie) return close();
    const rating = currentModalRating || 5;
    const mid = currentModalMovie.movieId || currentModalMovie.tmdb_id || currentModalMovie.tmdbId;

    try {
      await fetch("/api/rate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId: state.userId, movieId: mid, rating })
      });
      showToast(`Saved rating: ⭐ ${rating} for ${getDisplayTitle(currentModalMovie)}!`, "success");
      close();
      loadRecommendations();
      if (state.featuredMovies[state.activeCardIndex]) {
        loadActiveMovieRecommendations(state.featuredMovies[state.activeCardIndex]);
      }
    } catch (err) {
      showToast("Rating saved!", "info");
      close();
    }
  });
}

function renderShelfRow(trackEl, movies, badgeType = "cluster", isColdStart = true) {
  if (!trackEl) return;
  trackEl.innerHTML = "";

  if (!movies || movies.length === 0) {
    trackEl.innerHTML = `<div style="padding: 24px; color: #888;">No recommendations available in this category.</div>`;
    return;
  }

  movies.forEach(m => {
    const card = document.createElement("div");
    card.className = "rec-card";
    card.dataset.movieId = m.movieId || m.tmdbId;
    card.dataset.titleNative = m.title_native || m.title;
    card.dataset.titleEn = m.title_en || m.title;

    const displayTitle = escapeHtml(getDisplayTitle(m));
    const posterSrc = m.poster_url || m.poster_large_url || "https://image.tmdb.org/t/p/w500/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg";
    const simBadge = m.similarity_percent || (m.similarity_pct ? `${m.similarity_pct}% match` : "95% match");
    const clusterTag = m.clusterName || m.cluster_name || "Cinema";
    const whyText = m.why_this || `Cluster: ${clusterTag} · ${simBadge}`;
    const langName = m.language_name || LANG_DISPLAY_NAMES[m.lang] || "English";

    // One rating scale everywhere: TMDB score as ★ X.X/10 and user's 5-star rating as "Your rating: ★ X.X/5"
    let ratingSnippet = "";
    if (m.userRating) {
      ratingSnippet = `<span class="rec-sub-dot">&bull;</span><span class="rec-user-rating" title="Your rating">Your: ★ ${Number(m.userRating).toFixed(1)}/5</span>`;
    } else if (badgeType === "rating" && !isColdStart && (m.predictedRating || m.predicted_rating)) {
      const pval = Number(m.predictedRating || m.predicted_rating).toFixed(1);
      ratingSnippet = `<span class="rec-sub-dot">&bull;</span><span class="rec-pred-rating" title="Predicted rating">Pred: ★ ${pval}/5</span>`;
    } else if (m.avgRating) {
      ratingSnippet = `<span class="rec-sub-dot">&bull;</span><span class="rec-tmdb-rating" title="TMDB audience score">★ ${Number(m.avgRating).toFixed(1)}/10</span>`;
    }

    const mid = m.tmdb_id || m.tmdbId || m.movieId;
    const mediaType = m.media_type || "movie";
    card.dataset.tmdbId = mid;
    card.dataset.mediaType = mediaType;
    card.setAttribute("data-tmdb-id", mid);
    card.setAttribute("data-media-type", mediaType);
    const bmBtn = getBookmarkBtnHtml(mid, mediaType);

    card.innerHTML = `
      <div class="rec-poster-wrap">
        <img class="rec-poster-img" src="${posterSrc}" alt="${displayTitle}" loading="lazy"
             onerror="handlePosterError(this, '${displayTitle}', '${m.year || ""}')" />
        <span class="rec-badge-cluster" title="Cluster: ${escapeHtml(clusterTag)}">${escapeHtml(clusterTag)}</span>
        <span class="rec-badge-similarity">${escapeHtml(simBadge)}</span>
        ${bmBtn}
      </div>
      <div class="rec-meta-info">
        <div class="rec-movie-title" title="${displayTitle}">${displayTitle}</div>
        <div class="rec-movie-sub">
          <span>${m.year || "2024"}</span>
          <span class="rec-sub-dot">&bull;</span>
          <span>${escapeHtml(langName)}</span>
          ${ratingSnippet}
        </div>
      </div>
      <div class="rec-feedback-bar" style="display: flex; gap: 6px; padding: 4px 8px 8px; justify-content: flex-end;">
        <button class="rec-fb-btn" data-action="like" data-id="${mid}" title="Like this recommendation" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15); color: #ccc; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 0.75rem;">👍</button>
        <button class="rec-fb-btn" data-action="dislike" data-id="${mid}" title="Dislike" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15); color: #ccc; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 0.75rem;">👎</button>
        <button class="rec-fb-btn" data-action="not_interested" data-id="${mid}" title="Not interested" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15); color: #ccc; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 0.75rem;">🚫</button>
      </div>
      <div class="rec-why-tooltip">${escapeHtml(whyText)}</div>
    `;

    // Feedback event handlers
    card.querySelectorAll(".rec-fb-btn").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        const movieId = btn.dataset.id;
        try {
          const res = await fetch("/api/feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ movieId, action })
          });
          const data = await res.json();
          showToast(data.message || `Feedback recorded (${action})`, "success");
          btn.style.borderColor = "#f9e27d";
          btn.style.color = "#f9e27d";
          if (state.featuredMovies[state.activeCardIndex]) {
            loadActiveMovieRecommendations(state.featuredMovies[state.activeCardIndex]);
          }
        } catch (err) {
          showToast("Feedback recorded locally", "info");
        }
      });
    });

    card.addEventListener("click", () => {
      openRateModal(m);
    });

    trackEl.appendChild(card);
  });
}

function setupShelfCarouselControls(trackId, prevBtnId, nextBtnId, fadeLeftId, fadeRightId) {
  const track = document.getElementById(trackId);
  const prevBtn = document.getElementById(prevBtnId);
  const nextBtn = document.getElementById(nextBtnId);
  const fadeLeft = document.getElementById(fadeLeftId);
  const fadeRight = document.getElementById(fadeRightId);

  if (!track) return;

  const updateFades = () => {
    if (fadeLeft) fadeLeft.classList.toggle("visible", track.scrollLeft > 15);
    if (fadeRight) {
      const maxScroll = track.scrollWidth - track.clientWidth;
      fadeRight.classList.toggle("visible", track.scrollLeft < maxScroll - 15);
    }
  };

  updateFades();
  track.addEventListener("scroll", updateFades, { passive: true });

  // Arrow button navigation
  prevBtn?.addEventListener("click", () => {
    track.scrollBy({ left: -400, behavior: "smooth" });
  });
  nextBtn?.addEventListener("click", () => {
    track.scrollBy({ left: 400, behavior: "smooth" });
  });

  // Mouse wheel horizontal delegation
  track.addEventListener("wheel", (e) => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
      e.preventDefault();
      track.scrollLeft += e.deltaY * 0.85;
    }
  }, { passive: false });
}

// ============================================================
// POSTER GRID (Browse & Rate)
// ============================================================
async function loadMovies(genre = "All", page = 1, replace = true) {
  const grid = document.getElementById("posterGrid");
  if (!grid) return;

  if (replace) {
    grid.innerHTML = Array(12).fill('<div class="skeleton-card"></div>').join("");
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      gsap.from(".skeleton-card", { opacity: 0, y: 15, stagger: 0.03, duration: 0.35, ease: "power2.out" });
    }
  }

  try {
    const params = new URLSearchParams({
      category: genre,
      lang: state.currentLang,
      page,
      per_page: 20
    });
    const res = await fetch(`/api/movies?${params}`);
    const data = await res.json();

    if (replace) grid.innerHTML = "";
    else {
      grid.querySelectorAll(".skeleton-card").forEach(el => el.remove());
    }

    data.movies.forEach(movie => {
      const card = createPosterCard(movie);
      grid.appendChild(card);
    });

    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      gsap.from(grid.querySelectorAll(".poster-card:not(.loaded-anim)"), {
        y: 25, opacity: 0, stagger: 0.04, duration: 0.45, ease: "power2.out",
        onComplete: () => grid.querySelectorAll(".poster-card").forEach(c => c.classList.add("loaded-anim"))
      });
    }

    const loadMore = document.getElementById("loadMoreBtn");
    if (loadMore) {
      loadMore.style.display = data.total <= page * 20 ? "none" : "inline-flex";
    }

    return data.movies;
  } catch (err) {
    console.error("Failed to load movies:", err);
    grid.innerHTML = `<p style="color:#666;grid-column:1/-1;text-align:center;padding:40px">Failed to load movies. Server running?</p>`;
    return [];
  }
}

function createPosterCard(movie) {
  const card = document.createElement("div");
  card.className = "poster-card";
  card.dataset.titleNative = movie.title_native || movie.title;
  card.dataset.titleEn = movie.title_en || movie.title_clean || movie.title;
  const mid = movie.tmdb_id || movie.movieId;
  const mediaType = movie.media_type || "movie";
  card.dataset.tmdbId = mid;
  card.dataset.mediaType = mediaType;
  card.setAttribute("data-tmdb-id", mid);
  card.setAttribute("data-media-type", mediaType);

  const userRating = state.ratings[movie.movieId] || 0;
  const ratedBadge = userRating ? `<div class="poster-rated-badge">⭐ ${userRating}</div>` : "";
  const posterSrc = movie.poster_url || (movie.poster_large_url || "");
  const displayTitle = getDisplayTitle(movie);
  const langName = movie.language_name || LANG_DISPLAY_NAMES[movie.lang] || "English";
  const bmBtn = getBookmarkBtnHtml(mid, mediaType);

  card.innerHTML = `
    ${ratedBadge}
    ${bmBtn}
    <div class="poster-img-wrap">
      ${posterSrc ? `
        <img src="${posterSrc}" alt="${escapeHtml(displayTitle)}" loading="lazy" class="poster-img"
             onerror="handlePosterError(this, '${escapeHtml(displayTitle)}', '${movie.year || ""}')" />
      ` : `
        <div class="poster-fallback">
          <div class="poster-fallback-title">${escapeHtml(displayTitle)}</div>
          <div class="poster-fallback-year">${movie.year || ""}</div>
        </div>
      `}
    </div>
    <div class="poster-info">
      <div class="poster-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)}</div>
      <div class="poster-meta">${movie.year || ""} &middot; ${escapeHtml(langName)} &middot; ⭐ ${movie.avgRating}</div>
      <div class="poster-cluster-tag">${escapeHtml(movie.clusterName)}</div>
      <div class="star-rating" data-movie-id="${movie.movieId}" data-title="${escapeHtml(displayTitle)}">
        ${[1, 2, 3, 4, 5].map(s => `<span class="star${userRating >= s ? " active" : ""}" data-star="${s}">★</span>`).join("")}
      </div>
    </div>
  `;

  // Star ratings hover & click
  const starRow = card.querySelector(".star-rating");
  starRow.querySelectorAll(".star").forEach(star => {
    star.addEventListener("click", e => {
      e.stopPropagation();
      const rating = parseInt(star.dataset.star);
      rateMovie(movie.movieId, rating, starRow, card);
    });
    star.addEventListener("mouseenter", () => {
      const hoverVal = parseInt(star.dataset.star);
      starRow.querySelectorAll(".star").forEach(s => {
        s.classList.toggle("active", parseInt(s.dataset.star) <= hoverVal);
      });
    });
    star.addEventListener("mouseleave", () => {
      const current = state.ratings[movie.movieId] || 0;
      starRow.querySelectorAll(".star").forEach(s => {
        s.classList.toggle("active", parseInt(s.dataset.star) <= current);
      });
    });
  });

  return card;
}

async function rateMovie(movieId, rating, starRow, card) {
  const stars = starRow.querySelectorAll(".star");
  stars.forEach((s, i) => {
    s.classList.toggle("active", i < rating);
    if (i === rating - 1) {
      s.classList.add("pop");
      setTimeout(() => s.classList.remove("pop"), 350);
    }
  });

  state.ratings[movieId] = rating;
  const countEl = document.getElementById("ratingCount");
  if (countEl) countEl.textContent = Object.keys(state.ratings).length;

  let badge = card.querySelector(".poster-rated-badge");
  if (!badge) {
    badge = document.createElement("div");
    badge.className = "poster-rated-badge";
    card.prepend(badge);
  }
  badge.textContent = "⭐ " + rating;

  try {
    await fetch("/api/rate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId: state.userId, movieId, rating })
    });
    showToast(`Rated "${starRow.dataset.title}" ⭐ ${rating}`, "success");
  } catch {
    showToast("Rating not saved — is server running?", "error");
  }

  // Refresh recommendations dynamically
  if (!state.recRefreshPending) {
    state.recRefreshPending = true;
    setTimeout(() => {
      loadRecommendations();
      state.recRefreshPending = false;
    }, 1200);
  }
}

// ============================================================
// RECOMMENDED FOR YOU & CROSS-CULTURE REGIONAL PICKS
// ============================================================
async function loadRecommendations() {
  const model = document.getElementById("modelSelect")?.value || "rf";
  state.recReqId = (state.recReqId || 0) + 1;
  const currentReqId = state.recReqId;

  if (state.recAbortController) {
    try { state.recAbortController.abort(); } catch (_) {}
  }
  state.recAbortController = new AbortController();

  const explEl = document.getElementById("recModelExpl");
  if (explEl) {
    explEl.textContent = model === "knn"
      ? "KNN: finds movies similar to ones you rated"
      : "Random Forest: predicts from movie features";
  }

  const row = document.getElementById("recRow");
  const knnPanel = document.getElementById("knnColdStartPanel");
  const carouselWrap = document.getElementById("recCarouselWrapper");
  const noteEl = document.getElementById("recommendedNote");
  const badgeRow = document.getElementById("recBadgeRow");
  const srcBadge = document.getElementById("recSourceBadge");
  const overlapBadge = document.getElementById("recOverlapBadge");

  // Show shimmer skeleton in recRow while fetching
  if (row) {
    row.innerHTML = `<div class="rec-card-skeleton"></div><div class="rec-card-skeleton"></div><div class="rec-card-skeleton"></div><div class="rec-card-skeleton"></div>`;
  }

  const params = new URLSearchParams({
    userId: state.userId,
    model,
    lang: state.currentLang,
    _t: Date.now().toString()
  });

  try {
    const res = await fetch(`/api/personal/recommend?${params}`, { signal: state.recAbortController.signal });
    const data = await res.json();
    console.log("[RecFetch] Result for model " + model + ":", data);

    if (currentReqId !== state.recReqId) {
      return;
    }
    const currentDropdownModel = document.getElementById("modelSelect")?.value || "rf";
    if (model !== currentDropdownModel) {
      return;
    }

    const usedCount = data.used_ratings_count || data.ratings_count || 0;
    const modelDisplayName = model === "knn" ? "KNN" : "Random Forest";

    if (badgeRow) badgeRow.style.display = "flex";
    if (srcBadge) {
      srcBadge.textContent = `Results from: ${modelDisplayName} (${usedCount} movies used)`;
    }

    if (overlapBadge) {
      if (data.overlap && data.overlap.label) {
        overlapBadge.textContent = data.overlap.label;
        overlapBadge.style.display = "inline-flex";
      } else {
        overlapBadge.style.display = "none";
      }
    }

    // Check cold-start condition
    if (model === "knn" && (data.status === "needs_ratings" || data.cold_start)) {
      if (carouselWrap) carouselWrap.style.display = "none";
      if (overlapBadge) overlapBadge.style.display = "none";
      if (noteEl) {
        noteEl.textContent = data.note || "KNN needs at least 3 rated or saved movies";
        noteEl.style.display = "inline-block";
      }
      renderKnnColdStartPanel();
    } else {
      if (knnPanel) {
        knnPanel.style.display = "none";
        knnPanel.innerHTML = "";
      }
      if (carouselWrap) carouselWrap.style.display = "block";
      if (noteEl) {
        if (data.cold_start) {
          noteEl.textContent = data.note || "Rate 3 movies to personalise. Showing popular picks";
          noteEl.style.display = "inline-block";
        } else {
          noteEl.style.display = "none";
        }
      }
      renderRecommendations(data.recommendations || [], data.cold_start);
    }

    if (data.favCluster) {
      const favEl = document.getElementById("favClusterName");
      if (favEl) favEl.textContent = data.favCluster.clusterName;
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      console.error("Recommend error:", err);
    }
  }

  // Load dedicated cross-culture regional gems
  loadCrossCultureMovies();
}

async function renderKnnColdStartPanel() {
  const knnPanel = document.getElementById("knnColdStartPanel");
  if (!knnPanel) return;

  // Clear previous content to guarantee no double rendering
  knnPanel.innerHTML = `
    <div class="knn-cold-start-banner">
      <div class="knn-alert-icon">⚡</div>
      <div class="knn-alert-content">
        <h3 class="knn-alert-title">KNN needs at least 3 rated or saved movies</h3>
        <p class="knn-alert-desc">KNN is a taste-based algorithm: it predicts your rating by finding movies closest to ones you personally rated. Rate 5 diverse movies below or activate the demo profile instantly:</p>
        <div class="knn-actions-row">
          <button id="btnTryDemoProfile" class="btn-primary btn-sm" type="button">★ Try demo profile (8 ratings)</button>
          <span class="knn-or-text">or rate quick-pick movies across 5 industries:</span>
        </div>
      </div>
    </div>
    <div class="quick-rate-shelf">
      <div class="quick-rate-grid" id="quickRateGrid">
        <div class="rec-card-skeleton" style="height:220px;border-radius:10px;"></div>
        <div class="rec-card-skeleton" style="height:220px;border-radius:10px;"></div>
        <div class="rec-card-skeleton" style="height:220px;border-radius:10px;"></div>
        <div class="rec-card-skeleton" style="height:220px;border-radius:10px;"></div>
        <div class="rec-card-skeleton" style="height:220px;border-radius:10px;"></div>
      </div>
    </div>
  `;
  knnPanel.style.display = "block";
  setupTasteProfileControls();

  try {
    const res = await fetch("/api/quick-picks");
    const data = await res.json();
    const grid = document.getElementById("quickRateGrid");
    if (!grid) return;
    grid.innerHTML = "";

    (data.items || data.cards || []).forEach(card => {
      const cardEl = document.createElement("div");
      cardEl.className = "quick-rate-card";
      cardEl.setAttribute("data-movie-id", card.tmdb_id);
      cardEl.setAttribute("data-tmdb-id", card.tmdb_id);
      cardEl.setAttribute("data-media-type", card.media_type || "movie");
      cardEl.dataset.movieId = card.tmdb_id;
      cardEl.dataset.tmdbId = card.tmdb_id;
      cardEl.dataset.mediaType = card.media_type || "movie";

      cardEl.innerHTML = `
        <div class="quick-rate-poster-wrap">
          <img src="${card.poster_url}" alt="${escapeHtml(card.title_en)}" class="quick-rate-img" loading="lazy"
               onerror="handlePosterError(this, '${escapeHtml(card.title_en)}', '${card.year || ""}')" />
          <span class="quick-rate-badge">${escapeHtml(card.industry || "Cinema")}</span>
        </div>
        <div class="quick-rate-info">
          <h4 class="quick-rate-title">${escapeHtml(card.title_en)}</h4>
          <div class="quick-stars" data-movie-id="${card.tmdb_id}">
            <span class="quick-star" data-val="1">★</span>
            <span class="quick-star" data-val="2">★</span>
            <span class="quick-star" data-val="3">★</span>
            <span class="quick-star" data-val="4">★</span>
            <span class="quick-star" data-val="5">★</span>
          </div>
        </div>
      `;
      grid.appendChild(cardEl);
    });

    setupTasteProfileControls();
  } catch (err) {
    console.error("Failed to load quick-picks:", err);
  }
}

function renderRecommendations(movies, coldStart) {
  const row = document.getElementById("recRow");
  const prompt = document.getElementById("coldStartPrompt");
  if (!row) return;

  if (!movies || !movies.length) {
    prompt?.classList.remove("hidden");
    row.innerHTML = "";
    return;
  }

  prompt?.classList.add("hidden");

  if (window.gsap && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    gsap.to(row, {
      opacity: 0,
      duration: 0.15,
      onComplete: () => {
        buildRecCards(movies, row, coldStart);
        gsap.fromTo(row.children,
          { opacity: 0, y: 15 },
          { opacity: 1, y: 0, stagger: 0.04, duration: 0.35, ease: "power2.out" }
        );
        gsap.to(row, { opacity: 1, duration: 0.2 });
      }
    });
  } else {
    buildRecCards(movies, row, coldStart);
  }
}

function setupTasteProfileControls() {
  const btnDemo = document.getElementById("btnTryDemoProfile");
  if (btnDemo) {
    btnDemo.addEventListener("click", async () => {
      btnDemo.disabled = true;
      btnDemo.textContent = "Loading taste profile...";
      try {
        const res = await fetch("/api/user/demo-profile", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || ""
          },
          body: JSON.stringify({ userId: state.userId })
        });
        const data = await res.json();
        if (data.success) {
          showToast("Demo profile loaded with 8 ratings!");
          await loadRecommendations();
          const activeMovie = state.featuredMovies[state.activeCardIndex];
          if (activeMovie) loadActiveMovieRecommendations(activeMovie);
        }
      } catch (err) {
        console.error("Demo profile error:", err);
      } finally {
        btnDemo.disabled = false;
        btnDemo.textContent = "★ Try demo profile (8 ratings)";
      }
    });
  }

  // Interactive 5-star quick-rating cards
  document.querySelectorAll(".quick-stars").forEach(starContainer => {
    const mid = starContainer.getAttribute("data-movie-id");
    const stars = starContainer.querySelectorAll(".quick-star");

    stars.forEach(star => {
      star.addEventListener("click", async () => {
        const ratingVal = parseInt(star.getAttribute("data-val") || "5");
        stars.forEach(s => {
          const sVal = parseInt(s.getAttribute("data-val") || "0");
          s.classList.toggle("active", sVal <= ratingVal);
        });

        try {
          const res = await fetch("/api/rate", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || ""
            },
            body: JSON.stringify({
              movieId: parseInt(mid),
              userId: state.userId,
              rating: ratingVal
            })
          });
          const resData = await res.json();
          if (resData.success) {
            showToast(`Rated ${ratingVal}/5 stars!`);
            loadRecommendations();
          }
        } catch (err) {
          console.error("Quick rate error:", err);
        }
      });
    });
  });
}

function buildRecCards(movies, row, coldStart) {
  row.innerHTML = "";
  movies.forEach((m, i) => {
    const card = document.createElement("div");
    card.className = "rec-card";
    card.dataset.titleNative = m.title_native || m.title;
    card.dataset.titleEn = m.title_en || m.title_clean || m.title;

    const posterSrc = m.poster_url || m.poster_large_url;
    const displayTitle = getDisplayTitle(m);

    const mid = m.tmdb_id || m.movieId;
    const mediaType = m.media_type || "movie";
    card.dataset.tmdbId = mid;
    card.dataset.mediaType = mediaType;
    card.setAttribute("data-tmdb-id", mid);
    card.setAttribute("data-media-type", mediaType);
    const langName = m.language_name || LANG_DISPLAY_NAMES[m.lang] || "English";
    const bmBtn = getBookmarkBtnHtml(mid, mediaType);

    const isPopular = coldStart || m.is_popular_pick;
    const scoreHtml = isPopular
      ? `<div class="rec-predicted" style="color:#aaa;">Popular Pick &middot; ★ ${m.avgRating}/10</div>`
      : `<div class="rec-predicted" id="rec-score-${i}">Predicted: ⭐ 0.0/10</div>`;

    card.innerHTML = `
      <div class="rec-poster-wrap">
        ${posterSrc ? `
          <img src="${posterSrc}" alt="${escapeHtml(displayTitle)}" loading="lazy" class="rec-poster"
               onerror="handlePosterError(this, '${escapeHtml(displayTitle)}', '${m.year || ""}')" />
        ` : `
          <div class="poster-fallback">
            <div class="poster-fallback-title">${escapeHtml(displayTitle)}</div>
            <div class="poster-fallback-year">${m.year || ""}</div>
          </div>
        `}
        ${bmBtn}
      </div>
      <div class="rec-info">
        <div class="rec-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)}</div>
        ${scoreHtml}
        <div class="rec-cluster-tag">${escapeHtml(m.clusterName || "General")} &middot; ${escapeHtml(langName)}</div>
      </div>
    `;

    row.appendChild(card);
  });

  if (!coldStart) {
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      gsap.from(row.querySelectorAll(".rec-card"), {
        x: 50, opacity: 0, stagger: 0.08, duration: 0.55, ease: "power3.out"
      });

      movies.forEach((m, i) => {
        const el = document.getElementById(`rec-score-${i}`);
        if (!el) return;
        const targetVal = m.predicted_score_10 || (m.predictedRating ? (m.predictedRating <= 5 ? m.predictedRating * 2 : m.predictedRating) : 8.5);
        gsap.to({ val: 0 }, {
          val: targetVal,
          duration: 1.1,
          delay: i * 0.08,
          ease: "power1.out",
          onUpdate: function () {
            el.textContent = `Predicted: ⭐ ${this.targets()[0].val.toFixed(1)}/10`;
          }
        });
      });
    } else {
      movies.forEach((m, i) => {
        const el = document.getElementById(`rec-score-${i}`);
        if (!el) return;
        const targetVal = m.predicted_score_10 || (m.predictedRating ? (m.predictedRating <= 5 ? m.predictedRating * 2 : m.predictedRating) : 8.5);
        el.textContent = `Predicted: ⭐ ${Number(targetVal).toFixed(1)}/10`;
      });
    }
  }
}

async function loadCrossCultureMovies() {
  const row = document.getElementById("crossCultureRow");
  if (!row) return;

  try {
    const res = await fetch("/api/cross-culture");
    const data = await res.json();
    renderCrossCulturePicks(data.movies || []);
  } catch (err) {
    console.error("Cross-culture error:", err);
  }
}

function renderCrossCulturePicks(movies) {
  const row = document.getElementById("crossCultureRow");
  if (!row) return;

  row.innerHTML = "";
  movies.forEach(m => {
    const card = document.createElement("div");
    card.className = "rec-card";
    card.dataset.titleNative = m.title_native || m.title;
    card.dataset.titleEn = m.title_en || m.title_clean || m.title;

    const posterSrc = m.poster_url || m.poster_large_url;
    const displayTitle = getDisplayTitle(m);

    const mid = m.tmdb_id || m.movieId;
    const mediaType = m.media_type || "movie";
    card.dataset.tmdbId = mid;
    card.dataset.mediaType = mediaType;
    card.setAttribute("data-tmdb-id", mid);
    card.setAttribute("data-media-type", mediaType);
    const langCode = m.lang || "hi";
    const langName = m.language_name || LANG_DISPLAY_NAMES[langCode] || langCode.toUpperCase();
    const bmBtn = getBookmarkBtnHtml(mid, mediaType);

    card.innerHTML = `
      <div class="rec-poster-wrap">
        ${posterSrc ? `
          <img src="${posterSrc}" alt="${escapeHtml(displayTitle)}" loading="lazy" class="rec-poster"
               onerror="handlePosterError(this, '${escapeHtml(displayTitle)}', '${m.year || ""}')" />
        ` : `
          <div class="poster-fallback">
            <div class="poster-fallback-title">${escapeHtml(displayTitle)}</div>
            <div class="poster-fallback-year">${m.year || ""}</div>
          </div>
        `}
        ${bmBtn}
      </div>
      <div class="rec-info">
        <span class="lang-chip chip-${langCode}">${escapeHtml(langName)}</span>
        <div class="rec-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)}</div>
        <div class="rec-predicted">Rating: ⭐ ${m.avgRating}/10</div>
        <div class="rec-cluster-tag" style="background:rgba(249,226,125,0.12);color:#f9e27d;">${escapeHtml(m.clusterName || "General")}</div>
      </div>
    `;

    row.appendChild(card);
  });

  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    gsap.from(row.querySelectorAll(".rec-card"), {
      y: 30, opacity: 0, stagger: 0.06, duration: 0.45, ease: "power2.out"
    });
  }
}

// Horizontal scroll controls: Arrow buttons, drag, and mouse wheel
function initShelfScrollControls() {
  const tracks = [
    { track: document.getElementById("recRow"), prev: document.getElementById("recRowPrev"), next: document.getElementById("recRowNext") },
    { track: document.getElementById("crossCultureRow"), prev: document.getElementById("crossCulturePrev"), next: document.getElementById("crossCultureNext") }
  ];

  tracks.forEach(({ track, prev, next }) => {
    if (!track) return;

    if (prev) {
      prev.addEventListener("click", () => {
        track.scrollBy({ left: -420, behavior: "smooth" });
      });
    }
    if (next) {
      next.addEventListener("click", () => {
        track.scrollBy({ left: 420, behavior: "smooth" });
      });
    }

    // Mouse wheel horizontal scroll
    track.addEventListener("wheel", (e) => {
      if (e.deltaY !== 0) {
        e.preventDefault();
        track.scrollLeft += e.deltaY;
      }
    }, { passive: false });

    // Drag to scroll
    let isDown = false;
    let startX = 0;
    let scrollLeft = 0;

    track.addEventListener("mousedown", (e) => {
      isDown = true;
      track.classList.add("dragging");
      startX = e.pageX - track.offsetLeft;
      scrollLeft = track.scrollLeft;
    });

    track.addEventListener("mouseleave", () => {
      isDown = false;
      track.classList.remove("dragging");
    });

    track.addEventListener("mouseup", () => {
      isDown = false;
      track.classList.remove("dragging");
    });

    track.addEventListener("mousemove", (e) => {
      if (!isDown) return;
      e.preventDefault();
      const x = e.pageX - track.offsetLeft;
      const walk = (x - startX) * 1.5;
      track.scrollLeft = scrollLeft - walk;
    });
  });
}

// ============================================================
// MODEL INSIGHTS MODAL
// ============================================================
function initInsightsModal() {
  const modal = document.getElementById("insightsModal");
  if (!modal) return;
  const openers = ["openInsights", "openInsights2"];
  const closer = document.getElementById("closeInsights");
  const langSelect = document.getElementById("modalLangSelect");

  openers.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", openModal);
  });

  closer?.addEventListener("click", closeModal);
  modal.addEventListener("click", e => { if (e.target === modal) closeModal(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

  langSelect?.addEventListener("change", () => {
    const lang = langSelect.value;
    loadMetrics(lang);
    loadClusters(lang);
  });

  document.querySelectorAll(".modal-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".modal-tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".modal-panel-content").forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      const target = document.getElementById("panel-" + tab.dataset.panel);
      if (target) target.classList.add("active");

      const currentLang = langSelect ? langSelect.value : state.currentLang;
      if (tab.dataset.panel === "metrics") loadMetrics(currentLang);
      if (tab.dataset.panel === "clusters") loadClusters(currentLang);
    });
  });

  function openModal() {
    modal.classList.add("active");
    document.body.style.overflow = "hidden";
    if (langSelect) langSelect.value = state.currentLang;
    loadMetrics(state.currentLang);
    loadClusters(state.currentLang);

    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      gsap.from(".modal-panel", { scale: 0.9, opacity: 0, duration: 0.35, ease: "back.out(1.4)" });
    }
  }

  function closeModal() {
    modal.classList.remove("active");
    document.body.style.overflow = "";
  }
}

async function loadMetrics(lang = "all") {
  const loading = document.getElementById("metricsLoading");
  const content = document.getElementById("metricsContent");
  const tbody = document.getElementById("metricsTableBody");
  const pcaImg = document.getElementById("pcaPlotImg");

  try {
    const res = await fetch(`/api/metrics?lang=${lang}`);
    const data = await res.json();
    if (data.error) {
      if (loading) loading.textContent = data.error;
      return;
    }

    if (pcaImg && data.pca_plot) {
      pcaImg.src = `${data.pca_plot}?t=${Date.now()}`;
      pcaImg.style.display = "block";
    }

    const rows = [
      { label: "Random Forest (With Cluster)", key: "rf_with_cluster", cluster: "Yes" },
      { label: "Random Forest (No Cluster)", key: "rf_no_cluster", cluster: "No" },
      { label: "KNN Regressor (With Cluster)", key: "knn_with_cluster", cluster: "Yes" }
    ];

    const allRMSE = rows.map(r => data.metrics[r.key]?.rmse ?? Infinity);
    const bestRMSE = Math.min(...allRMSE);

    tbody.innerHTML = rows.map(r => {
      const m = data.metrics[r.key] || {};
      const isBest = m.rmse === bestRMSE;
      return `<tr>
        <td>${r.label}</td>
        <td>${r.cluster === "Yes" ? '<span style="color:#34d399">Yes ✓</span>' : '<span style="color:#777">No</span>'}</td>
        <td class="${isBest ? "best" : ""}">${m.rmse ?? "—"}</td>
        <td>${m.mae ?? "—"}</td>
        <td>${m.r2 ?? "—"}</td>
      </tr>`;
    }).join("");

    // Populate Ramayana Spotlight Insight Box
    const insightBox = document.getElementById("spotlightInsightBox");
    if (insightBox && data.ramayana_spotlight) {
      insightBox.innerHTML = `
        <div>
          <div class="spotlight-insight-title">&#127916; Spotlight: ${escapeHtml(data.ramayana_spotlight.title)}</div>
          <div class="spotlight-insight-desc">Assigned to <strong>Cluster #${data.ramayana_spotlight.cluster_id} (${escapeHtml(data.ramayana_spotlight.cluster_name)})</strong> based on genre vectors.</div>
        </div>
        <span class="spotlight-insight-badge">Cluster #${data.ramayana_spotlight.cluster_id}</span>
      `;
      insightBox.style.display = "flex";
    } else if (insightBox) {
      insightBox.style.display = "none";
    }

    // Populate Watchlist Implicit Ratings Insight Box
    const wlBox = document.getElementById("watchlistInsightBox");
    if (wlBox) {
      const count = data.watchlist_implicit_count !== undefined ? data.watchlist_implicit_count : 0;
      const r = data.watchlist_implicit_rating || 4;
      wlBox.innerHTML = `
        <div>
          <div class="spotlight-insight-title">&#128278; Watchlist Implicit Feedback</div>
          <div class="spotlight-insight-desc">Watchlist items used as implicit ratings: <strong>${count}</strong> (rated ⭐ ${r}.0 for taste profiling).</div>
        </div>
        <span class="spotlight-insight-badge">${count} items</span>
      `;
      wlBox.style.display = "flex";
    }

    if (loading) loading.style.display = "none";
    if (content) content.style.display = "block";
  } catch (err) {
    if (loading) loading.textContent = "Failed to load metrics. Server running?";
  }
}

async function loadClusters(lang = "all") {
  const loading = document.getElementById("clustersLoading");
  const grid = document.getElementById("clustersGrid");
  if (!grid) return;

  try {
    const res = await fetch(`/api/clusters?lang=${lang}`);
    const data = await res.json();
    if (data.error) { if (loading) loading.textContent = data.error; return; }

    grid.innerHTML = data.clusters.map(c => `
      <div class="cluster-chip">
        <div class="cluster-chip-id">Cluster #${c.id}</div>
        <div class="cluster-chip-name">${c.name}</div>
        <div class="cluster-chip-count">${c.count} movies</div>
      </div>
    `).join("");

    if (loading) loading.style.display = "none";
    grid.style.display = "grid";
  } catch {
    if (loading) loading.textContent = "Failed to load clusters.";
  }
}

// ============================================================
// TABS & EVENT LISTENERS
// ============================================================
function initTabs() {
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.currentGenre = tab.dataset.genre;
      state.currentPage = 1;
      loadMovies(state.currentGenre, 1, true);
    });
  });
}

function initNavbar() {
  const navbar = document.getElementById("navbar");
  window.addEventListener("scroll", () => {
    navbar?.classList.toggle("scrolled", window.scrollY > 30);
  }, { passive: true });

  document.getElementById("mobileToggle")?.addEventListener("click", () => {
    document.getElementById("navLinks")?.classList.toggle("open");
  });

  // More dropdown toggle
  const moreBtn = document.getElementById("navMoreBtn");
  const moreMenu = document.getElementById("navMoreMenu");
  if (moreBtn && moreMenu) {
    moreBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      moreMenu.classList.toggle("show");
    });
    document.addEventListener("click", (e) => {
      if (!moreMenu.contains(e.target) && e.target !== moreBtn) {
        moreMenu.classList.remove("show");
      }
    });
  }

  // Open AI Assistant from More menu
  document.getElementById("navOpenAiBtn")?.addEventListener("click", () => {
    openAiDrawer();
  });
}

let liveClusterChartInstance = null;

async function initLiveClusterChart(lang = "all") {
  const canvas = document.getElementById("liveClusterChart");
  if (!canvas || typeof Chart === "undefined") return;

  try {
    const res = await fetch(`/api/clusters?lang=${lang}`);
    const data = await res.json();
    const clusters = data.clusters || [];
    if (!clusters.length) return;

    const labels = clusters.map(c => c.name.length > 24 ? c.name.slice(0, 22) + "…" : c.name);
    const counts = clusters.map(c => c.count);

    const palette = [
      "#f9e27d", "#e50914", "#3b82f6", "#10b981", "#8b5cf6",
      "#ec4899", "#f59e0b", "#06b6d4", "#84cc16", "#6366f1",
      "#14b8a6", "#f43f5e", "#a855f7", "#eab308", "#22c55e",
      "#0ea5e9", "#d946ef", "#fb923c", "#4ade80", "#38bdf8"
    ];

    if (liveClusterChartInstance) {
      liveClusterChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    liveClusterChartInstance = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [{
          data: counts,
          backgroundColor: palette.slice(0, clusters.length),
          borderColor: "#0f0f12",
          borderWidth: 2,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#1a1a1f",
            titleColor: "#f9e27d",
            bodyColor: "#ffffff",
            borderColor: "rgba(255,255,255,0.1)",
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: function(context) {
                const idx = context.dataIndex;
                const c = clusters[idx];
                return `${c.count} movies (${c.name})`;
              }
            }
          }
        },
        cutout: "60%"
      }
    });
  } catch (err) {
    console.error("Failed to load cluster distribution chart:", err);
  }
}

function openAiDrawer() {
  const drawer = document.getElementById("aiDrawer");
  if (drawer) {
    drawer.style.display = "flex";
    document.getElementById("aiChatInput")?.focus();
  }
}

function initAiAssistant() {
  const fab = document.getElementById("aiFabBtn");
  const drawer = document.getElementById("aiDrawer");
  const closer = document.getElementById("closeAiDrawer");
  const form = document.getElementById("aiChatForm");
  const input = document.getElementById("aiChatInput");
  const messagesBox = document.getElementById("aiChatMessages");

  if (!fab || !drawer) return;

  fab.addEventListener("click", () => {
    const isShown = drawer.style.display === "flex";
    drawer.style.display = isShown ? "none" : "flex";
    if (!isShown) input?.focus();
  });

  closer?.addEventListener("click", () => {
    drawer.style.display = "none";
  });

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = (input.value || "").trim();
    if (!query) return;

    // Append user message
    const userMsg = document.createElement("div");
    userMsg.style.cssText = "background: #f9e27d; color: #0f0f12; padding: 10px 14px; border-radius: 10px; align-self: flex-end; max-width: 85%; font-weight: 500;";
    userMsg.textContent = query;
    messagesBox.appendChild(userMsg);
    input.value = "";
    messagesBox.scrollTop = messagesBox.scrollHeight;

    // Typing indicator
    const typing = document.createElement("div");
    typing.style.cssText = "background: rgba(255,255,255,0.05); padding: 8px 12px; border-radius: 8px; color: #aaa; align-self: flex-start; font-size: 0.8rem;";
    typing.textContent = "CineStream AI is thinking...";
    messagesBox.appendChild(typing);
    messagesBox.scrollTop = messagesBox.scrollHeight;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: query })
      });
      const data = await res.json();
      typing.remove();

      const aiMsg = document.createElement("div");
      aiMsg.style.cssText = "background: rgba(255,255,255,0.05); padding: 10px 14px; border-radius: 10px; color: #eee; align-self: flex-start; max-width: 85%; line-height: 1.4;";
      // Basic markdown bold conversion
      aiMsg.innerHTML = escapeHtml(data.reply || "").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
      messagesBox.appendChild(aiMsg);
      messagesBox.scrollTop = messagesBox.scrollHeight;
    } catch (err) {
      typing.textContent = "Sorry, I had trouble connecting. Please try again!";
    }
  });
}

function initVoiceSearch() {
  const btn = document.getElementById("voiceSearchBtn");
  const input = document.getElementById("searchInput");
  if (!btn || !input) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    btn.title = "Voice search not supported in this browser";
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;

  btn.addEventListener("click", () => {
    try {
      recognition.start();
      btn.style.color = "#e50914";
      showToast("🎙️ Listening... Speak movie title or genre", "info");
    } catch (e) {
      recognition.stop();
      btn.style.color = "";
    }
  });

  recognition.onresult = (event) => {
    btn.style.color = "";
    const transcript = event.results[0][0].transcript;
    input.value = transcript;
    showToast(`Searching for: "${transcript}"`, "info");
    const ev = new Event("input", { bubbles: true });
    input.dispatchEvent(ev);
  };

  recognition.onerror = () => {
    btn.style.color = "";
  };
  recognition.onend = () => {
    btn.style.color = "";
  };
}

function initNewsletter() {
  document.getElementById("newsletterForm")?.addEventListener("submit", e => {
    e.preventDefault();
    const email = document.getElementById("newsletterEmail").value;
    if (!email) return;
    showToast("🎬 Subscribed to CineStream updates!", "success");
    document.getElementById("newsletterEmail").value = "";
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      gsap.from(".newsletter-btn", { rotation: 360, duration: 0.5, ease: "back.out(2)" });
    }
  });
}

function initButtonActions() {
  setupTasteProfileControls();
  document.getElementById("heroMoreLikeThis")?.addEventListener("click", () => {
    document.getElementById("ramayanaSpotlightRecs")?.scrollIntoView({ behavior: "smooth" });
  });
  document.getElementById("epicAllLangsToggle")?.addEventListener("change", e => {
    state.epicAllLangs = e.target.checked;
    const activeMovie = state.featuredMovies[state.activeCardIndex];
    if (activeMovie) loadActiveMovieRecommendations(activeMovie);
  });
  document.getElementById("refreshRec")?.addEventListener("click", () => {
    loadRecommendations();
    const activeMovie = state.featuredMovies[state.activeCardIndex];
    if (activeMovie) loadActiveMovieRecommendations(activeMovie);
    document.getElementById("recommended")?.scrollIntoView({ behavior: "smooth" });
  });
  document.getElementById("loadMoreBtn")?.addEventListener("click", () => {
    state.currentPage++;
    loadMovies(state.currentGenre, state.currentPage, false);
  });
  document.getElementById("modelSelect")?.addEventListener("change", () => {
    loadRecommendations();
    const activeMovie = state.featuredMovies[state.activeCardIndex];
    if (activeMovie) loadActiveMovieRecommendations(activeMovie);
  });
}

async function initUserAuth() {
  const navLoginBtn = document.getElementById("navLoginBtn");
  const navUserWrap = document.getElementById("navUserWrap");
  const navAvatarBtn = document.getElementById("navAvatarBtn");
  const navAvatarEmoji = document.getElementById("navAvatarEmoji");
  const navAvatarName = document.getElementById("navAvatarName");
  const navUserMenuBox = document.getElementById("navUserMenuBox");
  const menuUserHeader = document.getElementById("menuUserHeader");
  const navMenuLogoutBtn = document.getElementById("navMenuLogoutBtn");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

  if (!navLoginBtn || !navUserWrap) return;

  try {
    const res = await fetch("/api/auth/me");
    if (!res.ok) return;
    const data = await res.json();

    if (data.authenticated && data.user) {
      navLoginBtn.style.display = "none";
      navUserWrap.style.display = "block";

      const prefs = data.preferences || {};
      const avatarMap = {
        "avatar-1": "🎬",
        "avatar-2": "🚀",
        "avatar-3": "🎭",
        "avatar-4": "⚡",
        "avatar-5": "🍿",
        "avatar-6": "🕵️"
      };
      if (navAvatarEmoji) {
        navAvatarEmoji.textContent = avatarMap[prefs.avatar] || "🎬";
      }
      if (navAvatarName) {
        navAvatarName.textContent = prefs.display_name || data.user.display_name || data.user.username;
      }
      if (menuUserHeader) {
        menuUserHeader.textContent = `@${data.user.username}`;
      }

      // Dropdown toggle
      if (navAvatarBtn && navUserMenuBox) {
        navAvatarBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          const isOpen = navUserMenuBox.style.display === "block";
          navUserMenuBox.style.display = isOpen ? "none" : "block";
        });

        document.addEventListener("click", (e) => {
          if (!navUserWrap.contains(e.target)) {
            navUserMenuBox.style.display = "none";
          }
        });
      }

      if (navMenuLogoutBtn) {
        navMenuLogoutBtn.addEventListener("click", async () => {
          try {
            await fetch("/api/auth/logout", {
              method: "POST",
              headers: { "X-CSRFToken": csrfToken }
            });
            window.location.reload();
          } catch (e) {
            window.location.reload();
          }
        });
      }
    } else {
      navLoginBtn.style.display = "inline-flex";
      navUserWrap.style.display = "none";
    }
  } catch (err) {
    console.error("Auth status check failed:", err);
  }
}

// ============================================================
// APP BOOTSTRAP WITH ERROR ISOLATION (safeInit)
// ============================================================
function safeInit(name, fn) {
  try {
    const res = fn();
    if (res && typeof res.catch === "function") {
      res.catch(err => console.error(`[Async Init Error] ${name}:`, err));
    }
  } catch (err) {
    console.error(`[Init Error] ${name}:`, err);
  }
}

async function boot() {
  safeInit("openingScreen", initOpeningScreen);
  safeInit("navbar", initNavbar);
  safeInit("userAuth", initUserAuth);
  safeInit("watchlist", () => initWatchlist());
  safeInit("languageSwitcher", initLanguageSwitcher);
  safeInit("search", initSearch);
  safeInit("tabs", initTabs);
  safeInit("newsletter", initNewsletter);
  safeInit("buttonActions", initButtonActions);
  safeInit("insightsModal", initInsightsModal);
  safeInit("rateModal", initRateModal);
  safeInit("liveClusterChart", initLiveClusterChart);
  safeInit("aiAssistant", initAiAssistant);
  safeInit("voiceSearch", initVoiceSearch);
  safeInit("emberCanvas", initEmberCanvas);
  safeInit("trailerDebugPanel", initTrailerDebugPanel);
  safeInit("heroCarousel", () => initHeroCarousel());
  safeInit("introAnimation", runIntroAnimation);
  safeInit("browseMovies", () => loadMovies("All", 1, true));
  safeInit("recommendations", () => loadRecommendations());
  safeInit("shelfScrollControls", initShelfScrollControls);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}

