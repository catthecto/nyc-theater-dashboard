(() => {
  let allShows = [];
  let metadata = {};
  let currentView = "grid";
  let leafletMap = null;
  let markerLayer = null;

  const grid = document.getElementById("card-grid");
  const mapContainer = document.getElementById("map-container");
  const emptyState = document.getElementById("empty-state");
  const showCount = document.getElementById("show-count");
  const freshness = document.getElementById("freshness");
  const filterToggle = document.getElementById("filter-toggle");
  const filterPanel = document.getElementById("filter-panel");
  const filterCountEl = document.getElementById("filter-count");
  const searchInput = document.getElementById("search-input");
  const sortSelect = document.getElementById("sort-select");

  const CORE_GENRES = new Set(["play", "musical"]);

  const filters = {
    genre: "core",
    category: "all",
    status: "running",
    price: "all",
    search: "",
    sort: "price-asc",
  };

  async function init() {
    try {
      const resp = await fetch("data/shows.json");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      allShows = data.shows;
      metadata = data.metadata;
      restoreFiltersFromHash();
      renderFreshness();
      render();
      bindEvents();
    } catch (err) {
      grid.innerHTML = `<p style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:3rem">Failed to load show data. Try refreshing.</p>`;
      console.error(err);
    }
  }

  function renderFreshness() {
    if (!metadata.last_updated) return;
    const updated = new Date(metadata.last_updated);
    const hoursAgo = Math.floor((Date.now() - updated) / 3600000);
    let dotClass = "fresh";
    let label;
    if (hoursAgo < 24) {
      label = hoursAgo < 1 ? "Just updated" : `Updated ${hoursAgo}h ago`;
    } else if (hoursAgo < 48) {
      label = "Updated yesterday";
      dotClass = "stale";
    } else {
      label = `Updated ${Math.floor(hoursAgo / 24)}d ago`;
      dotClass = "old";
    }
    freshness.innerHTML = `<span class="freshness-dot ${dotClass}"></span>${label}`;
  }

  function bindEvents() {
    document.querySelectorAll(".button-group").forEach((group) => {
      const filterName = group.dataset.filter;
      group.addEventListener("click", (e) => {
        const btn = e.target.closest(".chip");
        if (!btn) return;
        group.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        btn.classList.add("active");
        filters[filterName] = btn.dataset.value;
        syncHash();
        render();
      });
    });

    sortSelect.addEventListener("change", () => {
      filters.sort = sortSelect.value;
      syncHash();
      render();
    });

    searchInput.addEventListener("input", () => {
      filters.search = searchInput.value.trim().toLowerCase();
      syncHash();
      render();
    });

    document.querySelectorAll(".view-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".view-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentView = btn.dataset.view;
        render();
      });
    });

    filterToggle.addEventListener("click", () => {
      const open = filterPanel.classList.toggle("open");
      filterToggle.setAttribute("aria-expanded", open);
    });
  }

  function applyFilters() {
    return allShows.filter((show) => {
      if (filters.genre === "core" && !CORE_GENRES.has(show.genre)) return false;
      if (filters.category !== "all" && show.category !== filters.category) return false;
      if (filters.status === "closing-soon") {
        if (!show.closing_date) return false;
        const close = new Date(show.closing_date);
        const cutoff = new Date();
        cutoff.setDate(cutoff.getDate() + 30);
        if (close > cutoff) return false;
      } else if (filters.status !== "all" && show.status !== filters.status) return false;

      if (filters.price !== "all") {
        const p = show.price?.cheapest;
        if (p == null) return false;
        if (filters.price === "0-50" && p >= 50) return false;
        if (filters.price === "50-100" && (p < 50 || p >= 100)) return false;
        if (filters.price === "100-200" && (p < 100 || p >= 200)) return false;
        if (filters.price === "200+" && p < 200) return false;
      }

      if (filters.search) {
        const q = filters.search;
        const haystack = `${show.title} ${show.venue} ${show.genre || ""} ${(show.tags || []).join(" ")}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }

      return true;
    });
  }

  function sortShows(shows) {
    const sorted = [...shows];
    switch (filters.sort) {
      case "price-asc":
        sorted.sort((a, b) => (a.price?.cheapest ?? 9999) - (b.price?.cheapest ?? 9999));
        break;
      case "price-desc":
        sorted.sort((a, b) => (b.price?.cheapest ?? 0) - (a.price?.cheapest ?? 0));
        break;
      case "title-asc":
        sorted.sort((a, b) => a.title.localeCompare(b.title));
        break;
      case "rating":
        sorted.sort((a, b) => (b.review?.score ?? -1) - (a.review?.score ?? -1));
        break;
      case "closing-soon":
        sorted.sort((a, b) => {
          const aDate = a.closing_date ? new Date(a.closing_date) : new Date("2999-01-01");
          const bDate = b.closing_date ? new Date(b.closing_date) : new Date("2999-01-01");
          return aDate - bDate;
        });
        break;
    }
    return sorted;
  }

  function render() {
    const filtered = sortShows(applyFilters());
    const mappable = filtered.filter((s) => s.lat && s.lng);
    const countLabel = currentView === "map"
      ? `${mappable.length} of ${filtered.length} on map`
      : `${filtered.length} of ${allShows.length} shows`;
    showCount.textContent = countLabel;

    const activeCount = Object.entries(filters).filter(
      ([k, v]) => k !== "sort" && k !== "search" && v !== "all"
    ).length + (filters.search ? 1 : 0);
    filterCountEl.textContent = activeCount > 0 ? `(${activeCount})` : "";

    if (filtered.length === 0) {
      grid.innerHTML = "";
      grid.hidden = true;
      mapContainer.hidden = true;
      emptyState.hidden = false;
      return;
    }
    emptyState.hidden = true;

    if (currentView === "map") {
      grid.hidden = true;
      mapContainer.hidden = false;
      renderMap(filtered);
    } else {
      grid.hidden = false;
      mapContainer.hidden = true;
      grid.innerHTML = filtered.map((show, i) => renderCard(show, i)).join("");
      grid.querySelectorAll(".card").forEach((card) => {
        card.addEventListener("click", () => {
          const idx = parseInt(card.dataset.index, 10);
          openModal(filtered[idx]);
        });
      });
    }
  }

  function renderMap(shows) {
    if (!leafletMap) {
      leafletMap = L.map("map").setView([40.759, -73.985], 14);
      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19,
      }).addTo(leafletMap);
      markerLayer = L.layerGroup().addTo(leafletMap);
    }

    setTimeout(() => leafletMap.invalidateSize(), 100);
    markerLayer.clearLayers();

    const mappable = shows.filter((s) => s.lat && s.lng);
    const venueGroups = {};
    for (const show of mappable) {
      const key = `${show.lat},${show.lng}`;
      if (!venueGroups[key]) venueGroups[key] = [];
      venueGroups[key].push(show);
    }

    for (const [key, group] of Object.entries(venueGroups)) {
      const [lat, lng] = key.split(",").map(Number);
      const color = group[0].category === "broadway" ? "#e6a817" : "#17b8e6";
      const marker = L.circleMarker([lat, lng], {
        radius: Math.min(6 + group.length * 2, 14),
        fillColor: color,
        color: "#fff",
        weight: 1.5,
        fillOpacity: 0.9,
      });

      const popupHtml = group.map((show) => {
        const price = show.price ? `<div class="map-popup-price"><span class="from">from </span>$${show.price.cheapest}</div>` : "";
        let scoreHtml = "";
        if (show.review) {
          const cls = show.review.score >= 90 ? "score-high" : show.review.score >= 80 ? "score-mid" : "score-low";
          scoreHtml = `<span class="map-popup-score ${cls}">${show.review.score}</span>`;
        }
        return `<div class="map-popup">
          <div class="map-popup-title">${escapeHtml(show.title)}${scoreHtml}</div>
          <div class="map-popup-venue">${escapeHtml(show.venue)}</div>
          ${price}
          <span class="map-popup-link" data-show-id="${escapeAttr(show.id)}">View details</span>
        </div>`;
      }).join("<hr style='margin:0.5rem 0;border-color:#ddd'>");

      marker.bindPopup(popupHtml, { maxWidth: 280 });
      marker.on("popupopen", () => {
        document.querySelectorAll(".map-popup-link").forEach((link) => {
          link.addEventListener("click", () => {
            const show = mappable.find((s) => s.id === link.dataset.showId);
            if (show) openModal(show);
          });
        });
      });
      markerLayer.addLayer(marker);
    }

    const nycShows = mappable.filter((s) => s.lat >= 40.69 && s.lat <= 40.85 && s.lng >= -74.05 && s.lng <= -73.90);
    if (nycShows.length > 0) {
      const bounds = L.latLngBounds(nycShows.map((s) => [s.lat, s.lng]));
      leafletMap.fitBounds(bounds.pad(0.15), { maxZoom: 16 });
    }
  }

  function renderCard(show, index) {
    const badges = [];

    const catLabel = show.category === "broadway" ? "Broadway" : "Off-Bway";
    const catClass = show.category === "broadway" ? "badge-broadway" : "badge-off-broadway";
    badges.push(`<span class="badge ${catClass}">${catLabel}</span>`);

    if (show.status === "upcoming") {
      badges.push(`<span class="badge badge-upcoming">Upcoming</span>`);
    }

    if (show.closing_date) {
      const closing = new Date(show.closing_date);
      const weeksLeft = (closing - Date.now()) / (7 * 24 * 3600000);
      if (weeksLeft > 0 && weeksLeft <= 8) {
        const closeLabel = closing.toLocaleDateString("en-US", { month: "short", day: "numeric" });
        badges.push(`<span class="badge badge-closing">Closes ${closeLabel}</span>`);
      }
    }

    if (show.tags && show.tags.includes("rush-available")) {
      badges.push(`<span class="badge badge-rush">Rush</span>`);
    }

    const imageHtml = show.image_url
      ? `<img src="${escapeAttr(show.image_url)}" alt="${escapeAttr(show.title)}" loading="lazy">`
      : `<div class="placeholder-img">&#127917;</div>`;

    const priceHtml = show.price
      ? `<div class="card-price"><span class="from">from </span>$${show.price.cheapest}</div>`
      : `<div class="card-price-na">Price N/A</div>`;

    let ratingHtml = "";
    if (show.review) {
      const r = show.review;
      const scoreClass = r.score >= 90 ? "score-high" : r.score >= 80 ? "score-mid" : "score-low";
      ratingHtml = `<div class="card-rating ${scoreClass}" title="${r.review_count} reviews">${r.score}</div>`;
    }

    return `
      <article class="card" data-index="${index}">
        <div class="card-image">
          ${imageHtml}
          <div class="card-badges">${badges.join("")}</div>
          ${ratingHtml}
        </div>
        <div class="card-body">
          <div class="card-title">${escapeHtml(show.title)}</div>
          <div class="card-venue">${escapeHtml(show.venue)}</div>
        </div>
        <div class="card-footer">
          ${priceHtml}
          <div class="card-genre">${escapeHtml(show.genre || "")}</div>
        </div>
      </article>
    `;
  }

  function openModal(show) {
    closeModal();

    const badges = [];
    const catLabel = show.category === "broadway" ? "Broadway" : "Off-Broadway";
    const catClass = show.category === "broadway" ? "badge-broadway" : "badge-off-broadway";
    badges.push(`<span class="badge ${catClass}">${catLabel}</span>`);
    if (show.genre) badges.push(`<span class="badge badge-genre">${escapeHtml(show.genre)}</span>`);
    if (show.tags?.includes("rush-available")) badges.push(`<span class="badge badge-rush">Rush</span>`);

    if (show.closing_date) {
      const closing = new Date(show.closing_date);
      const weeksLeft = (closing - Date.now()) / (7 * 24 * 3600000);
      if (weeksLeft > 0 && weeksLeft <= 8) {
        const closeLabel = closing.toLocaleDateString("en-US", { month: "short", day: "numeric" });
        badges.push(`<span class="badge badge-closing">Closes ${closeLabel}</span>`);
      }
    }

    const imageHtml = show.image_url
      ? `<img src="${escapeAttr(show.image_url)}" alt="${escapeAttr(show.title)}">`
      : "";

    const priceHtml = show.price
      ? `<div class="modal-price"><span class="from">from </span>$${show.price.cheapest}</div>`
      : "";

    let reviewHtml = "";
    if (show.review) {
      const r = show.review;
      const scoreClass = r.score >= 90 ? "score-high" : r.score >= 80 ? "score-mid" : "score-low";
      const adj = r.adjectives.length ? `<span class="modal-review-adj">${r.adjectives.map(escapeHtml).join(" &middot; ")}</span>` : "";
      const countLabel = r.review_count >= 1000 ? `${(r.review_count / 1000).toFixed(1).replace(/\.0$/, "")}K` : r.review_count;
      reviewHtml = `
        <div class="modal-review">
          <span class="modal-review-score ${scoreClass}">${r.score}</span>
          <span class="modal-review-count">${countLabel} reviews</span>
          ${adj}
        </div>`;
    }

    const descHtml = show.description
      ? `<p class="modal-desc">${escapeHtml(show.description)}</p>`
      : `<p class="modal-desc modal-desc-none">No description available.</p>`;

    const links = [];
    if (show.todaytix_url) {
      links.push(`<a href="${escapeAttr(show.todaytix_url)}" target="_blank" rel="noopener" class="modal-btn modal-btn-primary">Buy Tickets</a>`);
    }
    if (show.playbill_url) {
      links.push(`<a href="${escapeAttr(show.playbill_url)}" target="_blank" rel="noopener" class="modal-btn modal-btn-secondary">View on Playbill</a>`);
    }

    const dates = [];
    if (show.opening_date) dates.push(`Opened ${new Date(show.opening_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`);
    if (show.closing_date) dates.push(`Closes ${new Date(show.closing_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`);

    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal" role="dialog" aria-label="${escapeAttr(show.title)}">
        <button class="modal-close" aria-label="Close">&times;</button>
        ${imageHtml ? `<div class="modal-image">${imageHtml}</div>` : ""}
        <div class="modal-body">
          <div class="modal-badges">${badges.join("")}</div>
          <h2 class="modal-title">${escapeHtml(show.title)}</h2>
          <div class="modal-venue">${escapeHtml(show.venue)}</div>
          ${dates.length ? `<div class="modal-dates">${dates.join(" &middot; ")}</div>` : ""}
          ${priceHtml}
          ${reviewHtml}
          ${descHtml}
          ${links.length ? `<div class="modal-links">${links.join("")}</div>` : ""}
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("open"));

    overlay.querySelector(".modal-close").addEventListener("click", closeModal);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeModal();
    });
    document.addEventListener("keydown", onEsc);
  }

  function closeModal() {
    document.removeEventListener("keydown", onEsc);
    const overlay = document.querySelector(".modal-overlay");
    if (overlay) overlay.remove();
  }

  function onEsc(e) {
    if (e.key === "Escape") closeModal();
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function escapeAttr(str) {
    return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function syncHash() {
    const parts = [];
    for (const [k, v] of Object.entries(filters)) {
      if (v && v !== "all" && !(k === "genre" && v === "core") && !(k === "status" && v === "running") && !(k === "sort" && v === "price-asc") && !(k === "search" && v === "")) {
        parts.push(`${k}=${encodeURIComponent(v)}`);
      }
    }
    history.replaceState(null, "", parts.length ? `#${parts.join("&")}` : location.pathname);
  }

  function restoreFiltersFromHash() {
    const hash = location.hash.slice(1);
    if (!hash) return;
    for (const pair of hash.split("&")) {
      const [key, val] = pair.split("=").map(decodeURIComponent);
      if (key in filters) filters[key] = val;
    }

    document.querySelectorAll(".button-group").forEach((group) => {
      const filterName = group.dataset.filter;
      if (!(filterName in filters)) return;
      group.querySelectorAll(".chip").forEach((chip) => {
        chip.classList.toggle("active", chip.dataset.value === filters[filterName]);
      });
    });

    sortSelect.value = filters.sort;
    searchInput.value = filters.search;
  }

  init();
})();
