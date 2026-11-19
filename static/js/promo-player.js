/**
 * PromoPlayer - Single-instance YouTube Trailer Controller
 * Replaces all separate player instances and loadVideoById calls.
 * Uses request tokens to guarantee stale requests are ignored.
 */
const PromoPlayer = (() => {
  let player, ready = false, pending = null, token = 0, interacted = false;
  let state = { slug: null, lang: null, candidates: [], idx: 0 };
  const listeners = { playing: [], ended: [], failed: [] };
  const emit = (k, d) => listeners[k].forEach(f => f(d));
  const on = (k, f) => listeners[k].push(f);

  window.addEventListener("pointerdown", () => (interacted = true), { once: true });
  window.addEventListener("keydown", () => (interacted = true), { once: true });

  function loadAPI() {
    return new Promise(res => {
      if (window.YT && window.YT.Player) return res(true);
      let settled = false;
      const done = (ok) => {
        if (!settled) {
          settled = true;
          res(ok);
        }
      };
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => { prev && prev(); done(true); };
      const s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      s.onerror = () => {
        console.warn("[promo] YouTube IFrame API blocked or network error");
        done(false);
      };
      document.head.appendChild(s);
      setTimeout(() => done(false), 2500); // 2.5s fallback
    });
  }

  async function init(containerId) {
    try {
      const ok = await loadAPI();
      if (!ok || !window.YT || !window.YT.Player) {
        console.warn("[promo] YouTube player API unavailable. Operating in static backdrop mode.");
        ready = false;
        emit("failed", { slug: state.slug, lang: state.lang, candidates: state.candidates });
        return;
      }
      player = new YT.Player(containerId, {
        playerVars: {
          controls: 0,
          rel: 0,
          modestbranding: 1,
          playsinline: 1,
          mute: 1,
          iv_load_policy: 3,
          disablekb: 1,
          origin: location.origin
        },
        events: {
          onReady: () => {
            ready = true;
            if (pending) {
              const j = pending;
              pending = null;
              run(j);
            }
          },
          onStateChange: e => {
            if (e.data === YT.PlayerState.PLAYING) emit("playing", { ...state, videoId: currentId() });
            if (e.data === YT.PlayerState.ENDED) emit("ended", { ...state });
          },
          onError: e => {
            console.warn("[promo] error", e.data, "slug:", state.slug, "id:", state.candidates[state.idx]);
            nextCandidate();
          }
        }
      });
    } catch (err) {
      console.warn("[promo] YT.Player init failed:", err);
      ready = false;
    }
  }

  const currentId = () => (player && player.getVideoData ? player.getVideoData().video_id : null);

  // candidates come ONLY from this movie, never from another movie or a global variable
  function candidatesFor(movie, lang) {
    const t = movie.trailers || {};
    const orig = movie.original_language || movie.original_lang || movie.default_lang;
    const list = [t[lang], t[orig], t.en, ...Object.values(t)].filter(Boolean);
    return [...new Set(list)];
  }

  // movie = the full movie object captured at call time (not an index looked up later)
  function play(movie, lang, opts = {}) {
    const job = { id: ++token, movie, lang, sound: !!opts.sound };
    if (!ready) {
      pending = job;
      if (!window.YT || !window.YT.Player) {
        emit("failed", { slug: movie.slug, lang, candidates: candidatesFor(movie, lang), idx: 0 });
      }
      return;
    }
    run(job);
  }

  function run(job) {
    state = { slug: job.movie.slug, lang: job.lang, candidates: candidatesFor(job.movie, job.lang), idx: 0, token: job.id, sound: job.sound };
    if (!state.candidates.length) { console.warn("[promo] no trailer for", job.movie.slug); emit("failed", state); return; }
    loadCurrent();
  }

  function loadCurrent() {
    const my = state.token, vid = state.candidates[state.idx];
    player.loadVideoById({ videoId: vid, startSeconds: 0 });   // ALWAYS load, even if something is playing
    if (state.sound && interacted) { player.unMute(); player.setVolume(100); } else player.mute();
    verify(my, vid, 0);
  }

  // safety net: confirm the player really switched to the requested video
  function verify(my, vid, tries) {
    setTimeout(() => {
      if (my !== token) return;                       // a newer request replaced this one
      if (currentId() !== vid) {
        if (tries < 3) { player.loadVideoById({ videoId: vid, startSeconds: 0 }); verify(my, vid, tries + 1); }
        else console.error("[promo] player did not switch to", vid, "for", state.slug);
      }
    }, 1200);
  }

  function nextCandidate() {
    if (state.idx + 1 < state.candidates.length) { state.idx++; loadCurrent(); }
    else emit("failed", { ...state });
  }

  const stop = () => { token++; pending = null; if (ready && player && player.pauseVideo) player.pauseVideo(); };
  const pause = () => { if (ready && player && player.pauseVideo) player.pauseVideo(); };
  const resume = () => { if (ready && player && player.playVideo) player.playVideo(); };
  const seekTo = (s) => { if (ready && player && player.seekTo) player.seekTo(s, true); };
  const getDuration = () => (ready && player && player.getDuration ? player.getDuration() : 0);
  const getCurrentTime = () => (ready && player && player.getCurrentTime ? player.getCurrentTime() : 0);
  const getPlayerState = () => (ready && player && player.getPlayerState ? player.getPlayerState() : -1);
  const setMuted = m => {
    if (!ready || !player) return;
    if (m) {
      if (player.mute) player.mute();
    } else {
      if (player.unMute) player.unMute();
      if (player.setVolume) player.setVolume(100);
    }
  };
  const getActualVideoId = () => currentId();
  const getState = () => ({ ...state, actualVideoId: currentId() });
  const isReady = () => ready;

  return {
    init,
    play,
    stop,
    pause,
    resume,
    seekTo,
    getDuration,
    getCurrentTime,
    getPlayerState,
    setMuted,
    on,
    getActualVideoId,
    getState,
    isReady
  };
})();