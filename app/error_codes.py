"""Stable public error codes for clients that localize server messages."""


def error_code(message):
    text = (message or "").casefold()
    rules = (
        ("aucun proxy configuré", "proxy_not_configured"),
        ("proxy indisponible", "proxy_unavailable"),
        ("session expirée", "session_expired"),
        ("maximum 20 fichiers", "too_many_files"),
        ("seuls les fichiers .torrent", "invalid_file_type"),
        ("fichier trop volumineux", "file_too_large"),
        ("torrent introuvable", "torrent_not_found"),
        ("déjà présent", "duplicate_torrent"),
        ("torrent ou magnet invalide", "invalid_torrent"),
        ("magnet invalide", "invalid_torrent"),
        ("moteur", "engine_unavailable"),
        ("destination déjà occupée", "storage_collision"),
        ("espace insuffisant", "storage_full"),
        ("fichiers répartis ou ambigus", "storage_ambiguous"),
        ("pièces manquantes ou corrompues", "storage_corrupt"),
        ("déplacement en cours", "move_in_progress"),
        ("aucun déplacement à réessayer", "move_not_retryable"),
        ("déplacement échoué", "move_failed"),
        ("chemin de reprise incohérent", "storage_restore_path"),
        ("stockage", "storage_unavailable"),
        ("dossier", "storage_unavailable"),
        ("chemin", "invalid_path"),
        ("torrent", "invalid_torrent"),
    )
    return next(
        (code for fragment, code in rules if fragment in text), "operation_failed"
    )


def proxy_message_code(proxy):
    if not proxy.get("configured"):
        return "proxy_not_configured"
    if not proxy.get("checked_at"):
        return "proxy_checking"
    if not proxy.get("tcp"):
        return "proxy_unavailable"
    if proxy.get("udp"):
        if "DHT" in proxy.get("message", ""):
            return "proxy_active_udp_no_dht"
        return "proxy_active_tcp_udp"
    return "proxy_active_tcp"
