/**
 * KAMU PERSONEL REHBERİ - WEB PORTAL MOTORU
 * Kurumsal, Minimalist ve Yüksek Performanslı İstemci Mantığı
 */

// =============================================================================
// SİSTEM KONFİGÜRASYONU & TOGGLE'LAR
// =============================================================================
const CONFIG = {
  // Canlı Destek ve Danışmanlık Altyapısı:
  // Altyapı tamamen hazırlandı. Kullanıcı talebi doğrultusunda şimdilik yayına
  // alınmamıştır (false). Canlıya almak için tek yapmanız gereken true yapmaktır.
  ENABLE_LIVE_SUPPORT: false,

  // Reklam & Monetization Alanı:
  // İlk hafta boyunca site %100 reklamsız ve kurumsal kalacaktır.
  // Gelecek hafta AdSense veya özel sponsorluk entegre edildiğinde true yapılacaktır.
  ENABLE_ADS: false,

  HERO_AUTO_SLIDE_INTERVAL: 6500, // milisaniye
  DATA_URL: 'data/jobs.json',
};

// =============================================================================
// UYGULAMA DURUM YÖNETİMİ (STATE)
// =============================================================================
const state = {
  jobs: [],
  meta: {},
  featuredJobs: [],
  activeCategory: 'all',
  searchQuery: '',
  filterOnlyOpen: false,
  filterOnlyCanc: false,
  sortBy: 'date_desc',
  currentHeroIndex: 0,
  heroTimer: null,
  collapsedGroups: new Set(),
};

// =============================================================================
// DOM YÜKLENDİĞİNDE BAŞLAT
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
  initApp();
  initCookieConsent();
  initLiveSupport();
});

async function initApp() {
  try {
    const res = await fetch(CONFIG.DATA_URL);
    if (!res.ok) throw new Error(`Veri yüklenemedi: HTTP ${res.status}`);
    const data = await res.json();

    state.jobs = data.jobs || [];
    state.meta = data.meta || {};
    state.featuredJobs = data.meta?.featured_jobs || state.jobs.slice(0, 5);

    // Meta ve İstatistikleri Güncelle
    updatePortalStats();

    // Hero Showcase Başlat
    initHeroShowcase();

    // Sol Sütun: Kategorileri Doldur
    renderCategoryMenu();

    // Sağ Sütun: İlanları Listele
    renderJobsFeed();

    // Arama ve Sıralama Olaylarını Bağla
    bindSearchAndFilters();
  } catch (err) {
    console.error('Veri yükleme hatası:', err);
    const feed = document.getElementById('jobs-feed');
    if (feed) {
      feed.innerHTML = `
        <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;padding:24px;text-align:center;color:#991B1B;">
          <h3 style="font-weight:700;margin-bottom:8px;">İlan Verileri Yüklenemedi</h3>
          <p style="font-size:0.875rem;">Lütfen internet bağlantınızı kontrol edip sayfayı yenileyiniz.</p>
        </div>
      `;
    }
  }
}

// =============================================================================
// PORTAL İSTATİSTİKLERİ VE SAYACLAR
// =============================================================================
function updatePortalStats() {
  const visitorsEl = document.getElementById('stat-active-visitors');
  if (visitorsEl && state.meta.active_visitors) {
    visitorsEl.textContent = state.meta.active_visitors.toLocaleString('tr-TR');
  }

  const totalJobsEl = document.getElementById('stat-total-jobs');
  if (totalJobsEl) {
    totalJobsEl.textContent = state.jobs.length.toLocaleString('tr-TR');
  }

  const listCountEl = document.getElementById('active-list-count');
  if (listCountEl) {
    listCountEl.textContent = state.jobs.length;
  }
}

