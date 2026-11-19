/**
 * watchlist.js - CineStream Watchlist Page Controller
 * Handles filtering, search, custom reordering with SortableJS,
 * 5-star rating sync, watched toggling, ML centroid recommendations,
 * Chart.js cluster distribution, export/import, and trailer playback.
 */

let allWatchlistItems = [];
let currentFilter = {
  status: "saved",      // "saved", "watched", "all"
  mediaType: "all",     // "all", "movie", "tv", "animation", "anime"
  lang: "all",          // "all", "en", "hi", "kn", "ta", "te", "ml", "ja"
  sort: "recently_added",// "recently_added", "title_asc", "year_desc", "rating_desc", "custom"
  searchQuery: ""
};

let sortableInstance = null;
let clusterChartInstance = null;
let toastTimer = null;

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

function ensureEnglish(text, fallback = "") {
  if (!text) return fallback;
  const NON_LATIN_RE = /[\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u3040-\u30FF\u4E00-\u9FFF]/;
  return NON_LATIN_RE.test(text) ? fallback : text;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showToast(msg, type = "success") {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.className = `toast show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3500);
}

function showToastWithUndo(msg, onUndo) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.innerHTML = `
    <span>${escapeHtml(msg)}</span>
    <button class="toast-undo-btn" id="toastUndoBtn">Undo</button>
  `;
  toast.className = "toast show";
  clearTimeout(toastTimer);
  const undoBtn = document.getElementById("toastUndoBtn");
  if (undoBtn) {
    undoBtn.onclick = () => {
      toast.classList.remove("show");
      if (typeof onUndo === "function") onUndo();
    };
  }
  toastTimer = setTimeout(() => toast.classList.remove("show"), 4000);
}

document.addEventListener("DOMContentLoaded", () => {
  initToolbar();
  initModals();
  initExportImport();
  loadWatchlist();
});

function initToolbar() {
  // Status tabs (Saved / Watched / All)
  document.querySelectorAll(".status-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".status-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentFilter.status = tab.dataset.status;
      renderGrid();
    });
  });

  // Media type pills
  document.querySelectorAll(".media-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".media-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentFilter.mediaType = pill.dataset.type;
      renderGrid();
    });
  });

  // Language select
  const langSelect = document.getElementById("watchlistLangSelect");
  langSelect?.addEventListener("change", (e) => {
    currentFilter.lang = e.target.value;
    renderGrid();
  });

  // Sort select
  const sortSelect = document.getElementById("watchlistSortSelect");
  sortSelect?.addEventListener("change", (e) => {
    currentFilter.sort = e.target.value;
    renderGrid();
  });

  // Search input
  const searchInput = document.getElementById("watchlistSearchInput");
  searchInput?.addEventListener("input", (e) => {
    currentFilter.searchQuery = e.target.value.trim().toLowerCase();
    renderGrid();
  });
}

function initModals() {
  // Clear confirm modal
  const clearBtn = document.getElementById("clearWatchlistBtn");
  const modal = document.getElementById("clearConfirmModal");
  const cancelBtn = document.getElementById("cancelClearBtn");
  const confirmBtn = document.getElementById("confirmClearBtn");

  clearBtn?.addEventListener("click", () => {
    if (allWatchlistItems.length === 0) {
      showToast("Watchlist is already empty.", "info");
      return;
    }
    modal?.classList.add("active");
  });

  cancelBtn?.addEventListener("click", () => {
    modal?.classList.remove("active");
  });

  confirmBtn?.addEventListener("click", async () => {
    modal?.classList.remove("active");
    try {
      const res = await fetch("/api/watchlist", { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        showToast("Your watchlist has been cleared.", "info");
        await loadWatchlist();
      }
    } catch {
      showToast("Failed to clear watchlist.", "error");
    }
  });

  // Trailer modal close
  const trailerModal = document.getElementById("watchlistTrailerModal");
  const closeTrailerBtn = document.getElementById("closeWatchlistTrailer");
  closeTrailerBtn?.addEventListener("click", () => {
    closeWatchlistTrailerModal();
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeWatchlistTrailerModal();
      modal?.classList.remove("active");
    }
  });
}

function closeWatchlistTrailerModal() {
  const trailerModal = document.getElementById("watchlistTrailerModal");
  if (trailerModal) {
    trailerModal.classList.remove("active");
  }
  if (window.PromoPlayer && typeof window.PromoPlayer.stop === "function") {
    window.PromoPlayer.stop();
  }
}

function initExportImport() {
  // Export JSON
  document.getElementById("exportWatchlistBtn")?.addEventListener("click", () => {
    if (!allWatchlistItems || allWatchlistItems.length === 0) {
      showToast("No items in watchlist to export.", "info");
      return;
    }
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(allWatchlistItems, null, 2));
    const a = document.createElement("a");
    a.href = dataStr;
    a.download = `cinestream_watchlist_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    showToast("Watchlist exported successfully!", "success");
  });

  // Import JSON
  const fileInput = document.getElementById("importWatchlistFile");
  fileInput?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const items = JSON.parse(text);
      if (!Array.isArray(items)) {
        showToast("Invalid JSON: Expected an array of movies.", "error");
        return;
      }

      let imported = 0;
      for (const it of items) {
        const tmdb_id = it.tmdb_id || it.movieId || it.id;
        if (!tmdb_id) continue;
        const media_type = it.media_type || "movie";
        const res = await fetch("/api/watchlist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            tmdb_id,
            media_type,
            title: ensureEnglish(it.title, it.title || "Movie"),
            poster_url: it.poster_url || "",
            release_year: it.release_year || it.year || "",
            lang: it.lang || "en",
            genres: it.genres || "",
            cluster_name: it.cluster_name || ""
          })
        });
        if (res.ok) imported++;
      }
      showToast(`Imported ${imported} items into Watchlist!`, "success");
      fileInput.value = "";
      await loadWatchlist();
    } catch (err) {
      showToast("Error importing file. Check format.", "error");
    }
  });
}

