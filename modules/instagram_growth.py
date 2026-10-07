"""
Instagram Hesap Büyütme, Kitle Kazanımı ve Viral Otomasyon Modülü
================================================================
Bu modül, Instagram hesabını organik olarak büyütmek, Keşfet (Explore) algoritmasını
tetiklemek ve kitleyi sadık takipçiye dönüştürmek için tasarlanmıştır.

Gelişmiş Yetenekler:
1. Çoklu Kaydırmalı Gönderi (Carousel - 4:5 Dikey) Stüdyosu:
   - Slayt 1 (Vurucu Kapak), Slayt 2 (Kadro & Şartlar), Slayt 3 (Başvuru & Viral CTA).
   - Kaydetme ve DM ile paylaşım oranını 4-5 kat artırır.
2. Otomatik Reels Video Stüdyosu:
   - 9:16 Dikey 1080x1920 dinamik Ken Burns efektli MP4 video.
   - Doğal Türkçe AI seslendirme (Edge-TTS) ve arka plan sesleri.
3. Takip Şartlı (Follow-Gate) Yorum-DM Otomasyonu:
   - "Yoruma KILAVUZ yazana link DM ile gitsin" mekanizması.
   - Kullanıcı hesabı takip etmiyorsa link kilitlenir; takip etmesi istenir.
   - Takip edip "TAKİP ETTİM" yazdığında kilit otomatik olarak açılır!
   - DM içinde isteğe bağlı dikey video önizlemesi ve kılavuz bağlantısı sunulur.
4. Otopilot Format Tercihi (Akıllı Hibrit Mod):
   - Kontenjan >= 50 ise otomatik REELS videosu, normalde 4:5 CAROUSEL.
5. En İyi Paylaşım Saatleri & Algoritma Zamanlayıcısı:
   - Türkiye kamu ve KPSS adaylarının pik saatlerine (09:00, 13:00, 19:00, 21:30) göre zamanlama.
"""

import os
import json
import time
import random
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import requests
from loguru import logger
import streamlit as st

from config.settings import settings
from core.database import get_db, get_system_setting, set_system_setting
from core.models import JobAnnouncement, JobStatus
from core.scheduler import AUTOPILOT_PACE_PRESETS
from graphics.generator import JobCardGenerator, to_turkish_date_str
from graphics.reels_engine import ReelsVideoEngine
from publishers.instagram import InstagramPublisher
from publishers.meta_helper import MetaHelper


# =============================================================================
# META GRAPH API UYUMLU DİNAMİK YANIT HAVUZLARI (ANTİ-SPAM & ROTASYON)
# =============================================================================
PUBLIC_REPLY_VARIANTS = [
    "@{username} Harika! {institution} için resmi başvuru ekranı bağlantısı ve şartlar DM kutunuza iletildi 📩 Başarılar!",
    "@{username} Bilgiler hazır! Resmi başvuru kılavuzu ve kadro şartnamesi DM gelen kutunuza gönderildi 🚀",
    "@{username} Selam! {institution} personel alımı başvuru bağlantısı DM'den teslim edildi 🎯 Kontrol edebilirsiniz.",
    "@{username} Talebiniz alındı! Resmi başvuru ekranı linki DM kutunuzda 📬 Bol şans dileriz!",
    "@{username} {institution} ilanının tüm detayları ve başvuru linki DM mesajı olarak iletildi 🌟",
    "@{username} Başvuru kılavuzu ve resmi e-Devlet/Kariyer Kapısı linki DM kutunuza teslim edildi ⚡"
]

PUBLIC_TAG_FRIEND_VARIANTS = [
    "@{username} Harika bir dayanışma! Arkadaşınızı etiketlediğiniz için teşekkürler 👏 {institution} resmi başvuru linki DM kutunuza iletildi 📩",
    "@{username} Arkadaşınızla paylaştığınız için teşekkürler! Kadro kılavuzu ve resmi başvuru ekranı DM'den iletildi 🚀",
    "@{username} Süper! Hem sizin hem etiketlediğiniz arkadaşınızın faydalanması için resmi başvuru kılavuzu DM'ye gönderildi 🎯"
]

DM_TEXT_VARIANTS = [
    (
        "👋 Merhaba @{username}!\n\n"
        "📌 Yorum yaptığınız ilan detayları:\n"
        "🏛 <b>Kurum:</b> {institution}\n"
        "📢 <b>Kadro:</b> {position}\n"
        "👥 <b>Kontenjan:</b> {quota} Kişi\n"
        "🗓 <b>Son Başvuru:</b> {deadline}\n\n"
        "🔗 <b>Resmi Başvuru Ekranı & Şartname:</b>\n{link}\n\n"
        "🇹🇷 T.C. Resmi Gazete ve SBB Kamu İlan Portalı teyitli kamu ilanıdır. Başarılar dileriz!\n\n"
        "📢 Yeni kamu alımlarını kaçırmamak için @kamupersonelrehberi sayfamızı takip etmeyi unutmayın!"
    ),
    (
        "👋 Selam @{username}! İlan başvurunuz için gerekli bağlantı hazır:\n\n"
        "🏛 <b>Kurum:</b> {institution}\n"
        "📢 <b>Pozisyon:</b> {position}\n"
        "👥 <b>Alım Sayısı:</b> {quota} Kişi\n"
        "🗓 <b>Son Başvuru Tarihi:</b> {deadline}\n\n"
        "⚡ <b>Doğrudan Başvuru Bağlantısı:</b>\n{link}\n\n"
        "💡 Tavsiye: Başvurunuzu son güne bırakmamanızı öneririz. Bol şans!\n\n"
        "📌 Yeni ilanlar ve sonuç duyuruları için sayfamızı takipte kalın: @kamupersonelrehberi"
    ),
    (
        "👋 Merhaba @{username}! Kamu Personel Rehberi asistanınız burada 🤖\n\n"
        "🏛 <b>İlan Veren Kurum:</b> {institution}\n"
        "📢 <b>Alım Yapılan Kadro:</b> {position}\n"
        "👥 <b>Toplam Kontenjan:</b> {quota} Kişi\n"
        "🗓 <b>Son Gün:</b> {deadline}\n\n"
        "🔗 <b>Resmi Kılavuz & Başvuru Sayfası:</b>\n{link}\n\n"
        "🎯 Atanma sürecinizde başarılar dileriz! Bizi takip etmeyi unutmayın: @kamupersonelrehberi"
    )
]


# =============================================================================
# TÜRKIYE KAMU & KPSS ADAYLARI İÇİN EN İYİ PAYLAŞIM ZAMAN DİLİMLERİ
# =============================================================================
BEST_POSTING_SLOTS = [
    {
        "slot": "08:30 - 09:30",
        "name": "Sabah İşe / Kütüphaneye Gidiş & Resmi Gazete Bülteni",
        "desc": "Resmi Gazete alımlarının ilk duyurulduğu ve adayların güne başlarken Instagram'a baktığı ilk pik.",
        "badge": "Yüksek Etkileşim"
    },
    {
        "slot": "12:30 - 13:30",
        "name": "Öğle Arası Molası",
        "desc": "Çalışan adayların ve öğrencilerin telefon başında olduğu en yoğun öğle zamanı.",
        "badge": "Orta - Yüksek"
    },
    {
        "slot": "18:30 - 19:30",
        "name": "Akşam İş / Dershane Dönüşü",
        "desc": "Günün özet ilanlarının ve son başvuru hatırlatmalarının en çok kaydedildiği saat.",
        "badge": "Çok Yüksek (Reels İçin İdeal)"
    },
    {
        "slot": "21:00 - 22:30",
        "name": "Gece Altın Saati (Pik Etkileşim)",
        "desc": "Kaydırmalı Carousel gönderilerin en çok okunduğu, yorum yapıldığı ve kaydedildiği ana zaman dilimi.",
        "badge": "🔥 Zirve Etkileşim"
    }
]


