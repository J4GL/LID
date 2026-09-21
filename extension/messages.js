// Server error codes mapped to extension messages (EXT-CLI-002).

const messages = {
  en: {
    duplicate_torrent: "This torrent is already in LID.",
    proxy_unavailable: "Proxy unavailable: proxy downloads are blocked.",
    proxy_not_configured: "No proxy configured: proxy download blocked.",
    invalid_torrent: "Invalid torrent or magnet link.",
    invalid_file_type: "Only .torrent files are accepted.",
    file_too_large: "The torrent file is too large (10 MiB maximum).",
    session_expired: "LID session expired. Please retry.",
    server_unreachable: "LID server unreachable. Check the address and network.",
    tracker_unreachable: "The .torrent file could not be fetched from this site.",
    blob_unavailable:
      "The page is gone or revoked the file before it could be read. Start the download on the page again and retry.",
    blob_no_tab: "No open tab for this site: keep the page open and retry.",
    origin_revoked:
      "Site access is off: re-enable this site in chrome://extensions, then retry.",
    unexpected_response: "Unexpected response from the LID server.",
  },
  fr: {
    duplicate_torrent: "Ce torrent est déjà présent dans LID.",
    proxy_unavailable: "Proxy indisponible : téléchargements proxy bloqués.",
    proxy_not_configured: "Aucun proxy configuré : téléchargement proxy bloqué.",
    invalid_torrent: "Torrent ou magnet invalide.",
    invalid_file_type: "Seuls les fichiers .torrent sont acceptés.",
    file_too_large: "Fichier trop volumineux (maximum 10 Mio).",
    session_expired: "Session LID expirée. Réessayez.",
    server_unreachable: "Serveur LID injoignable. Vérifiez l’adresse et le réseau.",
    tracker_unreachable: "Le fichier .torrent n’a pas pu être récupéré sur ce site.",
    blob_unavailable:
      "La page a été fermée ou a révoqué le fichier avant sa lecture. Relancez le téléchargement sur la page et réessayez.",
    blob_no_tab: "Aucun onglet ouvert pour ce site : gardez la page ouverte et réessayez.",
    origin_revoked:
      "Accès au site désactivé : réactivez ce site dans chrome://extensions, puis réessayez.",
    unexpected_response: "Réponse inattendue du serveur LID.",
  },
};

export function messageFor(code, lang = "en") {
  const table = messages[lang === "fr" ? "fr" : "en"];
  return table[code] || table.unexpected_response;
}
