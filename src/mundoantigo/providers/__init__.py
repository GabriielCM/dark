"""Adaptadores de provedores. Todo provedor externo passa por aqui."""

from .base import BaseProvider, CallContext, Provider
from .registry import ProviderRegistry, fake_registry

__all__ = ["BaseProvider", "CallContext", "Provider", "ProviderRegistry", "fake_registry"]
