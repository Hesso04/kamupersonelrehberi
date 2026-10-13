/**
 * KAMU PERSONEL REHBERİ - EDITORIAL APPLE GLASS & TACTILE MOTORU (v6.0)
 * 3D Cursor/Touch Weight Tilt, iOS Bottom Sheet Swipe, SBB Senkronizasyonu & Hızlı Sayfalama
 */

const CONFIG = {
  PAGE_SIZE: 15,
  DATA_URL: 'data/jobs.json',
};

// Uygulama Durumu (State)
const state = {
  allJobs: [],
  filteredJobs: [],
  meta: {},
  activeCategory: 'all',
  quickPill: 'all',
  searchQuery: '',
  educationLevel: 'all',
  filterOnlyOpen: false,
  filterOnlyCanc: false,
  filterOnlyPdf: false,
  filterKpssSartsiz: false,
  sortBy: 'date_desc',
  currentPage: 1,
  theme: 'light',
};

// DOM Yüklendiğinde Başlat
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initApp();
  initCookieConsent();
  initGlobalKeyboardShortcuts();
  initModalSwipeDown();
  trackAnalytics('PAGEVIEW');
});

// =============================================================================
// 1. TEMA YÖNETİMİ (LIGHT MONOKROM TAŞ / DARK EDİTORYAL)
// =============================================================================
function initTheme() {
  const savedTheme = localStorage.getItem('kpr_theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
    state.theme = 'dark';
    document.documentElement.classList.add('dark');
  } else {
    state.theme = 'light';
    document.documentElement.classList.remove('dark');
  }
  updateThemeIcon();

  const themeBtn = document.getElementById('theme-toggle-btn');
  if (themeBtn) {
    themeBtn.addEventListener('click', toggleTheme);
  }
}

function toggleTheme() {
  if (state.theme === 'dark') {
    state.theme = 'light';
    document.documentElement.classList.remove('dark');
    localStorage.setItem('kpr_theme', 'light');
  } else {
    state.theme = 'dark';
    document.documentElement.classList.add('dark');
    localStorage.setItem('kpr_theme', 'dark');
  }
  updateThemeIcon();
}

function updateThemeIcon() {
  const iconEl = document.getElementById('theme-icon');
  if (iconEl) {
    iconEl.innerHTML = state.theme === 'dark'
      ? `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`
      : `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`;
  }
}

