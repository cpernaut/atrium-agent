"""Dólar MEP quotes from a public source (ArgentinaDatos).

``mep_promedio(fecha)`` returns the average between compra and venta for that
date or, if there is no quote that day (weekend, holiday, not published yet),
for the closest previous business day.

The whole series is fetched in one request and cached for an hour. The URL is
fixed in ``Settings`` (never built from user input) and the response is treated
as untrusted: size-capped, and every row is validated before use.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from atrium.config import settings

_MAX_BYTES = 5_000_000
# Sane range for ARS per USD. Rows outside it are treated as bad data (and the
# database column numeric(12,4) couldn't store them anyway).
_MIN_VALOR = Decimal("0.01")
_MAX_VALOR = Decimal("10000000")


class CotizacionError(RuntimeError):
    """The quote source could not be reached or returned unusable data."""


@dataclass(frozen=True)
class Cotizacion:
    fecha: date  # the date the quote belongs to (may be before the one asked for)
    compra: Decimal
    venta: Decimal

    @property
    def promedio(self) -> Decimal:
        return ((self.compra + self.venta) / 2).quantize(Decimal("0.0001"))


# --------------------------------------------------------------------------- #
# Fetching (the only part that touches the network; tests replace it)
# --------------------------------------------------------------------------- #
def _fetch_json() -> object:
    url = settings.cotizaciones_url
    if not url.startswith("https://"):
        raise CotizacionError("La fuente de cotizaciones tiene que ser https.")
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "atrium-agent"}
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.cotizaciones_timeout) as resp:
            body = resp.read(_MAX_BYTES + 1)
    except Exception as exc:  # noqa: BLE001 - any network failure means "no quote now"
        raise CotizacionError(f"No se pudo consultar el dólar MEP: {exc}") from exc
    if len(body) > _MAX_BYTES:
        raise CotizacionError("La respuesta de cotizaciones es demasiado grande.")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise CotizacionError("La fuente de cotizaciones devolvió datos inválidos.") from exc


def _parse(payload: object) -> dict[date, Cotizacion]:
    """Keep only well-formed rows: ISO date and positive compra/venta."""

    if not isinstance(payload, list):
        raise CotizacionError("La fuente de cotizaciones devolvió un formato inesperado.")
    serie: dict[date, Cotizacion] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            fecha = date.fromisoformat(str(row["fecha"])[:10])
            compra = Decimal(str(row["compra"]))
            venta = Decimal(str(row["venta"]))
        except (KeyError, ValueError, InvalidOperation):
            continue
        if all(v.is_finite() and _MIN_VALOR <= v <= _MAX_VALOR for v in (compra, venta)):
            serie[fecha] = Cotizacion(fecha, compra, venta)
    if not serie:
        raise CotizacionError("La fuente de cotizaciones no trajo ningún dato válido.")
    return serie


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
_cache: dict[str, object] = {"serie": None, "hasta": 0.0}


def clear_cache() -> None:
    with _lock:
        _cache.update(serie=None, hasta=0.0)


def _serie() -> dict[date, Cotizacion]:
    with _lock:
        if _cache["serie"] is not None and time.monotonic() < _cache["hasta"]:
            return _cache["serie"]  # type: ignore[return-value]
    serie = _parse(_fetch_json())
    with _lock:
        _cache.update(serie=serie, hasta=time.monotonic() + settings.cotizaciones_ttl_seconds)
    return serie


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def mep(fecha: date) -> Cotizacion | None:
    """The MEP quote for ``fecha`` or the closest previous one.

    Returns ``None`` when there is no quote within
    ``settings.cotizaciones_max_dias_atras`` days. Raises ``CotizacionError``
    when the source can't be used at all.
    """

    serie = _serie()
    for atras in range(settings.cotizaciones_max_dias_atras + 1):
        encontrada = serie.get(fecha - timedelta(days=atras))
        if encontrada:
            return encontrada
    return None


def mep_promedio(fecha: date) -> Decimal | None:
    """Average of compra and venta (ARS per USD), see ``mep``."""

    cotizacion = mep(fecha)
    return cotizacion.promedio if cotizacion else None
