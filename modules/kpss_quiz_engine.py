"""
KPSS Soru & Quiz Motoru (Yapay Zeka + Telegram Bot Poll + Instagram Minimalist Kart)
=====================================================================================
Kamu Personel Rehberi - Günlük KPSS Soru & Quiz Otomasyonu.
ÖSYM formatında Tarih, Coğrafya, Vatandaşlık, Türkçe, Matematik ve Güncel Bilgiler
konularından günlük 10-20 soru üretir, Telegram'da resmi Quiz Anket olarak paylaşır,
Instagram için kullanıcıların yoruma cevap yazmasını sağlayan (doğru cevabı gizli tutan),
renk cümbüşünden uzak, hırsızlığa karşı şeffaf filigranlı minimalist görsel üretir.
"""

import json
import os
import random
import re
import time
import textwrap
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import requests
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from config.settings import settings
from core.database import get_system_setting, set_system_setting


# =============================================================================
# DOĞRULANMIŞ ÖSYM KPSS SORU BANKASI (Zengin Çevrimdışı & Yedekleme Havuzu)
# =============================================================================
KPSS_VERIFIED_BANK: List[Dict[str, Any]] = [
    {
        "subject": "KPSS Tarih",
        "topic": "İlk Türk Devletleri",
        "question": "İslamiyet öncesi Türk devletlerinde devlet işlerinin görüşülüp karara bağlandığı meclise ne ad verilirdi?",
        "options": ["Toy (Kurultay)", "Tigin", "Yarlığ", "Ayukı", "Tudun"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Toy (Kurultay). İlk Türk devletlerinde hükümdarın başkanlığında toplanan danışma meclisidir."
    },
    {
        "subject": "KPSS Tarih",
        "topic": "Osmanlı Kültür ve Medeniyeti",
        "question": "Osmanlı Devleti'nde ilk resmî gazete olan 'Takvim-i Vekayi' hangi padişah döneminde yayımlanmaya başlamıştır?",
        "options": ["II. Mahmud", "III. Selim", "Abdülmecid", "II. Abdülhamid", "I. Mahmud"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) II. Mahmud. Takvim-i Vekayi 1831 yılında II. Mahmud devrinde ilk resmî gazete olarak yayımlanmıştır."
    },
    {
        "subject": "KPSS Tarih",
        "topic": "Milli Mücadele Dönemi",
        "question": "Mustafa Kemal Paşa'nın 'Geldikleri gibi giderler' sözünü söylediği yer aşağıdakilerden hangisidir?",
        "options": ["İstanbul Boğazı (Kartal İstimbotu)", "Samsun Tütün İskelesi", "Amasya Saraydüzü Kışlası", "Erzurum Kongre Binası", "Sivas Lisesi"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) İstanbul Boğazı. 13 Kasım 1918'de İtilaf Donanması İstanbul'a girdiğinde Kartal istimbotunda söylenmiştir."
    },
    {
        "subject": "KPSS Tarih",
        "topic": "Atatürk İnkılapları",
        "question": "Aşağıdakilerden hangisi Türkiye'de saltanatın kaldırılmasının (1 Kasım 1922) doğrudan bir sonucudur?",
        "options": ["Lozan Barış Konferansı'na TBMM'nin tek temsilci olarak katılması", "Halifeliğin hemen o gün kaldırılması", "Ankara'nın aynı gün başkent yapılması", "Çok partili hayata kesin olarak geçilmesi", "Medeni Kanun'un kabul edilmesi"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Lozan Konferansı. İtilaf Devletleri'nin ikilik çıkarma planını engellemek için saltanat kaldırılmıştır."
    },
    {
        "subject": "KPSS Coğrafya",
        "topic": "Türkiye'nin Fiziki Coğrafyası",
        "question": "Türkiye'de kalker (kireçtaşı) arazilerin yaygın olmasına bağlı olarak karstik şekiller en fazla hangi bölgede görülür?",
        "options": ["Akdeniz Bölgesi (Teke ve Taşeli)", "Güneydoğu Anadolu Bölgesi", "Doğu Karadeniz Bölümü", "Ergene Havzası", "İç Anadolu (Konya Bölümü)"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Akdeniz. Teke ve Taşeli platolarında kalkerli kayaçlar yoğun olduğundan lapyalar, dolinler ve mağaralar yaygındır."
    },
    {
        "subject": "KPSS Coğrafya",
        "topic": "Türkiye'nin İklimi ve Bitki Örtüsü",
        "question": "Türkiye'de yıllık yağış miktarının en az olduğu ve rüzgâr erozyonunun en belirgin hissedildiği alan hangisidir?",
        "options": ["Tuz Gölü Çevresi ve Konya Kapalı Havzası", "Rize Kıyı Şeridi", "Yıldız Dağları Yöresi", "Hakkâri Yüksek Dağlık Alanı", "Menteşe Yöresi"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Tuz Gölü Çevresi. Etrafı dağlarla çevrili kapalı havza özelliği nedeniyle yıllık yağış 300 mm civarındadır."
    },
    {
        "subject": "KPSS Vatandaşlık",
        "topic": "Temel Hukuk Kavramları",
        "question": "Hukuk kurallarının diğer sosyal düzen kurallarından (din, ahlak, görgü) en temel ayırt edici farkı nedir?",
        "options": ["Maddi (Devlet Gücüne Dayalı) Yaptırımlı Olması", "Yazılı Olması", "Toplum Düzenini Sağlaması", "Sürekli Olması", "Genel Olması"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Maddi Yaptırım. Hukuk kurallarına uyulmaması halinde devletin zorlama gücü (ceza, cebri icra, tazminat) devreye girer."
    },
    {
        "subject": "KPSS Vatandaşlık",
        "topic": "1982 Anayasası - Yasama",
        "question": "1982 Anayasası'na göre Türkiye Büyük Millet Meclisi'nin üye tamsayısı kaçtır?",
        "options": ["600", "550", "450", "500", "650"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) 600. 2017 Anayasa değişikliği ile TBMM milletvekili sayısı 550'den 600'e çıkarılmıştır."
    },
    {
        "subject": "KPSS Vatandaşlık",
        "topic": "1982 Anayasası - Yürütme",
        "question": "1982 Anayasası'na göre Cumhurbaşkanlığı Kararnameleri ile aşağıdakilerden hangisi doğrudan düzenlenemez?",
        "options": ["Kişi Hakları ve Ödevleri ile Siyasi Haklar", "Bakanlıkların Kuruluşu", "Devlet Memurlarının Atanma Usulleri", "Üst Kademe Kamu Yöneticileri", "Milli Güvenlik Kurulu Genel Sekreterliği"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Kişi Hakları ve Siyasi Haklar. Anayasa md. 104'e göre temel haklar ve siyasi haklar CBK ile düzenlenemez."
    },
    {
        "subject": "KPSS Türkçe",
        "topic": "Yazım Kuralları",
        "question": "Aşağıdaki cümlelerin hangisinde 'ki' bağlacının yazımıyla ilgili bir YAZIM YANLIŞI yapılmıştır?",
        "options": ["Bilmemki nasıl anlatsam bu durumu.", "Mademki gelmedin, ben de tek başıma gittim.", "Evdeki hesap çarşıya uymadı.", "Oysaki her şey çok güzel başlamıştı.", "Seninki yine ortalıkta görünmüyor."],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Bilmemki. Fiillerden sonra gelen 'ki' bağlaçtır ve ayrı yazılır ('Bilmem ki'). 'Mademki' ve 'Oysaki' ise kalıplaşmış bitişiktir (SOMBAHÇEMİ)."
    },
    {
        "subject": "KPSS Güncel Bilgiler",
        "topic": "Genel Kültür",
        "question": "Cumhuriyet döneminde 'Bozkırın Tezenesi' unvanıyla anılan ünlü halk ozanımız kimdir?",
        "options": ["Neşet Ertaş", "Aşık Veysel", "Mahzuni Şerif", "Murat Çobanoğlu", "Aşık Daimi"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Neşet Ertaş. Yaşar Kemal tarafından 'Bozkırın Tezenesi' olarak adlandırılmış büyük Türk halk ozanıdır."
    },
    {
        "subject": "KPSS Tarih",
        "topic": "Osmanlı Tarihi",
        "question": "Osmanlı Devleti'nde sadrazam sefere çıktığında yerine başkentte vekalet eden görevli kimdir?",
        "options": ["Sadaret Kaymakamı", "Nişancı", "Reisülküttab", "Defterdar", "Kaptanıderya"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Sadaret Kaymakamı. Sadrazam orduyla sefere çıktığında İstanbul'daki işleri yürütmek için yerine Sadaret Kaymakamı bırakılırdı."
    },
    {
        "subject": "KPSS Coğrafya",
        "topic": "Türkiye'nin Madenleri",
        "question": "Dünya rezervlerinin yaklaşık %72'sine sahip olduğumuz ve Balıkesir (Bigadiç), Kütahya (Emet), Eskişehir (Kırka)'de çıkarılan maden hangisidir?",
        "options": ["Bor", "Krom", "Bakır", "Boksit", "Demir"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Bor Mineralleri. Türkiye dünya bor rezervlerinin lideridir ve en büyük yatakları Kırka, Bigadiç, Emet ve Kestelek'tedir."
    },
    {
        "subject": "KPSS Vatandaşlık",
        "topic": "İdare Hukuku",
        "question": "Aşağıdakilerden hangisi Türkiye'de Anayasa Mahkemesi'ne doğrudan iptal davası (Soyut Norm Denetimi) açmaya yetkili DEĞİLDİR?",
        "options": ["Danıştay Başkanı", "Cumhurbaşkanı", "TBMM'de En Fazla Üyeye Sahip Birinci Siyasi Parti Grubu", "TBMM'de En Fazla Üyeye Sahip İkinci Siyasi Parti Grubu", "TBMM Üye Tamsayısının En Az Beşte Biri (120 Milletvekili)"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Danıştay Başkanı. Anayasa md. 150 uyarınca sadece CB, en çok üyeye sahip ilk iki parti grubu ve 1/5 milletvekili doğrudan iptal davası açabilir."
    },
    {
        "subject": "KPSS Tarih",
        "topic": "I. Dünya Savaşı",
        "question": "Osmanlı Devleti'nin I. Dünya Savaşı'nda toprak kazandığı TEK cephe aşağıdakilerden hangisidir?",
        "options": ["Kafkas Cephesi", "Çanakkale Cephesi", "Kanal Cephesi", "Irak Cephesi", "Hicaz-Yemen Cephesi"],
        "correct_option_id": 0,
        "explanation": "Doğru Cevap: A) Kafkas Cephesi. Brest-Litovsk Antlaşması (1918) ile Kars, Ardahan ve Batum (Elviye-i Selase) geri alınmıştır."
    }
]


class KPSSQuizEngine:
    """
    KPSS Soru Üretim, Telegram Quiz ve Instagram Görsel Oluşturma Motoru.
    """

    HISTORY_FILE = Path("data/kpss_quiz_history.json")

    def __init__(self):
        self.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load_history()

    def _load_history(self) -> List[str]:
        if self.HISTORY_FILE.exists():
            try:
                with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        else:
            self.history = []
        return self.history

    def _save_history(self):
        try:
            with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history[-500:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Soru geçmişi kaydedilemedi: {e}")

    @staticmethod
    def shuffle_question(q_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sorunun şıklarını rastgele karıştırır ve doğru şıkkı (A, B, C, D, E)
        her seferinde farklı bir konuma atar. Açıklama metnindeki şık harfini de günceller.
        Böylece doğru cevabın hep 'A' çıkması engellenir.
        """
        options = [str(o).strip() for o in q_entry.get("options", [])[:5]]
        if len(options) < 2:
            return q_entry

        letters = ["A", "B", "C", "D", "E"]
        clean_options = []
        for opt in options:
            t = opt
            for l in letters:
                for p in [f"{l})", f"{l}]", f"{l} -", f"{l}:"]:
                    if t.startswith(p):
                        t = t[len(p):].strip()
            clean_options.append(t)

        old_corr_idx = int(q_entry.get("correct_option_id", 0))
        if old_corr_idx >= len(clean_options):
            old_corr_idx = 0
        correct_text = clean_options[old_corr_idx]

        # Şıkları rastgele karıştır
        random.shuffle(clean_options)
        new_corr_idx = clean_options.index(correct_text)
        new_letter = letters[new_corr_idx]

        # Açıklama metnindeki harf referansını güncelle
        expl = q_entry.get("explanation", "")
        expl = re.sub(r"Doğru Cevap:\s*[A-E][\)\s]*(?:şıkkı)?", f"Doğru Cevap: {new_letter}) ", expl, flags=re.IGNORECASE)

        return {
            **q_entry,
            "options": clean_options,
            "correct_option_id": new_corr_idx,
            "explanation": expl
        }

    def generate_ai_questions(self, count: int = 10, target_subjects: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Aktif LLM (NVIDIA, Groq veya Özel) üzerinden ÖSYM standartlarında soru üretir.
        API yanıt vermezse doğrulanmış soru havuzundan otomatik tamamlar.
        """
        all_subjects = ["KPSS Tarih", "KPSS Coğrafya", "KPSS Vatandaşlık", "KPSS Türkçe", "KPSS Genel Kültür"]
        selected_subjects = target_subjects or all_subjects

        generated_questions: List[Dict[str, Any]] = []

        # 1. LLM Çağrısı Denemesi
        try:
            from ai.llm_client import LLMClient
            client = LLMClient()
            active_provider = client.active_provider

            prompt_content = f"""Sen ÖSYM KPSS (Kamu Personel Seçme Sınavı) soru hazırlama komisyonu uzmanısın.
Adaylar için {count} adet birbirinden tamamen farklı, kaliteli, yanıltıcı çeldiricileri olan, güncel müfredata uygun 5 şıklı KPSS sorusu hazırla.
Dönüş formatın SADECE geçerli bir JSON listesi (array of objects) olmalıdır. Hiçbir markdown tırnağı (```json gibi) veya açıklama ekleme.

Format:
[
  {{
    "subject": "KPSS Tarih / KPSS Coğrafya / KPSS Vatandaşlık / vb.",
    "question": "Soru kökü ve metni (maksimum 250 karakter)",
    "options": ["A) Şık 1", "B) Şık 2", "C) Şık 3", "D) Şık 4", "E) Şık 5"],
    "correct_option_id": 0,
    "explanation": "Doğru cevabın ÖSYM standartlarında net ve öğretici açıklaması (maksimum 180 karakter)"
  }}
]

Kural: Konuları dengeli dağıt ({', '.join(selected_subjects)}). Her sorunun doğru cevabı 0, 1, 2, 3 veya 4 indeksine karşılık gelmelidir."""

            raw_reply = client._dispatch_completion(active_provider, prompt_content)
            if raw_reply:
                items = []
                if isinstance(raw_reply, list):
                    items = raw_reply
                elif isinstance(raw_reply, dict):
                    for v in raw_reply.values():
                        if isinstance(v, list):
                            items = v
                            break

                for it in items:
                    if isinstance(it, dict) and "question" in it and "options" in it and len(it.get("options", [])) >= 4:
                        clean_options = [str(o).strip() for o in it["options"][:5]]
                        while len(clean_options) < 5:
                            clean_options.append("Belirtilmedi")
                        correct_id = int(it.get("correct_option_id", 0))
                        if correct_id < 0 or correct_id >= len(clean_options):
                            correct_id = 0

                        q_entry = {
                            "subject": it.get("subject", "KPSS Genel"),
                            "question": it["question"].strip(),
                            "options": clean_options,
                            "correct_option_id": correct_id,
                            "explanation": it.get("explanation", f"Doğru cevap: {clean_options[correct_id]}")[:190]
                        }
                        # Şıkları rastgele konumlara karıştır (hep A olmasın)
                        shuffled_entry = self.shuffle_question(q_entry)
                        generated_questions.append(shuffled_entry)
                        self.history.append(shuffled_entry["question"])

            if generated_questions:
                logger.info(f"Yapay zeka başarıyla {len(generated_questions)} adet KPSS sorusu üretti.")
        except Exception as e:
            logger.warning(f"AI soru üretimi başarısız oldu veya API kapalı: {e}")

        # 2. Eksik kalanları veya API yoksa Yedek Havuzdan Doldur
        if len(generated_questions) < count:
            needed = count - len(generated_questions)
            pool = [q for q in KPSS_VERIFIED_BANK if q["question"] not in self.history]
            if not pool:
                pool = KPSS_VERIFIED_BANK.copy()
            random.shuffle(pool)

            for q in pool[:needed]:
                # Havuzdaki soruları da rastgele karıştırarak ekle (doğru cevap A, B, C, D, E dağılsın)
                shuffled_pool_q = self.shuffle_question(q)
                generated_questions.append(shuffled_pool_q)
                self.history.append(shuffled_pool_q["question"])

        self._save_history()
        return generated_questions[:count]

    def send_quiz_to_telegram(
        self,
        question_data: Dict[str, Any],
        channel_id: Optional[str] = None,
        bot_token: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Telegram kanalına native Quiz Poll (Anket) gönderir.
        Kullanıcı şıkka bastığında:
        - Doğruysa: Yeşil tik ve konfeti patlar.
        - Yanlışsa: Seçilen şık kırmızı çarpı, doğru şık yeşil tik olur ve çözüm açıklaması açılır!
        """
        token = bot_token or settings.active_telegram_bot_token
        target_channel = channel_id or settings.active_telegram_channel_id or "@kamupersonelrehberi"

        if not token or token == "your_telegram_bot_token_here":
            return False, "Telegram Bot Token tanımlı değil."
        if not target_channel:
            return False, "Hedef Telegram Kanalı belirtilmedi."

        q_text = question_data.get("question", "")
        options = question_data.get("options", [])
        correct_id = int(question_data.get("correct_option_id", 0))
        explanation = question_data.get("explanation", "")
        subject = question_data.get("subject", "KPSS")

        # Telegram Poll Sınırları: Soru max 300, Şık max 100, Açıklama max 200 karakter
        poll_question = f"[{subject}] {q_text}"
        if len(poll_question) > 295:
            poll_question = poll_question[:290] + "..."

        safe_options = []
        for opt in options[:5]:
            safe_opt = str(opt).strip()
            if len(safe_opt) > 95:
                safe_opt = safe_opt[:92] + "..."
            safe_options.append(safe_opt)

        safe_expl = str(explanation).strip()
        if len(safe_expl) > 195:
            safe_expl = safe_expl[:190] + "..."

        url = f"https://api.telegram.org/bot{token}/sendPoll"
        payload = {
            "chat_id": target_channel,
            "question": poll_question,
            "options": json.dumps(safe_options),
            "is_anonymous": True,
            "type": "quiz",
            "correct_option_id": correct_id,
            "explanation": safe_expl,
            "explanation_parse_mode": "HTML"
        }

        try:
            res = requests.post(url, data=payload, timeout=20)
            if res.status_code == 200:
                logger.info(f"Quiz başarıyla Telegram kanalına ({target_channel}) gönderildi.")
                return True, "Quiz başarıyla Telegram kanalında yayınlandı!"
            else:
                err_msg = res.text
                logger.error(f"Telegram sendPoll hatası ({res.status_code}): {err_msg}")
                return False, f"Telegram Hatası: {err_msg}"
        except Exception as e:
            logger.error(f"Telegram bağlantı hatası: {e}")
            return False, f"Bağlantı Hatası: {str(e)}"

    def generate_instagram_quiz_card(
        self,
        question_data: Dict[str, Any],
        output_dir: str = "graphics/output"
    ) -> str:
        """
        Instagram için etkileşimi (yorumları) tavan yaptıran,
        kesinlikle doğru cevabı açık etmeyen, renk cümbüşünden uzak,
        sade mat antrasit, kristal beyaz tipografi ve hırsızlığa karşı
        şeffaf koruma filigranı (watermark) içeren 1080x1350 soru kartı üretir.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        width, height = 1080, 1350
        timestamp = int(time.time())
        file_card = out_path / f"ig_kpss_quiz_{timestamp}.png"

        font_path = "graphics/assets/fonts/font_bold.ttf"
        font_regular_path = "graphics/assets/fonts/font.ttf"

        def get_font(size: int, bold: bool = False):
            p = font_path if bold else font_regular_path
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                return ImageFont.load_default()

        # 1. Mat Koyu Antrasit / Gece Slate Zemin (#12161A)
        bg_color = (18, 22, 26)
        img = Image.new("RGBA", (width, height), (*bg_color, 255))

        # 2. HIRSIZLIĞA KARŞI ŞEFFAF FİLİGRAN (WATERMARK)
        # Okumayı engellemeyecek, ancak çalınmayı önleyecek %6 şeffaflıkta marka filigranı
        watermark_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        wm_draw = ImageDraw.Draw(watermark_layer)
        wm_font = get_font(42, bold=True)
        wm_color = (255, 255, 255, 14)  # ~5% çok hafif beyaz filigran
        # Çapraz 3 satır filigran damgası
        wm_draw.text((width // 2, 420), "@kamupersonelrehberi", font=wm_font, fill=wm_color, anchor="mm")
        wm_draw.text((width // 2, 850), "@kamupersonelrehberi", font=wm_font, fill=wm_color, anchor="mm")
        wm_draw.text((width // 2, 1180), "kamupersonelrehberi.com", font=wm_font, fill=wm_color, anchor="mm")
        img = Image.alpha_composite(img, watermark_layer)

        draw = ImageDraw.Draw(img)

        # 3. İnce Üst Çerçeve Çizgisi
        draw.line([(80, 40), (width - 80, 40)], fill=(38, 48, 60), width=1)

        # 4. Üst Rozet: [ KPSS GÜNLÜK SORU ] (Zarif oval pill)
        pill_w, pill_h = 320, 48
        pill_x = (width - pill_w) // 2
        pill_y = 65
        draw.rounded_rectangle(
            [(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)],
            radius=24,
            fill=(26, 33, 42),
            outline=(71, 85, 105),
            width=1
        )
        font_pill = get_font(22, bold=True)
        draw.text((width // 2, pill_y + pill_h // 2), "KPSS GÜNLÜK SORU", font=font_pill, fill=(203, 213, 225), anchor="mm")

        # 5. Konu Başlığı (Örn: "TARİH GÜNLÜK SORU")
        subject = question_data.get("subject", "GENEL KÜLTÜR").upper().replace("KPSS ", "")
        font_sub = get_font(30, bold=True)
        draw.text((width // 2, 155), f"{subject} GÜNLÜK SORU", font=font_sub, fill=(148, 163, 184), anchor="mm")

        # 6. Soru Metni (Büyük, Okunaklı, Kristal Beyaz, Kusursuz Boşluklu)
        q_text = question_data.get("question", "")
        for em in ["🎯", "❓", "📌", "💡", "✍️", "📢"]:
            q_text = q_text.replace(em, "")
        q_text = q_text.strip()

        wrapped_q = textwrap.fill(q_text, width=38)
        font_q = get_font(38, bold=True)

        q_start_y = 240
        draw.text((width // 2, q_start_y), wrapped_q, font=font_q, fill=(255, 255, 255), spacing=18, align="center", anchor="ma")

        # Şıkların başlangıç konumunu dinamik ayarla
        q_line_count = len(wrapped_q.split("\n"))
        base_options_y = q_start_y + (q_line_count * 58) + 45
        if base_options_y < 580:
            base_options_y = 580

        # 7. Şıklar (A, B, C, D, E) — NÖTR, ŞIK ÇERÇEVELİ KUTULAR (DOĞRU CEVAP ASLA GÖSTERİLMEZ!)
        options = question_data.get("options", [])
        opt_letters = ["A", "B", "C", "D", "E"]
        opt_h = 88
        opt_spacing = 16
        opt_y = base_options_y

        font_letter = get_font(32, bold=True)
        font_opt_text = get_font(30, bold=False)

        for i, opt in enumerate(options[:5]):
            letter = opt_letters[i]
            clean_text = str(opt).strip()
            for l in opt_letters:
                if clean_text.startswith(f"{l})") or clean_text.startswith(f"{l} -") or clean_text.startswith(f"{l}]"):
                    clean_text = clean_text[2:].strip(" -)]")

            # Şık Kartı Kutusu (Sade, mat koyu zemin, ince çerçeve)
            draw.rounded_rectangle(
                [(90, opt_y), (width - 90, opt_y + opt_h)],
                radius=18,
                fill=(22, 28, 36),
                outline=(51, 65, 82),
                width=2
            )

            # Harf Etiketi (Örn: "A]")
            draw.text((130, opt_y + opt_h // 2), f"{letter}]", font=font_letter, fill=(148, 163, 184), anchor="lm")
            # Şık Metni (Sade kristal beyaz)
            draw.text((185, opt_y + opt_h // 2), clean_text[:46], font=font_opt_text, fill=(241, 245, 249), anchor="lm")

            opt_y += opt_h + opt_spacing

        # 8. Alt Çağrı Alanı (Call to Action - Yorum Etkileşimi)
        cta_y = height - 110
        draw.line([(100, cta_y - 35), (width - 100, cta_y - 35)], fill=(32, 42, 54), width=1)

        font_cta = get_font(30, bold=True)
        font_handle = get_font(22, bold=False)

        draw.text((width // 2, cta_y), "Cevabınızı yorumlara yazın >> A, B, C, D, E", font=font_cta, fill=(226, 232, 240), anchor="mm")
        draw.text((width // 2, cta_y + 42), "@kamupersonelrehberi • Çözüm ve açıklama Telegram kanalımızda", font=font_handle, fill=(100, 116, 139), anchor="mm")

        # RGB formatına dönüştürüp kaydet
        final_rgb = img.convert("RGB")
        final_rgb.save(str(file_card), "PNG")
        logger.info(f"Minimalist filigranlı Instagram quiz kartı oluşturuldu: {file_card.name}")

        return str(file_card)

    def publish_automated_quiz(
        self,
        channel_id: Optional[str] = None,
        generate_card: bool = True
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[str]]:
        """
        Otopilot için 1 adet taze KPSS sorusu üretir, Telegram'da quiz anket olarak yayınlar
        ve Instagram için minimalist filigranlı kart görseli üretir.
        Dönüş: (Başarılı mı, Mesaj, Soru Sözlüğü, Kart Dosya Yolu)
        """
        fresh_questions = self.generate_ai_questions(count=1)
        if not fresh_questions:
            return False, "Soru üretilemedi.", None, None

        q_item = fresh_questions[0]
        succ, msg = self.send_quiz_to_telegram(q_item, channel_id=channel_id)

        card_path = None
        if generate_card:
            try:
                card_path = self.generate_instagram_quiz_card(q_item)
            except Exception as ce:
                logger.warning(f"Otopilot Instagram kartı oluşturulamadı: {ce}")

        # Başarılı paylaşımı log kaydına ekle
        if succ:
            today_str = datetime.now().strftime("%Y-%m-%d")
            log_entry = {
                "date": today_str,
                "time": datetime.now().strftime("%H:%M:%S"),
                "subject": q_item.get("subject", "KPSS"),
                "question": q_item.get("question", "")[:80],
                "card_path": card_path
            }
            try:
                hist_log = Path("data/kpss_daily_autopilot_log.json")
                cur_logs = []
                if hist_log.exists():
                    with open(hist_log, "r", encoding="utf-8") as f:
                        cur_logs = json.load(f)
                cur_logs.append(log_entry)
                with open(hist_log, "w", encoding="utf-8") as f:
                    json.dump(cur_logs[-200:], f, ensure_ascii=False, indent=2)
            except Exception as log_err:
                logger.debug(f"Otopilot log kaydı uyarısı: {log_err}")

        return succ, msg, q_item, card_path

    def get_autopilot_stats(self) -> Dict[str, Any]:
        """
        Günün otopilot istatistiklerini (bugün kaç soru atıldı, hedef nedir, durum nedir) döndürür.
        """
        enabled = get_system_setting("AUTO_KPSS_QUIZ_ENABLED", "true") == "true"
        target_daily = int(get_system_setting("AUTO_KPSS_QUIZ_DAILY_TARGET", "10"))
        today_str = datetime.now().strftime("%Y-%m-%d")

        sent_today = 0
        last_sent_time = "Henüz gönderilmedi"
        last_question = ""
        last_card = None

        hist_log = Path("data/kpss_daily_autopilot_log.json")
        if hist_log.exists():
            try:
                with open(hist_log, "r", encoding="utf-8") as f:
                    cur_logs = json.load(f)
                for entry in cur_logs:
                    if entry.get("date") == today_str:
                        sent_today += 1
                        last_sent_time = entry.get("time", "")
                        last_question = entry.get("question", "")
                        last_card = entry.get("card_path")
            except Exception:
                pass

        return {
            "enabled": enabled,
            "target_daily": target_daily,
            "sent_today": sent_today,
            "last_sent_time": last_sent_time,
            "last_question": last_question,
            "last_card": last_card
        }