// =============================================================================
// 2. ANA UYGULAMA BAŞLATICI (DATA LOADING & INIT)
// =============================================================================
async function initApp() {
  try {
    const res = await fetch(CONFIG.DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    state.allJobs = data.jobs || [];
    state.meta = data.meta || {};

    // İstatistik Kartlarını Güncelle
    updatePortalStats();

    // Filtre & Sayfalamayı Başlat
    applyFiltersAndPaginate(1);

    // Olay Dinleyicilerini Bağla
    bindSearchAndFilters();

    // 3D Dokunsal Ağırlık / Eğilme Motorunu Başlat
    initCursorWeightTilt();

    // Deep Link İlan Kontrolü (?ilan=123)
    checkAndOpenDeepLinkedJob();
  } catch (err) {
    console.error('İlan verisi yüklenirken hata:', err);
    const feed = document.getElementById('jobs-feed');
    if (feed) {
      feed.innerHTML = `
        <div style="background:var(--glass-bg);border:1px solid var(--warning-border);border-radius:16px;padding:32px 20px;text-align:center;color:var(--text-primary);">
          <div style="font-size:2rem;margin-bottom:8px;">⚠️</div>
          <strong style="font-size:1.1rem;display:block;margin-bottom:6px;">İlan verileri yüklenemedi.</strong>
          <p style="font-size:0.875rem;color:var(--text-secondary);max-width:460px;margin:0 auto 16px auto;">
            Sunucu veya internet bağlantınızı kontrol ederek sayfayı yeniden yükleyiniz.
          </p>
          <button onclick="location.reload()" class="btn-apple-primary">Sayfayı Yenile</button>
        </div>
      `;
    }
  }
}

function updatePortalStats() {
  // Aktif Ziyaretçi
  const visitors = state.meta.active_visitors || 2071;
  const visitorsEl = document.getElementById('stat-active-visitors');
  const visitorsFooterEl = document.getElementById('stat-active-visitors-footer');
  if (visitorsEl) visitorsEl.textContent = visitors.toLocaleString('tr-TR');
  if (visitorsFooterEl) visitorsFooterEl.textContent = visitors.toLocaleString('tr-TR');

  // Toplam İlan
  const totalJobs = state.allJobs.length;
  const totalJobsEl = document.getElementById('stat-total-jobs');
  const totalJobsFooterEl = document.getElementById('stat-total-jobs-footer');
  if (totalJobsEl) totalJobsEl.textContent = totalJobs.toLocaleString('tr-TR');
  if (totalJobsFooterEl) totalJobsFooterEl.textContent = totalJobs.toLocaleString('tr-TR');

  // Toplam Kontenjan
  const totalQuota = state.allJobs.reduce((acc, j) => acc + (parseInt(j.total_positions, 10) || 1), 0);
  const quotaEl = document.getElementById('stat-total-quota');
  if (quotaEl) quotaEl.textContent = totalQuota > 0 ? `${totalQuota.toLocaleString('tr-TR')}+` : '14.850+';

  // Canlı Şerit Rozeti
  const countBadge = document.getElementById('strip-count-badge');
  if (countBadge) countBadge.textContent = `${totalJobs} İLAN YAYINDA`;
}

// =============================================================================
// 3. FİLTRELEME & AKILLI SAYFALAMA MOTORU
// =============================================================================
function applyFiltersAndPaginate(page = 1) {
  state.currentPage = page;

  // Filtreler
  state.filteredJobs = state.allJobs.filter(job => {
    // 1. Kategori Filtresi
    if (state.activeCategory !== 'all' && job.category_slug !== state.activeCategory) {
      return false;
    }

    // 2. Arama Metni
    if (state.searchQuery) {
      const q = state.searchQuery.toLocaleLowerCase('tr-TR');
      const searchTarget = `${job.institution} ${job.title} ${job.position} ${job.city}`.toLocaleLowerCase('tr-TR');
      if (!searchTarget.includes(q)) return false;
    }

    // 3. Öğrenim Düzeyi Filtresi
    if (state.educationLevel !== 'all') {
      const edu = (job.education_level || '').toLocaleLowerCase('tr-TR');
      if (state.educationLevel === 'lisans' && !edu.includes('lisans') && !edu.includes('fakülte')) return false;
      if (state.educationLevel === 'onlisans' && !edu.includes('ön lisans') && !edu.includes('önlisans') && !edu.includes('meslek yüksek')) return false;
      if (state.educationLevel === 'lise' && !edu.includes('lise') && !edu.includes('ortaöğretim')) return false;
      if (state.educationLevel === 'ilkogretim' && !edu.includes('ilköğretim') && !edu.includes('ilkokul') && !edu.includes('ortaokul')) return false;
    }

    // 4. Hızlı Durum Filtreleri
    if (state.filterOnlyOpen && job.status !== 'BAŞVURUYA AÇIK') return false;
    if (state.filterOnlyCanc && !job.is_cancellation) return false;
    if (state.filterOnlyPdf && !job.has_pdf) return false;
    if (state.filterKpssSartsiz) {
      const kpss = (job.kpss_requirement || '').toLocaleLowerCase('tr-TR');
      const isSartsiz = kpss.includes('şartsız') || kpss.includes('aranmamaktadır') || kpss.includes('muaf') || kpss.includes('kura');
      if (!isSartsiz) return false;
    }

    return true;
  });

  // Sıralama
  if (state.sortBy === 'quota_desc') {
    state.filteredJobs.sort((a, b) => (b.total_positions || 0) - (a.total_positions || 0));
  } else if (state.sortBy === 'quota_asc') {
    state.filteredJobs.sort((a, b) => (a.total_positions || 0) - (b.total_positions || 0));
  } else {
    state.filteredJobs.sort((a, b) => (b.sort_key || 0) - (a.sort_key || 0));
  }

  // Canlı Şerit Sayaç Güncellemesi
  const countBadge = document.getElementById('strip-count-badge');
  if (countBadge) {
    countBadge.textContent = `${state.filteredJobs.length} İLAN LİSTELENDİ`;
  }

  // Sayfalama Hesabı
  const totalPages = Math.ceil(state.filteredJobs.length / CONFIG.PAGE_SIZE) || 1;
  if (state.currentPage > totalPages) state.currentPage = totalPages;

  const startIndex = (state.currentPage - 1) * CONFIG.PAGE_SIZE;
  const pageJobs = state.filteredJobs.slice(startIndex, startIndex + CONFIG.PAGE_SIZE);

  // İlan Listesini ve Sayfalamayı Çiz
  renderJobsFeed(pageJobs);
  renderPaginationBar(totalPages);

  // Yeniden çizilen satırlara 3D tilt motorunu bağla
  rebindTiltSurfaces();
}

// =============================================================================
// 4. İLAN LİSTESİ ÇİZİMİ (HORIZONTAL STACKED ROWS)
// =============================================================================
function renderJobsFeed(jobsToRender) {
  const feed = document.getElementById('jobs-feed');
  if (!feed) return;

  if (jobsToRender.length === 0) {
    feed.innerHTML = `
      <div class="apple-glass" style="border-radius:20px;padding:56px 24px;text-align:center;">
        <div style="font-size:2.8rem;margin-bottom:12px;">🔍</div>
        <h3 class="font-editorial" style="font-size:1.35rem;font-weight:600;color:var(--text-primary);margin-bottom:6px;">
          Kriterlere Uygun İlan Bulunamadı
        </h3>
        <p style="font-size:0.875rem;color:var(--text-secondary);max-width:440px;margin:0 auto 18px auto;">
          Arama teriminizi değiştirmeyi veya filtreleri temizlemeyi deneyebilirsiniz.
        </p>
        <button onclick="resetAllFilters()" class="btn-apple-primary">Filtreleri Temizle</button>
      </div>
    `;
    return;
  }

  feed.innerHTML = jobsToRender.map(job => renderJobRowItem(job)).join('');
}

function renderJobRowItem(job) {
  const isCanc = job.is_cancellation;
  const emblemChar = (job.institution || 'K').trim()[0].toUpperCase();
  const quota = job.total_positions || 1;
  const dateStr = escapeHtml(job.date_interval || job.end_date_str || 'Güncel İlan');
  const eduStr = escapeHtml(job.education_level || 'Belirtilmedi');
  const kpssStr = escapeHtml(job.kpss_requirement || 'KPSS Şartı İlanda');
  const cityStr = escapeHtml(job.city || 'Türkiye Geneli');

  // Durum Rozeti
  let statusBadge = '';
  if (isCanc) {
    statusBadge = `<span class="job-status-pill amber">🚨 İptal / Düzeltme</span>`;
  } else {
    const kpssLow = (job.kpss_requirement || '').toLowerCase();
    if (kpssLow.includes('şartsız') || kpssLow.includes('aranmamaktadır') || kpssLow.includes('muaf') || kpssLow.includes('kura')) {
      statusBadge = `<span class="job-status-pill pine">KPSS Şartsız</span>`;
    } else {
      statusBadge = `<span class="job-status-pill pine">Kariyer Kapısı</span>`;
    }
  }

  return `
    <article class="job-stacked-row apple-glass tilt-surface ${isCanc ? 'is-cancellation' : ''}" onclick="openJobDetailModal(${job.id})" role="button" tabindex="0" aria-label="${escapeHtml(job.institution)}: ${escapeHtml(job.title)}">
      
      <!-- ================= MASAÜSTÜ 12 SÜTUNLU GÖRÜNÜM ================= -->
      <div class="job-row-desktop-grid">
        
        <!-- Col 5: Kurum & İlan Başlığı -->
        <div class="col-job-identity">
          <div class="job-inst-emblem" aria-hidden="true">${emblemChar}</div>
          <div class="job-identity-text">
            <div class="job-inst-kicker-line">
              <span class="job-inst-name-kicker">${escapeHtml(job.institution)}</span>
              ${statusBadge}
            </div>
            <h2 class="job-row-title-headline font-editorial">${escapeHtml(job.title)}</h2>
          </div>
        </div>

        <!-- Col 2: Öğrenim Düzeyi & KPSS -->
        <div class="col-job-education">
          <span class="job-meta-primary">
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>
            ${eduStr}
          </span>
          <span class="job-meta-secondary">
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
            ${kpssStr}
          </span>
        </div>

        <!-- Col 2: Görev Yeri & Kaynak -->
        <div class="col-job-location">
          <span class="job-meta-primary">
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
            ${cityStr}
          </span>
          <span class="job-meta-secondary">
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            Resmi Kamu İlanı
          </span>
        </div>

        <!-- Col 1: Kontenjan Sayısı -->
        <div class="col-job-quota">
          <span class="job-quota-number font-editorial">${quota}</span>
          <span class="job-quota-caption">Kontenjan</span>
        </div>

        <!-- Col 2: Son Başvuru Tarihi & Ok Butonu -->
        <div class="col-job-action">
          <div class="job-deadline-wrap">
            <div class="job-deadline-status-line">
              <span class="status-dot-green" aria-hidden="true"></span>
              <span>Son Gün</span>
            </div>
            <span class="job-deadline-date-sub">${dateStr}</span>
          </div>
          <div class="job-row-arrow-btn" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
          </div>
        </div>

      </div>

      <!-- ================= MOBİL DUYARLI GÖRÜNÜM (KESİNTİSİZ BAŞLIK) ================= -->
      <div class="job-row-mobile-view">
        <div class="mobile-row-header">
          <span class="mobile-inst-tag">${escapeHtml(job.institution)}</span>
          ${statusBadge}
        </div>

        <!-- Kesilmeyen, Alt Satıra Temiz Kayabilen Başlık -->
        <h2 class="mobile-title-text font-editorial">${escapeHtml(job.title)}</h2>

        <div class="mobile-divider"></div>

        <div class="mobile-pills-wrap">
          <span class="mobile-info-pill quota">
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
            ${quota} Kişi
          </span>
          <span class="mobile-info-pill">
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>
            ${eduStr}
          </span>
          <span class="mobile-info-pill">
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
            ${cityStr}
          </span>
        </div>

        <div class="mobile-bottom-bar">
          <span class="mobile-kpss-req">
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
            ${kpssStr}
          </span>
          <span class="mobile-date-arrow">
            <span>${dateStr}</span>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--primary-accent);"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </span>
        </div>
      </div>

    </article>
  `;
}

// =============================================================================
// 5. SAYFALAMA ÇUBUĞU
// =============================================================================
function renderPaginationBar(totalPages) {
  const container = document.getElementById('pagination-container');
  if (!container) return;

  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  const current = state.currentPage;
  let buttonsHtml = '';

  // Önceki Butonu
  buttonsHtml += `
    <button class="pagination-btn" ${current === 1 ? 'disabled' : ''} onclick="goToPage(${current - 1})">
      ◀ Önceki
    </button>
  `;

  // Sayfa Butonları
  const maxButtons = 5;
  let startPage = Math.max(1, current - 2);
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);

  if (endPage - startPage < maxButtons - 1) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  if (startPage > 1) {
    buttonsHtml += `<button class="pagination-btn" onclick="goToPage(1)">1</button>`;
    if (startPage > 2) buttonsHtml += `<span style="color:var(--text-tertiary);padding:0 4px;">…</span>`;
  }

  for (let p = startPage; p <= endPage; p++) {
    buttonsHtml += `
      <button class="pagination-btn ${p === current ? 'active' : ''}" onclick="goToPage(${p})">
        ${p}
      </button>
    `;
  }

  if (endPage < totalPages) {
    if (endPage < totalPages - 1) buttonsHtml += `<span style="color:var(--text-tertiary);padding:0 4px;">…</span>`;
    buttonsHtml += `<button class="pagination-btn" onclick="goToPage(${totalPages})">${totalPages}</button>`;
  }

  // Sonraki Butonu
  buttonsHtml += `
    <button class="pagination-btn" ${current === totalPages ? 'disabled' : ''} onclick="goToPage(${current + 1})">
      Sonraki ▶
    </button>
  `;

  container.innerHTML = `
    <div class="pagination-glass-card apple-glass">
      <div class="pagination-stat-info">
        Sayfa <strong>${current}</strong> / <strong>${totalPages}</strong> &nbsp;•&nbsp; 
        Toplam <strong>${state.filteredJobs.length}</strong> ilan
      </div>
      <div class="pagination-btn-group">
        ${buttonsHtml}
      </div>
    </div>
  `;
}

