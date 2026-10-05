from abc import ABC, abstractmethod
from typing import Tuple
from core.models import JobAnnouncement


class BasePublisher(ABC):
    """Tüm sosyal medya ve mesajlaşma yayıncıları için temel soyut sınıf"""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name

    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """Admin panelinden kanal/hesap bağlantısını test eder."""
        pass

    @abstractmethod
    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """İlanı metin ve görseliyle birlikte platforma gönderir."""
        pass
