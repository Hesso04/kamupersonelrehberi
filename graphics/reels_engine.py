"""
Instagram Reels Otomatik Dikey Video Motoru (v1.0 Ultra HD MP4)
==============================================================
Resmi kamu alım ilanlarını 9:16 (1080x1920) formatında dinamik,
hareketli ve profesyonel Türkçe seslendirmeli Instagram Reels videosuna dönüştürür.
- Tamamen yerel ve %100 ÜCRETSİZ çalışır (FFmpeg + Edge-TTS).
- Algoritmayı patlatmak için 8-12 saniyelik kusursuz loop (başa sarma) yapısına sahiptir.
"""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from loguru import logger

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

from config.settings import settings
from graphics.generator import JobCardGenerator, to_turkish_date_str


class ReelsVideoEngine:
    """
    Kamu İlanları için Otomatik Reels ve TikTok Video Üretim Motoru.
    """

    def __init__(self):
        self.output_dir = Path("graphics/output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scratch_dir = Path("graphics/scratch")
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.card_generator = JobCardGenerator()

    @property
    def ffmpeg_exe(self) -> Optional[str]:
        if imageio_ffmpeg:
            try:
                return imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                pass
        return "ffmpeg"

    async def generate_voiceover(
        self,
        text: str,
        output_path: Path,
        voice: str = "tr-TR-AhmetNeural"
    ) -> bool:
        """Edge-TTS ile doğal insan sesinde Türkçe seslendirme üretir."""
        if not edge_tts:
            logger.warning("edge-tts kütüphanesi yüklü değil, seslendirme atlanıyor.")
            return False

        try:
            communicate = edge_tts.Communicate(text=text, voice=voice)
            await communicate.save(str(output_path))
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as e:
            logger.error(f"Reels seslendirme üretilemedi: {e}")
            return False

    def build_voice_script(
        self,
        institution: str,
        position: str,
        total_positions: Optional[int],
        kpss_requirement: Optional[str],
        deadline: Optional[str]
    ) -> str:
        """Algoritmayı yakalayan 8-10 saniyelik vurucu Reels seslendirme metni oluşturur."""
        tot = total_positions or 1
        pos_clean = position.split("-")[0].strip() if position else "Personel Alımı"
        d_str = to_turkish_date_str(deadline)
        
        script = (
            f"Flaş kamu ilanı! {institution}, {tot:,} kişilik {pos_clean} kadrosu açtı! "
            f"Son başvuru {d_str}. "
            f"Başvuru linki ve kılavuz için yoruma KILAVUZ yazın, anında DM kutunuza gelsin!"
        ).replace(",", ".")
        return script

    def create_reels_video(
        self,
        job_id: int,
        institution: str,
        position: str,
        total_positions: Optional[int] = None,
        kpss_requirement: Optional[str] = None,
        education_level: Optional[str] = None,
        deadline: Optional[str] = None,
        source_url: Optional[str] = None,
        theme: Optional[str] = None,
        title: str = "",
        voice: str = "tr-TR-AhmetNeural",
        duration_seconds: int = 10
    ) -> Tuple[bool, Optional[Path], str]:
        """
        Tam teşekküllü 1080x1920 MP4 Reels videosu üretir.
        Dönüş: (Başarılı mı, Video Dosya Yolu, Mesaj)
        """
        ffmpeg_bin = self.ffmpeg_exe
        if not ffmpeg_bin:
            return False, None, "FFmpeg çalıştırıcısı bulunamadı."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_filename = f"reels_{job_id}_{timestamp}.mp4"
        video_path = self.output_dir / video_filename
        voice_path = self.scratch_dir / f"voice_{job_id}_{timestamp}.mp3"

        # 1. 9:16 Dikey Story/Reels Görselini Oluştur
        try:
            story_img_path = self.card_generator.generate_story_card(
                job_id=job_id,
                institution=institution,
                position=position,
                total_positions=total_positions,
                kpss_requirement=kpss_requirement,
                education_level=education_level,
                deadline=deadline,
                source_url=source_url,
                theme=theme,
                title=title
            )
        except Exception as ge:
            return False, None, f"Reels görseli üretilemedi: {ge}"

        # 2. Türkçe Seslendirme Üret
        voice_script = self.build_voice_script(
            institution=institution,
            position=position,
            total_positions=total_positions,
            kpss_requirement=kpss_requirement,
            deadline=deadline
        )

        has_voice = False
        try:
            asyncio.run(self.generate_voiceover(voice_script, voice_path, voice=voice))
            has_voice = voice_path.exists() and voice_path.stat().st_size > 0
        except Exception as ve:
            logger.warning(f"Seslendirme adımında hata: {ve}")

        # 3. FFmpeg ile Ken Burns Dinamik Zoom Efektli MP4 Render
        # 1080x1920 dikey video, 30 FPS, H.264 video codec
        total_frames = duration_seconds * 30
        vf_filter = (
            f"scale=1080:1920,"
            f"zoompan=z='min(zoom+0.0006,1.06)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
        )

        cmd = [
            ffmpeg_bin,
            "-y",
            "-loop", "1",
            "-i", str(story_img_path),
        ]

        if has_voice:
            cmd.extend([
                "-i", str(voice_path),
                "-c:a", "aac",
                "-b:a", "128k",
            ])

        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-vf", vf_filter,
            "-t", str(duration_seconds),
            str(video_path)
        ])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            if res.returncode == 0 and video_path.exists():
                size_kb = video_path.stat().st_size // 1024
                logger.info(f"Reels videosu başarıyla oluşturuldu: {video_path} ({size_kb} KB)")
                return True, video_path, f"Reels videosu başarıyla üretildi ({size_kb} KB, {duration_seconds} sn)"
            else:
                err_msg = res.stderr.decode("utf-8", errors="ignore")[:300]
                logger.error(f"FFmpeg render hatası: {err_msg}")
                return False, None, f"Video render hatası: {err_msg}"
        except Exception as fe:
            logger.error(f"FFmpeg çalıştırma istisnası: {fe}")
            return False, None, f"FFmpeg çalıştırma hatası: {fe}"