function goToPage(page) {
  applyFiltersAndPaginate(page);
  const target = document.getElementById('ilanlar');
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// =============================================================================
// 6. 3D CURSOR & TOUCH WEIGHT TILT MOTORU (.tilt-surface)
// =============================================================================
function initCursorWeightTilt() {
  document.addEventListener('mousemove', handleTiltMove);
  document.addEventListener('mouseleave', handleTiltLeave, true);
  document.addEventListener('touchmove', handleTiltTouch, { passive: true });
  document.addEventListener('touchend', handleTiltTouchEnd, { passive: true });
}

function rebindTiltSurfaces() {
  // Dinamik olarak eklenen elemanlar zaten event delegation ile handleTiltMove tarafından yakalanır.
}

function handleTiltMove(e) {
  const target = e.target.closest('.tilt-surface');
  if (!target) return;

  const rect = target.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;

  const normX = x / rect.width - 0.5;
  const normY = y / rect.height - 0.5;

  // İnce satırlar (<120px) için 2.6deg, büyük kartlar için 4.2deg
  const maxTilt = rect.height < 120 ? 2.6 : 4.2;

  const rx = (-normY * maxTilt * 2).toFixed(2);
  const ry = (normX * maxTilt * 2).toFixed(2);

  target.style.setProperty('--rx', `${rx}deg`);
  target.style.setProperty('--ry', `${ry}deg`);
  target.style.setProperty('--tz', '-2px');
  target.style.setProperty('--spot-x', `${((normX + 0.5) * 100).toFixed(1)}%`);
  target.style.setProperty('--spot-y', `${((normY + 0.5) * 100).toFixed(1)}%`);
  target.classList.add('is-tilting');
}

function handleTiltLeave(e) {
  const target = e.target.closest ? e.target.closest('.tilt-surface') : null;
  if (!target) return;
  resetTiltSurface(target);
}

function handleTiltTouch(e) {
  if (!e.touches || !e.touches[0]) return;
  const touch = e.touches[0];
  const target = document.elementFromPoint(touch.clientX, touch.clientY)?.closest('.tilt-surface');
  if (!target) return;

  const rect = target.getBoundingClientRect();
  const normX = (touch.clientX - rect.left) / rect.width - 0.5;
  const normY = (touch.clientY - rect.top) / rect.height - 0.5;
  const maxTilt = rect.height < 120 ? 2.6 : 4.2;

  const rx = (-normY * maxTilt * 2).toFixed(2);
  const ry = (normX * maxTilt * 2).toFixed(2);

  target.style.setProperty('--rx', `${rx}deg`);
  target.style.setProperty('--ry', `${ry}deg`);
  target.style.setProperty('--tz', '-3px');
  target.style.setProperty('--spot-x', `${((normX + 0.5) * 100).toFixed(1)}%`);
  target.style.setProperty('--spot-y', `${((normY + 0.5) * 100).toFixed(1)}%`);
  target.classList.add('is-tilting');
}

function handleTiltTouchEnd() {
  document.querySelectorAll('.tilt-surface.is-tilting').forEach(resetTiltSurface);
}

function resetTiltSurface(el) {
  el.style.setProperty('--rx', '0deg');
  el.style.setProperty('--ry', '0deg');
  el.style.setProperty('--tz', '0px');
  el.classList.remove('is-tilting');
}

// =============================================================================
// 7. iOS SWIPEABLE BOTTOM SHEET DETAY MODALI
// =============================================================================
let touchStartY = 0;
let touchCurrentY = 0;

function initModalSwipeDown() {
  const sheet = document.getElementById('modal-sheet-container');
  if (!sheet) return;

  sheet.addEventListener('touchstart', e => {
    if (e.touches && e.touches[0]) {
      touchStartY = e.touches[0].clientY;
      touchCurrentY = touchStartY;
    }
  }, { passive: true });

  sheet.addEventListener('touchmove', e => {
    if (e.touches && e.touches[0]) {
      touchCurrentY = e.touches[0].clientY;
      const deltaY = touchCurrentY - touchStartY;
      if (deltaY > 0) {
        sheet.style.transform = `translateY(${deltaY}px)`;
      }
    }
  }, { passive: true });

  sheet.addEventListener('touchend', () => {
    const deltaY = touchCurrentY - touchStartY;
    sheet.style.transform = '';
    // 75px'den fazla aşağı çekildiyse kapat
    if (deltaY > 75) {
      closeJobDetailModal();
    }
  }, { passive: true });
}

function openJobDetailModal(jobId) {
  const job = state.allJobs.find(j => String(j.id) === String(jobId));
  if (!job) return;

  const modal = document.getElementById('job-detail-modal');
  if (!modal) return;

  document.getElementById('modal-inst-name').textContent = job.institution;
  document.getElementById('modal-job-title').textContent = job.title;

  document.getElementById('modal-spec-position').textContent = job.position || 'Kamu Personeli';
  document.getElementById('modal-spec-quota').textContent = `${job.total_positions || 1} Kişi`;
  document.getElementById('modal-spec-dates').textContent = job.date_interval || job.end_date_str || 'Resmi İlanda Belirtilmiştir';
  document.getElementById('modal-spec-education').textContent = job.education_level || 'Resmi Kılavuzda Belirtilmiştir';
  document.getElementById('modal-spec-kpss').textContent = job.kpss_requirement || 'Resmi İlanda Belirtilmiştir';
  document.getElementById('modal-spec-city').textContent = job.city || 'Türkiye Geneli / İlanda Belirtilen İller';

  // İptal Uyarısı
  const alertBox = document.getElementById('modal-cancel-alert');
  if (alertBox) {
    if (job.is_cancellation) {
      alertBox.style.display = 'block';
      alertBox.innerHTML = `
        <div style="background:var(--warning-bg);border:1px solid var(--warning-border);border-radius:10px;padding:12px 16px;color:var(--warning-text);font-size:0.8125rem;">
          <strong>🚨 DİKKAT: ALIM İPTALİ / DÜZELTME DUYURUSUDUR!</strong><br>
          Bu alım süreci ilgili kamu kurumu tarafından iptal edilmiş veya düzeltilmiştir. Yeni başvuru alınmamaktadır.
        </div>
      `;
    } else {
      alertBox.style.display = 'none';
    }
  }

  // PDF İndirme Butonu
  const pdfBtn = document.getElementById('modal-pdf-download-btn');
  if (pdfBtn) {
    if (job.has_pdf && job.pdf_url) {
      pdfBtn.style.display = 'inline-flex';
      pdfBtn.href = job.pdf_url;
      pdfBtn.download = `sbb_${job.id}_kilavuz.pdf`;
      pdfBtn.innerHTML = `<span>📄</span> Resmi Kılavuzu İndir (PDF)`;
    } else {
      pdfBtn.style.display = 'inline-flex';
      pdfBtn.href = job.source_url || 'https://kamuilan.sbb.gov.tr/';
      pdfBtn.removeAttribute('download');
      pdfBtn.innerHTML = `<span>📄</span> Kılavuz Bağlantısı (Resmi Portal)`;
    }
    pdfBtn.onclick = () => {
      trackAnalytics('PDF_DOWNLOAD', { jobId: job.id, jobTitle: job.title });
    };
  }

  // Kaynak Butonu
  const sourceBtn = document.getElementById('modal-source-btn');
  if (sourceBtn) {
    sourceBtn.href = job.source_url || 'https://kamuilan.sbb.gov.tr/';
    sourceBtn.onclick = () => {
      trackAnalytics('APPLY_CLICK', { jobId: job.id, jobTitle: job.title, category: job.category_name });
    };
  }

  // Paylaş Butonu
  const shareBtn = document.getElementById('modal-share-btn');
  if (shareBtn) {
    shareBtn.onclick = () => {
      const shareUrl = `https://kamupersonelrehberiniz.me/?ilan=${job.id}`;
      const shareText = `📢 ${job.institution} Personel Alım İlanı:\n${job.title}\nDetaylar: ${shareUrl}`;
      if (navigator.share) {
        navigator.share({ title: job.institution, text: shareText, url: shareUrl }).catch(() => {});
      } else {
        navigator.clipboard.writeText(shareText).then(() => alert('✅ İlan bağlantısı kopyalandı!'));
      }
    };
  }

  // Modal'ı Aç
  modal.classList.add('active');
  document.body.style.overflow = 'hidden';

  // Analitik & Dinamik SEO
  trackAnalytics('JOB_VIEW', { jobId: job.id, jobTitle: job.title, category: job.category_name });
  updateJobSeoMetadata(job);
}

function closeJobDetailModal() {
  const modal = document.getElementById('job-detail-modal');
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
  resetJobSeoMetadata();
}

// Modal dışına tıklandığında kapat
document.addEventListener('click', e => {
  const modal = document.getElementById('job-detail-modal');
  if (modal && modal.classList.contains('active') && e.target === modal) {
    closeJobDetailModal();
  }
});

// ESC Tuşu ile Modal Kapatma
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeJobDetailModal();
    closeLegalModal('modal-kvkk');
    closeLegalModal('modal-legal-warning');
  }
});

