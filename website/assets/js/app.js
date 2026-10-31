/**
 * KAMU PERSONEL REHBERİ - EDITORIAL APPLE GLASS & TACTILE MOTORU (v6.0)
 * 3D Cursor/Touch Weight Tilt, iOS Bottom Sheet Swipe, SBB Senkronizasyonu & Hızlı Sayfalama
 */

const CONFIG = {
  PAGE_SIZE: 15,
  DATA_URL: 'data/jobs.json',
  NEWS_URL: 'data/news.json',
};

// Uygulama Durumu (State)
const state = {
  allJobs: [],
  filteredJobs: [],
  allNews: [],
  activeNewsCategory: 'all',
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

    // 1. Kategori Sekmelerindeki Sayıları Otomatik Hesapla & Rozetleri Çiz
    populateCategoryTabCounts();

    // 2. URL Parametrelerini Çöz ve Durumu Uygula (?kategori=, ?q=, ?ogrenim=, ?kpss= vs.)
    applyInitialUrlParams();

    // 3. İstatistik Kartlarını Güncelle & Canlı Trafik Sayacını Çek
    updatePortalStats();
    fetchLiveVisitorCount();
    setInterval(fetchLiveVisitorCount, 45000);

    // 3. Olay Dinleyicilerini Bağla
    bindSearchAndFilters();

    // 4. Filtre & Sayfalamayı Başlat (İlk parametrelerle hesapla)
    applyFiltersAndPaginate(state.currentPage || 1);

    // 5. 3D Dokunsal Ağırlık / Eğilme Motorunu Başlat
    initCursorWeightTilt();

    // 6. Deep Link İlan Kontrolü (?ilan=123)
    checkAndOpenDeepLinkedJob();

    // 7. Kamu Haberleri ve Doğrulama Akışını Çek & Çiz
    fetchNewsData();

    // 8. Yeni İlan Bildirim Sistemini Başlat
    initPushNotifications();
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

async function fetchLiveVisitorCount() {
  try {
    const supabaseUrl = 'https://lxffirosgbrfptnbjvdg.supabase.co';
    const supabaseKey = 'sb_publishable_VHW7Sg89AM9NV6DqOHLTzQ_BMO4BBV9';
    const res = await fetch(`${supabaseUrl}/rest/v1/site_analytics_events?select=id&limit=1`, {
      headers: {
        'apikey': supabaseKey,
        'Authorization': `Bearer ${supabaseKey}`,
        'Range-Unit': 'items',
        'Prefer': 'count=exact'
      }
    });

    let totalEvents = 0;
    if (res.ok) {
      const cr = res.headers.get('content-range');
      if (cr && cr.includes('/')) {
        totalEvents = parseInt(cr.split('/')[1], 10) || 0;
      }
    }

    // Gerçek etkileşim veritabanı + saatlik doğal trafik simülasyonu
    const hour = new Date().getHours();
    const timeFactor = (hour >= 9 && hour <= 22) ? 1.25 : 0.75;
    const baseCount = 1850 + (totalEvents * 4) + Math.floor((Math.sin(Date.now() / 90000) * 110) * timeFactor);
    const displayCount = Math.max(1340, baseCount);

    const visitorsEl = document.getElementById('stat-active-visitors');
    const visitorsFooterEl = document.getElementById('stat-active-visitors-footer');
    if (visitorsEl) visitorsEl.textContent = displayCount.toLocaleString('tr-TR');
    if (visitorsFooterEl) visitorsFooterEl.textContent = displayCount.toLocaleString('tr-TR');
  } catch (err) {
    const fallback = state.meta.active_visitors || 2071;
    const visitorsEl = document.getElementById('stat-active-visitors');
    const visitorsFooterEl = document.getElementById('stat-active-visitors-footer');
    if (visitorsEl) visitorsEl.textContent = fallback.toLocaleString('tr-TR');
    if (visitorsFooterEl) visitorsFooterEl.textContent = fallback.toLocaleString('tr-TR');
  }
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

    // 2. Arama Metni (Çoklu kelime & tüm alanları kapsayan akıllı arama)
    if (state.searchQuery) {
      const q = state.searchQuery.toLocaleLowerCase('tr-TR').trim();
      const searchTarget = `${job.institution || ''} ${job.title || ''} ${job.position || ''} ${job.city || ''} ${job.education_level || ''} ${job.kpss_requirement || ''} ${job.category_name || ''}`.toLocaleLowerCase('tr-TR');
      const qWords = q.split(/\s+/).filter(w => w.length > 0);
      const matchesAll = qWords.every(word => searchTarget.includes(word));
      if (!matchesAll) return false;
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

  // Sıralama (Başvuruya açık ilanlar her zaman öncelikli, ardından kontenjan veya tarih)
  const getOpenScore = (j) => (j.status === 'BAŞVURUYA AÇIK' ? 1 : 0);

  if (state.sortBy === 'quota_desc') {
    state.filteredJobs.sort((a, b) => {
      const openDiff = getOpenScore(b) - getOpenScore(a);
      if (openDiff !== 0) return openDiff;
      return (b.total_positions || 0) - (a.total_positions || 0);
    });
  } else if (state.sortBy === 'quota_asc') {
    state.filteredJobs.sort((a, b) => {
      const openDiff = getOpenScore(b) - getOpenScore(a);
      if (openDiff !== 0) return openDiff;
      return (a.total_positions || 0) - (b.total_positions || 0);
    });
  } else {
    // Varsayılan: date_desc (Önce açık ilanlar, sonra sort_key azalan)
    state.filteredJobs.sort((a, b) => {
      const openDiff = getOpenScore(b) - getOpenScore(a);
      if (openDiff !== 0) return openDiff;
      return (b.sort_key || 0) - (a.sort_key || 0);
    });
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

  // Aktif Filtre Çiplerini Çiz
  renderActiveFilterChips();

  // URL'i filtre durumlarıyla senkronize et
  syncUrlWithState();
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
  const isExpired = job.status === 'SÜRESİ DOLDU';
  const isOpen = job.status === 'BAŞVURUYA AÇIK';
  const emblemChar = (job.institution || 'K').trim()[0].toUpperCase();
  const isExactQuota = job.is_exact_quota !== false;
  const quota = job.total_positions || 1;
  const quotaDisplay = isExactQuota ? (job.quota_display || `${quota} Kişi`) : 'Kılavuzda';
  const quotaNumberDisplay = isExactQuota ? quota : '—';
  const dateStr = escapeHtml(job.date_interval || job.end_date_str || 'Güncel İlan');
  const eduStr = escapeHtml(job.education_level || 'Belirtilmedi');
  const kpssStr = escapeHtml(job.kpss_requirement || 'KPSS Şartı İlanda');
  const cityStr = escapeHtml(job.city || 'Türkiye Geneli');
  const sourceName = escapeHtml(job.source_name || 'Resmi Kamu İlanı');

  // Durum & Kaynak Rozeti
  let statusBadge = '';
  if (isCanc) {
    statusBadge = `<span class="job-status-pill amber">🚨 İptal / Düzeltme</span>`;
  } else if (isOpen) {
    const kpssLow = (job.kpss_requirement || '').toLowerCase();
    if (kpssLow.includes('şartsız') || kpssLow.includes('aranmamaktadır') || kpssLow.includes('muaf') || kpssLow.includes('kura')) {
      statusBadge = `<span class="job-status-pill green">🟢 Başvuruya Açık</span> <span class="job-status-pill pine">KPSS Şartsız</span>`;
    } else {
      statusBadge = `<span class="job-status-pill green">🟢 Başvuruya Açık</span>`;
    }
  } else {
    statusBadge = `<span class="job-status-pill gray">Süresi Doldu</span>`;
  }

  // Tarih ve Durum Göstergesi
  let deadlineHtml = '';
  let mobileDateHtml = '';

  if (isCanc) {
    deadlineHtml = `
      <div class="job-deadline-status-line">
        <span class="status-dot-amber" aria-hidden="true"></span>
        <span style="color:var(--warning-text);font-weight:700;">İptal/Düzeltme</span>
      </div>
      <span class="job-deadline-date-sub">${dateStr}</span>
    `;
    mobileDateHtml = `
      <span class="mobile-date-arrow cancel">
        <span style="color:var(--warning-text);"><span class="status-dot-amber" style="display:inline-block;vertical-align:middle;margin-right:4px;"></span>${dateStr} (İptal)</span>
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--warning-text);"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
      </span>
    `;
  } else if (isOpen) {
    deadlineHtml = `
      <div class="job-deadline-status-line">
        <span class="status-dot-green" aria-hidden="true"></span>
        <span style="color:var(--emerald-status);font-weight:700;">Son Gün</span>
      </div>
      <span class="job-deadline-date-sub">${dateStr}</span>
    `;
    mobileDateHtml = `
      <span class="mobile-date-arrow">
        <span><span class="status-dot-green" style="display:inline-block;vertical-align:middle;margin-right:4px;"></span>Son: ${dateStr}</span>
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--primary-accent);"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
      </span>
    `;
  } else {
    deadlineHtml = `
      <div class="job-deadline-status-line">
        <span class="status-dot-expired" aria-hidden="true"></span>
        <span style="color:var(--text-tertiary);font-weight:600;">Süresi Doldu</span>
      </div>
      <span class="job-deadline-date-sub" style="text-decoration:line-through;color:var(--text-tertiary);">${dateStr}</span>
    `;
    mobileDateHtml = `
      <span class="mobile-date-arrow expired">
        <span style="color:var(--text-tertiary);"><span class="status-dot-expired" style="display:inline-block;vertical-align:middle;margin-right:4px;"></span>${dateStr} (Doldu)</span>
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--text-tertiary);"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
      </span>
    `;
  }

  return `
    <article class="job-stacked-row apple-glass tilt-surface ${isCanc ? 'is-cancellation' : ''} ${isExpired ? 'is-expired' : ''}" onclick="openJobDetailModal(${job.id})" role="button" tabindex="0" aria-label="${escapeHtml(job.institution)}: ${escapeHtml(job.title)}">
      
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
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="6" r="6"/><circle cx="12" cy="12" r="2"/></svg>
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
            ${sourceName}
          </span>
        </div>

        <!-- Col 1: Kontenjan Sayısı -->
        <div class="col-job-quota">
          <span class="job-quota-number font-editorial">${quotaNumberDisplay}</span>
          <span class="job-quota-caption">${isExactQuota ? 'Kontenjan' : 'Kılavuzda'}</span>
        </div>

        <!-- Col 2: Son Başvuru Tarihi & Ok Butonu -->
        <div class="col-job-action">
          <div class="job-deadline-wrap">
            ${deadlineHtml}
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
            ${quotaDisplay}
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
            <svg class="mini-meta-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="6" r="6"/><circle cx="12" cy="12" r="2"/></svg>
            ${kpssStr}
          </span>
          ${mobileDateHtml}
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
// 6. 3D CURSOR & TOUCH WEIGHT TILT MOTORU (KULLANICI TALEBİYLE KALDIRILDI)
// =============================================================================
function initCursorWeightTilt() {
  // Sayfanın yamulma/eğilme animasyonları görsel stabilite için komple kaldırıldı.
}

function rebindTiltSurfaces() {}
function handleTiltMove(e) {}
function handleTiltLeave(e) {}
function handleTiltTouch(e) {}
function handleTiltTouchEnd() {}
function resetTiltSurface(el) {
  if (!el) return;
  el.style.transform = 'none';
  el.classList.remove('is-tilting');
}

// =============================================================================
// 7. iOS SWIPEABLE BOTTOM SHEET DETAY MODALI
// =============================================================================
let touchStartY = 0;
let touchCurrentY = 0;

function initModalSwipeDown() {
  const sheet = document.getElementById('modal-sheet-container');
  const scrollBody = document.querySelector('.modal-scroll-body');
  if (!sheet) return;

  let isDragging = false;

  sheet.addEventListener('touchstart', e => {
    const target = e.target;
    const isGrabberOrHeader = target.closest('.modal-grabber') || target.closest('.modal-header-block');
    const isAtTop = !scrollBody || scrollBody.scrollTop <= 2;

    if (isGrabberOrHeader || isAtTop) {
      if (e.touches && e.touches[0]) {
        touchStartY = e.touches[0].clientY;
        touchCurrentY = touchStartY;
        isDragging = true;
      }
    } else {
      isDragging = false;
    }
  }, { passive: true });

  sheet.addEventListener('touchmove', e => {
    if (!isDragging) return;
    if (e.touches && e.touches[0]) {
      touchCurrentY = e.touches[0].clientY;
      const deltaY = touchCurrentY - touchStartY;
      const isAtTop = !scrollBody || scrollBody.scrollTop <= 2;
      if (deltaY > 0 && isAtTop) {
        sheet.style.transform = `translateY(${deltaY}px)`;
      } else {
        sheet.style.transform = '';
      }
    }
  }, { passive: true });

  sheet.addEventListener('touchend', () => {
    if (!isDragging) return;
    isDragging = false;
    const deltaY = touchCurrentY - touchStartY;
    sheet.style.transform = '';
    if (deltaY > 80) {
      closeJobDetailModal();
    }
    touchStartY = 0;
    touchCurrentY = 0;
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

  // Durum Bildirim Kartı (#modal-status-banner)
  const statusBanner = document.getElementById('modal-status-banner');
  if (statusBanner) {
    const isExpired = job.status === 'SÜRESİ DOLDU' || (job.application_end_date && new Date(job.application_end_date) < new Date());
    if (job.is_cancellation) {
      statusBanner.className = 'modal-status-banner cancel';
      statusBanner.style.display = 'block';
      statusBanner.innerHTML = `<strong>🚨 İptal / Düzeltme İlanı:</strong> Bu personel alımı ilgili kamu kurumu tarafından iptal edilmiş veya başvuru şartlarında düzeltme yapılmıştır. Yeni başvuru alınmamaktadır.`;
    } else if (isExpired) {
      statusBanner.className = 'modal-status-banner expired';
      statusBanner.style.display = 'block';
      const endDateStr = job.application_end_date_formatted || job.end_date_str || 'Sona Erdi';
      statusBanner.innerHTML = `<strong>⏳ Başvuru Süresi Sona Erdi:</strong> Bu ilanın son başvuru tarihi (${endDateStr}) geçmiştir. Arşiv ve inceleme amaçlı listelenmektedir.`;
    } else {
      statusBanner.className = 'modal-status-banner open';
      statusBanner.style.display = 'block';
      const endDateStr = job.application_end_date_formatted || job.end_date_str || 'Resmi Kılavuzda';
      statusBanner.innerHTML = `<strong>🟢 Başvurular Devam Ediyor:</strong> Son başvuru tarihi: <strong>${endDateStr}</strong>. Başvurunuzu resmi portal veya kılavuz üzerinden tamamlayabilirsiniz.`;
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

  // Kaynak Butonu (Doğrudan ilgili resmi başvuru / ilan ekranına gider)
  const sourceBtn = document.getElementById('modal-source-btn');
  if (sourceBtn) {
    sourceBtn.href = job.source_url || 'https://kamuilan.sbb.gov.tr/';
    const sName = escapeHtml(job.source_name || 'Resmi Portal');
    sourceBtn.innerHTML = `
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
        <polyline points="15 3 21 3 21 9"/>
        <line x1="10" y1="14" x2="21" y2="3"/>
      </svg>
      <span>${sName} Başvuru / İlan Ekranı</span>
    `;
    sourceBtn.onclick = () => {
      trackAnalytics('APPLY_CLICK', { jobId: job.id, jobTitle: job.title, category: job.category });
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

  // URL'e ilan parametresini ekle (Geri butonu ve doğrudan link paylaşımı için)
  try {
    const curUrl = new URL(window.location.href);
    curUrl.searchParams.set('ilan', job.id);
    window.history.pushState({ modalOpen: true, jobId: job.id }, '', curUrl.toString());
  } catch (e) {}

  // Analitik & Dinamik SEO
  trackAnalytics('JOB_VIEW', { jobId: job.id, jobTitle: job.title, category: job.category_name });
  updateJobSeoMetadata(job);
}

function closeJobDetailModal(skipHistory = false) {
  const modal = document.getElementById('job-detail-modal');
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
  resetJobSeoMetadata();

  if (!skipHistory) {
    try {
      const curUrl = new URL(window.location.href);
      if (curUrl.searchParams.has('ilan') || curUrl.searchParams.has('job')) {
        curUrl.searchParams.delete('ilan');
        curUrl.searchParams.delete('job');
        window.history.replaceState(null, '', curUrl.toString());
      }
    } catch (e) {}
  }
}

// Tarayıcı Geri Butonu ile Modal Kapatma (Mobil ve Masaüstü Kusursuz UX)
window.addEventListener('popstate', () => {
  const modal = document.getElementById('job-detail-modal');
  if (modal && modal.classList.contains('active')) {
    closeJobDetailModal(true);
  }
});

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
    closeNewsDetailModal();
    closeLegalModal('modal-kvkk');
    closeLegalModal('modal-legal-warning');
  }
});

// =============================================================================
// 8. ETKİLEŞİM DİNLEYİCİLERİ, ARAMA & KISAYOLLAR
// =============================================================================
function bindSearchAndFilters() {
  const sInput = document.getElementById('search-input');
  const clearBtn = document.getElementById('search-clear-btn');

  const updateClearBtnVisibility = () => {
    if (clearBtn && sInput) {
      clearBtn.style.display = sInput.value.trim().length > 0 ? 'inline-flex' : 'none';
    }
  };

  if (sInput) {
    sInput.addEventListener('input', debounce(e => {
      state.searchQuery = e.target.value.trim();
      updateClearBtnVisibility();
      applyFiltersAndPaginate(1);
      if (state.searchQuery.length >= 3) {
        trackAnalytics('SEARCH', { jobTitle: state.searchQuery });
      }
    }, 400));

    sInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        state.searchQuery = sInput.value.trim();
        updateClearBtnVisibility();
        applyFiltersAndPaginate(1);
        if (state.searchQuery.length >= 2) {
          trackAnalytics('SEARCH', { jobTitle: state.searchQuery });
        }
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      clearSearchQuery();
      if (sInput) sInput.focus();
    });
  }

  const sBtn = document.getElementById('search-btn-trigger');
  if (sBtn && sInput) {
    sBtn.addEventListener('click', () => {
      state.searchQuery = sInput.value.trim();
      updateClearBtnVisibility();
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

  // İlk açılışta temizleme butonu kontrolü
  updateClearBtnVisibility();
}

function clearSearchQuery() {
  state.searchQuery = '';
  const sInput = document.getElementById('search-input');
  if (sInput) sInput.value = '';
  const clearBtn = document.getElementById('search-clear-btn');
  if (clearBtn) clearBtn.style.display = 'none';
  applyFiltersAndPaginate(1);
}

function clearEducationFilter() {
  state.educationLevel = 'all';
  const eduSelect = document.getElementById('education-select');
  if (eduSelect) eduSelect.value = 'all';
  applyFiltersAndPaginate(1);
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
  } else if (pillType === 'memur') {
    state.activeCategory = 'memur';
  } else if (pillType === 'akademik') {
    state.activeCategory = 'akademik';
  } else if (pillType === 'belediye') {
    state.activeCategory = 'belediye';
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
  scrollToSection('ilanlar');
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

// Kategori Sekmelerindeki Sayı Rozetlerini Dinamik Hesapla
function populateCategoryTabCounts() {
  const allJobs = state.allJobs;
  if (!allJobs || allJobs.length === 0) return;

  const counts = {
    all: allJobs.length,
    open: allJobs.filter(j => j.status === 'BAŞVURUYA AÇIK').length,
    kpss_sartsiz: allJobs.filter(j => {
      const kpss = (j.kpss_requirement || '').toLocaleLowerCase('tr-TR');
      return kpss.includes('şartsız') || kpss.includes('aranmamaktadır') || kpss.includes('muaf') || kpss.includes('kura');
    }).length,
    pdf: allJobs.filter(j => j.has_pdf).length,
    canc: allJobs.filter(j => j.is_cancellation).length
  };

  // Kategori slug'larına göre sayım
  allJobs.forEach(j => {
    const slug = j.category_slug;
    if (slug) {
      counts[slug] = (counts[slug] || 0) + 1;
    }
  });

  // DOM'daki butonların .tab-badge rozetlerini güncelle
  document.querySelectorAll('.category-tab-btn').forEach(btn => {
    const cat = btn.getAttribute('data-cat');
    const badge = btn.querySelector('.tab-badge') || document.getElementById(`tab-count-${cat}`);
    if (badge && counts[cat] !== undefined) {
      badge.textContent = counts[cat].toLocaleString('tr-TR');
    }
  });
}

// Aktif Filtre Çiplerini Çiz
function renderActiveFilterChips() {
  const strip = document.getElementById('active-filter-tags-strip');
  if (!strip) return;

  const chips = [];

  // 1. Arama Çipi
  if (state.searchQuery) {
    chips.push(`
      <span class="filter-chip">
        <span class="filter-chip-label">Arama: "${escapeHtml(state.searchQuery)}"</span>
        <button type="button" class="filter-chip-remove" onclick="clearSearchQuery()" title="Aramayı Kaldır" aria-label="Aramayı Kaldır">×</button>
      </span>
    `);
  }

  // 2. Kategori Çipi
  if (state.activeCategory && state.activeCategory !== 'all') {
    const catNames = {
      memur: 'Memur Alımı',
      sozlesmeli: 'Sözleşmeli Personel',
      akademik: 'Akademik Kadro',
      bilisim: 'Bilişim & Yazılım',
      isci: 'Sürekli İşçi',
      belediye: 'Belediye & Mahalli İdareler',
      askeri: 'Askeri & Emniyet',
      saglik: 'Sağlık Personeli',
      diger: 'Diğer Kamu'
    };
    const catLabel = catNames[state.activeCategory] || state.activeCategory;
    chips.push(`
      <span class="filter-chip">
        <span class="filter-chip-label">Kategori: ${catLabel}</span>
        <button type="button" class="filter-chip-remove" onclick="filterByCategory('all')" title="Kategori Filtresini Kaldır" aria-label="Kategoriyi Kaldır">×</button>
      </span>
    `);
  }

  // 3. Öğrenim Düzeyi Çipi
  if (state.educationLevel && state.educationLevel !== 'all') {
    const eduNames = {
      lisans: 'Lisans Mezunu',
      onlisans: 'Ön Lisans',
      lise: 'Ortaöğretim / Lise',
      ilkogretim: 'İlköğretim / Ortaokul'
    };
    const eduLabel = eduNames[state.educationLevel] || state.educationLevel;
    chips.push(`
      <span class="filter-chip">
        <span class="filter-chip-label">Öğrenim: ${eduLabel}</span>
        <button type="button" class="filter-chip-remove" onclick="clearEducationFilter()" title="Öğrenim Filtresini Kaldır" aria-label="Öğrenimi Kaldır">×</button>
      </span>
    `);
  }

  // 4. Hızlı Durum Çipleri
  if (state.filterOnlyOpen) {
    chips.push(`
      <span class="filter-chip">
        <span class="filter-chip-label">🟢 Yalnızca Başvuruya Açık</span>
        <button type="button" class="filter-chip-remove" onclick="toggleQuickFilter('open')" title="Filtreyi Kaldır" aria-label="Açık Filtresini Kaldır">×</button>
      </span>
    `);
  }

  if (state.filterKpssSartsiz) {
    chips.push(`
      <span class="filter-chip">
        <span class="filter-chip-label">🎯 KPSS Şartsız</span>
        <button type="button" class="filter-chip-remove" onclick="toggleQuickFilter('kpss_sartsiz')" title="Filtreyi Kaldır" aria-label="KPSS Şartsız Kaldır">×</button>
      </span>
    `);
  }

  if (state.filterOnlyPdf) {
    chips.push(`
      <span class="filter-chip">
        <span class="filter-chip-label">📄 PDF Kılavuzlu</span>
        <button type="button" class="filter-chip-remove" onclick="toggleQuickFilter('pdf')" title="Filtreyi Kaldır" aria-label="PDF Filtresini Kaldır">×</button>
      </span>
    `);
  }

  if (state.filterOnlyCanc) {
    chips.push(`
      <span class="filter-chip">
        <span class="filter-chip-label">🚨 İptal / Düzeltme</span>
        <button type="button" class="filter-chip-remove" onclick="toggleQuickFilter('canc')" title="Filtreyi Kaldır" aria-label="İptal Filtresini Kaldır">×</button>
      </span>
    `);
  }

  if (chips.length > 0) {
    const clearAllHtml = chips.length > 1
      ? `<button type="button" class="filter-clear-all-btn" onclick="resetAllFilters()">Tümünü Temizle</button>`
      : '';
    strip.innerHTML = chips.join('') + clearAllHtml;
    strip.style.display = 'flex';
  } else {
    strip.innerHTML = '';
    strip.style.display = 'none';
  }
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
    } else {
      btn.classList.toggle('active', state.activeCategory === cat);
    }
  });

  // Hero Hızlı Hapları da Senkron Tut
  document.querySelectorAll('.quick-pill-item').forEach(btn => {
    const p = btn.getAttribute('data-pill');
    let isActive = false;
    if (p === 'all' && state.activeCategory === 'all' && !state.filterKpssSartsiz && !state.searchQuery) isActive = true;
    else if (p === 'kpss_sartsiz' && state.filterKpssSartsiz) isActive = true;
    else if (p === 'memur' && state.activeCategory === 'memur') isActive = true;
    else if (p === 'akademik' && state.activeCategory === 'akademik') isActive = true;
    else if (p === 'sozlesmeli' && state.activeCategory === 'sozlesmeli') isActive = true;
    else if (p === 'bilisim' && state.activeCategory === 'bilisim') isActive = true;
    else if (p === 'isci' && state.activeCategory === 'isci') isActive = true;
    else if (p === 'ankara' && state.searchQuery.toLowerCase() === 'ankara') isActive = true;
    btn.classList.toggle('active', isActive);
  });
}

// URL Parametrelerini Çöz ve Başlangıç Durumuna Uygula
function applyInitialUrlParams() {
  try {
    const params = new URLSearchParams(window.location.search);

    // Kategori
    const cat = params.get('kategori') || params.get('category');
    if (cat) {
      const validCats = ['all', 'memur', 'sozlesmeli', 'akademik', 'bilisim', 'isci', 'belediye', 'askeri', 'saglik', 'diger'];
      const normalizedCat = cat.toLowerCase();
      if (validCats.includes(normalizedCat)) {
        state.activeCategory = normalizedCat;
      }
    }

    // Arama
    const q = params.get('q') || params.get('ara') || params.get('search');
    if (q) {
      state.searchQuery = q.trim();
      const sInput = document.getElementById('search-input');
      if (sInput) sInput.value = q.trim();
    }

    // Öğrenim
    const edu = params.get('ogrenim') || params.get('egitim') || params.get('education');
    if (edu) {
      const validEdu = ['all', 'lisans', 'onlisans', 'lise', 'ilkogretim'];
      const normalizedEdu = edu.toLowerCase();
      if (validEdu.includes(normalizedEdu)) {
        state.educationLevel = normalizedEdu;
        const eduSelect = document.getElementById('education-select');
        if (eduSelect) eduSelect.value = normalizedEdu;
      }
    }

    // KPSS Şartsız
    const kpss = params.get('kpss');
    if (kpss && (kpss === 'sartsiz' || kpss === 'muaf' || kpss === '1')) {
      state.filterKpssSartsiz = true;
    }

    // Yalnızca Başvuruya Açık
    const statusParam = params.get('durum') || params.get('status');
    if (statusParam && (statusParam === 'acik' || statusParam === 'open' || statusParam === '1')) {
      state.filterOnlyOpen = true;
    }

    // Sıralama
    const sortParam = params.get('sirala') || params.get('sort');
    if (sortParam && ['date_desc', 'quota_desc', 'quota_asc'].includes(sortParam)) {
      state.sortBy = sortParam;
      const sortSelect = document.getElementById('sort-select');
      if (sortSelect) sortSelect.value = sortParam;
    }

    // Sayfa
    const pageParam = parseInt(params.get('sayfa') || params.get('page'), 10);
    if (!isNaN(pageParam) && pageParam > 1) {
      state.currentPage = pageParam;
    }

    updateCategoryTabsUI();
  } catch (e) {
    console.debug('URL parametreleri işlenirken istisna:', e);
  }
}

// Filtre Değişimlerini Adres Çubuğuna Senkronize Et
function syncUrlWithState() {
  try {
    const params = new URLSearchParams();
    if (state.activeCategory && state.activeCategory !== 'all') params.set('kategori', state.activeCategory);
    if (state.searchQuery) params.set('q', state.searchQuery);
    if (state.educationLevel && state.educationLevel !== 'all') params.set('ogrenim', state.educationLevel);
    if (state.filterKpssSartsiz) params.set('kpss', 'sartsiz');
    if (state.filterOnlyOpen) params.set('durum', 'acik');
    if (state.sortBy && state.sortBy !== 'date_desc') params.set('sirala', state.sortBy);
    if (state.currentPage && state.currentPage > 1) params.set('sayfa', state.currentPage);

    // Açık olan ilan varsa koru
    const curIlan = new URLSearchParams(window.location.search).get('ilan');
    if (curIlan) params.set('ilan', curIlan);

    const queryStr = params.toString();
    const newUrl = queryStr ? `${window.location.pathname}?${queryStr}` : window.location.pathname;
    window.history.replaceState(null, '', newUrl);
  } catch (e) {}
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
// 10. YASAL MODALLAR & ÇEREZ YÖNETİMİ & EDİTORYAL REHBER KÜTÜPHANESİ
// =============================================================================
const GUIDE_ARTICLES = {
  'kpss-guide': {
    badge: 'KPSS MEVZUAT REHBERİ',
    title: '2026 KPSS Puan Türleri (P3, P93, P94), Taban Puanlar ve Geçerlilik Kılavuzu',
    content: `
      <p>Kamu Personel Seçme Sınavı (KPSS), 657 Sayılı Devlet Memurları Kanunu kapsamında kamu kurumlarına memur ve sözleşmeli personel istihdamında kullanılan temel merkezi seçme sistemidir. Adayların eğitim düzeylerine göre puan türleri ve kullanım alanları temel farklılıklar göstermektedir.</p>
      
      <h3>1. Temel Puan Türleri ve Hedef Kadrolar</h3>
      <ul>
        <li><strong>KPSS P3 (Lisans Düzeyi):</strong> 4 yıllık fakülte ve yüksekokul mezunları için hesaplanır. Genel Yetenek ve Genel Kültür testlerinin eşit ağırlığıyla (%50 - %50) oluşur. Bakanlıklar, üniversiteler, belediyeler ve KİT'lerin lisans mezunu memur ve 4/B sözleşmeli personel kadrolarında kullanılır.</li>
        <li><strong>KPSS P93 (Ön Lisans Düzeyi):</strong> 2 yıllık meslek yüksekokulu mezunları için uygulanır. Sağlık teknikeri, büro personeli, zabıta, koruma ve güvenlik görevlisi gibi pozisyonlarda esas alınır.</li>
        <li><strong>KPSS P94 (Ortaöğretim / Lise Düzeyi):</strong> Lise ve dengi okul mezunları için hesaplanır. Hizmetli, şoför, teknisyen yardımcısı ve destek personeli alımlarında kullanılır.</li>
      </ul>

      <div class="guide-callout-box">
        <strong>📌 Çift Yıl / Tek Yıl Farkı:</strong> B Grubu genel memur ve sözleşmeli personel alımlarında yalnızca <em>çift yıllarda</em> (2024, 2026 vb.) yapılan KPSS puanları 2 yıl süreyle geçerlidir. Tek yıllarda yapılan KPSS oturumları (A Grubu Müfettiş/Uzman Yardımcılığı ve Öğretmenlik hariç) genel memur alımlarında kullanılamaz.
      </div>

      <h3>2. Taban Puan ve Başvuru Mekanizmaları</h3>
      <p>Kamu kurumları ilanlarında çoğunlukla <strong>60, 65 veya 70 taban puan</strong> şartı ararlar. Ancak bu taban puan yalnızca başvuru yapabilme asgari sınırıdır. Adaylar puan sırasına göre en yüksekten başlanarak kontenjanın 3, 5 veya 10 katı kadar sözlü sınava (mülakata) çağrılır ya da doğrudan KPSS puan üstünlüğüne göre asil/yedek listeler belirlenir.</p>

      <h3>3. Puanın Eşitliği Halinde Sıralama</h3>
      <p>Aynı kadroya başvuran iki adayın KPSS puanı eşit olduğunda; sırasıyla mezuniyet diploma notu yüksek olana, mezuniyet tarihi daha önce olana ve doğum tarihi daha büyük (yaşça büyük) olana öncelik tanınmaktadır.</p>
    `
  },
  'sartsiz-guide': {
    badge: 'SINAVSIZ KAMU İSTİHDAMI',
    title: 'KPSS Şartı Aranmayan Kamu Kadroları ve Sürekli İşçi Alım Mevzuatı',
    content: `
      <p>Türkiye'de kamu istihdamı yalnızca KPSS puanı ile sınırlı değildir. Mevzuatta yer alan istisnai düzenlemeler çerçevesinde, belirli meslek grupları ve statülerde sınavsız veya noter kurası ile daimi istihdam sağlanmaktadır.</p>
      
      <h3>1. İŞKUR Üzerinden Sürekli İşçi Kadroları</h3>
      <p>Kamu kurumlarının temizlik görevlisi, güvenlik görevlisi, hasta karşılama, aşçı, şoför ve bakım onarım personeli gibi kadroları <strong>4857 Sayılı İş Kanunu</strong> kapsamında "Sürekli İşçi" statüsünde istihdam edilir. Bu alımlarda KPSS şartı aranmaz; başvurular İŞKUR üzerinden alınır ve noter huzurunda yapılan dijital kura çekimi ile asil/yedek adaylar doğrudan belirlenir.</p>

      <h3>2. Üniversitelerin Akademik Kadro Alımları</h3>
      <ul>
        <li><strong>Araştırma Görevlisi & Öğretim Görevlisi:</strong> KPSS puanı yerine ALES (Akademik Personel ve Lisansüstü Eğitimi Giriş Sınavı) ve YDS / YÖKDİL yabancı dil puanları ile lisans mezuniyet notu değerlendirmeye alınır.</li>
        <li><strong>Doktor Öğretim Üyesi, Doçent & Profesör:</strong> 2547 Sayılı Yükseköğretim Kanunu uyarınca bilimsel yayınlar, atıflar ve jüri değerlendirmeleriyle doğrudan atanırlar.</li>
      </ul>

      <div class="guide-callout-box">
        <strong>💡 Kıdemli Bilişim Personeli Muafiyeti:</strong> Kamu kurumlarının Bilgi İşlem Daire Başkanlıkları bünyesinde istihdam edilen tecrübeli yazılım uzmanları, siber güvenlik uzmanları ve sistem mimarları; KPSS şartı aranmaksızın veya KPSS tabanının %70'i kabul edilerek mesleki tecrübe ve sözlü/uygulamalı mülakatla istihdam edilebilir.
      </div>
    `
  },
  'sozlesmeli-guide': {
    badge: '4/B PERSONEL MEVZUATI',
    title: '657 Sayılı Kanun 4/B Sözleşmeli Personel Hakları, 3+1 Kuralı ve Kadroya Geçiş',
    content: `
      <p>657 Sayılı Devlet Memurları Kanunu'nun 4/B maddesi kapsamında istihdam edilen sözleşmeli personel, son yasal düzenlemelerle birlikte kadrolu memurlara çok yakın özlük haklarına kavuşmuştur.</p>
      
      <h3>1. 3+1 Modeli ve Memur Kadrosuna Geçiş</h3>
      <p>Milli Eğitim Bakanlığı, Sağlık Bakanlığı, Diyanet İşleri Başkanlığı ve diğer genel bütçeli kurumlarda 4/B statüsünde göreve başlayan personel; <strong>3 yıl fiilen sözleşmeli olarak görev yaptıktan sonra</strong> talebi halinde bulunduğu yerde memur kadrosuna (4/A) atanır. Kadroya geçtikten sonra 1 yıl daha görev yapan personel genel yer değiştirme (tayin) hakkı elde eder.</p>

      <h3>2. İzin, Rapor ve Sosyal Haklar</h3>
      <ul>
        <li><strong>Yıllık İzin:</strong> 1 yıldan 10 yıla kadar hizmeti olanlar için 20 gün, 10 yıldan fazla olanlar için 30 gündür. Bir önceki yıldan devreden izin hakları kullanılabilir.</li>
        <li><strong>Mazeret ve Doğum İzni:</strong> Kadın personele doğumdan önce 8 ve doğumdan sonra 8 hafta olmak üzere toplam 16 hafta analık izni verilir. Erkek personele eşinin doğum yapması halinde 10 gün babalık izni tanınır.</li>
        <li><strong>Eş Durumu ve Sağlık Tayini:</strong> Sözleşmeli personel, her iki eşin de kamu personeli olması ve belirli hizmet sürelerinin tamamlanması halinde kurum içi eş durumu tayininden faydalanabilir.</li>
      </ul>

      <div class="guide-callout-box guide-callout-warning">
        <strong>⚠️ Sözleşme Feshi ve Cezai Bekleme Süresi:</strong> 4/B sözleşmeli personel, sözleşmesini usulsüz biçimde tek taraflı feshederse; fesih tarihinden itibaren 1 yıl geçmedikçe hiçbir kamu kurumunun sözleşmeli personel pozisyonuna yeniden başvuramaz.
      </div>
    `
  },
  'kariyerkapisi-guide': {
    badge: 'BAŞVURU REHBERİ',
    title: 'Kariyer Kapısı (CBİKO) Üzerinden Kamu İlanlarına Başvuru Rehberi',
    content: `
      <p>Cumhurbaşkanlığı İnsan Kaynakları Ofisi (CBİKO) tarafından hayata geçirilen <strong>Kariyer Kapısı Kamu İşe Alım Portalı</strong> (isealimkariyerkapisi.cbiko.gov.tr), Türkiye'deki tüm bakanlık, başkanlık ve kamu idarelerinin resmi alım kapısıdır.</p>
      
      <h3>1. e-Devlet ile Giriş ve Profil Güncelleme</h3>
      <p>Adaylar e-Devlet şifreleri ile sisteme giriş yaptıklarında YÖKSİS (üniversite mezuniyeti), MEBBİS (lise mezuniyeti), ÖSYM (KPSS puanları), Nüfus Müdürlüğü (ikametgah ve kimlik) ve Askerlik Durum belgeleri MERNİS üzerinden otomatik olarak sisteme çekilir.</p>

      <h3>2. Belge Yükleme Aşamasında Kritik Kurallar</h3>
      <ul>
        <li>Kurumların talep ettiği adli sicil kaydı, askerlik durum belgesi ve yerleşim yeri (ikametgah) belgeleri barkodlu veya karekodlu e-Devlet çıktısı (PDF) formatında yüklenmelidir.</li>
        <li>Sertifika ve ehliyet gibi belgeler ilanda belirtilen tarihten önce alınmış olmalıdır; ilan tarihinden sonra alınan sertifikalar sistem tarafından elenebilmektedir.</li>
      </ul>

      <div class="guide-callout-box">
        <strong>✅ Başvuru Onayı:</strong> Formu doldurup belgeleri yükledikten sonra mutlaka en alttaki <strong>"Başvuruyu Tamamla"</strong> butonuna basılmalı ve sistemin ürettiği <em>"Başvurunuz Başarıyla Kaydedilmiştir"</em> ibaresi ile başvuru takip numarası teyit edilmelidir.
      </div>
    `
  },
  'guvenlik-guide': {
    badge: 'ARŞİV VE GÜVENLİK',
    title: '7315 Sayılı Güvenlik Soruşturması ve Arşiv Araştırması Kapsamı',
    content: `
      <p>Kamuda herhangi bir kadroya atanmaya hak kazanan tüm adaylar hakkında göreve başlamadan önce 7315 Sayılı Kanun gereğince Arşiv Araştırması ve nitelikli kadrolar için Güvenlik Soruşturması yürütülür.</p>
      
      <h3>1. Arşiv Araştırmasında Neler İncelenir?</h3>
      <p>Kişinin adli sicil kaydı, kesinleşmiş mahkeme kararları, hakkında devam eden kamu davaları veya yakalama kararları ile kamu görevinden çıkarma cezası bulunup bulunmadığı adli kayıtlar üzerinden incelenir.</p>

      <h3>2. İnceleme Süresi ve Değerlendirme Komisyonu</h3>
      <p>Emniyet Genel Müdürlüğü veya Milli İstihbarat Teşkilatı tarafından yürütülen inceleme süreci genellikle <strong>30 ila 60 gün</strong> arasında tamamlanır. Elde edilen veriler kurum bünyesindeki Değerlendirme Komisyonu tarafından gizlilikle değerlendirilir. Olumsuz sonuçlanan kararlara karşı 60 gün içinde İdare Mahkemesi'nde iptal davası açma hakkı mevcuttur.</p>
    `
  },
  'maas-guide': {
    badge: 'ÖZLÜK HAKLARI & MAAŞ',
    title: 'Kamu Personeli Maaş Katsayıları, Taban Aylık ve Yan Ödeme Sistemi',
    content: `
      <p>Devlet memurlarının aylıkları 657 Sayılı Kanun'un mali hükümleri ve Hazine ve Maliye Bakanlığı tarafından her yıl Ocak ve Temmuz aylarında yayımlanan Genelgeler doğrultusunda hesaplanır.</p>
      
      <h3>1. Memur Maaşının Temel Bileşenleri</h3>
      <ul>
        <li><strong>Aylık Gösterge Tutarı:</strong> Memurun derece ve kademesine karşılık gelen gösterge rakamının aylık katsayısı ile çarpımıdır.</li>
        <li><strong>Ek Gösterge:</strong> Unvana ve hizmet sınıfına göre belirlenen (örneğin 3600 ek gösterge) ve hem çalışırken hem de emeklilik ikramiyesi ile maaşında en belirleyici olan unsurdur.</li>
        <li><strong>Taban Aylığı:</strong> Tüm memurlara eşit uygulanan taban aylık göstergesinin taban aylık katsayısı ile çarpımıdır.</li>
        <li><strong>Aile ve Çocuk Yardımı:</strong> Çalışmayan eş ve bakmakla yükümlü olunan çocuklar için her ay vergiden muaf olarak ödenir.</li>
      </ul>

      <div class="guide-callout-box">
        <strong>📊 657 Sayılı Kanun Güvencesi:</strong> Memur maaşları her ayın 15'inde peşin olarak ödenir. Emekli Sandığı (4/C) prim kesintileri kurum tarafından doğrudan SGK'ya aktarılır.
      </div>
    `
  }
};

function openGuideArticle(guideKey) {
  const guide = GUIDE_ARTICLES[guideKey];
  if (!guide) return;

  const badgeEl = document.getElementById('guide-modal-badge');
  const titleEl = document.getElementById('guide-modal-title');
  const contentEl = document.getElementById('guide-modal-content');

  if (badgeEl) badgeEl.textContent = guide.badge;
  if (titleEl) titleEl.textContent = guide.title;
  if (contentEl) contentEl.innerHTML = guide.content;

  openLegalModal('modal-guide-detail');
}

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
      job_id: payload.jobId ? parseInt(payload.jobId, 10) : null,
      job_title: payload.jobTitle ? String(payload.jobTitle).slice(0, 240) : null,
      category: payload.category || null,
      referrer: ref,
      user_agent: navigator.userAgent ? navigator.userAgent.slice(0, 240) : null,
      created_at: new Date().toISOString()
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

// =============================================================================
// 12. MOBİL DOCK VE BAŞA DÖN (SCROLL-TO-TOP)
// =============================================================================
function setDockActive(index) {
  document.querySelectorAll('.mobile-dock-btn').forEach((btn, i) => {
    btn.classList.toggle('active', i === index);
  });
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

window.addEventListener('scroll', () => {
  const scrollBtn = document.getElementById('scroll-to-top-btn');
  if (scrollBtn) {
    if (window.scrollY > 400) {
      scrollBtn.classList.add('visible');
    } else {
      scrollBtn.classList.remove('visible');
    }
  }
}, { passive: true });

// =============================================================================
// 13. RESMİ KAMU HABERLERİ VE DEZENFORMASYON DOĞRULAMA AKIŞI
// =============================================================================
async function fetchNewsData() {
  try {
    const res = await fetch(CONFIG.NEWS_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.allNews = data.news || [];
    renderNewsFeed();
  } catch (err) {
    console.debug('Haber verileri yüklenemedi:', err);
    const container = document.getElementById('news-grid-container');
    if (container) {
      container.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:30px 20px;color:var(--text-secondary);">
          Resmi kamu haber akışı şu anda güncelleniyor. Lütfen daha sonra tekrar deneyiniz.
        </div>
      `;
    }
  }
}

function renderNewsFeed() {
  const container = document.getElementById('news-grid-container');
  if (!container) return;

  const filteredNews = state.allNews.filter(n => {
    if (state.activeNewsCategory === 'all') return true;
    return n.category === state.activeNewsCategory;
  });

  if (filteredNews.length === 0) {
    container.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;padding:40px 20px;color:var(--text-secondary);">
        Bu kategoride henüz yayımlanmış resmi bir duyuru bulunmamaktadır.
      </div>
    `;
    return;
  }

  container.innerHTML = filteredNews.map(news => {
    let badgeClass = 'resmi';
    let badgeLabel = '🏛️ Resmi Duyuru';

    if (news.category === 'DEZENFORMASYON') {
      badgeClass = 'dezenformasyon';
      badgeLabel = '🛡️ DMM Doğrulama';
    } else if (news.category === 'OZLUK_MAAS') {
      badgeClass = 'ozluk';
      badgeLabel = '📊 Özlük & Maaş';
    } else if (news.category === 'MEVZUAT') {
      badgeClass = 'mevzuat';
      badgeLabel = '📜 Mevzuat';
    }

    const safeTitle = escapeHtml(news.title);
    const safeInst = escapeHtml(news.institution || 'T.C. Kamu Kurumu');
    const safeSummary = escapeHtml(news.summary || '');
    const dateFormatted = escapeHtml(news.publish_date_formatted || 'Güncel');

    return `
      <article class="news-card-item tilt-surface" onclick="openNewsDetailModal(${news.id})" role="button" tabindex="0" aria-label="${safeTitle}">
        <div class="news-card-top">
          <span class="news-badge ${badgeClass}">${badgeLabel}</span>
          <span class="news-verified-pill">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            Teyitli
          </span>
        </div>

        <div>
          <div class="news-card-inst">${safeInst}</div>
          <h3 class="news-card-title">${safeTitle}</h3>
          <p class="news-card-summary">${safeSummary}</p>
        </div>

        <div class="news-card-bottom">
          <span class="news-date">${dateFormatted}</span>
          <span class="news-read-btn">
            Haberi Oku
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </span>
        </div>
      </article>
    `;
  }).join('');

  rebindTiltSurfaces();
}

function filterNewsByCategory(catSlug) {
  state.activeNewsCategory = catSlug;
  document.querySelectorAll('#news-filter-tabs .news-filter-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-newscat') === catSlug);
  });
  renderNewsFeed();
}

function openNewsDetailModal(newsId) {
  const news = state.allNews.find(n => n.id === newsId);
  if (!news) return;

  const modal = document.getElementById('news-detail-modal');
  if (!modal) return;

  document.getElementById('modal-news-title').textContent = news.title;
  document.getElementById('modal-news-inst').textContent = news.institution || 'T.C. Kamu Kurumu';
  document.getElementById('modal-news-date').textContent = `Resmi Yayın Tarihi: ${news.publish_date_formatted || 'Güncel'}`;
  document.getElementById('modal-news-summary').textContent = news.summary || '';
  document.getElementById('modal-news-content').textContent = news.content || news.summary || '';

  const badgeEl = document.getElementById('modal-news-badge');
  if (badgeEl) {
    let bClass = 'news-badge resmi';
    let bText = '🏛️ T.C. Resmi Duyuru';
    if (news.category === 'DEZENFORMASYON') {
      bClass = 'news-badge dezenformasyon';
      bText = '🛡️ DMM Doğrulama Bülteni';
    } else if (news.category === 'OZLUK_MAAS') {
      bClass = 'news-badge ozluk';
      bText = '📊 Özlük & Mali Haklar';
    } else if (news.category === 'MEVZUAT') {
      bClass = 'news-badge mevzuat';
      bText = '📜 Mevzuat Değişikliği';
    }
    badgeEl.className = bClass;
    badgeEl.textContent = bText;
  }

  const sourceBtn = document.getElementById('modal-news-source-btn');
  if (sourceBtn) {
    sourceBtn.href = news.source_url || 'https://www.iletisim.gov.tr';
  }

  const shareBtn = document.getElementById('modal-news-share-btn');
  if (shareBtn) {
    shareBtn.onclick = () => {
      const shareUrl = news.source_url || 'https://kamupersonelrehberiniz.me/#haberler';
      const shareText = `📢 [T.C. Resmi Kamu Haberi]:\n${news.title}\n\nDetaylar: ${shareUrl}`;
      if (navigator.share) {
        navigator.share({ title: news.title, text: shareText, url: shareUrl }).catch(() => {});
      } else {
        navigator.clipboard.writeText(shareText).then(() => alert('✅ Resmi haber bağlantısı kopyalandı!'));
      }
    };
  }

  modal.classList.add('active');
  document.body.style.overflow = 'hidden';
  trackAnalytics('NEWS_VIEW', { jobId: news.id, jobTitle: news.title, category: news.category });
}

function closeNewsDetailModal() {
  const modal = document.getElementById('news-detail-modal');
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Haber Modalı dışına tıklandığında veya ESC basıldığında kapat
document.addEventListener('click', e => {
  const newsModal = document.getElementById('news-detail-modal');
  if (newsModal && newsModal.classList.contains('active') && e.target === newsModal) {
    closeNewsDetailModal();
  }
});


// =============================================================================
// YENİ İLAN BİLDİRİM YÖNETİCİSİ (PUSH & LOCAL NOTIFICATIONS)
// =============================================================================
const NOTIFY_STORAGE_KEY = 'kpr_notifications_enabled';
const LAST_NOTIFIED_JOB_KEY = 'kpr_last_notified_job_id';

function initPushNotifications() {
  // Service Worker Kaydı
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(err => {
      console.debug('Service Worker register not completed:', err);
    });
  }

  updateNotifyBtnState();

  const notifyBtn = document.getElementById('nav-notify-toggle-btn');
  if (notifyBtn) {
    notifyBtn.addEventListener('click', toggleNotificationPreference);
  }

  // Kullanıcı daha önce onay vermişse yeni ilanları kontrol et
  if (isNotificationEnabled() && Notification.permission === 'granted') {
    checkAndNotifyNewJobs();
  } else if (!localStorage.getItem('kpr_notify_prompt_dismissed') && Notification.permission !== 'denied') {
    // İlk ziyarette 8 saniye sonra zarif bir davet kartı göster
    setTimeout(showNotificationBanner, 8000);
  }
}

function isNotificationEnabled() {
  return localStorage.getItem(NOTIFY_STORAGE_KEY) === 'true';
}

function updateNotifyBtnState() {
  const btn = document.getElementById('nav-notify-toggle-btn');
  const label = document.getElementById('nav-notify-label');
  if (!btn) return;

  if (isNotificationEnabled() && Notification.permission === 'granted') {
    btn.classList.add('active');
    btn.innerHTML = `
      <span class="notify-badge-dot"></span>
      <span>Bildirimler Açık</span>
    `;
    btn.title = "Yeni ilan bildirimleri açık (Kapatmak için tıklayın)";
  } else {
    btn.classList.remove('active');
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
        <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
      </svg>
      <span>Bildirimleri Aç</span>
    `;
    btn.title = "Yeni yayımlanan resmi ilanlardan anında haberdar olun";
  }
}

async function toggleNotificationPreference() {
  if (!('Notification' in window)) {
    alert('Tarayıcınız masaüstü / mobil web bildirimlerini desteklememektedir.');
    return;
  }

  if (isNotificationEnabled()) {
    // Kapat
    localStorage.setItem(NOTIFY_STORAGE_KEY, 'false');
    updateNotifyBtnState();
    showToastNotification('🔕 İlan bildirimleri kapatıldı.');
  } else {
    // Açma isteği
    const perm = await Notification.requestPermission();
    if (perm === 'granted') {
      localStorage.setItem(NOTIFY_STORAGE_KEY, 'true');
      updateNotifyBtnState();
      
      // Hoş geldin bildirimi gönder
      sendNativeNotification(
        '🔔 Bildirimler Başarıyla Açıldı!',
        'Kamu Personel Rehberi teyitli kamu ilanlarını artık anında size iletecektir.',
        'https://kamupersonelrehberiniz.me'
      );
      showToastNotification('🔔 Bildirimler başarıyla açıldı!');
      hideNotificationBanner();
    } else {
      alert('Bildirim izni verilmedi. Tarayıcı ayarlarından bildirimlere izin verebilirsiniz.');
    }
  }
}

function showNotificationBanner() {
  if (document.getElementById('notify-floating-card') || isNotificationEnabled()) return;

  const banner = document.createElement('div');
  banner.id = 'notify-floating-card';
  banner.className = 'notify-floating-banner apple-glass';
  banner.innerHTML = `
    <div class="notify-floating-header">
      <div class="notify-floating-title">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#10B981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        <span>Yeni İlanları Kaçırmayın</span>
      </div>
      <button class="notify-floating-close" onclick="dismissNotificationBanner()" aria-label="Kapat">✕</button>
    </div>
    <p class="notify-floating-desc">
      Resmi Gazete ve Kamu İlan Portalı'ndan yeni bir kamu personeli veya memur alımı yayımlandığında anında teyitli bildirim alın.
    </p>
    <div class="notify-floating-actions">
      <button class="btn-notify-allow" onclick="allowNotificationFromBanner()">Bildirimleri Aç</button>
      <button class="btn-notify-dismiss" onclick="dismissNotificationBanner()">Daha Sonra</button>
    </div>
  `;

  document.body.appendChild(banner);
}

function hideNotificationBanner() {
  const banner = document.getElementById('notify-floating-card');
  if (banner) banner.remove();
}

function dismissNotificationBanner() {
  localStorage.setItem('kpr_notify_prompt_dismissed', 'true');
  hideNotificationBanner();
}

async function allowNotificationFromBanner() {
  hideNotificationBanner();
  await toggleNotificationPreference();
}

function checkAndNotifyNewJobs() {
  if (!state.allJobs || state.allJobs.length === 0) return;

  // En son ilanı bul
  const latestJob = state.allJobs[0];
  if (!latestJob || !latestJob.id) return;

  const lastNotifiedId = parseInt(localStorage.getItem(LAST_NOTIFIED_JOB_KEY) || '0', 10);

  // İlk açılış ise sadece son ID'yi kaydet, hemen spam yapma
  if (lastNotifiedId === 0) {
    localStorage.setItem(LAST_NOTIFIED_JOB_KEY, latestJob.id.toString());
    return;
  }

  // Yeni ilan gelmişse
  if (latestJob.id > lastNotifiedId) {
    const qStr = latestJob.quota_display || `${latestJob.total_positions || 1} Kişi`;
    sendNativeNotification(
      `📢 Yeni İlan: ${latestJob.institution}`,
      `${latestJob.title} (${qStr}) yayımlandı. Detaylar ve resmi kılavuz için tıklayın.`,
      `https://kamupersonelrehberiniz.me/?ilan=${latestJob.id}`
    );
    localStorage.setItem(LAST_NOTIFIED_JOB_KEY, latestJob.id.toString());
  }
}

function sendNativeNotification(title, body, url) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return;

  try {
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then(reg => {
        reg.showNotification(title, {
          body: body,
          icon: '/favicon.ico',
          badge: '/favicon.ico',
          vibrate: [100, 50, 100],
          data: { url: url }
        });
      });
    } else {
      const n = new Notification(title, {
        body: body,
        icon: '/favicon.ico'
      });
      n.onclick = () => {
        window.focus();
        window.location.href = url;
      };
    }
  } catch (e) {
    console.debug('Notification trigger error:', e);
  }
}

function showToastNotification(msg) {
  let toast = document.getElementById('kpr-site-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'kpr-site-toast';
    toast.style.cssText = `
      position: fixed;
      top: 24px;
      left: 50%;
      transform: translateX(-50%);
      background: var(--bg-primary);
      border: 1px solid var(--glass-border);
      color: var(--text-primary);
      padding: 10px 20px;
      border-radius: 999px;
      font-size: 0.875rem;
      font-weight: 600;
      box-shadow: 0 10px 30px rgba(0,0,0,0.25);
      z-index: 9999;
      pointer-events: none;
      transition: all 0.3s ease;
    `;
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  setTimeout(() => {
    toast.style.opacity = '0';
  }, 3500);
}



