"""Licenca de uma foto do Wikimedia Commons: aceita ou nao como base de img2img.

Regras decididas no alinhamento de 09/2026:
- aceitas: CC0, dominio publico e CC BY (com credito na descricao);
- recusadas: BY-SA (a ilustracao redesenhada pode contar como obra derivada e
  herdar a licenca), NC, ND, GFDL, arquivos nao livres e com restricoes;
- contradicao descarta: "All rights reserved" no autor junto de uma licenca
  CC, como saiu num credito do pacote antigo;
- CC0 ou dominio publico sem autor entra, creditado como "autor desconhecido";
  CC BY sem autor nao entra, porque o credito e a condicao da licenca.

Funcao pura, como `books/rights.classify`: recebe o `extmetadata` da API do
Commons e devolve um veredito com o motivo.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

_REJECT_MARKERS: tuple[tuple[str, str], ...] = (
    ("by-sa", "compartilha igual (SA)"),
    ("sharealike", "compartilha igual (SA)"),
    ("share alike", "compartilha igual (SA)"),
    ("-nc", "uso nao comercial (NC)"),
    ("noncommercial", "uso nao comercial (NC)"),
    ("non-commercial", "uso nao comercial (NC)"),
    ("-nd", "sem derivadas (ND)"),
    ("noderiv", "sem derivadas (ND)"),
    ("no deriv", "sem derivadas (ND)"),
    ("gfdl", "GFDL"),
    ("fair use", "uso justo, nao livre"),
)
_SIGNATURE = re.compile(r"\s*\((?:talk|discuss[ãa]o|contribs?)\)[^,;]*", re.IGNORECASE)
_DATETIME = re.compile(r"\s*\d{1,2}:\d{2},?\s+\d{1,2}\s+\w+\s+\d{4}\s*\(UTC\)", re.IGNORECASE)
_UNKNOWN = re.compile(r"^(unknown|desconhecido|anonymous|an[oô]nimo|n/?a)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LicenseVerdict:
    accepted: bool
    license: str  # como aparece no credito: "CC0", "Domínio público", "CC BY 2.0"
    author: str | None
    reason: str
    attribution_required: bool = False
    license_url: str | None = None


def _field(meta: dict[str, Any], key: str) -> str:
    raw = meta.get(key)
    value = raw.get("value") if isinstance(raw, dict) else raw
    return str(value or "").strip()


def _plain(text: str) -> str:
    """Tira HTML e entidades: o `Artist` do Commons costuma vir com links."""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(no_tags).split())


def clean_author(raw: str) -> str | None:
    author = _plain(raw)
    author = _DATETIME.sub("", author)
    author = _SIGNATURE.sub("", author)
    #  Prefixo de template do Commons ("Creator:Princeton Group").
    author = re.sub(r"^(?:Creator|Author|Autor):\s*", "", author, flags=re.IGNORECASE)
    author = author.strip(" ,;-—")
    if not author or _UNKNOWN.match(author):
        return None
    return author[:100]


def _truthy(value: str) -> bool:
    return value.lower() in {"true", "1", "yes", "sim"}


def classify(meta: dict[str, Any]) -> LicenseVerdict:
    short = _field(meta, "LicenseShortName")
    code = _field(meta, "License")
    terms = _field(meta, "UsageTerms")
    url = _field(meta, "LicenseUrl") or None
    author = clean_author(_field(meta, "Artist"))
    credit = _plain(_field(meta, "Credit"))
    combined = " ".join((short, code, terms)).lower()

    def reject(reason: str) -> LicenseVerdict:
        return LicenseVerdict(False, short or code or "?", author, reason, license_url=url)

    if _truthy(_field(meta, "NonFree")):
        return reject("arquivo marcado como nao livre")
    restrictions = _field(meta, "Restrictions")
    if restrictions:
        return reject(f"restricoes de uso: {restrictions}")
    for marker, label in _REJECT_MARKERS:
        if marker in combined:
            return reject(f"licenca {short or code} recusada: {label}")

    everything = f"{_plain(_field(meta, 'Artist'))} {credit}".lower()
    if "all rights reserved" in everything or "todos os direitos reservados" in everything:
        #  "All rights reserved" ao lado de uma licenca livre: um dos dois esta
        #  errado, e nao ha como saber qual.
        return reject("contradicao: o autor declara todos os direitos reservados")

    is_public_domain = (
        code.lower().startswith("pd")
        or "public domain" in combined
        or "dominio publico" in combined
    )
    is_cc0 = "cc0" in combined or "cc-zero" in combined
    if is_public_domain or is_cc0:
        #  CC0 e renuncia a direitos que existem: o Commons marca `Copyrighted`
        #  como verdadeiro, e isso nao e contradicao. So vale para dominio publico.
        if is_public_domain and not is_cc0 and _truthy(_field(meta, "Copyrighted")):
            return reject("contradicao: dominio publico marcado como protegido")
        label = "CC0" if is_cc0 else "Domínio público"
        return LicenseVerdict(True, label, author, "livre, sem exigencia de credito", False, url)

    match = re.search(r"cc[- ]by[- ](\d(?:\.\d)?)", combined)
    if match or re.search(r"\bcc[- ]by\b", combined):
        if author is None:
            return reject("CC BY sem autor: nao ha como dar o credito que a licenca exige")
        version = f" {match.group(1)}" if match else ""
        return LicenseVerdict(True, f"CC BY{version}", author, "livre com credito", True, url)

    return reject(f"licenca nao reconhecida: {short or code or 'ausente'}")