// =============================================================================
// 8. ETKİLEŞİM DİNLEYİCİLERİ, ARAMA & KISAYOLLAR
// =============================================================================
function bindSearchAndFilters() {
  const sInput = document.getElementById('search-input');
  if (sInput) {
    sInput.addEventListener('input', debounce(e => {
      state.searchQuery = e.target.value.trim();
      applyFiltersAndPaginate(1);
    }, 250));

    sInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        state.searchQuery = sInput.value.trim();
        applyFiltersAndPaginate(1);
      }
    });
  }

  const sBtn = document.getElementById('search-btn-trigger');
  if (sBtn && sInput) {
    sBtn.addEventListener('click', () => {
      state.searchQuery = sInput.value.trim();
      applyFiltersAndPaginate(1);
    });
  }

  const eduSelect = document.getElementById('education-select');
  if (eduSelect) {
    eduSelect.addEventListener('change', e => {
      state.educationLevel = e.target.value;
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

  const cmdBtn = document.getElementById('nav-cmd-search-btn');
  if (cmdBtn) {
    cmdBtn.addEventListener('click', focusSpotlightSearch);
  }
}

function initGlobalKeyboardShortcuts() {
  window.addEventListener('keydown', e => {
    // ⌘K veya Ctrl+K ile aramaya odaklan
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      focusSpotlightSearch();
    }
  });
}

function focusSpotlightSearch() {
  const sInput = document.getElementById('search-input');
  if (sInput) {
    sInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => sInput.focus(), 300);
  }
}