// =============================================================================
// HERO SHOWCASE SLIDER (ACİL & YÜKSEK KONTENJANLI MANŞET İLANLAR)
// =============================================================================
function initHeroShowcase() {
  const track = document.getElementById('hero-slider-track');
  const dotsContainer = document.getElementById('hero-dots');
  if (!track || !state.featuredJobs.length) return;

  track.innerHTML = '';
  if (dotsContainer) dotsContainer.innerHTML = '';

  state.featuredJobs.forEach((job, idx) => {
    // Slayt Kartı
    const slide = document.createElement('div');
    slide.className = 'hero-slide';

    const isUrgent = job.total_positions >= 50;
    const badgeText = isUrgent ? '🔥 YÜKSEK KONTENJAN' : '⚡ RESMİ ALIM';

    slide.innerHTML = `
      <div class="hero-showcase-card">
        <div class="hero-card-left">
          <div class="hero-badges-row">
            <span class="hero-flag-badge">🇹🇷 ${badgeText}</span>
            <span class="hero-quota-badge">👥 ${job.total_positions} Personel Alımı</span>
            <span style="color:#94A3B8;font-size:0.75rem;font-weight:600;">🗓 ${job.date_interval || job.end_date_str}</span>
          </div>
          <div class="hero-card-inst">${escapeHtml(job.institution)}</div>
          <h2 class="hero-card-title">${escapeHtml(job.title)}</h2>
          <div class="hero-details-row">
            <span class="hero-detail-item">🎓 ${escapeHtml(job.education_level)}</span>
            <span class="hero-detail-item">🎯 ${escapeHtml(job.kpss_requirement)}</span>
            <span class="hero-detail-item">📍 ${escapeHtml(job.city)}</span>
          </div>
        </div>
        <div class="hero-card-right">
          <button class="hero-cta-btn" onclick="openJobDetailModal(${job.id})">
            İlanı ve Şartları İncele →
          </button>
          <a href="${job.official_doc_url || job.source_url}" target="_blank" rel="noopener noreferrer" class="hero-secondary-btn">
            📄 Resmi Kılavuz (PDF)
          </a>
        </div>
      </div>
    `;
    track.appendChild(slide);

    // Gösterge Noktası
    if (dotsContainer) {
      const dot = document.createElement('div');
      dot.className = `hero-dot ${idx === 0 ? 'active' : ''}`;
      dot.addEventListener('click', () => goToSlide(idx));
      dotsContainer.appendChild(dot);
    }
  });

  // Buton Olayları
  const prevBtn = document.getElementById('hero-prev-btn');
  const nextBtn = document.getElementById('hero-next-btn');

  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      stopHeroAutoSlide();
      state.currentHeroIndex = (state.currentHeroIndex - 1 + state.featuredJobs.length) % state.featuredJobs.length;
      updateHeroSlidePosition();
      startHeroAutoSlide();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      stopHeroAutoSlide();
      state.currentHeroIndex = (state.currentHeroIndex + 1) % state.featuredJobs.length;
      updateHeroSlidePosition();
      startHeroAutoSlide();
    });
  }

  startHeroAutoSlide();
}

function goToSlide(idx) {
  stopHeroAutoSlide();
  state.currentHeroIndex = idx;
  updateHeroSlidePosition();
  startHeroAutoSlide();
}

function updateHeroSlidePosition() {
  const track = document.getElementById('hero-slider-track');
  if (track) {
    track.style.transform = `translateX(-${state.currentHeroIndex * 100}%)`;
  }
  const dots = document.querySelectorAll('.hero-dot');
  dots.forEach((dot, idx) => {
    dot.classList.toggle('active', idx === state.currentHeroIndex);
  });
}

function startHeroAutoSlide() {
  stopHeroAutoSlide();
  state.heroTimer = setInterval(() => {
    state.currentHeroIndex = (state.currentHeroIndex + 1) % state.featuredJobs.length;
    updateHeroSlidePosition();
  }, CONFIG.HERO_AUTO_SLIDE_INTERVAL);
}

function stopHeroAutoSlide() {
  if (state.heroTimer) clearInterval(state.heroTimer);
}

// =============================================================================
// SOL SÜTUN: KATEGORİ MENÜSÜ (25% WIDTH SIDEBAR)
// =============================================================================
function renderCategoryMenu() {
  const menu = document.getElementById('category-menu-list');
  if (!menu) return;

  const categories = state.meta.categories || [];
  const totalCount = state.jobs.length;

  let html = `
    <li class="category-menu-item">
      <button class="category-btn ${state.activeCategory === 'all' ? 'active' : ''}" onclick="filterByCategory('all')">
        <span class="category-btn-title">
          <span>🌐</span>
          <span>Tüm İlanlar</span>
        </span>
        <span class="category-counter">${totalCount}</span>
      </button>
    </li>
  `;

  categories.forEach(cat => {
    const slug = getCategorySlug(cat.name);
    const icon = getCategoryIcon(cat.name);
    const isActive = state.activeCategory === slug;

    html += `
      <li class="category-menu-item">
        <button class="category-btn ${isActive ? 'active' : ''}" onclick="filterByCategory('${slug}')">
          <span class="category-btn-title">
            <span>${icon}</span>
            <span>${escapeHtml(cat.name)}</span>
          </span>
          <span class="category-counter">${cat.count}</span>
        </button>
      </li>
    `;
  });

  menu.innerHTML = html;
}

