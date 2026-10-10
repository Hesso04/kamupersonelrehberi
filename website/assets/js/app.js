/**
 * KAMU PERSONEL REHBERİ - WEB İSTEMCİ MOTORU (v5.0)
 * SBB Kamu İlan Referanslı, Cam Efektli (Glassmorphic) & Yüksek Hızlı Sayfalamalı Mimari
 */

const CONFIG = {
  PAGE_SIZE: 15, // Her sayfada tam 15 ilan gösterilir (Sayfanın aşırı uzun olmasını kalıcı çözer)
  HERO_AUTO_SLIDE_MS: 6000,
  DATA_URL: 'data/jobs.json',
};

// Uygulama Durumu (State)
const state = {
  allJobs: [],
  filteredJobs: [],
  meta: {},
  featuredJobs: [],
  activeCategory: 'all',
  searchQuery: '',
  filterOnlyOpen: false,
  filterOnlyCanc: false,
  filterOnlyPdf: false,
  sortBy: 'date_desc',
  currentPage: 1,
  currentHeroIndex: 0,
  heroTimer: null,
};

document.addEventListener('DOMContentLoaded', () => {
  initApp();
  initCookieConsent();
});

async function initApp() {
  try {
    const res = await fetch(CONFIG.DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    state.allJobs = data.jobs || [];
    state.meta = data.meta || {};
    state.featuredJobs = data.meta?.featured_jobs || state.allJobs.slice(0, 10);

    // İstatistikler
    updatePortalStats();

    // SBB Tarzı Numaralı Manşet Vitrini (1 2 3 ... 10)
    initHeroShowcase();

    // Sol Kategori Menüsü
    renderCategoryMenu();

    // Filtrele & Sayfala
    applyFiltersAndPaginate(1);

    // Etkileşim Dinleyicileri
    bindSearchAndFilters();

    // URL'deki ?ilan=123 parametresiyle ilanı doğrudan aç (Telegram paylaşımları için)
    checkAndOpenDeepLinkedJob();
  } catch (err) {
    console.error('İlan verisi yüklenirken hata:', err);
    const feed = document.getElementById('jobs-feed');
    if (feed) {
      feed.innerHTML = `
        <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;padding:24px;text-align:center;color:#991B1B;">
          <strong>İlan verileri yüklenemedi.</strong> Lütfen internet bağlantınızı kontrol edip sayfayı yenileyiniz.
        </div>
      `;
    }
  }
}

function updatePortalStats() {
  const visitorsEl = document.getElementById('stat-active-visitors');
  if (visitorsEl && state.meta.active_visitors) {
    visitorsEl.textContent = state.meta.active_visitors.toLocaleString('tr-TR');
  }

  const totalJobsEl = document.getElementById('stat-total-jobs');
  if (totalJobsEl) {
    totalJobsEl.textContent = state.allJobs.length.toLocaleString('tr-TR');
  }
}

// =============================================================================
// HERO SHOWCASE (SBB STİLİ NUMARALI MANŞET VİTRİNİ)
// =============================================================================
function initHeroShowcase() {
  const showcaseContainer = document.getElementById('hero-showcase-content');
  const numbersNav = document.getElementById('hero-numbers-nav');
  if (!showcaseContainer || !state.featuredJobs.length) return;

  // 1. Numaralı Düğmeleri Oluştur (1 2 3 4 5 ...)
  if (numbersNav) {
    numbersNav.innerHTML = '';
    state.featuredJobs.forEach((job, idx) => {
      const btn = document.createElement('button');
      btn.className = `hero-num-btn ${idx === 0 ? 'active' : ''}`;
      btn.textContent = idx + 1;
      btn.title = job.institution;
      btn.addEventListener('click', () => {
        stopHeroTimer();
        state.currentHeroIndex = idx;
        renderHeroSlide();
        startHeroTimer();
      });
      numbersNav.appendChild(btn);
    });
  }

  // 2. İlk Slaytı Çiz
  renderHeroSlide();
  startHeroTimer();
}

function renderHeroSlide() {
  const container = document.getElementById('hero-showcase-content');
  if (!container || !state.featuredJobs.length) return;

  const job = state.featuredJobs[state.currentHeroIndex];
  const isCanc = job.is_cancellation;
  const badgeText = isCanc ? '🚨 İLAN İPTAL DUYURUSU' : (job.total_positions >= 50 ? '🔥 YÜKSEK KONTENJAN' : '🏛 RESMİ KAMU ALIMI');

  // PDF indirme bağlantısı: Doğrudan documents/sbb_{id}.pdf'e gider
  const pdfActionMarkup = job.has_pdf && job.pdf_url
    ? `<a href="${job.pdf_url}" target="_blank" rel="noopener noreferrer" class="hero-btn-pdf" download>📄 Kılavuzu İndir (PDF)</a>`
    : `<a href="${job.source_url || 'https://kamuilan.sbb.gov.tr/'}" target="_blank" rel="noopener noreferrer" class="hero-btn-pdf">🏛 Resmi Portal</a>`;

  container.innerHTML = `
    <div class="hero-glass-showcase">
      <div class="hero-showcase-left">
        <div class="hero-pill-row">
          <span class="hero-tag-badge">${badgeText}</span>
          <span class="hero-quota-pill">👥 ${job.total_positions} Personel Alımı</span>
          <span class="hero-date-highlight">🗓 Başvuru: ${escapeHtml(job.date_interval || job.end_date_str)}</span>
        </div>
        <div class="hero-inst-name">${escapeHtml(job.institution)}</div>
        <h2 class="hero-card-headline">${escapeHtml(job.title)}</h2>
        <div class="hero-meta-chips">
          <span>🎓 ${escapeHtml(job.education_level)}</span>
          <span>🎯 ${escapeHtml(job.kpss_requirement)}</span>
          <span>📍 ${escapeHtml(job.city)}</span>
        </div>
      </div>
      <div class="hero-showcase-right">
        <button class="hero-btn-primary" onclick="openJobDetailModal(${job.id})">
          Şartları İncele →
        </button>
        ${pdfActionMarkup}
      </div>
    </div>
  `;

  // Aktif numara butonunu güncelle
  const numBtns = document.querySelectorAll('.hero-num-btn');
  numBtns.forEach((btn, idx) => {
    btn.classList.toggle('active', idx === state.currentHeroIndex);
  });
}

function startHeroTimer() {
  stopHeroTimer();
  state.heroTimer = setInterval(() => {
    state.currentHeroIndex = (state.currentHeroIndex + 1) % state.featuredJobs.length;
    renderHeroSlide();
  }, CONFIG.HERO_AUTO_SLIDE_MS);
}

function stopHeroTimer() {
  if (state.heroTimer) clearInterval(state.heroTimer);
}

// =============================================================================
// SOL SÜTUN KATEGORİ MENÜSÜ
// =============================================================================
function renderCategoryMenu() {
  const menu = document.getElementById('category-menu-list');
  if (!menu) return;

  const categories = state.meta.categories || [];
  const total = state.allJobs.length;

  let html = `
    <li>
      <button class="category-pill-btn ${state.activeCategory === 'all' ? 'active' : ''}" onclick="filterByCategory('all')">
        <span>🌐 Tüm İlanlar</span>
        <span class="category-pill-counter">${total}</span>
      </button>
    </li>
  `;

  categories.forEach(cat => {
    const slug = getCategorySlug(cat.name);
    const icon = getCategoryIcon(cat.name);
    const isActive = state.activeCategory === slug;

    html += `
      <li>
        <button class="category-pill-btn ${isActive ? 'active' : ''}" onclick="filterByCategory('${slug}')">
          <span>${icon} ${escapeHtml(cat.name)}</span>
          <span class="category-pill-counter">${cat.count}</span>
        </button>
      </li>
    `;
  });

  menu.innerHTML = html;
}

function filterByCategory(slug) {
  state.activeCategory = slug;
  renderCategoryMenu();
  applyFiltersAndPaginate(1);
}

function getCategorySlug(catName) {
  const map = {
    'Memur & Genel İdari Kadrolar': 'memur',
    'Sözleşmeli Personel': 'sozlesmeli',
    'Akademik Kadrolar': 'akademik',
    'Bilişim & Teknik Kadrolar': 'bilisim',
    'Sağlık Personeli': 'saglik',
    'Askeri & Emniyet Personeli': 'askeri',
    'Sürekli İşçi Alımları': 'isci',
    'Belediye Başkanlıkları': 'belediye',
  };
  return map[catName] || 'diger';
}

function getCategoryIcon(catName) {
  const map = {
    'Memur & Genel İdari Kadrolar': '👔',
    'Sözleşmeli Personel': '📑',
    'Akademik Kadrolar': '🎓',
    'Bilişim & Teknik Kadrolar': '💻',
    'Sağlık Personeli': '🏥',
    'Askeri & Emniyet Personeli': '🛡',
    'Sürekli İşçi Alımları': '⚙',
    'Belediye Başkanlıkları': '🏛',
  };
  return map[catName] || '📋';
}

// =============================================================================
// FİLTRELEME & AKILLI SAYFALAMA MOTORU (SAYFANIN UZUN OLMASINI ENGELLEYEN ÇEKİRDEK)
// =============================================================================
function applyFiltersAndPaginate(page = 1) {
  state.currentPage = page;

  // 1. Filtrele
  state.filteredJobs = state.allJobs.filter(job => {
    // Kategori
    if (state.activeCategory !== 'all' && job.category_slug !== state.activeCategory) {
      return false;
    }

    // Arama
    if (state.searchQuery) {
      const q = state.searchQuery.toLocaleLowerCase('tr-TR');
      const text = `${job.institution} ${job.title} ${job.position} ${job.city}`.toLocaleLowerCase('tr-TR');
      if (!text.includes(q)) return false;
    }

    // Durum Filtreleri
    if (state.filterOnlyOpen && job.status !== 'BAŞVURUYA AÇIK') return false;
    if (state.filterOnlyCanc && !job.is_cancellation) return false;
    if (state.filterOnlyPdf && !job.has_pdf) return false;

    return true;
  });

  // 2. Sırala
  if (state.sortBy === 'quota_desc') {
    state.filteredJobs.sort((a, b) => (b.total_positions || 0) - (a.total_positions || 0));
  } else if (state.sortBy === 'quota_asc') {
    state.filteredJobs.sort((a, b) => (a.total_positions || 0) - (b.total_positions || 0));
  } else {
    state.filteredJobs.sort((a, b) => (b.sort_key || 0) - (a.sort_key || 0));
  }

  // 3. İstatistik Rozetini Güncelle
  const countBadge = document.getElementById('strip-count-badge');
  if (countBadge) {
    countBadge.textContent = `TÜM İLANLAR (${state.filteredJobs.length} İlan)`;
  }

  // 4. Sayfalamayı Hesapla
  const totalPages = Math.ceil(state.filteredJobs.length / CONFIG.PAGE_SIZE) || 1;
  if (state.currentPage > totalPages) state.currentPage = totalPages;

  const startIndex = (state.currentPage - 1) * CONFIG.PAGE_SIZE;
  const pageJobs = state.filteredJobs.slice(startIndex, startIndex + CONFIG.PAGE_SIZE);

  // 5. İlan Akışını ve Sayfalama Çubuğunu Çiz
  renderJobsFeed(pageJobs);
  renderPaginationBar(totalPages);
}

// =============================================================================
// KRONOLOJİK İLAN AKIŞI ÇİZİMİ (SBB KAMU İLAN GİBİ TARİHE GÖRE GRUPLANMIŞ)
// =============================================================================
function renderJobsFeed(jobsToRender) {
  const feed = document.getElementById('jobs-feed');
  if (!feed) return;

  if (jobsToRender.length === 0) {
    feed.innerHTML = `
      <div style="background:rgba(255,255,255,0.85);backdrop-filter:blur(10px);border:1px solid #E2E8F0;border-radius:10px;padding:48px 24px;text-align:center;">
        <div style="font-size:2.4rem;margin-bottom:10px;">🔍</div>
        <h3 style="font-size:1.1rem;font-weight:700;color:#0F172A;margin-bottom:6px;">Aradığınız Kriterlere Uygun İlan Bulunamadı</h3>
        <p style="font-size:0.875rem;color:#64748B;">Lütfen arama teriminizi değiştiriniz veya filtreleri sıfırlayınız.</p>
        <button onclick="resetFilters()" style="margin-top:14px;background:#2563EB;color:#FFF;padding:8px 18px;border-radius:6px;font-size:0.8125rem;font-weight:700;">Filtreleri Temizle</button>
      </div>
    `;
    return;
  }

  // Sayfadaki ilanları tarihe göre grupla (Örn: "9 Ekim", "8 Ekim", "28 Eylül")
  const groupsMap = new Map();
  jobsToRender.forEach(job => {
    const gName = job.pub_date_group || 'Güncel İlanlar';
    if (!groupsMap.has(gName)) {
      groupsMap.set(gName, []);
    }
    groupsMap.get(gName).push(job);
  });

  let html = '';

  groupsMap.forEach((groupJobs, groupName) => {
    html += `
      <section class="date-group-card">
        <div class="date-group-badge-row">
          <span class="date-group-badge-title">
            <span>📅</span>
            <span>${escapeHtml(groupName)}</span>
          </span>
          <span class="date-group-count-text">(${groupJobs.length} İlan)</span>
        </div>

        <div class="jobs-group-list">
          ${groupJobs.map(job => renderJobRowItem(job)).join('')}
        </div>
      </section>
    `;
  });

  feed.innerHTML = html;
}

function renderJobRowItem(job) {
  const isCanc = job.is_cancellation;
  const emblemLetter = (job.institution || 'K')[0].toUpperCase();

  // PDF aksiyon butonu: Eğer yerel dosya varsa doğrudan indirir, 404 vermez!
  let pdfBtn = '';
  if (job.has_pdf && job.pdf_url) {
    pdfBtn = `
      <a href="${job.pdf_url}" target="_blank" rel="noopener noreferrer" class="btn-row-action pdf" download onclick="event.stopPropagation()">
        📄 PDF İndir
      </a>
    `;
  }

  let tagMarkup = '';
  if (isCanc) {
    tagMarkup = `<span class="job-item-tag canc">🚨 İPTAL / DÜZELTME</span>`;
  } else if (job.category_slug === 'akademik') {
    tagMarkup = `<span class="job-item-tag badge">🎓 Akademik</span>`;
  } else if (job.category_slug === 'belediye') {
    tagMarkup = `<span class="job-item-tag badge">🏛 Belediye</span>`;
  }

  return `
    <article class="sbb-job-item ${isCanc ? 'cancellation' : ''}" onclick="openJobDetailModal(${job.id})">
      <div class="inst-emblem-badge">${emblemLetter}</div>

      <div class="job-item-text-wrap">
        <div class="job-item-inst-line">
          <strong class="job-item-inst-name">${escapeHtml(job.institution)}</strong>
          ${tagMarkup}
        </div>
        <div class="job-item-desc">${escapeHtml(job.title)}</div>
      </div>

      <div style="display:flex;align-items:center;gap:8px;">
        <span class="job-item-quota-pill">👥 ${job.total_positions} Kişi</span>
        <span class="job-item-date-pill">🗓 ( ${escapeHtml(job.date_interval || job.end_date_str)} )</span>
      </div>

      <div class="job-item-actions" onclick="event.stopPropagation()">
        ${pdfBtn}
        <button class="btn-row-action" onclick="openJobDetailModal(${job.id})">
          🔍 İncele
        </button>
      </div>
    </article>
  `;
}

// =============================================================================
// SAYFALAMA ÇUBUĞU (SBB GİBİ 1/12 SAYFA GEÇİŞİ)
// =============================================================================
function renderPaginationBar(totalPages) {
  const paginationContainer = document.getElementById('pagination-container');
  if (!paginationContainer) return;

  if (totalPages <= 1) {
    paginationContainer.innerHTML = '';
    return;
  }

  const current = state.currentPage;
  let buttonsHtml = '';

  // Önceki Butonu
  buttonsHtml += `
    <button class="pg-btn" ${current === 1 ? 'disabled' : ''} onclick="goToPage(${current - 1})">
      ◀ Önceki
    </button>
  `;

  // Sayfa Numaraları
  const maxButtons = 7;
  let startPage = Math.max(1, current - 3);
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);

  if (endPage - startPage < maxButtons - 1) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  if (startPage > 1) {
    buttonsHtml += `<button class="pg-btn" onclick="goToPage(1)">1</button>`;
    if (startPage > 2) buttonsHtml += `<span style="color:#94A3B8;padding:0 4px;">...</span>`;
  }

  for (let p = startPage; p <= endPage; p++) {
    buttonsHtml += `
      <button class="pg-btn ${p === current ? 'active' : ''}" onclick="goToPage(${p})">
        ${p}
      </button>
    `;
  }

  if (endPage < totalPages) {
    if (endPage < totalPages - 1) buttonsHtml += `<span style="color:#94A3B8;padding:0 4px;">...</span>`;
    buttonsHtml += `<button class="pg-btn" onclick="goToPage(${totalPages})">${totalPages}</button>`;
  }

  // Sonraki Butonu
  buttonsHtml += `
    <button class="pg-btn" ${current === totalPages ? 'disabled' : ''} onclick="goToPage(${current + 1})">
      Sonraki ▶
    </button>
  `;

  paginationContainer.innerHTML = `
    <div class="pagination-glass-bar">
      <div class="pagination-info-text">
        Sayfa <strong>${current}</strong> / <strong>${totalPages}</strong> &nbsp;•&nbsp; Toplam <strong>${state.filteredJobs.length}</strong> ilan
      </div>
      <div class="pagination-controls-wrap">
        ${buttonsHtml}
      </div>
    </div>
  `;
}