function scrollToSection(sectionId) {
  const el = document.getElementById(sectionId);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// Hızlı Filtre Hapları (Quick Pills)
function selectQuickPill(pillType) {
  state.quickPill = pillType;

  // Aktif hap sınıfını güncelle
  document.querySelectorAll('.quick-pill-item').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-pill') === pillType);
  });

  // Filtre durumlarını sıfırla
  state.searchQuery = '';
  state.activeCategory = 'all';
  state.filterKpssSartsiz = false;
  state.filterOnlyOpen = false;
  state.filterOnlyCanc = false;
  state.filterOnlyPdf = false;

  const sInput = document.getElementById('search-input');
  if (sInput) sInput.value = '';

  if (pillType === 'all') {
    // Tümü
  } else if (pillType === 'kpss_sartsiz') {
    state.filterKpssSartsiz = true;
  } else if (pillType === 'akademik') {
    state.activeCategory = 'akademik';
  } else if (pillType === 'sozlesmeli') {
    state.activeCategory = 'sozlesmeli';
  } else if (pillType === 'bilisim') {
    state.activeCategory = 'bilisim';
  } else if (pillType === 'ankara') {
    state.searchQuery = 'ankara';
    if (sInput) sInput.value = 'Ankara';
  } else if (pillType === 'isci') {
    state.activeCategory = 'isci';
  }

  updateCategoryTabsUI();
  applyFiltersAndPaginate(1);
  scrollToSection('ilanlar');
}