function filterByCategory(slug) {
  state.activeCategory = slug;
  renderCategoryMenu();
  renderJobsFeed();
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
// SAĞ SÜTUN: KRONOLOJİK İLAN AKIŞI (75% WIDTH CONTENT)
// SBB Kamu İlan gibi tarihe göre gruplanmış modern kart listesi
// =============================================================================
function renderJobsFeed() {
  const feed = document.getElementById('jobs-feed');
  const countEl = document.getElementById('active-list-count');
  if (!feed) return;

  // 1. Filtrele
  let filtered = state.jobs.filter(job => {
    // Kategori Filtresi
    if (state.activeCategory !== 'all' && job.category_slug !== state.activeCategory) {
      return false;
    }

    // Arama Sorgusu
    if (state.searchQuery) {
      const q = state.searchQuery.toLocaleLowerCase('tr-TR');
      const text = `${job.institution} ${job.title} ${job.position} ${job.city} ${job.kpss_requirement}`.toLocaleLowerCase('tr-TR');
      if (!text.includes(q)) return false;
    }

    // Durum Filtreleri
    if (state.filterOnlyOpen && job.status !== 'BAŞVURUYA AÇIK') return false;
    if (state.filterOnlyCanc && !job.is_cancellation) return false;

    return true;
  });

  // 2. Sırala
  if (state.sortBy === 'quota_desc') {
    filtered.sort((a, b) => (b.total_positions || 0) - (a.total_positions || 0));
  } else if (state.sortBy === 'quota_asc') {
    filtered.sort((a, b) => (a.total_positions || 0) - (b.total_positions || 0));
  } else {
    // Varsayılan: Tarihe göre azalan (En yeni tarih üstte)
    filtered.sort((a, b) => (b.sort_key || 0) - (a.sort_key || 0));
  }

  if (countEl) countEl.textContent = filtered.length;

  if (filtered.length === 0) {
    feed.innerHTML = `
      <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:8px;padding:48px 24px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
        <div style="font-size:2.5rem;margin-bottom:12px;">🔍</div>
        <h3 style="font-size:1.1rem;font-weight:700;color:#0F172A;margin-bottom:6px;">Aradığınız Kriterlere Uygun İlan Bulunamadı</h3>
        <p style="font-size:0.875rem;color:#64748B;">Lütfen arama teriminizi değiştiriniz veya filtreleri temizleyiniz.</p>
        <button onclick="resetFilters()" style="margin-top:16px;background:#2563EB;color:#FFF;padding:8px 18px;border-radius:6px;font-size:0.8125rem;font-weight:600;">Filtreleri Sıfırla</button>
      </div>
    `;
    return;
  }

  // 3. Tarihe Göre Grupla (SBB Kamu İlan gibi "9 Ekim", "8 Ekim", "28 Eylül" grupları)
  const groupsMap = new Map();
  filtered.forEach(job => {
    const groupName = job.pub_date_group || 'Güncel İlanlar';
    if (!groupsMap.has(groupName)) {
      groupsMap.set(groupName, []);
    }
    groupsMap.get(groupName).push(job);
  });

  let html = '';

  groupsMap.forEach((jobsInGroup, groupName) => {
    const isCollapsed = state.collapsedGroups.has(groupName);

    html += `
      <section class="date-group-section" id="group-${slugify(groupName)}">
        <!-- Tarih Grubu Başlığı -->
        <div class="date-group-header">
          <div class="date-group-title-wrap">
            <span class="date-indicator-badge">
              <span>📅</span>
              <span>${escapeHtml(groupName)}</span>
            </span>
            <span class="date-group-count">(${jobsInGroup.length} İlan)</span>
          </div>
          <button class="date-group-collapse-toggle" onclick="toggleDateGroup('${escapeHtml(groupName)}')">
            <span>${isCollapsed ? 'Genişlet ▼' : 'Daralt ▲'}</span>
          </button>
        </div>

        <!-- İlan Satırları -->
        <div class="jobs-list-container" style="${isCollapsed ? 'display:none;' : ''}">
          ${jobsInGroup.map(job => renderJobRow(job)).join('')}
        </div>
      </section>
    `;
  });

  feed.innerHTML = html;
}

function renderJobRow(job) {
  const isCanc = job.is_cancellation;
  const cancClass = isCanc ? 'cancellation' : '';

  let badgeMarkup = '';
  if (isCanc) {
    badgeMarkup = `<span class="badge-tag cancellation">🚨 İPTAL / DÜZELTME</span>`;
  } else if (job.category_slug === 'akademik') {
    badgeMarkup = `<span class="badge-tag academic">🎓 Akademik</span>`;
  } else if (job.category_slug === 'bilisim') {
    badgeMarkup = `<span class="badge-tag tech">💻 Bilişim</span>`;
  } else if (job.category_slug === 'belediye') {
    badgeMarkup = `<span class="badge-tag municipality">🏛 Belediye</span>`;
  }

  return `
    <article class="job-row-card ${cancClass}" onclick="openJobDetailModal(${job.id})">
      <!-- Sol: Kurum & Başlık -->
      <div class="job-row-main">
        <div class="job-row-inst-row">
          <h3 class="job-row-institution">${escapeHtml(job.institution)}</h3>
          ${badgeMarkup}
        </div>
        <div class="job-row-title">${escapeHtml(job.title)}</div>
      </div>

      <!-- Orta: Kontenjan & Tarih Aralığı -->
      <div class="job-row-meta">
        <span class="quota-pill">
          👥 ${job.total_positions} Kişi
        </span>
        <span class="dates-highlight-pill active">
          🗓 ${escapeHtml(job.date_interval || job.end_date_str)}
        </span>
      </div>

      <!-- Sağ: Eylem Butonu -->
      <div class="job-row-actions" onclick="event.stopPropagation()">
        <button class="btn-view-details" onclick="openJobDetailModal(${job.id})">
          İlanı İncele & PDF →
        </button>
      </div>
    </article>
  `;
}

function toggleDateGroup(groupName) {
  if (state.collapsedGroups.has(groupName)) {
    state.collapsedGroups.delete(groupName);
  } else {
    state.collapsedGroups.add(groupName);
  }
  renderJobsFeed();
}

function resetFilters() {
  state.searchQuery = '';
  state.activeCategory = 'all';
  state.filterOnlyOpen = false;
  state.filterOnlyCanc = false;
  state.sortBy = 'date_desc';

  const sInput = document.getElementById('search-input');
  if (sInput) sInput.value = '';

  const hInput = document.getElementById('header-search-input');
  if (hInput) hInput.value = '';

  const chkOpen = document.getElementById('chk-only-open');
  if (chkOpen) chkOpen.checked = false;

  const chkCanc = document.getElementById('chk-only-canc');
  if (chkCanc) chkCanc.checked = false;

  renderCategoryMenu();
  renderJobsFeed();
}

// =============================================================================
// ARAMA VE FİLTRELEME OLAYLARI
// =============================================================================
function bindSearchAndFilters() {
  // Sağ sütun arama kutusu
  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.addEventListener('input', debounce(e => {
      state.searchQuery = e.target.value.trim();
      renderJobsFeed();
    }, 250));
  }

  // Header hızlı arama kutusu
  const headerSearch = document.getElementById('header-search-input');
  if (headerSearch) {
    headerSearch.addEventListener('input', debounce(e => {
      state.searchQuery = e.target.value.trim();
      if (searchInput) searchInput.value = state.searchQuery;
      renderJobsFeed();
    }, 250));
  }

  // Sıralama Seçimi
  const sortSelect = document.getElementById('sort-select');
  if (sortSelect) {
    sortSelect.addEventListener('change', e => {
      state.sortBy = e.target.value;
      renderJobsFeed();
    });
  }

  // Durum Filtreleri (Sidebar Checkbox)
  const chkOpen = document.getElementById('chk-only-open');
  if (chkOpen) {
    chkOpen.addEventListener('change', e => {
      state.filterOnlyOpen = e.target.checked;
      renderJobsFeed();
    });
  }

  const chkCanc = document.getElementById('chk-only-canc');
  if (chkCanc) {
    chkCanc.addEventListener('change', e => {
      state.filterOnlyCanc = e.target.checked;
      renderJobsFeed();
    });
  }
}

