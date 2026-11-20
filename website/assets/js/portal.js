/* ==========================================================================
   KAMU PERSONEL REHBERİ — PORTAL INTERACTION & LIVE DATA ENGINE (v8.0)
   ========================================================================== */
(function () {
  "use strict";

  var ALL_JOBS = [];
  var FILTERED_JOBS = [];
  var SHOWN_COUNT = 24;
  var ACTIVE_CAT = "all";
  var ACTIVE_EDU = "all";
  var SEARCH_QUERY = "";

  var TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];

  function esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function norm(str) {
    return String(str || "")
      .toLocaleLowerCase("tr-TR")
      .replace(/ğ/g, "g").replace(/ü/g, "u").replace(/ş/g, "s")
      .replace(/ı/g, "i").replace(/ö/g, "o").replace(/ç/g, "c");
  }

  function setTodayDate() {
    var el = document.getElementById("header-today-date");
    if (!el) return;
    var d = new Date();
    el.textContent = d.getDate() + " " + TR_MONTHS[d.getMonth()] + " " + d.getFullYear();
  }

  function matchCategory(job, cat) {
    if (cat === "all") return true;
    var text = norm((job.title || "") + " " + (job.institution || "") + " " + (job.position || "") + " " + (job.category || "") + " " + (job.kpss_requirement || ""));
    if (cat === "kpss_sartsiz") return text.indexOf("sartsiz") !== -1 || text.indexOf("kpss'siz") !== -1 || text.indexOf("aranmaz") !== -1 || text.indexOf("iskur") !== -1;
    if (cat === "belediye") return text.indexOf("belediye") !== -1 || text.indexOf("zabita") !== -1 || text.indexOf("itfaiye") !== -1;
    if (cat === "universite") return text.indexOf("universite") !== -1 || text.indexOf("rektor") !== -1;
    if (cat === "bilisim") return text.indexOf("bilisim") !== -1 || text.indexOf("yazilim") !== -1 || text.indexOf("programci") !== -1 || text.indexOf("cozumleyici") !== -1;
    if (cat === "akademik") return text.indexOf("ogretim") !== -1 || text.indexOf("akademik") !== -1 || text.indexOf("arastirma gorevlisi") !== -1 || text.indexOf("ogretmen") !== -1;
    if (cat === "saglik") return text.indexOf("saglik") !== -1 || text.indexOf("hemsire") !== -1 || text.indexOf("hastane") !== -1 || text.indexOf("doktor") !== -1 || text.indexOf("tip") !== -1;
    if (cat === "guvenlik") return text.indexOf("guvenlik") !== -1 || text.indexOf("zabita") !== -1 || text.indexOf("polis") !== -1 || text.indexOf("infaz") !== -1 || text.indexOf("bekci") !== -1;
    if (cat === "sozlesmeli") return text.indexOf("sozlesmeli") !== -1 || text.indexOf("4/b") !== -1;
    if (cat === "memur") return text.indexOf("memur") !== -1 || text.indexOf("uzman yardimci") !== -1 || text.indexOf("mufettis") !== -1;
    return true;
  }

  function matchEdu(job, edu) {
    if (edu === "all") return true;
    var text = norm((job.education_level || "") + " " + (job.title || "") + " " + (job.position || ""));
    if (edu === "ilkokul") return text.indexOf("ilkokul") !== -1 || text.indexOf("ortaokul") !== -1 || text.indexOf("ilkogretim") !== -1 || text.indexOf("isci") !== -1 || text.indexOf("destek") !== -1;
    if (edu === "lise") return text.indexOf("lise") !== -1 || text.indexOf("ortaogretim") !== -1 || text.indexOf("teknisyen") !== -1 || text.indexOf("sofor") !== -1;
    if (edu === "onlisans") return text.indexOf("onlisans") !== -1 || text.indexOf("on lisans") !== -1 || text.indexOf("tekniker") !== -1;
    if (edu === "lisans") return text.indexOf("lisans") !== -1 || text.indexOf("muhendis") !== -1 || text.indexOf("uzman") !== -1 || text.indexOf("ogretim") !== -1 || text.indexOf("memur") !== -1;
    return true;
  }

  function pickCategoryPhoto(job) {
    if (matchCategory(job, "bilisim")) return "/assets/img/categories/bilisim.webp";
    if (matchCategory(job, "belediye")) return "/assets/img/categories/belediye.webp";
    if (matchCategory(job, "saglik")) return "/assets/img/categories/saglik.webp";
    if (matchCategory(job, "universite")) return "/assets/img/categories/universite.webp";
    if (matchCategory(job, "guvenlik")) return "/assets/img/categories/guvenlik.webp";
    if (matchCategory(job, "akademik")) return "/assets/img/categories/ogretmen.webp";
    if (matchCategory(job, "sozlesmeli")) return "/assets/img/categories/sozlesmeli.webp";
    return "/assets/img/categories/kamu-personel.webp";
  }

  function renderVisualCard(job) {
    var photo = pickCategoryPhoto(job);
    var deadline = job.end_date_str || job.date_interval || "Aktif İlan";
    var quota = job.quota_display || ((job.total_positions || 1) + " Kadro");
    var kpss = job.kpss_requirement || "Kılavuzda";
    var city = job.city || "Türkiye Geneli";
    var isKpssFree = norm(kpss).indexOf("sartsiz") !== -1;

    return (
      '<article class="job-visual-card" onclick="openJobModal(' + Number(job.id) + ')" style="cursor:pointer;">' +
        '<div class="job-visual-media">' +
          '<img src="' + photo + '" alt="' + esc(job.institution) + '" loading="lazy" width="480" height="270">' +
          '<div class="job-badge-row">' +
            '<span class="badge-deadline">Son: ' + esc(String(deadline).slice(0, 18)) + '</span>' +
            '<span class="badge-days-left' + (isKpssFree ? ' urgent' : '') + '">' + (isKpssFree ? "KPSS'siz" : esc(quota)) + '</span>' +
          '</div>' +
          '<div class="job-media-inst">' + esc(job.institution) + '</div>' +
        '</div>' +
        '<div class="job-visual-body">' +
          '<h3 class="job-visual-title">' + esc(job.title) + '</h3>' +
          '<div class="job-visual-meta">' +
            '<span class="meta-chip quota">' + esc(quota) + '</span>' +
            '<span class="meta-chip">' + esc(city) + '</span>' +
            '<span class="meta-chip">' + esc(kpss) + '</span>' +
          '</div>' +
        '</div>' +
      '</article>'
    );
  }

  function renderTicker(jobs) {
    var track = document.getElementById("ticker-track");
    if (!track || !jobs.length) return;
    var items = jobs.slice(0, 10).map(function (j) {
      return '<a href="#tum-ilanlar" class="ticker-item" onclick="openJobModal(' + Number(j.id) + ');return false;">• ' + esc(j.institution) + ' — ' + esc(j.position || j.title) + ' (' + esc(j.quota_display || "Aktif") + ')</a>';
    }).join("");
    track.innerHTML = items + items;
  }

  function updateCounters(jobs) {
    var set = function (id, val, suffix) {
      var el = document.getElementById(id);
      if (el) el.textContent = val.toLocaleString("tr-TR") + (suffix || "");
    };
    var cAll = jobs.length;
    var cKpssSiz = jobs.filter(function (j) { return matchCategory(j, "kpss_sartsiz"); }).length;
    var cSoz = jobs.filter(function (j) { return matchCategory(j, "sozlesmeli"); }).length;
    var cBel = jobs.filter(function (j) { return matchCategory(j, "belediye"); }).length;
    var cAka = jobs.filter(function (j) { return matchCategory(j, "akademik"); }).length;
    var cGuv = jobs.filter(function (j) { return matchCategory(j, "guvenlik"); }).length;
    var cBil = jobs.filter(function (j) { return matchCategory(j, "bilisim"); }).length;
    var cUni = jobs.filter(function (j) { return matchCategory(j, "universite"); }).length;
    var cSag = jobs.filter(function (j) { return matchCategory(j, "saglik"); }).length;
    var cMem = jobs.filter(function (j) { return matchCategory(j, "memur"); }).length;

    set("cnt-all-jobs", cAll, " ilan");
    set("cnt-kpss-siz", cKpssSiz, " ilan");
    set("cnt-sozlesmeli", cSoz, " ilan");
    set("cnt-belediye", cBel, " ilan");
    set("cnt-akademik", cAka, " ilan");
    set("cnt-guvenlik", cGuv, " ilan");
    set("cnt-bilisim", cBil, " ilan");
    set("cnt-universite", cUni, " ilan");
    set("cnt-saglik", cSag, " ilan");

    set("pop-belediye", cBel, "");
    set("pop-sozlesmeli", cSoz, "");
    set("pop-bilisim", cBil, "");
    set("pop-universite", cUni, "");
    set("pop-kpss-siz", cKpssSiz, "");
    set("pop-memur", cMem, "");
    set("pop-akademik", cAka, "");

    set("edu-cnt-ilkokul", jobs.filter(function (j) { return matchEdu(j, "ilkokul"); }).length, " ilan");
    set("edu-cnt-lise", jobs.filter(function (j) { return matchEdu(j, "lise"); }).length, " ilan");
    set("edu-cnt-onlisans", jobs.filter(function (j) { return matchEdu(j, "onlisans"); }).length, " ilan");
    set("edu-cnt-lisans", jobs.filter(function (j) { return matchEdu(j, "lisans"); }).length, " ilan");
  }

  function renderCategoryShowcases(jobs) {
    var fill = function (elId, cat) {
      var el = document.getElementById(elId);
      if (!el) return;
      var matched = jobs.filter(function (j) { return matchCategory(j, cat); }).slice(0, 3);
      if (matched.length < 3) matched = jobs.slice(0, 3);
      el.innerHTML = matched.map(renderVisualCard).join("");
    };
    fill("grid-bilisim", "bilisim");
    fill("grid-belediye", "belediye");
    fill("grid-sozlesmeli", "sozlesmeli");
  }

  function applyFilters(resetCount) {
    if (resetCount) SHOWN_COUNT = 24;
    var q = norm(SEARCH_QUERY);
    FILTERED_JOBS = ALL_JOBS.filter(function (job) {
      if (!matchCategory(job, ACTIVE_CAT)) return false;
      if (!matchEdu(job, ACTIVE_EDU)) return false;
      if (q) {
        var hay = norm((job.institution || "") + " " + (job.title || "") + " " + (job.position || "") + " " + (job.city || "") + " " + (job.kpss_requirement || ""));
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
    renderJobsList();
  }

  function renderJobsList() {
    var container = document.getElementById("main-jobs-list");
    var lbl = document.getElementById("filtered-count-label");
    var moreBtn = document.getElementById("load-more-btn");
    if (!container) return;

    if (lbl) lbl.textContent = FILTERED_JOBS.length.toLocaleString("tr-TR") + " aktif ilan listeleniyor";

    if (!FILTERED_JOBS.length) {
      container.innerHTML = '<div style="padding:32px;text-align:center;color:var(--text-muted);">Aradığınız kriterlere uygun aktif ilan bulunamadı. Filtreleri temizleyip tekrar deneyin.</div>';
      if (moreBtn) moreBtn.style.display = "none";
      return;
    }

    var slice = FILTERED_JOBS.slice(0, SHOWN_COUNT);
    container.innerHTML = slice.map(function (job) {
      var quota = job.quota_display || ((job.total_positions || 1) + " Kadro");
      var dates = job.date_interval || job.end_date_str || "Resmi Kılavuzda";
      var city = job.city || "Türkiye Geneli";
      var kpss = job.kpss_requirement || "Kılavuzda";
      return (
        '<div class="job-row-item" onclick="openJobModal(' + Number(job.id) + ')">' +
          '<div class="job-row-main">' +
            '<div class="job-row-inst">' + esc(job.institution) + '</div>' +
            '<div class="job-row-title">' + esc(job.title) + '</div>' +
            '<div class="job-row-tags">' +
              '<span>' + esc(city) + '</span><span>•</span>' +
              '<span>' + esc(kpss) + '</span><span>•</span>' +
              '<span>' + esc(job.source_name || "Resmi Kaynak") + '</span>' +
            '</div>' +
          '</div>' +
          '<div class="job-row-right">' +
            '<span class="job-row-quota">' + esc(quota) + '</span>' +
            '<span class="job-row-date">' + esc(dates) + '</span>' +
          '</div>' +
        '</div>'
      );
    }).join("");

    if (moreBtn) {
      moreBtn.style.display = FILTERED_JOBS.length > SHOWN_COUNT ? "inline-flex" : "none";
    }
  }

  function renderEditorialNews(articles) {
    var grid = document.getElementById("grid-news");
    var side = document.getElementById("sidebar-news-list");
    var cnt = document.getElementById("cnt-haberler");
    if (cnt) cnt.textContent = articles.length + " haber";

    if (grid && articles.length) {
      grid.innerHTML = articles.slice(0, 3).map(function (a) {
        return (
          '<a href="/haber/' + esc(a.slug) + '/" class="job-visual-card">' +
            '<div class="job-visual-media">' +
              '<img src="' + esc(a.cover_image || "/assets/img/og-banner.png") + '" alt="' + esc(a.cover_alt || a.headline) + '" loading="lazy" width="600" height="338">' +
              '<div class="job-badge-row"><span class="badge-deadline">' + esc(a.publish_date_formatted || "Güncel") + '</span></div>' +
              '<div class="job-media-inst">' + esc(a.institution) + '</div>' +
            '</div>' +
            '<div class="job-visual-body">' +
              '<h3 class="job-visual-title">' + esc(a.headline) + '</h3>' +
              '<div class="job-visual-meta">' +
                '<span class="meta-chip">' + esc(a.category_label || "Resmi Duyuru") + '</span>' +
                '<span class="meta-chip quota">Haberi Oku →</span>' +
              '</div>' +
            '</div>' +
          '</a>'
        );
      }).join("");
    }

    if (side && articles.length) {
      side.innerHTML = articles.slice(0, 5).map(function (a) {
        return '<li class="popular-item"><a href="/haber/' + esc(a.slug) + '/" style="font-size:0.84rem;line-height:1.4;font-weight:600;">' + esc(a.headline) + '</a></li>';
      }).join("");
    }
  }

  window.openJobModal = function (jobId) {
    var job = ALL_JOBS.find(function (j) { return Number(j.id) === Number(jobId); });
    if (!job) return;
    var modal = document.getElementById("job-modal");
    document.getElementById("modal-job-inst").textContent = job.institution || "T.C. Kamu Kurumu";
    document.getElementById("modal-job-title").textContent = job.title || "";
    document.getElementById("modal-job-body").innerHTML =
      '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:16px;">' +
        '<div style="background:var(--bg-subtle);padding:12px;border-radius:8px;"><div style="font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;">Kontenjan</div><div style="font-weight:700;">' + esc(job.quota_display || "Kılavuzda") + '</div></div>' +
        '<div style="background:var(--bg-subtle);padding:12px;border-radius:8px;"><div style="font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;">Başvuru Tarihleri</div><div style="font-weight:700;">' + esc(job.date_interval || job.end_date_str || "Kılavuzda") + '</div></div>' +
        '<div style="background:var(--bg-subtle);padding:12px;border-radius:8px;"><div style="font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;">KPSS Şartı</div><div style="font-weight:700;">' + esc(job.kpss_requirement || "Kılavuzda") + '</div></div>' +
        '<div style="background:var(--bg-subtle);padding:12px;border-radius:8px;"><div style="font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;">Şehir / Öğrenim</div><div style="font-weight:700;">' + esc(job.city || "Türkiye Geneli") + ' • ' + esc(job.education_level || "Kılavuzda") + '</div></div>' +
      '</div>' +
      '<p style="font-size:0.9rem;color:var(--text-secondary);line-height:1.65;">Bu ilan <strong>' + esc(job.source_name || "Resmi Kaynak") + '</strong> üzerinden teyit edilmiştir. Özel başvuru şartları, nitelik kodları ve istenen belgeler için aşağıdaki resmi kılavuz bağlantısını açınız.</p>';

    var btns = "";
    if (job.pdf_url) {
      var href = job.pdf_url.indexOf("http") === 0 ? job.pdf_url : "/" + job.pdf_url.replace(/^\/+/, "");
      btns += '<a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer" class="btn-portal-primary">Resmi PDF Kılavuzunu Aç ↗</a>';
    }
    if (job.source_url) {
      btns += '<a href="' + esc(job.source_url) + '" target="_blank" rel="noopener noreferrer nofollow" class="btn-portal-primary" style="background:var(--brand-blue);">Resmi İlan Kaynağı ↗</a>';
    }
    btns += '<button onclick="closeJobModal()" style="padding:10px 16px;border:1px solid var(--border-color);border-radius:8px;font-weight:600;">Kapat</button>';
    document.getElementById("modal-job-foot").innerHTML = btns;
    modal.classList.add("open");
  };

  window.closeJobModal = function () {
    var modal = document.getElementById("job-modal");
    if (modal) modal.classList.remove("open");
  };

  window.portalFilter = function (cat) {
    ACTIVE_CAT = cat;
    ACTIVE_EDU = "all";
    var sel = document.getElementById("main-cat-select");
    if (sel) sel.value = cat;
    var eduSel = document.getElementById("main-edu-select");
    if (eduSel) eduSel.value = "all";
    applyFilters(true);
    var target = document.getElementById("tum-ilanlar");
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  window.portalFilterEdu = function (edu) {
    ACTIVE_EDU = edu;
    ACTIVE_CAT = "all";
    var eduSel = document.getElementById("main-edu-select");
    if (eduSel) eduSel.value = edu;
    var catSel = document.getElementById("main-cat-select");
    if (catSel) catSel.value = "all";
    applyFilters(true);
    var target = document.getElementById("tum-ilanlar");
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  function initEvents() {
    var themeBtn = document.getElementById("theme-toggle-btn");
    if (themeBtn) {
      themeBtn.addEventListener("click", function () {
        var isDark = document.documentElement.classList.toggle("dark");
        try { localStorage.setItem("kpr_theme", isDark ? "dark" : "light"); } catch (e) {}
      });
    }

    var searchIn = document.getElementById("main-search-input");
    if (searchIn) {
      searchIn.addEventListener("input", function (e) {
        SEARCH_QUERY = e.target.value;
        applyFilters(true);
      });
    }

    var headerForm = document.getElementById("header-search-form");
    var headerInput = document.getElementById("header-search-input");
    if (headerForm && headerInput) {
      headerForm.addEventListener("submit", function (e) {
        e.preventDefault();
        SEARCH_QUERY = headerInput.value;
        if (searchIn) searchIn.value = SEARCH_QUERY;
        applyFilters(true);
        var t = document.getElementById("tum-ilanlar");
        if (t) t.scrollIntoView({ behavior: "smooth" });
      });
    }

    var catSel = document.getElementById("main-cat-select");
    if (catSel) {
      catSel.addEventListener("change", function (e) {
        ACTIVE_CAT = e.target.value;
        applyFilters(true);
      });
    }

    var eduSel = document.getElementById("main-edu-select");
    if (eduSel) {
      eduSel.addEventListener("change", function (e) {
        ACTIVE_EDU = e.target.value;
        applyFilters(true);
      });
    }

    var moreBtn = document.getElementById("load-more-btn");
    if (moreBtn) {
      moreBtn.addEventListener("click", function () {
        SHOWN_COUNT += 30;
        renderJobsList();
      });
    }

    var modal = document.getElementById("job-modal");
    if (modal) {
      modal.addEventListener("click", function (e) {
        if (e.target === modal) closeJobModal();
      });
    }
  }

  function boot() {
    setTodayDate();
    initEvents();

    fetch("/data/jobs.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        ALL_JOBS = (data.jobs || []).filter(function (j) { return !j.is_cancellation; });
        ALL_JOBS.sort(function (a, b) { return (b.sort_key || 0) - (a.sort_key || 0); });
        renderTicker(ALL_JOBS);
        updateCounters(ALL_JOBS);
        renderCategoryShowcases(ALL_JOBS);
        applyFilters(true);
      })
      .catch(function () {
        var c = document.getElementById("main-jobs-list");
        if (c) c.innerHTML = '<div style="padding:24px;text-align:center;">İlan verisi yüklenirken geçici bir hata oluştu. Lütfen sayfayı yenileyin.</div>';
      });

    fetch("/data/editorial_news.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderEditorialNews(data.articles || []);
      })
      .catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