async function loadWatchlist() {
  try {
    const res = await fetch("/api/watchlist");
    const data = await res.json();
    allWatchlistItems = data.items || [];

    updateCounts();
    renderGrid();
    loadRecommendations();
    loadClusters();
  } catch (err) {
    console.error("Failed to fetch watchlist:", err);
  }
}

function updateCounts() {
  const total = allWatchlistItems.length;
  const saved = allWatchlistItems.filter(i => !i.watched).length;
  const watched = allWatchlistItems.filter(i => i.watched).length;

  const badgeNav = document.getElementById("navWatchlistBadge");
  if (badgeNav) badgeNav.textContent = total;

  const countWl = document.getElementById("watchlistCount");
  if (countWl) countWl.textContent = total;

  const cSaved = document.getElementById("countSaved");
  if (cSaved) cSaved.textContent = saved;

  const cWatched = document.getElementById("countWatched");
  if (cWatched) cWatched.textContent = watched;

  const cAll = document.getElementById("countAll");
  if (cAll) cAll.textContent = total;
}

function renderGrid() {
  const grid = document.getElementById("watchlistGrid");
  const emptyState = document.getElementById("watchlistEmptyState");
  const dragBanner = document.getElementById("dragHintBanner");
  if (!grid) return;

  grid.innerHTML = "";

  // Filter items
  let filtered = allWatchlistItems.filter(item => {
    // Status
    if (currentFilter.status === "saved" && item.watched) return false;
    if (currentFilter.status === "watched" && !item.watched) return false;

    // Media type
    if (currentFilter.mediaType !== "all") {
      const itType = (item.media_type || "movie").toLowerCase();
      if (currentFilter.mediaType === "animation" || currentFilter.mediaType === "anime") {
        const g = (item.genres || "").toLowerCase();
        if (!g.includes("animation")) return false;
      } else if (itType !== currentFilter.mediaType) {
        return false;
      }
    }

    // Language
    if (currentFilter.lang !== "all" && item.lang !== currentFilter.lang) {
      return false;
    }

    // Search query
    if (currentFilter.searchQuery) {
      const title = (item.title || "").toLowerCase();
      if (!title.includes(currentFilter.searchQuery)) return false;
    }

    return true;
  });

  // Sort items
  if (currentFilter.sort === "title_asc") {
    filtered.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
  } else if (currentFilter.sort === "year_desc") {
    filtered.sort((a, b) => parseInt(b.release_year || b.year || 0) - parseInt(a.release_year || a.year || 0));
  } else if (currentFilter.sort === "rating_desc") {
    filtered.sort((a, b) => (b.user_rating || b.rating || 0) - (a.user_rating || a.rating || 0));
  } else if (currentFilter.sort === "custom") {
    filtered.sort((a, b) => (a.position || 0) - (b.position || 0));
  } else {
    // recently_added
    filtered.sort((a, b) => new Date(b.added_at || 0) - new Date(a.added_at || 0));
  }

  // Handle SortableJS instance
  if (currentFilter.sort === "custom" && currentFilter.status === "all" && !currentFilter.searchQuery) {
    dragBanner.style.display = "block";
    if (!sortableInstance) {
      sortableInstance = Sortable.create(grid, {
        animation: 180,
        handle: ".drag-handle",
        ghostClass: "sortable-ghost",
        onEnd: async function () {
          const reordered = Array.from(grid.children).map((card, idx) => ({
            tmdb_id: parseInt(card.dataset.id),
            media_type: card.dataset.type,
            position: idx
          }));
          await fetch("/api/watchlist/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ items: reordered })
          });
          // Update local positions
          reordered.forEach(r => {
            const it = allWatchlistItems.find(i => i.tmdb_id === r.tmdb_id && i.media_type === r.media_type);
            if (it) it.position = r.position;
          });
        }
      });
    }
  } else {
    dragBanner.style.display = "none";
    if (sortableInstance) {
      sortableInstance.destroy();
      sortableInstance = null;
    }
  }

  if (filtered.length === 0) {
    if (emptyState) emptyState.style.display = "block";
    return;
  }
  if (emptyState) emptyState.style.display = "none";

  // Build cards
  filtered.forEach(item => {
    const card = createWatchlistCard(item);
    grid.appendChild(card);
  });

  // Animate cards appearance
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    gsap.from(grid.querySelectorAll(".watchlist-card"), {
      opacity: 0,
      y: 20,
      stagger: 0.04,
      duration: 0.4,
      ease: "power2.out"
    });
  }
}