// =============================================================================
// İLAN DETAY MODALI (DETAYLAR, ŞARTLAR & PDF İNDİRME)
// =============================================================================
function openJobDetailModal(jobId) {
  const job = state.jobs.find(j => j.id === jobId);
  if (!job) return;

  const modal = document.getElementById('job-detail-modal');
  if (!modal) return;

  // Bilgileri Doldur
  document.getElementById('modal-inst-name').textContent = job.institution;
  document.getElementById('modal-job-title').textContent = job.title;

  document.getElementById('modal-spec-position').textContent = job.position || 'Kamu Personeli';
  document.getElementById('modal-spec-quota').textContent = `${job.total_positions} Kişi`;
  document.getElementById('modal-spec-dates').textContent = job.date_interval || job.end_date_str;
  document.getElementById('modal-spec-education').textContent = job.education_level || 'Resmi Kılavuzda Belirtilmiştir';
  document.getElementById('modal-spec-kpss').textContent = job.kpss_requirement || 'Resmi İlanda Belirtilen Şartlar';
  document.getElementById('modal-spec-city').textContent = job.city || 'İlanda Belirtilmiştir';

  // İptal İlanı İse Özel Uyarı Ekle
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

  // PDF İndirme ve Resmi Sayfa Butonları
  const pdfBtn = document.getElementById('modal-pdf-download-btn');
  if (pdfBtn) {
    pdfBtn.href = job.official_doc_url || job.source_url;
  }

  const sourceBtn = document.getElementById('modal-source-btn');
  if (sourceBtn) {
    sourceBtn.href = job.source_url || 'https://kamuilan.sbb.gov.tr/';
  }

  // Reklam Alanı Kontrolü (Gelecek hafta için hazır slot)
  const adSlot = document.getElementById('modal-ad-slot');
  if (adSlot) {
    if (CONFIG.ENABLE_ADS) {
      adSlot.classList.add('active');
    } else {
      adSlot.classList.remove('active');
    }
  }

  // Paylaşım Butonu
  const shareBtn = document.getElementById('modal-share-btn');
  if (shareBtn) {
    shareBtn.onclick = () => {
      const shareUrl = window.location.href.split('#')[0] + `#ilan-${job.id}`;
      const shareText = `📢 ${job.institution} Personel Alım İlanı:\n${job.title}\nDetaylar & PDF: ${shareUrl}`;
      if (navigator.share) {
        navigator.share({ title: job.institution, text: shareText, url: shareUrl }).catch(() => {});
      } else {
        navigator.clipboard.writeText(shareText).then(() => {
          alert('✅ İlan bilgileri ve bağlantısı panoya kopyalandı!');
        });
      }
    };
  }

  // Modalı Göster
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

// =============================================================================
// YASAL UYARI, KVKK VE ÇEREZ POLİTİKASI DİYALOGLARI
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

// =============================================================================
// ÇEREZ POLİTİKASI & KULLANICI ONAY BANNERI (6698 SAYILI KVKK UYUMLU)
// =============================================================================
function initCookieConsent() {
  const banner = document.getElementById('cookie-consent-banner');
  if (!banner) return;

  const consent = localStorage.getItem('kpr_cookie_consent');
  if (!consent) {
    setTimeout(() => {
      banner.classList.add('show');
    }, 1200);
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
      localStorage.setItem('kpr_cookie_consent', 'essential_only');
      banner.classList.remove('show');
    });
  }
}

// =============================================================================
// CANLI DESTEK VE DANIŞMANLIK ALTYAPISI
// (Varsayılan olarak yayında değil; ENABLE_LIVE_SUPPORT=true ile açılır)
// =============================================================================
function initLiveSupport() {
  const widget = document.getElementById('live-support-widget');
  if (!widget) return;

  if (CONFIG.ENABLE_LIVE_SUPPORT) {
    widget.classList.add('enabled');

    const trigger = document.getElementById('live-support-trigger');
    const card = document.getElementById('live-support-card');
    const closeBtn = document.getElementById('live-support-close-btn');

    if (trigger && card) {
      trigger.addEventListener('click', () => {
        card.classList.toggle('open');
      });
    }

    if (closeBtn && card) {
      closeBtn.addEventListener('click', () => {
        card.classList.remove('open');
      });
    }
  } else {
    widget.classList.remove('enabled');
  }
}

// =============================================================================
// YARDIMCI FONKSİYONLAR
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

function slugify(text) {
  return text
    .toString()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^\w\-]+/g, '')
    .replace(/\-\-+/g, '-')
    .replace(/^-+/, '')
    .replace(/-+$/, '');
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