function goToPage(page) {
  applyFiltersAndPaginate(page);
  const target = document.getElementById('jobs-feed');
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// =============================================================================
// İLAN DETAY MODALI (DOĞRUDAN AKTARMALI PDF & SIFIR 404 HATASI)
// =============================================================================
function openJobDetailModal(jobId) {
  const job = state.allJobs.find(j => j.id === jobId);
  if (!job) return;

  const modal = document.getElementById('job-detail-modal');
  if (!modal) return;

  document.getElementById('modal-inst-name').textContent = job.institution;
  document.getElementById('modal-job-title').textContent = job.title;

  document.getElementById('modal-spec-position').textContent = job.position || 'Kamu Personeli';
  document.getElementById('modal-spec-quota').textContent = `${job.total_positions} Kişi`;
  document.getElementById('modal-spec-dates').textContent = job.date_interval || job.end_date_str;
  document.getElementById('modal-spec-education').textContent = job.education_level || 'Resmi Kılavuzda Belirtilmiştir';
  document.getElementById('modal-spec-kpss').textContent = job.kpss_requirement || 'Resmi İlanda Belirtilmiştir';
  document.getElementById('modal-spec-city').textContent = job.city || 'Türkiye Geneli / İlanda Belirtilen İller';

  // İptal Uyarısı
  const alertBox = document.getElementById('modal-cancel-alert');
  if (alertBox) {
    if (job.is_cancellation) {
      alertBox.style.display = 'block';
      alertBox.innerHTML = `
        <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:6px;padding:12px 16px;color:#991B1B;font-size:0.8125rem;">
          <strong>🚨 DİKKAT: ALIM İPTALİ / DÜZELTME DUYURUSUDUR!</strong><br>
          Bu alım süreci ilgili resmi kamu kurumu tarafından iptal edilmiş veya düzeltilmiştir. Yeni başvuru alınmamaktadır.
        </div>
      `;
    } else {
      alertBox.style.display = 'none';
    }
  }

  // PDF İndirme Butonu (Doğrudan Yerel Dosya Eşleştirmesi - 0 Hata)
  const pdfBtn = document.getElementById('modal-pdf-download-btn');
  if (pdfBtn) {
    if (job.has_pdf && job.pdf_url) {
      pdfBtn.style.display = 'inline-flex';
      pdfBtn.href = job.pdf_url;
      pdfBtn.download = `sbb_${job.id}_kilavuz.pdf`;
      pdfBtn.innerHTML = `<span>📄</span> Resmi Kılavuzu İndir (PDF)`;
    } else {
      // Yerel PDF henüz indirilmemişse doğrudan resmi ana portala yönlendir (404 sayfası yerine)
      pdfBtn.style.display = 'inline-flex';
      pdfBtn.href = job.source_url || 'https://kamuilan.sbb.gov.tr/';
      pdfBtn.removeAttribute('download');
      pdfBtn.innerHTML = `<span>🏛</span> Resmi Kurum Portalı`;
    }
  }

  const sourceBtn = document.getElementById('modal-source-btn');
  if (sourceBtn) {
    sourceBtn.href = job.source_url || 'https://kamuilan.sbb.gov.tr/';
  }

  // Paylaş
  const shareBtn = document.getElementById('modal-share-btn');
  if (shareBtn) {
    shareBtn.onclick = () => {
      const shareText = `📢 ${job.institution} Personel Alım İlanı:\n${job.title}\nDetaylar: https://kamupersonelrehberiniz.me/`;
      if (navigator.share) {
        navigator.share({ title: job.institution, text: shareText, url: window.location.href }).catch(() => {});
      } else {
        navigator.clipboard.writeText(shareText).then(() => alert('✅ İlan bilgileri kopyalandı!'));
      }
    };
  }

  modal.classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeJobDetailModal() {
  const modal = document.getElementById('job-detail-modal');
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

function checkAndOpenDeepLinkedJob() {
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const targetJobId = urlParams.get('ilan') || urlParams.get('job') || window.location.hash.replace('#ilan-', '').replace('#job-', '');
    if (targetJobId) {
      const numId = parseInt(targetJobId, 10);
      if (!isNaN(numId)) {
        setTimeout(() => {
          openJobDetailModal(numId);
        }, 350);
      }
    }
  } catch (e) {
    console.warn('Deep link yönlendirme hatası:', e);
  }
}

// =============================================================================
// ARAMA VE FİLTRELEME OLAYLARI
// =============================================================================
function bindSearchAndFilters() {
  const sInput = document.getElementById('search-input');
  if (sInput) {
    sInput.addEventListener('input', debounce(e => {
      state.searchQuery = e.target.value.trim();
      applyFiltersAndPaginate(1);
    }, 250));
  }

  const sBtn = document.getElementById('search-btn-trigger');
  if (sBtn && sInput) {
    sBtn.addEventListener('click', () => {
      state.searchQuery = sInput.value.trim();
      applyFiltersAndPaginate(1);
    });
  }

  const sortSelect = document.getElementById('sort-select');
  if (sortSelect) {
    sortSelect.addEventListener('change', e => {
      state.sortBy = e.target.value;
      applyFiltersAndPaginate(1);
    });
  }

  const chkOpen = document.getElementById('chk-only-open');
  if (chkOpen) {
    chkOpen.addEventListener('change', e => {
      state.filterOnlyOpen = e.target.checked;
      applyFiltersAndPaginate(1);
    });
  }

  const chkCanc = document.getElementById('chk-only-canc');
  if (chkCanc) {
    chkCanc.addEventListener('change', e => {
      state.filterOnlyCanc = e.target.checked;
      applyFiltersAndPaginate(1);
    });
  }

  const chkPdf = document.getElementById('chk-only-pdf');
  if (chkPdf) {
    chkPdf.addEventListener('change', e => {
      state.filterOnlyPdf = e.target.checked;
      applyFiltersAndPaginate(1);
    });
  }
}

function resetFilters() {
  state.searchQuery = '';
  state.activeCategory = 'all';
  state.filterOnlyOpen = false;
  state.filterOnlyCanc = false;
  state.filterOnlyPdf = false;
  state.sortBy = 'date_desc';

  const sInput = document.getElementById('search-input');
  if (sInput) sInput.value = '';

  const chkOpen = document.getElementById('chk-only-open');
  if (chkOpen) chkOpen.checked = false;

  const chkCanc = document.getElementById('chk-only-canc');
  if (chkCanc) chkCanc.checked = false;

  const chkPdf = document.getElementById('chk-only-pdf');
  if (chkPdf) chkPdf.checked = false;

  renderCategoryMenu();
  applyFiltersAndPaginate(1);
}

// =============================================================================
// YASAL MODALLAR & ÇEREZ YÖNETİMİ
// =============================================================================
function openLegalModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeLegalModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

function initCookieConsent() {
  const banner = document.getElementById('cookie-consent-banner');
  if (!banner) return;

  const consent = localStorage.getItem('kpr_cookie_consent');
  if (!consent) {
    setTimeout(() => banner.classList.add('show'), 1000);
  }

  const acceptBtn = document.getElementById('cookie-accept-btn');
  if (acceptBtn) {
    acceptBtn.addEventListener('click', () => {
      localStorage.setItem('kpr_cookie_consent', 'accepted');
      banner.classList.remove('show');
    });
  }

  const declineBtn = document.getElementById('cookie-decline-btn');
  if (declineBtn) {
    declineBtn.addEventListener('click', () => {
      localStorage.setItem('kpr_cookie_consent', 'essential');
      banner.classList.remove('show');
    });
  }
}

// =============================================================================
// YARDIMCI METOTLAR
// =============================================================================
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}