// Kategori Sekmesi Seçimi
function filterByCategory(catSlug) {
  state.activeCategory = catSlug;
  state.filterOnlyOpen = false;
  state.filterOnlyCanc = false;
  state.filterOnlyPdf = false;
  state.filterKpssSartsiz = false;

  updateCategoryTabsUI();
  applyFiltersAndPaginate(1);
}

function toggleQuickFilter(type) {
  if (type === 'open') {
    state.filterOnlyOpen = !state.filterOnlyOpen;
  } else if (type === 'kpss_sartsiz') {
    state.filterKpssSartsiz = !state.filterKpssSartsiz;
  } else if (type === 'pdf') {
    state.filterOnlyPdf = !state.filterOnlyPdf;
  } else if (type === 'canc') {
    state.filterOnlyCanc = !state.filterOnlyCanc;
  }

  updateCategoryTabsUI();
  applyFiltersAndPaginate(1);
}

function updateCategoryTabsUI() {
  const tabs = document.querySelectorAll('.category-tab-btn');
  tabs.forEach(btn => {
    const cat = btn.getAttribute('data-cat');
    if (cat === 'all') {
      btn.classList.toggle('active', state.activeCategory === 'all' && !state.filterOnlyOpen && !state.filterKpssSartsiz && !state.filterOnlyPdf && !state.filterOnlyCanc);
    } else if (cat === 'open') {
      btn.classList.toggle('active', state.filterOnlyOpen);
    } else if (cat === 'kpss_sartsiz') {
      btn.classList.toggle('active', state.filterKpssSartsiz);
    } else if (cat === 'pdf') {
      btn.classList.toggle('active', state.filterOnlyPdf);
    } else if (cat === 'canc') {
      btn.classList.toggle('active', state.filterOnlyCanc);
    }
  });
}