function createWatchlistCard(item) {
  const card = document.createElement("div");
  card.className = `watchlist-card ${item.watched ? "is-watched" : ""}`;
  card.dataset.id = item.tmdb_id;
  card.dataset.type = item.media_type || "movie";

  const displayTitle = ensureEnglish(item.title, item.title || "Movie");
  const posterSrc = item.poster_url || "https://image.tmdb.org/t/p/w500/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg";
  const year = item.release_year || item.year || "2024";
  const langName = item.language_name || LANG_DISPLAY_NAMES[item.lang] || "English";
  const clusterName = item.cluster_name || item.clusterName || "General";
  const userRating = item.user_rating || item.rating || 0;

  card.innerHTML = `
    <div class="wl-poster-wrap">
      <img src="${posterSrc}" alt="${escapeHtml(displayTitle)}" class="wl-poster-img" loading="lazy"
           onerror="this.src='https://image.tmdb.org/t/p/w500/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg'" />
      
      <div class="wl-watched-ribbon" style="${item.watched ? '' : 'display:none;'}">
        <span>&#10003; Watched</span>
      </div>

      <button class="wl-remove-btn" title="Remove from Watchlist" aria-label="Remove">&times;</button>
      <div class="drag-handle" title="Drag to reorder" style="${currentFilter.sort === 'custom' ? '' : 'display:none;'}">&#8693;</div>
      
      <button class="wl-play-trailer-btn" title="Play Trailer">
        <span class="btn-play-icon">&#9654;</span>
      </button>
    </div>

    <div class="wl-info-wrap">
      <div class="wl-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)}</div>
      <div class="wl-meta">
        <span>${year}</span> &middot; <span>${escapeHtml(langName)}</span>
      </div>
      <div class="wl-cluster-tag">${escapeHtml(clusterName)}</div>

      <!-- Watched Switch & 5-Star Rating -->
      <div class="wl-controls">
        <label class="wl-watched-toggle" title="Mark as watched">
          <input type="checkbox" class="watched-checkbox" ${item.watched ? "checked" : ""} />
          <span class="watched-slider"></span>
          <span class="watched-label">${item.watched ? "Watched" : "Unwatched"}</span>
        </label>

        <div class="wl-star-rating" data-id="${item.tmdb_id}" data-type="${item.media_type}">
          ${[1, 2, 3, 4, 5].map(s => `<span class="wl-star ${userRating >= s ? 'active' : ''}" data-val="${s}">★</span>`).join("")}
        </div>
      </div>
    </div>
  `;

  // Remove button
  card.querySelector(".wl-remove-btn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    removeItem(item);
  });

  // Watched checkbox toggle
  const chk = card.querySelector(".watched-checkbox");
  chk?.addEventListener("change", (e) => {
    e.stopPropagation();
    toggleWatched(item, chk.checked, card);
  });

  // Star ratings
  const starContainer = card.querySelector(".wl-star-rating");
  starContainer?.querySelectorAll(".wl-star").forEach(st => {
    st.addEventListener("click", (e) => {
      e.stopPropagation();
      const val = parseInt(st.dataset.val);
      setRating(item, val, starContainer, card);
    });
    st.addEventListener("mouseenter", () => {
      const val = parseInt(st.dataset.val);
      starContainer.querySelectorAll(".wl-star").forEach(s => {
        s.classList.toggle("hover", parseInt(s.dataset.val) <= val);
      });
    });
    st.addEventListener("mouseleave", () => {
      starContainer.querySelectorAll(".wl-star").forEach(s => s.classList.remove("hover"));
    });
  });

  // Play trailer button
  card.querySelector(".wl-play-trailer-btn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    openTrailerModal(item);
  });

  return card;
}

