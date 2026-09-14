# -*- coding: utf-8 -*-
"""Interfaz de envío (pluggable). Implementá send() para agregar otro proveedor."""
from abc import ABC, abstractmethod

class Sender(ABC):
    @abstractmethod
    def send(self, to_email: str, to_name: str, subject: str, html: str, text: str) -> str:
        """Envía un mail. Devuelve el message_id. Lanza excepción si falla."""
        raise NotImplementedError