function filterByKpssGeneral() {
  state.searchQuery = 'kpss';
  const sInput = document.getElementById('search-input');
  if (sInput) sInput.value = 'KPSS';
  applyFiltersAndPaginate(1);
  scrollToSection('ilanlar');
}

function resetAllFilters() {
  state.searchQuery = '';
  state.activeCategory = 'all';
  state.quickPill = 'all';
  state.educationLevel = 'all';
  state.filterOnlyOpen = false;
  state.filterOnlyCanc = false;
  state.filterOnlyPdf = false;
  state.filterKpssSartsiz = false;
  state.sortBy = 'date_desc';

  const sInput = document.getElementById('search-input');
  if (sInput) sInput.value = '';

  const eduSelect = document.getElementById('education-select');
  if (eduSelect) eduSelect.value = 'all';

  const sortSelect = document.getElementById('sort-select');
  if (sortSelect) sortSelect.value = 'date_desc';

  document.querySelectorAll('.quick-pill-item').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-pill') === 'all');
  });

  updateCategoryTabsUI();
  applyFiltersAndPaginate(1);
}

// =============================================================================
// 9. DİNAMİK SEO & GOOGLE FOR JOBS ŞEMASI
// =============================================================================
function updateJobSeoMetadata(job) {
  try {
    const jobTitle = `${job.institution || 'Kamu Kurumu'} ${job.position || 'Personel'} Alımı (${job.total_positions || 1} Kişi)`;
    const fullTitle = `${jobTitle} - Kamu Personel Rehberi`;
    const jobDesc = `${job.institution} tarafından yayımlanan ${job.total_positions || 1} kişilik ${job.position} alım ilanı. Son başvuru: ${job.application_end_date_formatted || 'Resmi Kılavuzda'}. Resmi PDF başvuru kılavuzu ve şartları.`;
    const deepUrl = `https://kamupersonelrehberiniz.me/?ilan=${job.id}`;

    document.title = fullTitle;

    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) metaDesc.setAttribute('content', jobDesc);

    let canonical = document.querySelector('link[rel="canonical"]');
    if (canonical) canonical.setAttribute('href', deepUrl);

    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) ogTitle.setAttribute('content', fullTitle);
    const ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) ogDesc.setAttribute('content', jobDesc);
    const ogUrl = document.querySelector('meta[property="og:url"]');
    if (ogUrl) ogUrl.setAttribute('content', deepUrl);

    let schemaScript = document.getElementById('dynamic-jobposting-schema');
    if (!schemaScript) {
      schemaScript = document.createElement('script');
      schemaScript.id = 'dynamic-jobposting-schema';
      schemaScript.type = 'application/ld+json';
      document.head.appendChild(schemaScript);
    }

    const jobSchema = {
      "@context": "https://schema.org/",
      "@type": "JobPosting",
      "title": `${job.institution} ${job.position || 'Personel'} Alımı`,
      "description": `<p>${jobDesc}</p><p>Başvuru tarihleri: ${job.application_dates || 'Resmi ilanda'}. KPSS Şartı: ${job.kpss_requirement || 'Resmi ilanda'}.</p>`,
      "identifier": {
        "@type": "PropertyValue",
        "name": job.institution || "Kamu Kurumu",
        "value": String(job.id)
      },
      "datePosted": (job.publish_date ? job.publish_date.split('T')[0] : new Date().toISOString().split('T')[0]),
      "validThrough": (job.application_end_date ? job.application_end_date.split('T')[0] : "2026-12-31"),
      "employmentType": job.is_contract ? "CONTRACTOR" : "FULL_TIME",
      "hiringOrganization": {
        "@type": "Organization",
        "name": job.institution || "T.C. Kamu Kurumu",
        "sameAs": job.source_url || "https://kamuilan.sbb.gov.tr/"
      },
      "jobLocation": {
        "@type": "Place",
        "address": {
          "@type": "PostalAddress",
          "addressLocality": job.city || "Türkiye",
          "addressCountry": "TR"
        }
      },
      "applicantLocationRequirements": {
        "@type": "Country",
        "name": "TR"
      },
      "url": deepUrl
    };

    schemaScript.textContent = JSON.stringify(jobSchema, null, 2);
  } catch (err) {
    console.debug('SEO güncelleme istisnası:', err);
  }
}

