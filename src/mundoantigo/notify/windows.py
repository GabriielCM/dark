"""Toast do Windows com som (biblioteca windows-toasts, extra `windows`).

O clique abre a pagina da producao no navegador: o link vai como ativacao
por protocolo, que o proprio Windows resolve, mesmo depois que o processo que
mostrou o aviso terminou.
"""

from __future__ import annotations

import logging

from .base import Notice

log = logging.getLogger(__name__)


class WindowsToastNotifier:
    name = "windows"

    def __init__(
        self,
        *,
        app_name: str = "Mundo Antigo",
        sound: str = "Reminder",
        insistent: bool = True,
        aumid: str | None = None,
    ) -> None:
        self.app_name = app_name
        self.sound = sound
        self.insistent = insistent
        self.aumid = aumid

    def send(self, notice: Notice) -> bool:
        try:
            from windows_toasts import (
                AudioSource,
                InteractableWindowsToaster,
                Toast,
                ToastAudio,
                ToastButton,
                ToastScenario,
            )
        except ImportError:
            log.warning("windows-toasts nao instalado: rode `uv sync --extra windows`")
            return False
        try:
            insistent = notice.insistent and self.insistent
            sound = AudioSource[self.sound] if self.sound in AudioSource.__members__ else None
            actions = [ToastButton("Abrir a página", launch=notice.url)] if notice.url else []
            toast = Toast(
                text_fields=[notice.title, notice.body],
                audio=ToastAudio(sound) if sound else ToastAudio(),
                group=(notice.video_id or "mundoantigo")[:64],
                launch_action=notice.url,
                #  Lembrete: fica na tela ate o revisor fechar. Pede um botao.
                scenario=ToastScenario.Reminder if insistent and actions else ToastScenario.Default,
                actions=actions,
            )
            InteractableWindowsToaster(self.app_name, self.aumid).show_toast(toast)
            return True
        except Exception as exc:  # um aviso nunca derruba o worker
            log.warning("nao consegui mostrar o aviso do Windows: %s", exc)
            return False
