# -*- coding: utf-8 -*-
"""Interfaz de envío (pluggable). Implementá send() para agregar otro proveedor."""
from abc import ABC, abstractmethod

class Sender(ABC):
    @abstractmethod
    def send(self, to_email: str, to_name: str, subject: str, html: str, text: str,
             from_override=None) -> str:
        """Envía un mail. Devuelve el message_id. Lanza excepción si falla.
        from_override=(email, name): usa ESE remitente (para que la firma coincida)."""
        raise NotImplementedError

    def next_from(self):
        """Devuelve el próximo remitente (email, name) SIN enviar. Permite firmar el
        cuerpo con el mismo nombre que va en el From. Default: el From de siempre."""
        return (None, None)