function resetJobSeoMetadata() {
  try {
    document.title = 'Kamu Personel Rehberi - 2026 Güncel Memur ve Personel Alım İlanları';
    const defDesc = '2026 T.C. Kamu kurum ve kuruluşlarının güncel memur alımı, 4/B sözleşmeli personel, işçi ve akademik kadro ilanları. Resmi Gazete ve SBB Kamu İlan Portalı teyitli başvuru kılavuzları.';
    const defUrl = 'https://kamupersonelrehberiniz.me/';

    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) metaDesc.setAttribute('content', defDesc);

    let canonical = document.querySelector('link[rel="canonical"]');
    if (canonical) canonical.setAttribute('href', defUrl);

    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) ogTitle.setAttribute('content', document.title);
    const ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) ogDesc.setAttribute('content', defDesc);
    const ogUrl = document.querySelector('meta[property="og:url"]');
    if (ogUrl) ogUrl.setAttribute('content', defUrl);

    const schemaScript = document.getElementById('dynamic-jobposting-schema');
    if (schemaScript) schemaScript.remove();
  } catch (err) {
    console.debug('SEO sıfırlama istisnası:', err);
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
// 10. YASAL MODALLAR & ÇEREZ YÖNETİMİ
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
    setTimeout(() => banner.classList.add('show'), 1200);
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
// 11. YARDIMCI METOTLAR (ESCAPE, DEBOUNCE, ANALYTICS)
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

function trackAnalytics(eventType, payload = {}) {
  try {
    const supabaseUrl = 'https://lxffirosgbrfptnbjvdg.supabase.co';
    const supabaseKey = 'sb_publishable_VHW7Sg89AM9NV6DqOHLTzQ_BMO4BBV9';

    let ref = 'Doğrudan (Direct)';
    const docRef = document.referrer.toLowerCase();
    const query = window.location.search.toLowerCase();

    if (docRef.includes('t.me') || docRef.includes('telegram') || query.includes('utm_source=telegram') || query.includes('ilan=')) {
      ref = 'Telegram Kanalı';
    } else if (docRef.includes('instagram.com') || query.includes('utm_source=instagram')) {
      ref = 'Instagram Bio';
    } else if (docRef.includes('google.') || docRef.includes('yandex.')) {
      ref = 'Google Arama';
    }

    const bodyData = {
      event_type: eventType,
      job_id: payload.jobId || null,
      job_title: payload.jobTitle ? String(payload.jobTitle).slice(0, 240) : null,
      category: payload.category || null,
      referrer: ref,
      user_agent: navigator.userAgent ? navigator.userAgent.slice(0, 240) : null
    };

    fetch(`${supabaseUrl}/rest/v1/site_analytics_events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': supabaseKey,
        'Authorization': `Bearer ${supabaseKey}`,
        'Prefer': 'return=minimal'
      },
      body: JSON.stringify(bodyData)
    }).catch(() => {});
  } catch (err) {
    // Analitik sessizce devam eder
  }
}