async function removeItem(item) {
  const displayTitle = ensureEnglish(item.title, item.title || "Movie");
  // Optimistically remove from allWatchlistItems
  const idx = allWatchlistItems.findIndex(i => i.tmdb_id === item.tmdb_id && i.media_type === item.media_type);
  if (idx !== -1) {
    allWatchlistItems.splice(idx, 1);
  }
  updateCounts();
  renderGrid();
  loadRecommendations();
  loadClusters();

  showToastWithUndo(`Removed "${displayTitle}" from Watchlist`, async () => {
    // Undo
    await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tmdb_id: item.tmdb_id,
        media_type: item.media_type,
        title: item.title,
        poster_url: item.poster_url,
        release_year: item.release_year,
        lang: item.lang,
        genres: item.genres,
        cluster_name: item.cluster_name
      })
    });
    await loadWatchlist();
  });

  try {
    await fetch(`/api/watchlist/${item.media_type}/${item.tmdb_id}`, { method: "DELETE" });
  } catch (err) {
    console.error("Failed to delete item:", err);
  }
}

async function toggleWatched(item, isWatched, card) {
  item.watched = isWatched ? 1 : 0;
  const ribbon = card.querySelector(".wl-watched-ribbon");
  if (ribbon) ribbon.style.display = isWatched ? "block" : "none";
  const label = card.querySelector(".watched-label");
  if (label) label.textContent = isWatched ? "Watched" : "Unwatched";
  card.classList.toggle("is-watched", isWatched);

  updateCounts();
  if (currentFilter.status !== "all") {
    setTimeout(renderGrid, 250);
  }

  try {
    await fetch(`/api/watchlist/${item.media_type}/${item.tmdb_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ watched: isWatched ? 1 : 0 })
    });
  } catch (err) {
    console.error("Failed to update watched status:", err);
  }
}

async function setRating(item, score, starContainer, card) {
  item.user_rating = score;
  item.rating = score;

  starContainer.querySelectorAll(".wl-star").forEach(s => {
    const val = parseInt(s.dataset.val);
    s.classList.toggle("active", val <= score);
  });

  // Automatically mark as watched when rated
  if (!item.watched) {
    const chk = card.querySelector(".watched-checkbox");
    if (chk) chk.checked = true;
    toggleWatched(item, true, card);
  }

  showToast(`Rated "${ensureEnglish(item.title, item.title)}" ⭐ ${score}`);

  try {
    await fetch(`/api/watchlist/${item.media_type}/${item.tmdb_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating: score, watched: 1 })
    });
    loadRecommendations();
  } catch (err) {
    console.error("Failed to sync rating:", err);
  }
}

function openTrailerModal(item) {
  const modal = document.getElementById("watchlistTrailerModal");
  const titleEl = document.getElementById("trailerModalTitle");
  const metaEl = document.getElementById("trailerModalMeta");

  const displayTitle = ensureEnglish(item.title, item.title || "Movie");
  if (titleEl) titleEl.textContent = `${displayTitle} — Trailer`;
  if (metaEl) {
    metaEl.textContent = `${item.release_year || item.year || ""} · ${LANG_DISPLAY_NAMES[item.lang] || "English"} · ${item.cluster_name || ""}`;
  }

  modal?.classList.add("active");

  if (window.PromoPlayer && typeof window.PromoPlayer.play === "function") {
    // Construct playable movie object
    const movieObj = {
      slug: item.slug || `movie-${item.tmdb_id}`,
      title: displayTitle,
      trailers: item.trailers || {
        [item.lang || "en"]: item.trailer_youtube_id || item.trailer_id || ""
      },
      selected_audio: item.lang || "en",
      trailer_youtube_id: item.trailer_youtube_id || item.trailer_id
    };
    window.PromoPlayer.play(movieObj, item.lang || "en", { sound: true });
  }
}

