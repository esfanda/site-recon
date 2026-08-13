"""Identity & age collectors: RDAP, DNS, TLS, Wayback."""
from __future__ import annotations

import json
import ssl
from datetime import datetime, timezone
from typing import Any

import httpx

from site_recon.utils import cache_key, cache_read, cache_write, evidence_error, evidence_fact, http_get


def collect_identity(domain: str, ttl_hours: float = 168.0) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    evidence["rdap"] = _rdap(domain, ttl_hours)
    evidence["dns"] = _dns(domain, ttl_hours)
    evidence["tls"] = _tls(domain, ttl_hours)
    evidence["wayback"] = _wayback(domain, ttl_hours)
    return evidence


def _rdap(domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("rdap", domain), ttl_hours)
    if cache is not None:
        return cache

    url = f"https://rdap.org/domain/{domain}"
    try:
        resp = http_get(url, timeout=15.0)
        data = resp.json()
        result = {
            "creation_date": None,
            "last_changed": None,
            "registrar": None,
            "nameservers": [],
            "privacy": None,
        }
        for event in data.get("events", []):
            if event.get("eventAction") == "registration":
                result["creation_date"] = event.get("eventDate")
            elif event.get("eventAction") == "last changed":
                result["last_changed"] = event.get("eventDate")
        for ent in data.get("entities", []):
            vcard = ent.get("vcardArray", [])
            if isinstance(vcard, list) and len(vcard) > 1:
                for prop in vcard[1]:
                    if isinstance(prop, list) and len(prop) > 3 and prop[0] == "fn":
                        result["registrar"] = prop[3]
            roles = ent.get("roles", [])
            if "registrar" in roles and not result["registrar"]:
                result["registrar"] = ent.get("handle")
        for ns in data.get("nameservers", []):
            result["nameservers"].append(ns.get("ldhName"))
        result["privacy"] = any(
            "REDACTED" in str(v) or "PRIVACY" in str(v).upper()
            for v in [result.get("registrar"), data.get("handle")]
            if v
        )
        fact = evidence_fact(result, url, "rdap")
        cache_write(cache_key("rdap", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), url, "rdap")
        cache_write(cache_key("rdap", domain), err)
        return err


def _dns(domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("dns", domain), ttl_hours)
    if cache is not None:
        return cache

    url = "https://cloudflare-dns.com/dns-query"
    types = ["A", "MX", "NS", "TXT"]
    records: dict[str, list[str]] = {}
    try:
        for rtype in types:
            resp = http_get(
                f"{url}?name={domain}&type={rtype}",
                headers={"Accept": "application/dns-json"},
                timeout=10.0,
            )
            data = resp.json()
            answers = data.get("Answer", [])
            records[rtype] = [a.get("data", "") for a in answers]
        fact = evidence_fact(records, url, "dns_over_https")
        cache_write(cache_key("dns", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), url, "dns_over_https")
        cache_write(cache_key("dns", domain), err)
        return err


def _tls(domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("tls", domain), ttl_hours)
    if cache is not None:
        return cache

    try:
        context = ssl.create_default_context()
        with ssl.create_connection((domain, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                san_list = []
                for _, san in cert.get("subjectAltName", []):
                    san_list.append(san)
                result = {
                    "issuer": cert.get("issuer"),
                    "not_before": cert.get("notBefore"),
                    "not_after": cert.get("notAfter"),
                    "sans": san_list,
                    "cipher": cipher[0] if cipher else None,
                }
        fact = evidence_fact(result, f"https://{domain}", "ssl_socket")
        cache_write(cache_key("tls", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), f"https://{domain}", "ssl_socket")
        cache_write(cache_key("tls", domain), err)
        return err


def _wayback(domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("wayback", domain), ttl_hours)
    if cache is not None:
        return cache

    url = (
        f"http://web.archive.org/cdx/search/cdx"
        f"?url={domain}&output=json&fl=timestamp,original&collapse=timestamp:6"
    )
    try:
        resp = http_get(url, timeout=30.0)
        lines = resp.json()
        if not lines or len(lines) < 2:
            fact = evidence_fact({"first_snapshot": None, "capture_count": 0}, url, "wayback_cdx")
            cache_write(cache_key("wayback", domain), fact)
            return fact

        entries = lines[1:]  # skip header
        first_ts = entries[0][0]
        count = len(entries)
        # fetch earliest snapshot title/h1
        earliest_url = f"http://web.archive.org/web/{first_ts}/{entries[0][1]}"
        title = None
        h1 = None
        try:
            snap = http_get(earliest_url, timeout=15.0)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(snap.text, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else None
            h1_tag = soup.find("h1")
            h1 = h1_tag.get_text(strip=True) if h1_tag else None
        except Exception:
            pass

        result = {
            "first_snapshot": first_ts,
            "capture_count": count,
            "earliest_title": title,
            "earliest_h1": h1,
        }
        fact = evidence_fact(result, url, "wayback_cdx")
        cache_write(cache_key("wayback", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), url, "wayback_cdx")
        cache_write(cache_key("wayback", domain), err)
        return err