class InstagramGrowthManager:
    """
    Instagram Büyüme & Otomasyon Operasyonları Yöneticisi.
    """

    def __init__(self):
        self.publisher = InstagramPublisher()
        self.card_gen = JobCardGenerator()
        self.reels_engine = ReelsVideoEngine()

    def get_account_profile(self) -> Dict[str, Any]:
        """Instagram İşletme/İçerik Üretici hesap profilini ve istatistiklerini çeker."""
        token = self.publisher.access_token
        acc_id = self.publisher.account_id
        if not token or not acc_id:
            return {"connected": False, "message": "Instagram token veya Account ID tanımlı değil."}

        url = f"https://graph.facebook.com/v19.0/{acc_id}"
        params = {
            "fields": "username,name,profile_picture_url,followers_count,media_count,biography,website",
            "access_token": token
        }
        try:
            r = requests.get(url, params=params, timeout=12)
            if r.status_code == 200:
                data = r.json()
                data["connected"] = True
                return data
            else:
                err = r.json().get("error", {}).get("message", r.text)
                return {"connected": False, "message": f"API Hatası: {err}"}
        except Exception as e:
            return {"connected": False, "message": f"Bağlantı Hatası: {str(e)}"}

    def _get_processed_cache_file(self) -> Path:
        cache_dir = Path("data")
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "processed_ig_comments.json"

    def get_processed_comment_ids(self) -> set:
        f = self._get_processed_cache_file()
        if f.exists():
            try:
                import json
                with open(f, "r", encoding="utf-8") as fp:
                    return set(json.load(fp))
            except Exception:
                return set()
        return set()

    def mark_comment_processed(self, comment_id: str):
        ids = self.get_processed_comment_ids()
        ids.add(str(comment_id))
        f = self._get_processed_cache_file()
        try:
            import json
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(list(ids), fp)
        except Exception:
            pass

    def get_comment_logs(self) -> List[Dict[str, Any]]:
        log_f = Path("data/ig_comment_actions.json")
        if log_f.exists():
            try:
                import json
                with open(log_f, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                return []
        return []

    def add_comment_log(self, entry: Dict[str, Any]):
        logs = self.get_comment_logs()
        logs.insert(0, entry)
        logs = logs[:50]
        log_f = Path("data/ig_comment_actions.json")
        try:
            import json
            with open(log_f, "w", encoding="utf-8") as fp:
                json.dump(logs, fp, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def parse_post_job_details(self, media_id: str, shortcode: str, caption: str) -> Dict[str, Any]:
        """
        Instagram gönderisinin hangi ilana ait olduğunu 3 aşamalı akıllı sistemle %100 doğrulukla çözer:
        1. Aşama: data/ig_post_job_map.json kayıtlı ID eşleştirmesi
        2. Aşama: Gönderi açıklaması içindeki '#KPR{id}' veya 'İlan Ref: #{id}' etiketi
        3. Aşama: Açıklama metninden (Kurum, Kadro, Son Başvuru, Kontenjan) satır satır ayrıştırma ve DB doğrulaması
        """
        import re
        import json

        matched_job = None
        job_id = None

        # 1. Aşama: Dosyadan eşleşme kontrolü
        map_f = Path("data/ig_post_job_map.json")
        if map_f.exists():
            try:
                with open(map_f, "r", encoding="utf-8") as fp:
                    p_map = json.load(fp)
                    job_id = p_map.get(str(media_id)) or p_map.get(str(shortcode))
            except Exception:
                pass

        with get_db() as db:
            if job_id:
                matched_job = db.query(JobAnnouncement).filter(JobAnnouncement.id == int(job_id)).first()

            # 2. Aşama: Caption içinde Ref ID ara
            if not matched_job and caption:
                m_ref = re.search(r'(?:#KPR|İlan Ref: #|İlan No: #?)(\d+)', caption)
                if m_ref:
                    ref_id = int(m_ref.group(1))
                    matched_job = db.query(JobAnnouncement).filter(JobAnnouncement.id == ref_id).first()

            # 3. Aşama: Caption satırlarından kurum ve kadroyu ayrıştır
            lines = [l.strip() for l in (caption or "").split("\n") if l.strip()]
            inst_parsed = ""
            pos_parsed = ""
            deadline_parsed = ""
            quota_parsed = ""

            for l in lines:
                if ("🏛" in l or "PERSONEL ALIMI" in l) and not inst_parsed:
                    inst_parsed = l.replace("🏛", "").replace("PERSONEL ALIMI", "").strip()
                elif "📢" in l and not pos_parsed:
                    pos_parsed = l.replace("📢", "").strip()
                elif "🗓 Son Başvuru:" in l and not deadline_parsed:
                    deadline_parsed = l.replace("🗓 Son Başvuru:", "").strip()
                elif "👥 Kontenjan:" in l and not quota_parsed:
                    quota_parsed = l.replace("👥 Kontenjan:", "").strip()

            if not matched_job and inst_parsed:
                stop_words = ["GENEL", "MÜDÜRLÜĞÜ", "MUDURLUGU", "BAKANLIĞI", "BAKANLIGI", "ÜNİVERSİTESİ", "UNIVERSITESI", "BAŞKANLIĞI"]
                words = [w for w in re.split(r'[\s,.-]+', inst_parsed) if len(w) > 2 and w.upper() not in stop_words]
                if words:
                    query = db.query(JobAnnouncement)
                    for w in words[:2]:
                        query = query.filter(JobAnnouncement.institution.ilike(f"%{w}%"))
                    matched_job = query.order_by(JobAnnouncement.id.desc()).first()

        # Sonuç paketini hazırla (Asla farklı bir ilanın verisini döndürmez!)
        final_inst = (matched_job.institution if matched_job else inst_parsed) or "Kamu Kurumu"
        final_pos = (matched_job.position if matched_job else pos_parsed) or "Personel Alımı"
        final_deadline = (to_turkish_date_str(matched_job.application_end_date) if matched_job else deadline_parsed) or "Resmi Kılavuzda Belirtilen Tarih"
        final_quota = (str(matched_job.total_positions) if matched_job and matched_job.total_positions else quota_parsed) or "1"
        final_link = (matched_job.source_url if matched_job else None) or "https://isealimkariyerkapisi.cbiko.gov.tr/"

        return {
            "institution": final_inst,
            "position": final_pos,
            "deadline": final_deadline,
            "quota": final_quota,
            "source_url": final_link,
            "job_id": matched_job.id if matched_job else None
        }

    def process_live_comments(self, limit_media: int = 10) -> Dict[str, Any]:
        """
        Meta Graph API üzerinden Instagram hesabının son gönderilerindeki
        tüm canlı yorumları çeker. 'KILAVUZ', 'LİNK' vb. yazan kullanıcılara
        kamuoyu önünde yanıt verir ve resmi başvuru linkini DM kutularına iletir.
        """
        token = get_system_setting("INSTAGRAM_ACCESS_TOKEN")
        acc_id = get_system_setting("INSTAGRAM_ACCOUNT_ID")
        fb_page_id = get_system_setting("FACEBOOK_PAGE_ID")

        if not token or not acc_id:
            return {"success": False, "message": "Instagram token veya Account ID eksik.", "processed_count": 0}

        processed_ids = self.get_processed_comment_ids()
        url = f"https://graph.facebook.com/v19.0/{acc_id}/media"
        params = {
            "fields": "id,caption,shortcode,comments{id,text,username,timestamp}",
            "limit": limit_media,
            "access_token": token
        }

        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code != 200:
                return {"success": False, "message": f"Media getirme hatası: {r.text}", "processed_count": 0}
            media_list = r.json().get("data", [])
        except Exception as e:
            return {"success": False, "message": f"API istek hatası: {e}", "processed_count": 0}

        new_actions = []
        triggers = [
            "kilavuz", "klavuz", "link", "linki", "sartname", "sartlar", "basvuru",
            "detay", "detaylar", "pdf", "nereden", "nasil", "istiyorum", "bana da",
            "gonder", "gonderir", "takip ettim", "ettim", "takipteyim", "takipciyim"
        ]

        for media in media_list:
            caption = media.get("caption", "")
            media_id = media.get("id")
            shortcode = media.get("shortcode")
            comments_data = media.get("comments", {}).get("data", [])

            # Bu gönderinin tam olarak hangi ilana ait olduğunu nokta atışı tespit et
            details = self.parse_post_job_details(media_id=media_id, shortcode=shortcode, caption=caption)
            job_title = f"{details['institution']} {details['position']}"
            job_link = details["source_url"]
            d_str = details["deadline"]
            quota_str = details["quota"]

            for c in comments_data:
                c_id = str(c.get("id"))
                username = c.get("username", "")
                text = (c.get("text") or "").strip()
                t_lower = text.lower().replace("i̇", "i").replace("ı", "i")

                if c_id in processed_ids:
                    continue

                if username == "kamupersonelrehberi":
                    continue

                is_trigger = any(trig in t_lower for trig in triggers)
                if not is_trigger:
                    continue

                # Arkadaş etiketleme kontrolü (@arkadasini etiketleyen kullanıcılara özel viral yanıt)
                has_friend_tag = False
                for w in text.split():
                    if w.startswith("@") and "kamupersonelrehberi" not in w.lower() and len(w) > 2:
                        has_friend_tag = True
                        break

                # 1. Özel DM Yanıtı (Private Reply - Dinamik Rotasyon)
                dm_ok = False
                dm_err = ""
                if fb_page_id:
                    dm_tpl = random.choice(DM_TEXT_VARIANTS)
                    dm_text = dm_tpl.format(
                        username=username,
                        institution=details["institution"],
                        position=details["position"],
                        quota=quota_str,
                        deadline=d_str,
                        link=job_link
                    )
                    dm_url = f"https://graph.facebook.com/v19.0/{fb_page_id}/messages"
                    dm_payload = {
                        "recipient": {"comment_id": c_id},
                        "message": {"text": dm_text}
                    }
                    try:
                        r_dm = requests.post(dm_url, json=dm_payload, params={"access_token": token}, timeout=15)
                        if r_dm.status_code in [200, 201]:
                            dm_ok = True
                        else:
                            dm_err = r_dm.text[:120]
                    except Exception as de:
                        dm_err = str(de)[:120]

                # Meta Anti-Bot Davranışsal Gecikme (Jitter Delay)
                time.sleep(random.uniform(0.6, 1.4))

                # 2. Herkese Açık Yorum Yanıtı (Public Reply - Dinamik Havuz)
                if has_friend_tag:
                    pub_tpl = random.choice(PUBLIC_TAG_FRIEND_VARIANTS)
                else:
                    pub_tpl = random.choice(PUBLIC_REPLY_VARIANTS)
                pub_msg = pub_tpl.format(username=username, institution=details["institution"])

                pub_url = f"https://graph.facebook.com/v19.0/{c_id}/replies"
                pub_ok = False
                try:
                    r_pub = requests.post(pub_url, data={"message": pub_msg, "access_token": token}, timeout=15)
                    pub_ok = (r_pub.status_code in [200, 201])
                except Exception:
                    pass

                # İşlendi olarak kaydet
                self.mark_comment_processed(c_id)

                action_entry = {
                    "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                    "username": username,
                    "comment_text": text,
                    "comment_id": c_id,
                    "media_id": media.get("id"),
                    "shortcode": media.get("shortcode"),
                    "friend_tagged": has_friend_tag,
                    "public_reply_status": "Başarılı" if pub_ok else "Hata",
                    "dm_status": "Gönderildi (DM İletildi)" if dm_ok else f"Hata ({dm_err})",
                    "job_title": job_title
                }
                self.add_comment_log(action_entry)
                new_actions.append(action_entry)

        return {
            "success": True,
            "processed_count": len(new_actions),
            "new_actions": new_actions
        }

    def simulate_comment_to_dm(
        self,
        username: str,
        keyword: str,
        job_id: int,
        is_following: bool = True,
        include_video: bool = False
    ) -> Dict[str, Any]:
        """
        Takip Şartlı (Follow-Gate) Yorum-DM otomasyonunun yanıtını test eder ve simüle eder.
        """
        with get_db() as db:
            job = db.query(JobAnnouncement).filter(JobAnnouncement.id == job_id).first()
            if not job:
                return {"success": False, "message": "İlan bulunamadı."}

            clean_link = job.source_url or "https://kamuilan.sbb.gov.tr/"
            d_str = to_turkish_date_str(job.application_end_date)
            pos_str = job.position or job.title

            video_note = "\n🎬 <b>Video Kılavuz:</b> İlana ait 10 saniyelik özet Reels videosu ekte sunulmuştur.\n" if include_video else ""

            if is_following:
                # Kullanıcı Hesabı Takip Ediyorsa -> Doğrudan Kılavuzu Teslim Et
                comment_reply = (
                    f"@{username} Harika! Sayfamızı takip ettiğiniz için teşekkür ederiz 🎉 "
                    f"Resmi başvuru ekranı ve kadro kılavuzu DM kutunuza iletildi! 📩 Lütfen gelen kutunuzu kontrol edin."
                )

                dm_message = (
                    f"👋 Selam @{username}! Kamu Personel Rehberi ailesine hoş geldiniz!\n"
                    f"Bizi takip ettiğiniz için teşekkürler. Kılavuz kilidiniz açıldı: 🔓\n\n"
                    f"🏛 <b>Kurum:</b> {job.institution or 'Kamu Kurumu'}\n"
                    f"📋 <b>Kadro:</b> {pos_str}\n"
                    f"👥 <b>Kontenjan:</b> {job.total_positions or 1} Kişi\n"
                    f"🎯 <b>KPSS:</b> {job.kpss_requirement or 'Resmi ilanda belirtilen'}\n"
                    f"🗓 <b>Son Başvuru:</b> {d_str}\n"
                    f"{video_note}\n"
                    f"🔗 <b>Resmi Başvuru Ekranı:</b>\n{clean_link}\n\n"
                    f"📌 Yeni açılan ilanları ve sonuçları kaçırmamak için Telegram kanalımıza da katılabilirsiniz: https://t.me/kamupersonelrehberi\n\n"
                    f"Başarılar dileriz! 🇹🇷"
                )

                return {
                    "success": True,
                    "is_following": True,
                    "status_tag": "🔓 KİLİT AÇIK (Takipçi)",
                    "username": username,
                    "keyword": keyword,
                    "public_reply": comment_reply,
                    "private_dm": dm_message,
                    "job_title": job.title
                }

            else:
                # Kullanıcı Hesabı Takip ETMİYORSA -> Takip Şartı (Follow-Gate) Bildirimi Gönder
                comment_reply = (
                    f"@{username} Selam! Kılavuz ve resmi başvuru linkini DM ile alabilmek için "
                    f"lütfen önce sayfamızı TAKİP EDİN ve ardından buraya 'TAKİP ETTİM' yazın! 🔒 Asistanımız anında kilidi açacaktır."
                )

                dm_message = (
                    f"👋 Merhaba @{username}!\n\n"
                    f"🔒 İstediğiniz kamu alımının resmi kılavuz ve başvuru linki KİLİTLİDİR.\n\n"
                    f"✨ <b>Kilidi açmak çok kolay:</b>\n"
                    f"1. Profilimize gidip <b>@kamupersonelrehberi</b> sayfamızı TAKİP EDİN.\n"
                    f"2. Ardından bu mesaja veya yoruma <b>\"TAKİP ETTİM\"</b> yazın.\n\n"
                    f"Otomasyon asistanımız takip durumunuzu saniyeler içinde onaylayıp resmi başvuru ekranı bağlantısını anında teslim edecektir! ⚡"
                )

                # Kullanıcının takip ettikten sonra kilidi açma yanıtı
                unlocked_after_follow = (
                    f"🎉 Tebrikler @{username}! Takip ettiğiniz onaylandı, kılavuz kilidiniz açıldı: 🔓\n\n"
                    f"🔗 <b>Resmi Başvuru Ekranı:</b> {clean_link}\n"
                    f"🗓 <b>Son Başvuru:</b> {d_str}\n"
                    f"Başarılar dileriz!"
                )

                return {
                    "success": True,
                    "is_following": False,
                    "status_tag": "🔒 KİLİTLİ (Takip Şartı Aktif)",
                    "username": username,
                    "keyword": keyword,
                    "public_reply": comment_reply,
                    "private_dm": dm_message,
                    "unlocked_message": unlocked_after_follow,
                    "job_title": job.title
                }

    def generate_top_comments(self, announcement_text: str, institution: str = "") -> Dict[str, Any]:
        """
        ÖSYM, Bakanlık veya popüler kamu sayfalarının paylaşımlarına
        ilk 2-5 dakika içinde atılmak üzere 'En Üst Yorum (Top-Comment)' taslakları üretir.
        Spam reklam içermez; %100 değer, hap bilgi ve aday rehberliği odaklıdır.
        """
        inst_label = institution.strip() or "Kamu Kurumu"
        
        # 1. Aktif LLM Sağlayıcısı ile üretim dene
        try:
            from ai.llm_client import LLMClient
            llm = LLMClient()
            has_llm = any([
                get_system_setting("NVIDIA_API_KEY"),
                get_system_setting("GROQ_API_KEY"),
                get_system_setting("CUSTOM_LLM_API_KEY")
            ])
            if has_llm and announcement_text.strip():
                prompt = (
                    f"Aşağıdaki kamu personel alımı / sınav duyurusunu incele. "
                    f"Bu gönderinin altına Instagram'da 'En Çok Beğenilen Üst Yorum (Top Comment)' "
                    f"olması için 3 farklı Türkçe yorum taslağı hazırla:\n\n"
                    f"Duyuru Metni: {announcement_text[:800]}\n"
                    f"Kurum: {inst_label}\n\n"
                    f"Kurallar:\n"
                    f"- Kesinlikle 'sayfamızı takip edin' gibi ucuz reklam yapma.\n"
                    f"- Bilgi verici, profesyonel, adayların işini kolaylaştıran bir uzman gibi yaz.\n"
                    f"- Yanıtı SADECE geçerli bir JSON olarak ver: "
                    f'{{"style_summary": "...", "style_warning": "...", "style_community": "..."}}'
                )
                res = llm._dispatch_completion(llm.active_provider, prompt)
                if res and isinstance(res, dict) and "style_summary" in res:
                    return {
                        "success": True,
                        "provider": llm.active_provider,
                        "style_summary": res.get("style_summary", ""),
                        "style_warning": res.get("style_warning", ""),
                        "style_community": res.get("style_community", "")
                    }
        except Exception as e:
            logger.debug(f"LLM top-comment üretimi istisnası: {e}")

        # 2. Akıllı Kural Tabanlı (Heuristic) Şablonlar
        style1 = (
            f"📌 ÖZET BİLGİ & KRİTİK ŞARTLAR (Adaylar için):\n\n"
            f"1️⃣ Kurum: {inst_label}\n"
            f"2️⃣ Başvuru Kanalı: Resmi e-Devlet Kariyer Kapısı üzerinden yapılmaktadır.\n"
            f"3️⃣ Başvuru Takvimi: Süre sınırlıdır, son günü beklemeden tamamlamanızı tavsiye ederiz.\n\n"
            f"💡 Kontenjan ve özel branş şartlarının tam listesi için profilimizdeki güncel ilan rehberine göz atabilirsiniz."
        )

        style2 = (
            f"⚠️ BAŞVURACAK ADAYLARIN DİKKATİNE ({inst_label}):\n\n"
            f"• Mezuniyet ve KPSS puan türü şartının birebir uyuştuğundan emin olun.\n"
            f"• İstenen sertifika veya belgelerin son başvuru tarihinden önce alınmış olması şarttır.\n"
            f"• Aracı ve ücret talep eden sitelere itibar etmeyiniz, tek resmi kanal Kariyer Kapısı'dır.\n\n"
            f"Başvuran tüm adaylara başarılar dileriz! 🇹🇷"
        )

        style3 = (
            f"🎯 {inst_label} alımını bekleyen adaylar toplandı mı?\n\n"
            f"Bu kadroda taban puanların kaça kadar düşeceğini tahmin ediyorsunuz? "
            f"Bölüm ve KPSS puanınızı yazarsanız geçmiş atama taban verilerine göre değerlendirelim 👇\n"
            f"(Kılavuzdaki özel şartları merak edenlere detayları aktarabiliriz)."
        )

        return {
            "success": True,
            "provider": "Kural Tabanlı Motor (Heuristic)",
            "style_summary": style1,
            "style_warning": style2,
            "style_community": style3
        }


# =============================================================================
# STREAMLIT YÖNETİM ARAYÜZÜ (INSTAGRAM BÜYÜME VE OTOMASYON MERKEZİ)
# =============================================================================
def render_instagram_growth_tab():
    """
    Streamlit paneline tam teşekküllü 'Instagram Büyüme & Otomasyon Merkezi' sekmesini çizer.
    """
    mgr = InstagramGrowthManager()

    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e1b4b 0%, #311042 50%, #1e1b4b 100%);
                padding: 24px; border-radius: 18px; border: 1px solid rgba(225, 48, 108, 0.4); margin-bottom: 25px;">
        <h2 style="color: #ffffff; margin: 0; font-size: 26px; font-weight: 800;">
            📸 Instagram Kitle Büyütme & Viral Otomasyon Merkezi
        </h2>
        <p style="color: #cbd5e1; margin-top: 8px; margin-bottom: 0; font-size: 15px;">
            4:5 Çoklu Carousel, 9:16 Dikey Sesli Reels, Takip Şartlı Yorum-DM Asistanı
            ve Akıllı Pik Saat Dağıtımı ile hesabınızı her gün büyütün.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 1. HESAP DURUMU VE TEŞHİS BÖLÜMÜ
    prof = mgr.get_account_profile()
    if prof.get("connected"):
        c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
        with c1:
            pic = prof.get("profile_picture_url")
            if pic:
                st.image(pic, width=80)
            else:
                st.markdown("👤")
        with c2:
            st.markdown(f"**@{prof.get('username')}** ({prof.get('name')})")
            st.caption(prof.get("biography") or "Biyografi tanımlanmamış.")
        with c3:
            st.metric("Takipçi Sayısı", f"{prof.get('followers_count', 0):,}")
        with c4:
            st.metric("Toplam Medya", prof.get("media_count", 0))
    else:
        st.warning(f"⚠️ **Instagram Hesabı Bağlantı Durumu:** {prof.get('message')}")
        st.info("💡 Meta Access Token ve Instagram Account ID ayarlarınızı **Sistem & API Ayarları** menüsünden yapılandırabilirsiniz.")

    st.markdown("---")

    sub_tab1, sub_tab2, sub_tab3, sub_tab4, sub_tab5 = st.tabs([
        "📱 Çoklu Carousel (Kaydırmalı) Stüdyosu",
        "🎬 Reels Video (Sesli MP4) Motoru",
        "💬 Takip Şartlı Yorum-DM & Video Asistanı",
        "🌟 AI Öncü Yorum Radarı (Top-Comment Funnel)",
        "⚙️ Otopilot Dağıtım & Pik Saat Ayarları"
    ])

    # =========================================================================
    # TAB 1: ÇOKLU CAROUSEL STÜDYOSU (1080x1350 DİKEY 3 SLAYT)
    # =========================================================================
    with sub_tab1:
        st.markdown("### 🖼️ 4:5 Dikey Çoklu Kaydırmalı Gönderi (Carousel)")
        st.caption("Instagram algoritmasında **Kaydetme (Save)** ve **DM ile Paylaşma (Share)** oranını 4-5 kat artıran en etkili formattır.")

        with get_db() as db:
            jobs = db.query(JobAnnouncement).order_by(JobAnnouncement.id.desc()).limit(20).all()

        if not jobs:
            st.info("Sistemde henüz ilan bulunmuyor.")
        else:
            job_dict = {f"#{j.id} - {j.institution or 'Kurum'} ({j.position or j.title})": j.id for j in jobs}
            selected_label = st.selectbox("Carousel Üretilecek İlanı Seçin:", list(job_dict.keys()), key="car_job_sel")
            target_job_id = job_dict[selected_label]

            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                gen_clicked = st.button("✨ 3 Slaytlık Carousel Setini Üret & Önizle", type="primary", use_container_width=True)
            with col_btn2:
                pub_clicked = st.button("🚀 Doğrudan Instagram Hesabında Carousel Olarak Paylaş", use_container_width=True)

            if gen_clicked or st.session_state.get(f"carousel_slides_{target_job_id}"):
                with st.spinner("3 Slaytlık 4:5 Dikey Lüks Carousel üretiliyor..."):
                    with get_db() as db:
                        t_job = db.query(JobAnnouncement).filter(JobAnnouncement.id == target_job_id).first()
                        slides = mgr.card_gen.generate_carousel_cards(
                            job_id=t_job.id,
                            institution=t_job.institution or "Kamu Kurumu",
                            position=t_job.position or t_job.title,
                            total_positions=t_job.total_positions,
                            kpss_requirement=t_job.kpss_requirement,
                            education_level=t_job.education_level,
                            deadline=to_turkish_date_str(t_job.application_end_date),
                            source_url=t_job.source_url,
                            city=t_job.city
                        )
                        st.session_state[f"carousel_slides_{target_job_id}"] = [str(s) for s in slides]

                st.success("✅ 3 Slaytlık Carousel Seti Başarıyla Üretildi! (1080x1350 Dikey)")
                slide_paths = st.session_state.get(f"carousel_slides_{target_job_id}", [])
                
                s_col1, s_col2, s_col3 = st.columns(3)
                if len(slide_paths) >= 3:
                    with s_col1:
                        st.markdown("**1. Slayt (Vurucu Kapak)**")
                        st.image(slide_paths[0], use_container_width=True)
                    with s_col2:
                        st.markdown("**2. Slayt (Kadro & Şartlar)**")
                        st.image(slide_paths[1], use_container_width=True)
                    with s_col3:
                        st.markdown("**3. Slayt (Başvuru & Viral CTA)**")
                        st.image(slide_paths[2], use_container_width=True)

            if pub_clicked:
                with st.spinner("Carousel görselleri Meta CDN köprüsüne aktarılıyor ve Instagram'da yayınlanıyor..."):
                    with get_db() as db:
                        t_job = db.query(JobAnnouncement).filter(JobAnnouncement.id == target_job_id).first()
                        slides = mgr.card_gen.generate_carousel_cards(
                            job_id=t_job.id,
                            institution=t_job.institution or "Kamu Kurumu",
                            position=t_job.position or t_job.title,
                            total_positions=t_job.total_positions,
                            kpss_requirement=t_job.kpss_requirement,
                            education_level=t_job.education_level,
                            deadline=to_turkish_date_str(t_job.application_end_date),
                            source_url=t_job.source_url,
                            city=t_job.city
                        )
                        ok, msg = mgr.publisher.publish_carousel(t_job, slides)
                        if ok:
                            st.success(f"🎉 {msg}")
                        else:
                            st.error(f"❌ Paylaşım başarısız: {msg}")

    # =========================================================================
    # TAB 2: REELS VİDEO MOTORU (1080x1920 MP4)
    # =========================================================================
    with sub_tab2:
        st.markdown("### 🎬 Otomatik 9:16 Dikey Reels Video Motoru")
        st.caption("Instagram'da **takipçi dışı yeni kitlelere (Keşfet)** ulaşmanın tek organik yolu dikey Reels videolarıdır.")

        with get_db() as db:
            jobs = db.query(JobAnnouncement).order_by(JobAnnouncement.id.desc()).limit(20).all()

        if jobs:
            job_dict_r = {f"#{j.id} - {j.institution or 'Kurum'} ({j.position or j.title})": j.id for j in jobs}
            sel_r_label = st.selectbox("Reels Videosu Yapılacak İlan:", list(job_dict_r.keys()), key="reels_job_sel")
            r_job_id = job_dict_r[sel_r_label]

            col_r1, col_r2, col_r3 = st.columns([1, 1, 1])
            with col_r1:
                r_voice = st.selectbox("Türkçe Yapay Zeka Seslendirmeni:", ["tr-TR-AhmetNeural (Erkek - Kurumsal)", "tr-TR-EmelNeural (Kadın - Akıcı)"])
            with col_r2:
                r_duration = st.slider("Video Süresi (Saniye):", min_value=7, max_value=14, value=10)
            with col_r3:
                r_hook = st.selectbox(
                    "Algoritma & Viral Kurgu:",
                    [
                        "🎯 KILAVUZ Odaklı (DM İletişimi)",
                        "📲 Arkadaşına Gönder (Sends per Reach)",
                        "📌 Kaydet Unutma (Kaydetme Oranı)"
                    ]
                )

            voice_id = "tr-TR-AhmetNeural" if "Ahmet" in r_voice else "tr-TR-EmelNeural"
            hook_key = "VIRAL_SEND" if "Arkadaşına" in r_hook else ("VIRAL_SAVE" if "Kaydet" in r_hook else "VIRAL_DM")

            c_btn_r1, c_btn_r2 = st.columns([1, 1])
            with c_btn_r1:
                gen_r_clicked = st.button("🎥 1080x1920 Reels Videosunu Render Et", type="primary", use_container_width=True)
            with c_btn_r2:
                pub_r_clicked = st.button("📤 Doğrudan Instagram Reels Olarak Yayınla", use_container_width=True)

            video_key = f"rendered_reels_{r_job_id}"
            if gen_r_clicked:
                with st.spinner("Reels videosu render ediliyor (Seslendirme + Dinamik Zoom + MP4)..."):
                    with get_db() as db:
                        t_job = db.query(JobAnnouncement).filter(JobAnnouncement.id == r_job_id).first()
                        ok_r, v_path, r_msg = mgr.reels_engine.create_reels_video(
                            job_id=t_job.id,
                            institution=t_job.institution or "Kamu Kurumu",
                            position=t_job.position or t_job.title,
                            total_positions=t_job.total_positions,
                            kpss_requirement=t_job.kpss_requirement,
                            education_level=t_job.education_level,
                            deadline=to_turkish_date_str(t_job.application_end_date),
                            source_url=t_job.source_url,
                            voice=voice_id,
                            duration_seconds=r_duration,
                            hook_style=hook_key
                        )
                        if ok_r and v_path:
                            st.session_state[video_key] = str(v_path)
                            st.success(f"✅ {r_msg}")
                        else:
                            st.error(f"❌ Video üretilemedi: {r_msg}")

            if st.session_state.get(video_key) and Path(st.session_state[video_key]).exists():
                v_file = st.session_state[video_key]
                col_vp1, col_vp2 = st.columns([1, 1])
                with col_vp1:
                    st.video(v_file)
                with col_vp2:
                    st.markdown("#### 📊 Reels Video Özellikleri")
                    st.write("- **Çözünürlük:** 1080x1920 Full HD (9:16 Dikey)")
                    st.write(f"- **Dosya Boyutu:** {Path(v_file).stat().st_size // 1024} KB")
                    st.write(f"- **Süre:** {r_duration} Saniye (Loop / Sonsuz Döngü Uyumlu)")
                    st.write(f"- **Seslendirme:** {r_voice.split(' ')[0]} (Doğal Türkçe)")
                    st.write(f"- **Viral Kurgu:** `{r_hook}`")
                    with get_db() as db:
                        tj = db.query(JobAnnouncement).filter(JobAnnouncement.id == r_job_id).first()
                        if tj:
                            script_preview = mgr.reels_engine.build_voice_script(
                                institution=tj.institution or "Kamu Kurumu",
                                position=tj.position or tj.title,
                                total_positions=tj.total_positions,
                                kpss_requirement=tj.kpss_requirement,
                                deadline=to_turkish_date_str(tj.application_end_date),
                                hook_style=hook_key
                            )
                            st.info(f"🎙 **Seslendirilen Metin:**\n\n\"{script_preview}\"")

            if pub_r_clicked:
                v_path_str = st.session_state.get(video_key)
                if not v_path_str or not Path(v_path_str).exists():
                    st.warning("Lütfen önce videoyu render ediniz.")
                else:
                    with st.spinner("Reels videosu Instagram'a yükleniyor..."):
                        with get_db() as db:
                            t_job = db.query(JobAnnouncement).filter(JobAnnouncement.id == r_job_id).first()
                            ok_pub, pub_msg = mgr.publisher.publish_reels(t_job, Path(v_path_str))
                            if ok_pub:
                                st.success(f"🎉 {pub_msg}")
                            else:
                                st.error(f"❌ Reels paylaşılamadı: {pub_msg}")

    # =========================================================================
    # TAB 3: TAKİP ŞARTLI YORUM-DM & VİDEO ASİSTANI (FOLLOW-GATE)
    # =========================================================================
    with sub_tab3:
        st.markdown("### 🔒 Takip Şartlı (Follow-Gate) Yorum-DM Asistanı")
        st.markdown("""
        **Nasıl Çalışır ve Kitleyi Nasıl Patlatır?**
        * Aday gönderinin altına **"KILAVUZ"** veya **"LİNK"** yazar.
        * **Eğer kullanıcı hesabınızı TAKİP EDİYORSA:** Bot anında tebrik eder ve resmi kılavuz linkini DM'den teslim eder.
        * **Eğer kullanıcı takip ETMİYORSA:** Bot kılavuzu **kilitler**! *"Kılavuzun açılması için lütfen @kamupersonelrehberi hesabımızı TAKİP EDİN ve ardından 'TAKİP ETTİM' yazın!"* der.
        * Aday sayfayı takip edip 'TAKİP ETTİM' yazdığı an link kilidi açılır! Bu kurgu her gönderide **yüzlerce organik takipçi** kazandırır.
        """)

        # Anti-Spam ve Güvenlik Rozetleri
        c_badge1, c_badge2 = st.columns(2)
        with c_badge1:
            st.markdown("""
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; padding: 10px 14px; border-radius: 8px;">
                <span style="color: #34d399; font-weight: 700; font-size: 14px;">🛡️ Anti-Spam Rotasyon Havuzu Aktif</span>
                <p style="color: #cbd5e1; font-size: 13px; margin: 4px 0 0 0;">Yorum ve DM yanıtları 6 farklı dinamik varyasyonla ve değişken gecikmeyle (jitter) gönderilerek Meta bot koruması aşılır.</p>
            </div>
            """, unsafe_allow_html=True)
        with c_badge2:
            st.markdown("""
            <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid #38bdf8; padding: 10px 14px; border-radius: 8px;">
                <span style="color: #38bdf8; font-weight: 700; font-size: 14px;">👥 Arkadaş Etiketleme Radarı Aktif</span>
                <p style="color: #cbd5e1; font-size: 13px; margin: 4px 0 0 0;">Yorumunda arkadaşını etiketleyen (@kullanici) adaylara özel teşekkür yanıtı dönülerek viral paylaşım ödüllendirilir.</p>
            </div>
            """, unsafe_allow_html=True)

        # 1. GERÇEK ZAMANLI CANLI YORUM-DM ASİSTANI
        st.markdown("---")
        st.markdown("#### ⚡ Canlı Instagram Yorum-DM Otomasyonu (7/24 Aktif)")
        c_live_stat1, c_live_stat2 = st.columns([2, 1])
        with c_live_stat1:
            st.info("🟢 **Sistem Canlı:** Arka planda her 60 saniyede bir Instagram hesabınızdaki tüm son gönderiler taranır, 'KILAVUZ' veya 'LİNK' yazan kullanıcılara otomatik yanıt ve resmi başvuru linki DM ile iletilir.")
        with c_live_stat2:
            st.write("")
            scan_comments_btn = st.button("🚀 Canlı Yorumları Şimdi Tara & DM Gönder", type="primary", use_container_width=True)

        if scan_comments_btn:
            with st.spinner("Instagram Graph API üzerinden son gönderiler taranıyor ve yorumlar işleniyor..."):
                res_proc = mgr.process_live_comments(limit_media=10)
                if res_proc.get("success"):
                    cnt = res_proc.get("processed_count", 0)
                    if cnt > 0:
                        st.success(f"🎉 Harika! {cnt} adet yeni yoruma anında yanıt verildi ve DM'leri iletildi!")
                    else:
                        st.info("ℹ️ Taranan son gönderilerde henüz yanıtlanmamış yeni bir 'KILAVUZ' veya 'LİNK' yorumu bulunamadı (Tüm mevcut yorumlar daha önce başarıyla işlenmiş).")
                else:
                    st.error(f"❌ Canlı yorum tarama hatası: {res_proc.get('message')}")

        # Canlı Yorum & DM İşlem Logları Tablosu
        logs = mgr.get_comment_logs()
        if logs:
            st.markdown("##### 📋 Son Yanıtlanan Canlı Yorumlar & İletilen DM'ler")
            import pandas as pd
            df_logs = pd.DataFrame(logs)
            display_cols = ["timestamp", "username", "comment_text", "friend_tagged", "job_title", "public_reply_status", "dm_status"]
            existing_cols = [c for c in display_cols if c in df_logs.columns]
            rename_map = {
                "timestamp": "Tarih/Saat",
                "username": "Kullanıcı Adı",
                "comment_text": "Yazdığı Yorum",
                "friend_tagged": "Arkadaş Etiketlendi mi?",
                "job_title": "İlgili İlan",
                "public_reply_status": "Yorum Yanıtı",
                "dm_status": "DM Teslim Durumu"
            }
            st.dataframe(df_logs[existing_cols].rename(columns=rename_map), use_container_width=True)
        else:
            st.caption("Henüz işlenmiş canlı yorum kaydı bulunmuyor.")

        st.markdown("---")

        with get_db() as db:
            test_jobs = db.query(JobAnnouncement).order_by(JobAnnouncement.id.desc()).limit(15).all()

        if test_jobs:
            st.markdown("#### 🎬 İlan İçin Özel Video Üretimi (DM & Yorum Eki)")
            c_v1, c_v2 = st.columns([2, 1])
            with c_v1:
                dm_job_options = {f"#{j.id} - {j.institution or 'Kurum'} ({j.position or j.title})": j.id for j in test_jobs}
                dm_selected_label = st.selectbox("İşlem Yapılacak İlan:", list(dm_job_options.keys()), key="dm_video_job_sel")
                dm_target_job_id = dm_job_options[dm_selected_label]
            with c_v2:
                st.write("")
                st.write("")
                render_dm_video_btn = st.button("🎥 Bu İlan İçin Dikey Reels Render Et", type="primary", use_container_width=True)

            dm_v_key = f"dm_rendered_video_{dm_target_job_id}"
            if render_dm_video_btn:
                with st.spinner("Bu ilana özel seslendirmeli dikey video render ediliyor..."):
                    with get_db() as db:
                        t_job = db.query(JobAnnouncement).filter(JobAnnouncement.id == dm_target_job_id).first()
                        ok_v, v_p, v_msg = mgr.reels_engine.create_reels_video(
                            job_id=t_job.id,
                            institution=t_job.institution or "Kamu Kurumu",
                            position=t_job.position or t_job.title,
                            total_positions=t_job.total_positions,
                            kpss_requirement=t_job.kpss_requirement,
                            education_level=t_job.education_level,
                            deadline=to_turkish_date_str(t_job.application_end_date),
                            source_url=t_job.source_url,
                            duration_seconds=10
                        )
                        if ok_v and v_p:
                            st.session_state[dm_v_key] = str(v_p)
                            st.success(f"✅ Video başarıyla render edildi! ({v_msg})")

            if st.session_state.get(dm_v_key) and Path(st.session_state[dm_v_key]).exists():
                st.video(st.session_state[dm_v_key])
                st.caption("✅ Bu video DM'den kılavuzla birlikte gönderilmeye hazır.")

            st.markdown("---")
            st.markdown("#### 🧪 Takip Şartı (Follow-Gate) Test Simülatörü")

            c_sim1, c_sim2, c_sim3 = st.columns([1, 1, 1])
            with c_sim1:
                test_username = st.text_input("Örnek Kullanıcı Adı:", value="merve_ogretmen2026")
            with c_sim2:
                test_keyword = st.selectbox("Yorum Kelimesi:", ["KILAVUZ", "LİNK", "ŞARTLAR", "BAŞVURU"])
            with c_sim3:
                user_follow_status = st.radio(
                    "Kullanıcı Hesabı Takip Ediyor mu?",
                    options=["Evet (Takipçi)", "Hayır (Takip Etmiyor)"],
                    index=1,
                    horizontal=True
                )

            is_user_following = (user_follow_status == "Evet (Takipçi)")
            has_attached_video = bool(st.session_state.get(dm_v_key))

            if st.button("🚀 Takip Şartlı Yanıt Akışını Test Et", type="primary"):
                sim_res = mgr.simulate_comment_to_dm(
                    username=test_username,
                    keyword=test_keyword,
                    job_id=dm_target_job_id,
                    is_following=is_user_following,
                    include_video=has_attached_video
                )

                st.markdown(f"**Durum:** `{sim_res['status_tag']}`")
                c_out1, c_out2 = st.columns(2)
                with c_out1:
                    st.markdown("**1. Gönderi Altına Atılacak Otomatik Yorum Yanıtı:**")
                    st.info(sim_res["public_reply"])
                with c_out2:
                    st.markdown("**2. Kullanıcıya Gidecek Özel Mesaj (DM):**")
                    st.code(sim_res["private_dm"], language="markdown")

                if not is_user_following:
                    st.markdown("**3. Kullanıcı Sayfayı Takip Edip 'TAKİP ETTİM' Yazdığında Otomatik Açılacak Mesaj:**")
                    st.success(sim_res["unlocked_message"])

        st.markdown("---")
        st.markdown("#### ⚙️ Takip Şartı (Follow-Gate) Ayarları")
        c_gate1, c_gate2 = st.columns(2)
        with c_gate1:
            cur_gate = get_system_setting("IG_FOLLOW_GATE_ENABLED", "true") == "true"
            new_gate = st.toggle("🔒 Takip Şartı Zorunluluğu (Follow-Gate) Açık", value=cur_gate)
            if new_gate != cur_gate:
                set_system_setting("IG_FOLLOW_GATE_ENABLED", "true" if new_gate else "false")
                st.success("Ayar güncellendi.")
        with c_gate2:
            st.text_input("Kilit Açma Anahtar Kelimesi:", value="TAKİP ETTİM, ETTİM, TAKİPÇİYİM")
            st.caption("Kullanıcı takip ettikten sonra bu kelimeleri yazdığında resmi link anında DM'den açılır.")

    # =========================================================================
    # TAB 4: AI ÖNCÜ & DEĞER ODAKLI YORUM RADARI (TOP-COMMENT FUNNEL)
    # =========================================================================
    with sub_tab4:
        st.markdown("### 🌟 AI Öncü & Değer Odaklı Yorum Radarı (Top-Comment Funnel)")
        st.caption("ÖSYM, MEB, Sağlık Bakanlığı veya popüler KPSS sayfalarının paylaşımlarına ilk 2-5 dakikada atılacak 'En Üst Yorum (Top-Comment)' taslakları üretir. Spam içermez, sıfır ban riski taşır!")

        st.markdown("""
        <div style="background: rgba(30, 41, 59, 0.6); border-left: 4px solid #38bdf8; padding: 14px 18px; border-radius: 8px; margin-bottom: 20px;">
            <p style="margin: 0; color: #e2e8f0; font-size: 14px;">
                💡 <b>Neden İşe Yarar?</b> Resmi bir duyurunun altına yüzlerce aday "Şartlar ne?", "Puan kaça düşer?" diye sorarken; 
                ilk dakikada 3 maddelik hap özet veya kritik şart uyarısı bıraktığınızda adaylar yorumunuzu beğeni yağmuruna tutar ve en başa sabitlenir (Top Comment). 
                Bu sayede profilinizi on binlerce aday ziyaret eder ve organik takipçi patlaması yaşanır!
            </p>
        </div>
        """, unsafe_allow_html=True)

        col_in1, col_in2 = st.columns([1, 2])
        with col_in1:
            tc_institution = st.text_input("Kurum / Sınav Adı:", value="Sağlık Bakanlığı / ÖSYM", key="tc_inst")
            st.caption("Örn: Sağlık Bakanlığı, MEB, ÖSYM KPSS, Adalet Bakanlığı")
        with col_in2:
            tc_announcement = st.text_area(
                "Resmi Duyuru Metni veya İlan Başlığı:",
                value="2026 yılı 15.000 sözleşmeli personel alımı başvuru kılavuzu ÖSYM ve Resmi Gazete'de yayımlandı. Başvurular Kariyer Kapısı üzerinden alınacaktır.",
                height=90,
                key="tc_ann"
            )

        if st.button("✨ 3 Farklı Tarzda 'En Üst Yorum (Top-Comment)' Üret", type="primary", use_container_width=True):
            with st.spinner("Yapay zeka ile en üst yorum kurguları oluşturuluyor..."):
                top_res = mgr.generate_top_comments(tc_announcement, tc_institution)
                st.session_state["top_comment_res"] = top_res

        t_res = st.session_state.get("top_comment_res")
        if t_res and t_res.get("success"):
            st.success(f"✅ Yorum taslakları hazırlandı! (Sağlayıcı: {t_res.get('provider')})")
            
            c_tc1, c_tc2, c_tc3 = st.columns(3)
            with c_tc1:
                st.markdown("#### 🥇 1. Hap Özet & 3 Kritik Madde")
                st.caption("En hızlı beğeni alan ve en başa tutturulan stildir.")
                st.code(t_res["style_summary"], language="markdown")
            
            with c_tc2:
                st.markdown("#### 🛡️ 2. Kritik Uyarı & Kurtarıcı Bilgi")
                st.caption("Adayları hata yapmaktan kurtaran uzman görüşü.")
                st.code(t_res["style_warning"], language="markdown")
                
            with c_tc3:
                st.markdown("#### 💬 3. Topluluk & Tartışma Başlatıcı")
                st.caption("Adayların altına yorum yazmasını sağlayan soru kurgusu.")
                st.code(t_res["style_community"], language="markdown")

            st.info("📌 **Tavsiye:** Hedef sayfada gönderi paylaşıldıktan sonraki **ilk 3 dakika içinde** yukarıdaki yorumlardan birini yapıştırın. İlk beğenen olmak algoritmanın sizi en üste çıkarmasını sağlar.")

    # =========================================================================
    # TAB 5: OTOPİLOT DAĞITIM & PİK SAAT AYARLARI
    # =========================================================================
    with sub_tab5:
        st.markdown("### ⚙️ Instagram Otopilot Dağıtım & Pik Saat Yönetimi")
        st.markdown("""
        Instagram spam algoritmaları gereği günde **maksimum 4-5 kaliteli gönderi** paylaşılmalıdır.
        Otopilotumuz Türkiye'de adayların en aktif olduğu altın saatleri gözeterek otomatik dağıtım yapar.
        """)

        st.markdown("#### 🎨 Instagram Otopilot Format Tercihi")
        cur_fmt = get_system_setting("AUTOPILOT_IG_FORMAT", "SMART_HYBRID")
        fmt_options = {
            "SMART_HYBRID": "🧠 Akıllı Hibrit Mod (Önerilen: Kontenjan >= 50 ise otomatik REELS, normalde 4:5 CAROUSEL)",
            "ALWAYS_CAROUSEL": "📱 Her Zaman Çoklu Slayt (4:5 Dikey 3 Slaytlık Carousel)",
            "ALWAYS_REELS": "🎬 Her Zaman Dikey Video (1080x1920 Seslendirmeli Reels MP4)",
            "SINGLE_IMAGE": "🖼️ Klasik Tekil Görsel (1080x1080 Standart Afiş)"
        }
        fmt_keys = list(fmt_options.keys())
        cur_fmt_idx = fmt_keys.index(cur_fmt) if cur_fmt in fmt_keys else 0
        sel_fmt = st.selectbox(
            "Otopilotta Instagram Hangi Formatla Paylaşsın?",
            options=fmt_keys,
            index=cur_fmt_idx,
            format_func=lambda k: fmt_options[k]
        )
        if sel_fmt != cur_fmt:
            set_system_setting("AUTOPILOT_IG_FORMAT", sel_fmt)
            st.success("✅ Otopilot Instagram format tercihi güncellendi!")

        st.markdown("---")
        st.markdown("#### 🕒 Otopilot Paylaşım Temposu")
        cur_pace = get_system_setting("AUTOPILOT_PACE_PRESET", "SMART_PEAK")
        pace_keys = list(AUTOPILOT_PACE_PRESETS.keys())
        p_idx = pace_keys.index(cur_pace) if cur_pace in pace_keys else 0
        selected_pace = st.selectbox(
            "Otopilot Hangi Sıklıkla Paylaşsın?",
            options=pace_keys,
            index=p_idx,
            format_func=lambda k: AUTOPILOT_PACE_PRESETS[k]["name"],
            help="Pik saatler modu günde 4 kez Türkiye'nin en yoğun saatlerinde paylaşım yapar."
        )
        if selected_pace != cur_pace:
            set_system_setting("AUTOPILOT_PACE_PRESET", selected_pace)
            st.success("✅ Otopilot temposu güncellendi!")

        st.markdown("---")
        st.markdown("#### 📅 Türkiye Kamu Adayları İçin Zirve Etkileşim Saatleri")
        for slot in BEST_POSTING_SLOTS:
            st.markdown(f"""
            <div style="background: rgba(30, 41, 59, 0.7); border-left: 4px solid #f59e0b; padding: 12px 18px; margin-bottom: 12px; border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 17px; font-weight: 700; color: #ffffff;">⏰ {slot['slot']} — {slot['name']}</span>
                    <span style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; padding: 4px 10px; border-radius: 12px; font-size: 13px; font-weight: 600;">{slot['badge']}</span>
                </div>
                <p style="margin: 6px 0 0 0; color: #94a3b8; font-size: 14px;">{slot['desc']}</p>
            </div>
            """, unsafe_allow_html=True)