async function loadRecommendations() {
  const section = document.getElementById("watchlistRecsSection");
  const row = document.getElementById("watchlistRecsRow");
  if (!section || !row) return;

  if (allWatchlistItems.length === 0) {
    section.style.display = "none";
    return;
  }

  try {
    const res = await fetch("/api/watchlist/recommend?top_n=10");
    const data = await res.json();
    const recs = data.recommendations || [];

    if (recs.length === 0) {
      section.style.display = "none";
      return;
    }

    row.innerHTML = "";
    recs.forEach(m => {
      const card = document.createElement("div");
      card.className = "rec-card wl-rec-card";
      const displayTitle = ensureEnglish(m.title_en || m.title, m.title_en || "Movie");
      const posterSrc = m.poster_url || m.poster_large_url || "https://image.tmdb.org/t/p/w500/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg";
      const simMatch = m.match_percentage || 92;
      const whyThis = m.why_this || `High affinity with your saved movies`;
      const clusterTag = m.clusterName || m.cluster_name || "General";
      const langName = m.language_name || LANG_DISPLAY_NAMES[m.lang] || "English";

      card.innerHTML = `
        <div class="rec-poster-wrap">
          <img class="rec-poster-img" src="${posterSrc}" alt="${escapeHtml(displayTitle)}" loading="lazy"
               onerror="this.src='https://image.tmdb.org/t/p/w500/vBQ7wks68OhJKlb3RnXSl2yXBXK.jpg'" />
          <span class="rec-badge-similarity">${simMatch}% match</span>
          <button class="wl-add-rec-btn" title="Add to Watchlist" aria-label="Add to Watchlist">+</button>
        </div>
        <div class="rec-meta-info">
          <div class="rec-movie-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)}</div>
          <div class="rec-movie-sub">
            <span>${m.year || "2024"}</span>
            <span class="rec-sub-dot">&bull;</span>
            <span>${escapeHtml(langName)}</span>
          </div>
        </div>
        <div class="rec-why-tooltip">${escapeHtml(whyThis)}</div>
      `;

      card.querySelector(".wl-add-rec-btn")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        await fetch("/api/watchlist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            tmdb_id: m.tmdb_id || m.movieId,
            media_type: m.media_type || "movie",
            title: displayTitle,
            poster_url: posterSrc,
            release_year: m.year,
            lang: m.lang,
            genres: m.genres,
            cluster_name: clusterTag
          })
        });
        showToast(`Added "${displayTitle}" to Watchlist!`);
        await loadWatchlist();
      });

      row.appendChild(card);
    });

    section.style.display = "block";
  } catch (err) {
    console.error("Failed to load watchlist recommendations:", err);
  }
}

async function loadClusters() {
  const section = document.getElementById("watchlistClusterSection");
  const canvas = document.getElementById("watchlistClusterChart");
  const legend = document.getElementById("clusterChartLegend");
  if (!section || !canvas) return;

  if (allWatchlistItems.length === 0) {
    section.style.display = "none";
    return;
  }

  try {
    const res = await fetch("/api/watchlist/clusters");
    const data = await res.json();
    if (!data.labels || data.labels.length === 0 || data.total === 0) {
      section.style.display = "none";
      return;
    }

    section.style.display = "block";

    const colors = [
      "#f9e27d", "#38bdf8", "#ec4899", "#34d399",
      "#a78bfa", "#fb923c", "#f43f5e", "#2dd4bf"
    ];

    if (clusterChartInstance) {
      clusterChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    clusterChartInstance = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: data.labels,
        datasets: [{
          data: data.data,
          backgroundColor: colors.slice(0, data.labels.length),
          borderWidth: 2,
          borderColor: "#16161f"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: function (context) {
                const count = context.raw;
                const pct = Math.round((count / data.total) * 100);
                return ` ${context.label}: ${count} movies (${pct}%)`;
              }
            }
          }
        },
        cutout: "65%"
      }
    });

    if (legend) {
      legend.innerHTML = data.labels.map((lbl, i) => {
        const count = data.data[i];
        const pct = Math.round((count / data.total) * 100);
        const col = colors[i % colors.length];
        return `
          <div class="legend-pill">
            <span class="legend-color-dot" style="background:${col}"></span>
            <span class="legend-name">${escapeHtml(lbl)}</span>
            <span class="legend-count">${count} (${pct}%)</span>
          </div>
        `;
      }).join("");
    }
  } catch (err) {
    console.error("Failed to load cluster chart:", err);
  }
}
